"""
Circuit Breaker pattern implementation for per-credential health tracking.
"""

import time
import asyncio
import logging
from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, Optional, Callable, Awaitable

logger = logging.getLogger(__name__)


class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class CircuitBreakerConfig:
    failure_threshold: int = 5
    recovery_timeout: float = 60.0
    success_threshold: int = 2
    half_open_max_calls: int = 1


@dataclass
class CredentialCircuit:
    credential_id: str
    state: CircuitState = CircuitState.CLOSED
    failure_count: int = 0
    success_count: int = 0
    last_failure_time: float = 0.0
    last_success_time: float = 0.0
    last_state_change: float = field(default_factory=time.time)
    total_failures: int = 0
    total_successes: int = 0
    half_open_calls: int = 0

    def to_dict(self) -> dict:
        return {
            "credential_id": self.credential_id,
            "state": self.state.value,
            "failure_count": self.failure_count,
            "success_count": self.success_count,
            "last_failure_time": self.last_failure_time,
            "last_success_time": self.last_success_time,
            "last_state_change": self.last_state_change,
            "total_failures": self.total_failures,
            "total_successes": self.total_successes,
        }


class CircuitBreakerManager:
    _instance: Optional["CircuitBreakerManager"] = None

    def __init__(self, config: Optional[CircuitBreakerConfig] = None):
        self._config = config or CircuitBreakerConfig()
        self._circuits: Dict[str, CredentialCircuit] = {}
        self._lock = asyncio.Lock()
        self._on_state_change: Optional[Callable[[str, CircuitState, CircuitState], Awaitable[None]]] = None

    @classmethod
    def get_instance(cls, config: Optional[CircuitBreakerConfig] = None) -> "CircuitBreakerManager":
        if cls._instance is None:
            cls._instance = cls(config)
        return cls._instance

    @classmethod
    def reset_instance(cls):
        cls._instance = None

    def set_on_state_change(self, callback: Callable[[str, CircuitState, CircuitState], Awaitable[None]]):
        self._on_state_change = callback

    def _get_circuit(self, credential_id: str) -> CredentialCircuit:
        if credential_id not in self._circuits:
            self._circuits[credential_id] = CredentialCircuit(credential_id=credential_id)
        return self._circuits[credential_id]

    async def record_success(self, credential_id: str, latency_ms: float = 0.0):
        async with self._lock:
            circuit = self._get_circuit(credential_id)
            circuit.last_success_time = time.time()
            circuit.total_successes += 1

            if circuit.state == CircuitState.HALF_OPEN:
                circuit.success_count += 1
                if circuit.success_count >= self._config.success_threshold:
                    await self._transition(circuit, CircuitState.CLOSED)
            elif circuit.state == CircuitState.CLOSED:
                circuit.failure_count = 0

    async def record_failure(self, credential_id: str, status_code: int = 0, error: str = ""):
        async with self._lock:
            circuit = self._get_circuit(credential_id)
            circuit.last_failure_time = time.time()
            circuit.total_failures += 1
            circuit.failure_count += 1

            if circuit.state == CircuitState.HALF_OPEN:
                await self._transition(circuit, CircuitState.OPEN)
            elif circuit.state == CircuitState.CLOSED:
                if circuit.failure_count >= self._config.failure_threshold:
                    await self._transition(circuit, CircuitState.OPEN)

    def is_available(self, credential_id: str) -> bool:
        circuit = self._get_circuit(credential_id)

        if circuit.state == CircuitState.CLOSED:
            return True

        if circuit.state == CircuitState.OPEN:
            elapsed = time.time() - circuit.last_state_change
            if elapsed >= self._config.recovery_timeout:
                return True
            return False

        if circuit.state == CircuitState.HALF_OPEN:
            return circuit.half_open_calls < self._config.half_open_max_calls

        return False

    async def try_acquire(self, credential_id: str) -> bool:
        async with self._lock:
            circuit = self._get_circuit(credential_id)

            if circuit.state == CircuitState.CLOSED:
                return True

            if circuit.state == CircuitState.OPEN:
                elapsed = time.time() - circuit.last_state_change
                if elapsed >= self._config.recovery_timeout:
                    await self._transition(circuit, CircuitState.HALF_OPEN)
                    circuit.half_open_calls = 1
                    return True
                return False

            if circuit.state == CircuitState.HALF_OPEN:
                if circuit.half_open_calls < self._config.half_open_max_calls:
                    circuit.half_open_calls += 1
                    return True
                return False

            return False

    async def _transition(self, circuit: CredentialCircuit, new_state: CircuitState):
        old_state = circuit.state
        circuit.state = new_state
        circuit.last_state_change = time.time()

        if new_state == CircuitState.CLOSED:
            circuit.failure_count = 0
            circuit.success_count = 0
            circuit.half_open_calls = 0
        elif new_state == CircuitState.OPEN:
            circuit.success_count = 0
            circuit.half_open_calls = 0
        elif new_state == CircuitState.HALF_OPEN:
            circuit.success_count = 0
            circuit.half_open_calls = 0

        logger.warning(
            f"Circuit breaker [{circuit.credential_id}]: {old_state.value} -> {new_state.value}"
        )

        if self._on_state_change:
            try:
                await self._on_state_change(circuit.credential_id, old_state, new_state)
            except Exception as e:
                logger.error(f"State change callback error: {e}")

    def get_circuit_state(self, credential_id: str) -> dict:
        circuit = self._get_circuit(credential_id)
        data = circuit.to_dict()
        data["is_available"] = self.is_available(credential_id)
        if circuit.state == CircuitState.OPEN:
            elapsed = time.time() - circuit.last_state_change
            data["recovery_remaining"] = max(0, self._config.recovery_timeout - elapsed)
        return data

    def get_all_states(self) -> Dict[str, dict]:
        return {cid: self.get_circuit_state(cid) for cid in self._circuits}

    def get_summary(self) -> dict:
        states = {"closed": 0, "open": 0, "half_open": 0}
        for circuit in self._circuits.values():
            states[circuit.state.value] += 1
        return {
            "total_credentials": len(self._circuits),
            "states": states,
            "all_healthy": states["open"] == 0 and states["half_open"] == 0,
            "critical": states["open"] == len(self._circuits) and len(self._circuits) > 0,
        }

    async def force_close(self, credential_id: str):
        async with self._lock:
            circuit = self._get_circuit(credential_id)
            if circuit.state != CircuitState.CLOSED:
                await self._transition(circuit, CircuitState.CLOSED)

    async def force_open(self, credential_id: str):
        async with self._lock:
            circuit = self._get_circuit(credential_id)
            if circuit.state != CircuitState.OPEN:
                await self._transition(circuit, CircuitState.OPEN)

    def remove_credential(self, credential_id: str):
        self._circuits.pop(credential_id, None)

    @property
    def config(self) -> CircuitBreakerConfig:
        return self._config
