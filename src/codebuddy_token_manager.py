"""
CodeBuddy Token Manager - Manages CodeBuddy authentication tokens with
rotation, expiry checking, exhaustion tracking, and auto-refresh.
"""
import os
import glob
import json
import time
import base64
import asyncio
import logging
from typing import Dict, Optional, List, Any, Set
from .usage_stats_manager import usage_stats_manager
from .circuit_breaker import CircuitBreakerManager

logger = logging.getLogger(__name__)

EXHAUSTION_COOLDOWN_SECONDS = 12 * 3600  # 12 hours
TOKEN_REFRESH_BUFFER_SECONDS = 3600  # Refresh 1 hour before expiry
KEYCLOAK_TOKEN_URL = "https://www.codebuddy.ai/auth/realms/copilot/protocol/openid-connect/token"
KEYCLOAK_CLIENT_ID = "console"


class CodeBuddyTokenManager:

    def __init__(self, creds_dir=None):
        if creds_dir is None:
            from config import get_codebuddy_creds_dir, get_rotation_count
            creds_dir = get_codebuddy_creds_dir()

        self.creds_dir = os.path.join(os.path.dirname(__file__), '..', creds_dir)
        self.state_file = os.path.join(self.creds_dir, 'manager_state.json')
        self.credentials = []
        self.current_index = 0
        self.usage_count = 0
        self.manual_selected: Optional[str] = None  # credential_id (filename)
        self._lock = asyncio.Lock()
        self.auto_rotation_enabled = True
        # Exhausted keys: credential_id (filename) -> timestamp when marked exhausted
        self.exhausted_keys: Dict[str, float] = {}
        # Disabled keys: credential_id (filename) set
        self.disabled_keys: Set[str] = set()
        # Track ongoing refresh attempts to prevent duplicate refreshes
        self._refresh_in_progress: Set[str] = set()
        self.load_all_tokens()
        self.load_state()

    def _credential_id(self, index: int) -> Optional[str]:
        """Get credential_id (filename) for a given index."""
        if 0 <= index < len(self.credentials):
            return os.path.basename(self.credentials[index]['file_path'])
        return None

    def _index_for_credential_id(self, credential_id: str) -> Optional[int]:
        """Find index for a given credential_id (filename)."""
        for i, cred in enumerate(self.credentials):
            if os.path.basename(cred['file_path']) == credential_id:
                return i
        return None

    def load_all_tokens(self):
        self.credentials = []
        self.current_index = -1

        logger.info(f"Loading CodeBuddy credentials from: {self.creds_dir}")

        if not os.path.exists(self.creds_dir):
            os.makedirs(self.creds_dir)
            logger.warning(f"Credentials directory created at {self.creds_dir}. No credentials found.")
            return

        token_files = sorted(glob.glob(os.path.join(self.creds_dir, '*.json')))
        for file_path in token_files:
            if os.path.basename(file_path) == 'manager_state.json':
                continue
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if 'bearer_token' in data:
                        self.credentials.append({
                            'file_path': file_path,
                            'data': data
                        })
                        logger.info(f"Loaded credential: {os.path.basename(file_path)}")
                    else:
                        logger.warning(f"Skipping invalid credential (missing bearer_token): {os.path.basename(file_path)}")
            except Exception as e:
                logger.error(f"Failed to load credential {os.path.basename(file_path)}: {e}")

        logger.info(f"Loaded {len(self.credentials)} CodeBuddy credentials total.")

    def load_state(self):
        try:
            if os.path.exists(self.state_file):
                with open(self.state_file, 'r', encoding='utf-8') as f:
                    state = json.load(f)

                # --- Migration: support old integer-keyed state ---
                # New format: manual_selected is a credential_id string
                saved_manual = state.get('manual_selected')
                if saved_manual is not None and isinstance(saved_manual, str):
                    resolved_idx = self._index_for_credential_id(saved_manual)
                    if resolved_idx is not None:
                        self.manual_selected = saved_manual
                        self.current_index = resolved_idx
                        logger.info(f"Restored manual selection: {saved_manual}")
                elif state.get('manual_selected_index') is not None:
                    old_idx = state.get('manual_selected_index')
                    old_filename = state.get('manual_selected_filename')
                    if old_filename:
                        resolved_idx = self._index_for_credential_id(old_filename)
                        if resolved_idx is not None:
                            self.manual_selected = old_filename
                            self.current_index = resolved_idx
                            logger.info(f"Migrated manual selection from index {old_idx} to credential_id: {old_filename}")
                    elif isinstance(old_idx, int) and 0 <= old_idx < len(self.credentials):
                        cid = self._credential_id(old_idx)
                        if cid:
                            self.manual_selected = cid
                            self.current_index = old_idx
                            logger.info(f"Migrated manual selection from index {old_idx} to credential_id: {cid}")

                self.auto_rotation_enabled = state.get('auto_rotation_enabled', True)

                if self.manual_selected is None:
                    saved_current_index = state.get('current_index', 0)
                    if 0 <= saved_current_index < len(self.credentials):
                        self.current_index = saved_current_index

                # Restore exhausted keys (prune expired ones, migrate old int keys)
                saved_exhausted = state.get('exhausted_keys', {})
                now = time.time()
                for key_str, ts in saved_exhausted.items():
                    if now - ts >= EXHAUSTION_COOLDOWN_SECONDS:
                        continue  # expired cooldown, skip
                    # Check if key_str is an old integer index
                    try:
                        old_idx = int(key_str)
                        # It's an old integer key — migrate to credential_id
                        cid = self._credential_id(old_idx)
                        if cid:
                            self.exhausted_keys[cid] = ts
                            logger.info(f"Migrated exhausted key from index {old_idx} to credential_id: {cid}")
                    except ValueError:
                        # Already a credential_id string
                        if self._index_for_credential_id(key_str) is not None:
                            self.exhausted_keys[key_str] = ts

                # Restore disabled keys
                saved_disabled = state.get('disabled_keys', [])
                for cid in saved_disabled:
                    if self._index_for_credential_id(cid) is not None:
                        self.disabled_keys.add(cid)

                logger.info(f"State loaded: auto_rotation={self.auto_rotation_enabled}, "
                            f"current_index={self.current_index}, "
                            f"exhausted_keys={len(self.exhausted_keys)}, "
                            f"disabled_keys={len(self.disabled_keys)}")
        except Exception as e:
            logger.warning(f"Failed to load manager state: {e}")

    def save_state(self):
        try:
            if not os.path.exists(self.creds_dir):
                os.makedirs(self.creds_dir)

            state = {
                'auto_rotation_enabled': self.auto_rotation_enabled,
                'current_index': self.current_index,
                'manual_selected': self.manual_selected,
                'exhausted_keys': dict(self.exhausted_keys),
                'disabled_keys': list(self.disabled_keys),
                'saved_at': int(time.time())
            }

            from .usage_stats_manager import atomic_write_json
            atomic_write_json(self.state_file, state)

            logger.debug(f"Manager state saved to {self.state_file}")
        except Exception as e:
            logger.error(f"Failed to save manager state: {e}")

    def is_token_expired(self, credential_data: Dict) -> bool:
        try:
            created_at = credential_data.get('created_at')
            expires_in = credential_data.get('expires_in')

            if not created_at or not expires_in:
                return False

            current_time = int(time.time())
            expiry_time = created_at + expires_in
            buffer_time = 300  # 5 min early expiry buffer
            is_expired = current_time >= (expiry_time - buffer_time)

            if is_expired:
                user_id = credential_data.get('user_id', 'unknown')
                logger.warning(f"Token for user {user_id} is expired or expiring soon")

            # Schedule background refresh if nearing expiry and has refresh_token
            if self._needs_refresh(credential_data) and credential_data.get('refresh_token'):
                self._schedule_refresh(credential_data)

            return is_expired
        except Exception as e:
            logger.error(f"Error checking token expiry: {e}")
            return False

    def _needs_refresh(self, credential_data: Dict) -> bool:
        """Check if token is within the refresh buffer window (1 hour before expiry)."""
        created_at = credential_data.get('created_at')
        expires_in = credential_data.get('expires_in')
        if not created_at or not expires_in:
            return False
        # API keys don't need refresh
        if credential_data.get('token_type') == 'ApiKey':
            return False
        current_time = int(time.time())
        expiry_time = created_at + expires_in
        return current_time >= (expiry_time - TOKEN_REFRESH_BUFFER_SECONDS)

    def _schedule_refresh(self, credential_data: Dict):
        """Fire-and-forget background refresh for a credential."""
        user_id = credential_data.get('user_id', 'unknown')
        if user_id in self._refresh_in_progress:
            return  # Already refreshing
        self._refresh_in_progress.add(user_id)
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(self._refresh_token_async(credential_data))
            else:
                logger.debug(f"Event loop not running, skipping refresh for {user_id}")
                self._refresh_in_progress.discard(user_id)
        except RuntimeError:
            self._refresh_in_progress.discard(user_id)

    async def _refresh_token_async(self, credential_data: Dict):
        """Refresh an OAuth token using the refresh_token via Keycloak."""
        user_id = credential_data.get('user_id', 'unknown')
        refresh_token = credential_data.get('refresh_token')

        if not refresh_token:
            self._refresh_in_progress.discard(user_id)
            return

        logger.info(f"Auto-refreshing token for user: {user_id}")

        try:
            import httpx
            async with httpx.AsyncClient(verify=False, timeout=30.0) as client:
                response = await client.post(
                    KEYCLOAK_TOKEN_URL,
                    data={
                        "grant_type": "refresh_token",
                        "refresh_token": refresh_token,
                        "client_id": KEYCLOAK_CLIENT_ID,
                    },
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )

            if response.status_code != 200:
                logger.error(f"Token refresh failed for {user_id}: HTTP {response.status_code} - {response.text[:200]}")
                self._refresh_in_progress.discard(user_id)
                return

            token_data = response.json()
            new_access_token = token_data.get("access_token")
            new_refresh_token = token_data.get("refresh_token", refresh_token)
            new_expires_in = token_data.get("expires_in")

            if not new_access_token:
                logger.error(f"Token refresh returned no access_token for {user_id}")
                self._refresh_in_progress.discard(user_id)
                return

            # Generate new API key (bearer_token) from the access token
            # or use the new access_token directly if bearer was JWT-based
            old_bearer = credential_data.get('bearer_token', '')
            if old_bearer.startswith('ck_'):
                # API key type — shouldn't get here, but keep original
                new_bearer = old_bearer
            else:
                new_bearer = new_access_token

            # Find and update the credential file
            async with self._lock:
                cred_id = self.get_credential_id_for_data(credential_data)
                if not cred_id:
                    logger.error(f"Could not find credential file for {user_id}")
                    self._refresh_in_progress.discard(user_id)
                    return

                idx = self._index_for_credential_id(cred_id)
                if idx is None:
                    self._refresh_in_progress.discard(user_id)
                    return

                # Update in-memory
                cred = self.credentials[idx]['data']
                cred['bearer_token'] = new_bearer
                cred['access_token'] = new_access_token
                cred['refresh_token'] = new_refresh_token
                cred['created_at'] = int(time.time())
                if new_expires_in:
                    cred['expires_in'] = new_expires_in

                # Persist to file
                file_path = self.credentials[idx]['file_path']
                try:
                    from .usage_stats_manager import atomic_write_json
                    atomic_write_json(file_path, cred)
                    logger.info(f"✅ Token refreshed successfully for {user_id} (file: {cred_id})")
                except Exception as e:
                    logger.error(f"Failed to save refreshed token for {user_id}: {e}")

        except Exception as e:
            logger.error(f"Token refresh error for {user_id}: {e}")
        finally:
            self._refresh_in_progress.discard(user_id)

    def _is_key_exhausted(self, credential_id: str) -> bool:
        if credential_id not in self.exhausted_keys:
            return False
        ts = self.exhausted_keys[credential_id]
        if time.time() - ts >= EXHAUSTION_COOLDOWN_SECONDS:
            del self.exhausted_keys[credential_id]
            logger.info(f"Key {credential_id} exhaustion cooldown expired, re-enabled")
            return False
        return True

    def _is_key_disabled(self, credential_id: str) -> bool:
        return credential_id in self.disabled_keys

    async def mark_key_exhausted(self, credential_id: str):
        async with self._lock:
            self.exhausted_keys[credential_id] = time.time()
            logger.warning(f"Key marked exhausted: {credential_id}, "
                           f"will re-enable after {EXHAUSTION_COOLDOWN_SECONDS // 3600}h")
            self.save_state()

    def mark_key_exhausted_sync(self, credential_id: str):
        """Synchronous version for use in non-async contexts."""
        self.exhausted_keys[credential_id] = time.time()
        logger.warning(f"Key marked exhausted: {credential_id}, "
                       f"will re-enable after {EXHAUSTION_COOLDOWN_SECONDS // 3600}h")
        self.save_state()

    def get_healthy_keys_count(self) -> int:
        count = 0
        for i, cred in enumerate(self.credentials):
            cid = os.path.basename(cred['file_path'])
            if (not self.is_token_expired(cred['data'])
                    and not self._is_key_exhausted(cid)
                    and not self._is_key_disabled(cid)):
                count += 1
        return count

    def get_credential_index(self, credential_data: Dict) -> Optional[int]:
        """Find the index of a credential by its bearer_token."""
        token = credential_data.get('bearer_token')
        if not token:
            return None
        for i, cred in enumerate(self.credentials):
            if cred['data'].get('bearer_token') == token:
                return i
        return None

    def get_credential_id_for_data(self, credential_data: Dict) -> Optional[str]:
        """Find the credential_id (filename) for a credential by its bearer_token."""
        idx = self.get_credential_index(credential_data)
        if idx is not None:
            return self._credential_id(idx)
        return None

    async def get_next_credential_async(self) -> Optional[Dict]:
        async with self._lock:
            return self._get_next_credential_unlocked()

    def get_next_credential(self) -> Optional[Dict]:
        return self._get_next_credential_unlocked()

    def _get_next_credential_unlocked(self) -> Optional[Dict]:
        from config import get_rotation_count

        if not self.credentials:
            return None

        cb = CircuitBreakerManager.get_instance()
        valid_credentials = []
        for i, cred in enumerate(self.credentials):
            cid = os.path.basename(cred['file_path'])
            if self.is_token_expired(cred['data']):
                continue
            if self._is_key_exhausted(cid):
                continue
            if self._is_key_disabled(cid):
                continue
            if not cb.is_available(cid):
                continue
            valid_credentials.append((i, cred))

        if not valid_credentials:
            logger.error("No valid (non-expired, non-exhausted, non-disabled) credentials available")
            return None

        current_valid_indices = [i for i, _ in valid_credentials]
        if self.current_index not in current_valid_indices:
            self.current_index = current_valid_indices[0]
            self.usage_count = 0
            logger.info(f"Reset to first valid credential index: {self.current_index}")

        rotation_count = get_rotation_count()

        # Manual selection takes priority (if not expired/exhausted/disabled)
        if self.manual_selected is not None:
            manual_idx = self._index_for_credential_id(self.manual_selected)
            if manual_idx is not None:
                manual_cred = self.credentials[manual_idx]
                cid = self.manual_selected
                if (not self.is_token_expired(manual_cred['data'])
                        and not self._is_key_exhausted(cid)
                        and not self._is_key_disabled(cid)):
                    usage_stats_manager.record_credential_usage(cid)
                    logger.info(f"Using manually selected credential: {cid}")
                    return manual_cred['data']
                else:
                    logger.warning("Manually selected credential is expired/exhausted/disabled, falling back to auto rotation")
                    self.manual_selected = None
            else:
                logger.warning(f"Manually selected credential {self.manual_selected} no longer exists, clearing")
                self.manual_selected = None

        try:
            current_valid_position = current_valid_indices.index(self.current_index)
        except ValueError:
            current_valid_position = 0
            self.current_index = current_valid_indices[0]
            self.usage_count = 0

        should_rotate = self.auto_rotation_enabled and rotation_count > 0

        if not should_rotate:
            credential = self.credentials[self.current_index]
            credential_filename = os.path.basename(credential['file_path'])
            usage_stats_manager.record_credential_usage(credential_filename)
            logger.info(f"Using fixed credential: {credential_filename}")
            return credential['data']

        if self.usage_count >= rotation_count:
            best_index = self._pick_healthiest_key(valid_credentials)
            self.current_index = best_index
            self.usage_count = 0

        credential = self.credentials[self.current_index]
        self.usage_count += 1

        credential_filename = os.path.basename(credential['file_path'])
        usage_stats_manager.record_credential_usage(credential_filename)

        return credential['data']

    def _pick_healthiest_key(self, valid_credentials: List) -> int:
        cb = CircuitBreakerManager.get_instance()
        best_index = valid_credentials[0][0]
        best_score = -1

        for idx, cred in valid_credentials:
            filename = os.path.basename(cred['file_path'])
            stats = usage_stats_manager.get_key_stats(filename)
            total = stats.get('total_requests', 0)
            failed = stats.get('failed_requests', 0)
            last_used = stats.get('last_used_at', 0)

            staleness = time.time() - last_used if last_used > 0 else 999999
            failure_rate = failed / max(total, 1)
            score = staleness * (1.0 - failure_rate) / max(total, 1)

            circuit_state = cb.get_circuit_state(filename)
            if circuit_state["state"] == "closed":
                score *= 1.5
            elif circuit_state["state"] == "half_open":
                score *= 0.5

            if score > best_score:
                best_score = score
                best_index = idx

        return best_index

    def get_all_credentials(self) -> List[Dict]:
        return [cred['data'] for cred in self.credentials]

    def get_credentials_info(self) -> List[Dict]:
        credentials_info = []
        for i, cred in enumerate(self.credentials):
            data = cred['data']
            filename = os.path.basename(cred['file_path'])

            is_expired = self.is_token_expired(data)
            is_exhausted = self._is_key_exhausted(filename)
            is_disabled = self._is_key_disabled(filename)
            expires_at = None
            time_remaining = None

            if data.get('created_at') and data.get('expires_in'):
                expires_at = data['created_at'] + data['expires_in']
                time_remaining = expires_at - int(time.time())

            user_info = data.get('user_info', {})

            info = {
                'index': i,
                'credential_id': filename,
                'filename': filename,
                'user_id': data.get('user_id', 'unknown'),
                'email': user_info.get('email') or data.get('user_id'),
                'name': user_info.get('name'),
                'created_at': data.get('created_at'),
                'expires_in': data.get('expires_in'),
                'expires_at': expires_at,
                'time_remaining': time_remaining,
                'is_expired': is_expired,
                'is_exhausted': is_exhausted,
                'is_disabled': is_disabled,
                'exhausted_at': self.exhausted_keys.get(filename),
                'token_type': data.get('token_type', 'Bearer'),
                'scope': data.get('scope'),
                'domain': data.get('domain'),
                'has_refresh_token': bool(data.get('refresh_token')),
                'session_state': data.get('session_state'),
                'file_path': cred['file_path']
            }

            credentials_info.append(info)

        return credentials_info

    def add_credential(self, bearer_token: str, user_id: Optional[str] = None, filename: Optional[str] = None) -> bool:
        if not filename:
            filename = f"codebuddy_token_{len(self.credentials) + 1}.json"

        if not filename.endswith('.json'):
            filename += '.json'

        credential_data = {
            "bearer_token": bearer_token,
            "user_id": user_id,
            "created_at": int(time.time())
        }

        return self.add_credential_with_data(credential_data, filename)

    async def add_credential_with_data_async(self, credential_data: Dict[str, Any], filename: Optional[str] = None) -> bool:
        async with self._lock:
            return self._add_credential_with_data_unlocked(credential_data, filename)

    def add_credential_with_data(self, credential_data: Dict[str, Any], filename: Optional[str] = None) -> bool:
        return self._add_credential_with_data_unlocked(credential_data, filename)

    def _add_credential_with_data_unlocked(self, credential_data: Dict[str, Any], filename: Optional[str] = None) -> bool:
        if not filename:
            user_id = credential_data.get('user_id', 'unknown')
            timestamp = credential_data.get('created_at', int(time.time()))
            safe_user_id = "".join(c for c in str(user_id) if c.isalnum() or c in "._-")[:20]
            filename = f"codebuddy_{safe_user_id}_{timestamp}.json"

        if not filename.endswith('.json'):
            filename += '.json'

        file_path = os.path.join(self.creds_dir, filename)

        if 'created_at' not in credential_data:
            credential_data['created_at'] = int(time.time())

        try:
            if not os.path.exists(self.creds_dir):
                os.makedirs(self.creds_dir)

            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(credential_data, f, indent=4, ensure_ascii=False)

            logger.info(f"Added new credential: {filename}")
            self.load_all_tokens()
            return True
        except Exception as e:
            logger.error(f"Failed to save credential: {e}")
            return False

    async def delete_credential(self, credential_id: str) -> bool:
        """Delete a credential by credential_id (filename). Thread-safe."""
        async with self._lock:
            return self._delete_credential_unlocked(credential_id)

    def delete_credential_by_index(self, index: int) -> bool:
        """Delete a credential by index. Kept for backward compat."""
        cid = self._credential_id(index)
        if cid is None:
            logger.error(f"Invalid credential index for deletion: {index}")
            return False
        return self._delete_credential_unlocked(cid)

    def _delete_credential_unlocked(self, credential_id: str) -> bool:
        try:
            idx = self._index_for_credential_id(credential_id)
            if idx is None:
                logger.error(f"Credential not found for deletion: {credential_id}")
                return False

            file_path = self.credentials[idx]['file_path']

            # 1. Delete file
            if os.path.exists(file_path):
                os.remove(file_path)
                logger.info(f"Deleted credential file: {credential_id}")
            else:
                logger.warning(f"Credential file already missing: {credential_id}")

            # 2. Reload list (indices shift after this)
            self.load_all_tokens()

            # 3. Remove credential_id from exhausted_keys
            self.exhausted_keys.pop(credential_id, None)

            # 4. Remove from disabled_keys
            self.disabled_keys.discard(credential_id)

            # 5. Clear manual selection if deleted credential was selected
            if self.manual_selected == credential_id:
                self.manual_selected = None
                logger.info("Cleared manual selection because deleted credential was selected")

            # 6. Adjust current_index if out of bounds
            if self.credentials:
                if self.current_index >= len(self.credentials):
                    self.current_index = 0
            else:
                self.current_index = -1

            # 7. Save state
            self.save_state()
            return True
        except Exception as e:
            logger.error(f"Failed to delete credential {credential_id}: {e}")
            return False

    async def set_manual_credential(self, credential_id: str) -> bool:
        """Set manual credential by credential_id. Thread-safe."""
        async with self._lock:
            return self._set_manual_credential_unlocked(credential_id)

    def set_manual_credential_by_index(self, index: int) -> bool:
        """Set manual credential by index. Kept for backward compat."""
        cid = self._credential_id(index)
        if cid is None:
            logger.error(f"Invalid credential index: {index}")
            return False
        return self._set_manual_credential_unlocked(cid)

    def _set_manual_credential_unlocked(self, credential_id: str) -> bool:
        idx = self._index_for_credential_id(credential_id)
        if idx is None:
            logger.error(f"Credential not found: {credential_id}")
            return False
        self.manual_selected = credential_id
        self.current_index = idx
        logger.info(f"Manually selected credential: {credential_id}")
        self.save_state()
        return True

    def clear_manual_selection(self):
        self.manual_selected = None
        logger.info("Cleared manual credential selection, resumed automatic rotation")
        self.save_state()

    def enable_auto_rotation(self):
        self.auto_rotation_enabled = True
        logger.info("Auto rotation enabled")

    def disable_auto_rotation(self):
        self.auto_rotation_enabled = False
        logger.info("Auto rotation disabled")

    async def toggle_auto_rotation(self) -> bool:
        async with self._lock:
            self.auto_rotation_enabled = not self.auto_rotation_enabled
            status = "enabled" if self.auto_rotation_enabled else "disabled"
            logger.info(f"Auto rotation toggled: {status}")
            self.save_state()
            return self.auto_rotation_enabled

    def toggle_auto_rotation_sync(self) -> bool:
        """Synchronous version for backward compat."""
        self.auto_rotation_enabled = not self.auto_rotation_enabled
        status = "enabled" if self.auto_rotation_enabled else "disabled"
        logger.info(f"Auto rotation toggled: {status}")
        self.save_state()
        return self.auto_rotation_enabled

    async def resume_auto_rotation(self):
        async with self._lock:
            self.manual_selected = None
            logger.info("Cleared manual credential selection, resumed automatic rotation")
            self.save_state()

    async def disable_key(self, credential_id: str) -> bool:
        """Disable a key (skip in rotation). Thread-safe."""
        async with self._lock:
            if self._index_for_credential_id(credential_id) is None:
                return False
            self.disabled_keys.add(credential_id)
            logger.info(f"Key disabled: {credential_id}")
            self.save_state()
            return True

    async def enable_key(self, credential_id: str) -> bool:
        """Re-enable a disabled key. Thread-safe."""
        async with self._lock:
            if credential_id not in self.disabled_keys:
                return False
            self.disabled_keys.discard(credential_id)
            logger.info(f"Key re-enabled: {credential_id}")
            self.save_state()
            return True

    def get_current_credential_info(self) -> Dict:
        from config import get_rotation_count

        if not self.credentials:
            return {"status": "no_credentials"}

        rotation_count = get_rotation_count()

        if self.manual_selected is not None:
            manual_idx = self._index_for_credential_id(self.manual_selected)
            if manual_idx is not None:
                credential = self.credentials[manual_idx]
                return {
                    "status": "manual_selected",
                    "index": manual_idx,
                    "credential_id": self.manual_selected,
                    "filename": self.manual_selected,
                    "user_id": credential['data'].get('user_id', 'unknown'),
                    "healthy_keys": self.get_healthy_keys_count(),
                    "exhausted_keys": len(self.exhausted_keys),
                }

        if not self.auto_rotation_enabled:
            if not (0 <= self.current_index < len(self.credentials)):
                self.current_index = 0
            credential = self.credentials[self.current_index]
            cid = os.path.basename(credential['file_path'])
            return {
                "status": "auto_rotation_disabled",
                "index": self.current_index,
                "credential_id": cid,
                "filename": cid,
                "user_id": credential['data'].get('user_id', 'unknown'),
                "rotation_count": rotation_count,
                "auto_rotation_enabled": False,
                "healthy_keys": self.get_healthy_keys_count(),
                "exhausted_keys": len(self.exhausted_keys),
            }
        elif rotation_count == 0:
            if not (0 <= self.current_index < len(self.credentials)):
                self.current_index = 0
            credential = self.credentials[self.current_index]
            cid = os.path.basename(credential['file_path'])
            return {
                "status": "rotation_count_zero",
                "index": self.current_index,
                "credential_id": cid,
                "filename": cid,
                "user_id": credential['data'].get('user_id', 'unknown'),
                "rotation_count": rotation_count,
                "auto_rotation_enabled": True,
                "healthy_keys": self.get_healthy_keys_count(),
                "exhausted_keys": len(self.exhausted_keys),
            }
        else:
            if not (0 <= self.current_index < len(self.credentials)):
                self.current_index = 0
            credential = self.credentials[self.current_index]
            cid = os.path.basename(credential['file_path'])
            return {
                "status": "auto_rotation",
                "index": self.current_index,
                "credential_id": cid,
                "filename": cid,
                "user_id": credential['data'].get('user_id', 'unknown'),
                "usage_count": self.usage_count,
                "rotation_count": rotation_count,
                "auto_rotation_enabled": True,
                "healthy_keys": self.get_healthy_keys_count(),
                "exhausted_keys": len(self.exhausted_keys),
            }


codebuddy_token_manager = CodeBuddyTokenManager()
