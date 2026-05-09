# Skill: Game Development
# Loaded on-demand when task involves ECS architecture, game loops, physics, rendering, or multiplayer networking

## Auto-Detect

Trigger this skill when:
- Task mentions: game, ECS, entity component system, game loop, physics, rendering, multiplayer
- Files: `*.gdscript`, `*.unity`, `*.tres`, `*.tscn`, game engine configs
- Patterns: sprite, collision, input handling, state machine, networking
- `package.json` contains: `phaser`, `pixi.js`, `three`, `cannon-es`, `rapier`

---

## Decision Tree: Game Architecture

```
What type of game?
+-- 2D browser game?
|   +-- Simple (puzzle, platformer)? -> Phaser 3 or vanilla Canvas
|   +-- Complex (many entities)? -> Phaser + ECS (bitECS)
|   +-- Pixel art? -> Phaser or Pixi.js
+-- 3D browser game?
|   +-- Simple scene? -> Three.js
|   +-- Complex with physics? -> Three.js + Rapier (WASM physics)
|   +-- Full engine features? -> Babylon.js or PlayCanvas
+-- Native game?
|   +-- 2D indie? -> Godot (GDScript) or Unity (C#)
|   +-- 3D AAA? -> Unreal (C++) or Unity (C#)
|   +-- Rust ecosystem? -> Bevy (ECS-native)
+-- Multiplayer?
|   +-- Turn-based? -> Simple WebSocket + state sync
|   +-- Real-time (< 16 players)? -> Client-server with prediction
|   +-- MMO (100+ players)? -> Dedicated server + spatial partitioning
```

---

## ECS Architecture (Entity Component System)

```typescript
// ECS with bitECS (high-performance, TypeScript)
import { createWorld, defineComponent, defineQuery, addEntity, addComponent, Types } from 'bitecs';

// Components are pure data (no behavior)
const Position = defineComponent({
  x: Types.f32,
  y: Types.f32,
});

const Velocity = defineComponent({
  x: Types.f32,
  y: Types.f32,
});

const Health = defineComponent({
  current: Types.ui16,
  max: Types.ui16,
});

const Sprite = defineComponent({
  textureId: Types.ui8,
  width: Types.ui16,
  height: Types.ui16,
  frame: Types.ui8,
});

const Enemy = defineComponent(); // Tag component (no data)
const Player = defineComponent();

// Queries select entities by component composition
const movementQuery = defineQuery([Position, Velocity]);
const enemyQuery = defineQuery([Position, Health, Enemy]);
const renderQuery = defineQuery([Position, Sprite]);

// Systems are functions that operate on queried entities
function movementSystem(world: World, dt: number): void {
  const entities = movementQuery(world);
  for (let i = 0; i < entities.length; i++) {
    const eid = entities[i];
    Position.x[eid] += Velocity.x[eid] * dt;
    Position.y[eid] += Velocity.y[eid] * dt;
  }
}

function collisionSystem(world: World): void {
  const enemies = enemyQuery(world);
  const players = defineQuery([Position, Player])(world);

  for (const enemy of enemies) {
    for (const player of players) {
      const dx = Position.x[enemy] - Position.x[player];
      const dy = Position.y[enemy] - Position.y[player];
      const dist = Math.sqrt(dx * dx + dy * dy);

      if (dist < 32) { // Collision radius
        Health.current[player] -= 10;
        // Remove enemy or apply knockback
      }
    }
  }
}

// World setup
const world = createWorld();

// Spawn entities
function spawnEnemy(x: number, y: number): number {
  const eid = addEntity(world);
  addComponent(world, Position, eid);
  addComponent(world, Velocity, eid);
  addComponent(world, Health, eid);
  addComponent(world, Sprite, eid);
  addComponent(world, Enemy, eid);

  Position.x[eid] = x;
  Position.y[eid] = y;
  Health.current[eid] = 100;
  Health.max[eid] = 100;

  return eid;
}
```

---

## Game Loop

```typescript
// Fixed timestep game loop (deterministic physics)
class GameLoop {
  private accumulator = 0;
  private readonly FIXED_DT = 1 / 60; // 60 Hz physics
  private lastTime = 0;
  private running = false;

  constructor(
    private readonly update: (dt: number) => void,  // Fixed timestep (physics, logic)
    private readonly render: (alpha: number) => void // Variable timestep (rendering)
  ) {}

  start(): void {
    this.running = true;
    this.lastTime = performance.now();
    requestAnimationFrame(this.loop.bind(this));
  }

  stop(): void {
    this.running = false;
  }

  private loop(currentTime: number): void {
    if (!this.running) return;

    const frameTime = Math.min((currentTime - this.lastTime) / 1000, 0.25); // Cap at 250ms
    this.lastTime = currentTime;
    this.accumulator += frameTime;

    // Fixed update (may run multiple times per frame)
    while (this.accumulator >= this.FIXED_DT) {
      this.update(this.FIXED_DT);
      this.accumulator -= this.FIXED_DT;
    }

    // Render with interpolation alpha
    const alpha = this.accumulator / this.FIXED_DT;
    this.render(alpha);

    requestAnimationFrame(this.loop.bind(this));
  }
}

// Usage
const loop = new GameLoop(
  (dt) => {
    inputSystem(world);
    movementSystem(world, dt);
    collisionSystem(world);
    aiSystem(world, dt);
  },
  (alpha) => {
    // Interpolate positions for smooth rendering
    renderSystem(world, alpha);
    uiSystem(world);
  }
);
```

---

## State Machine (for game entities)

```typescript
// Hierarchical state machine for character behavior
interface State {
  name: string;
  enter?(entity: Entity): void;
  exit?(entity: Entity): void;
  update(entity: Entity, dt: number): void;
  transitions: Transition[];
}

interface Transition {
  to: string;
  condition: (entity: Entity) => boolean;
  priority?: number;
}

class StateMachine {
  private states = new Map<string, State>();
  private currentState: State | null = null;

  addState(state: State): void {
    this.states.set(state.name, state);
  }

  setState(name: string, entity: Entity): void {
    if (this.currentState?.name === name) return;

    this.currentState?.exit?.(entity);
    this.currentState = this.states.get(name) ?? null;
    this.currentState?.enter?.(entity);
  }

  update(entity: Entity, dt: number): void {
    if (!this.currentState) return;

    // Check transitions (sorted by priority)
    const sorted = [...this.currentState.transitions].sort(
      (a, b) => (b.priority ?? 0) - (a.priority ?? 0)
    );

    for (const transition of sorted) {
      if (transition.condition(entity)) {
        this.setState(transition.to, entity);
        return;
      }
    }

    this.currentState.update(entity, dt);
  }
}

// Example: Enemy AI states
const enemyFSM = new StateMachine();

enemyFSM.addState({
  name: 'idle',
  update(entity, dt) { /* Play idle animation */ },
  transitions: [
    { to: 'chase', condition: (e) => distToPlayer(e) < 200 },
    { to: 'patrol', condition: (e) => e.patrolTimer <= 0 },
  ],
});

enemyFSM.addState({
  name: 'chase',
  enter(entity) { entity.speed = 150; },
  update(entity, dt) { moveTowardPlayer(entity, dt); },
  transitions: [
    { to: 'attack', condition: (e) => distToPlayer(e) < 32, priority: 2 },
    { to: 'idle', condition: (e) => distToPlayer(e) > 400, priority: 1 },
  ],
});

enemyFSM.addState({
  name: 'attack',
  enter(entity) { entity.attackCooldown = 0.5; },
  update(entity, dt) {
    entity.attackCooldown -= dt;
    if (entity.attackCooldown <= 0) dealDamage(entity);
  },
  transitions: [
    { to: 'chase', condition: (e) => distToPlayer(e) > 48 },
  ],
});
```

---

## Multiplayer Networking

```typescript
// Client-side prediction + server reconciliation
class NetworkedPlayer {
  private inputSequence = 0;
  private pendingInputs: InputFrame[] = [];
  private serverState: PlayerState | null = null;

  // Client: Process input locally and send to server
  processInput(input: InputData): void {
    const frame: InputFrame = {
      sequence: this.inputSequence++,
      input,
      timestamp: Date.now(),
    };

    // Apply locally (prediction)
    this.applyInput(frame);
    this.pendingInputs.push(frame);

    // Send to server
    this.socket.send({ type: 'input', frame });
  }

  // Client: Receive authoritative state from server
  onServerUpdate(state: PlayerState, lastProcessedInput: number): void {
    this.serverState = state;

    // Remove acknowledged inputs
    this.pendingInputs = this.pendingInputs.filter(
      (input) => input.sequence > lastProcessedInput
    );

    // Reconciliation: re-apply unacknowledged inputs on top of server state
    let reconciledState = { ...state };
    for (const input of this.pendingInputs) {
      reconciledState = this.simulateInput(reconciledState, input);
    }

    // Smooth correction (don't snap)
    this.interpolateToState(reconciledState);
  }

  // Interpolation for other players (not locally controlled)
  private interpolationBuffer: StateSnapshot[] = [];
  private readonly INTERPOLATION_DELAY = 100; // ms

  interpolateRemotePlayer(renderTime: number): PlayerState {
    const targetTime = renderTime - this.INTERPOLATION_DELAY;

    // Find two snapshots to interpolate between
    let before: StateSnapshot | null = null;
    let after: StateSnapshot | null = null;

    for (let i = 0; i < this.interpolationBuffer.length - 1; i++) {
      if (this.interpolationBuffer[i].timestamp <= targetTime &&
          this.interpolationBuffer[i + 1].timestamp >= targetTime) {
        before = this.interpolationBuffer[i];
        after = this.interpolationBuffer[i + 1];
        break;
      }
    }

    if (before && after) {
      const t = (targetTime - before.timestamp) / (after.timestamp - before.timestamp);
      return this.lerp(before.state, after.state, t);
    }

    return this.interpolationBuffer[this.interpolationBuffer.length - 1]?.state;
  }
}

// Server: Authoritative game state
class GameServer {
  private tickRate = 20; // Server updates per second
  private players = new Map<string, ServerPlayer>();

  tick(): void {
    // Process all pending inputs
    for (const [id, player] of this.players) {
      while (player.inputQueue.length > 0) {
        const input = player.inputQueue.shift()!;
        this.processPlayerInput(player, input);
        player.lastProcessedInput = input.sequence;
      }
    }

    // Physics / collision
    this.physicsStep();

    // Broadcast state to all clients
    const snapshot = this.createSnapshot();
    for (const [id, player] of this.players) {
      player.socket.send({
        type: 'state',
        state: snapshot,
        lastInput: player.lastProcessedInput,
      });
    }
  }
}
```

---

## Asset Management

```typescript
// Asset loader with progress tracking
class AssetManager {
  private cache = new Map<string, any>();
  private loading = new Map<string, Promise<any>>();

  async loadManifest(manifest: AssetManifest): Promise<void> {
    const total = manifest.assets.length;
    let loaded = 0;

    const promises = manifest.assets.map(async (asset) => {
      await this.load(asset);
      loaded++;
      this.onProgress?.(loaded / total);
    });

    await Promise.all(promises);
  }

  async load(asset: AssetDefinition): Promise<any> {
    if (this.cache.has(asset.key)) return this.cache.get(asset.key);
    if (this.loading.has(asset.key)) return this.loading.get(asset.key);

    const promise = this.loadAsset(asset);
    this.loading.set(asset.key, promise);

    const result = await promise;
    this.cache.set(asset.key, result);
    this.loading.delete(asset.key);
    return result;
  }

  private async loadAsset(asset: AssetDefinition): Promise<any> {
    switch (asset.type) {
      case 'image': return this.loadImage(asset.url);
      case 'audio': return this.loadAudio(asset.url);
      case 'json': return this.loadJSON(asset.url);
      case 'spritesheet': return this.loadSpritesheet(asset.url, asset.frameWidth, asset.frameHeight);
    }
  }

  // Unload unused assets (memory management)
  unload(key: string): void {
    const asset = this.cache.get(key);
    if (asset instanceof HTMLImageElement) asset.src = '';
    if (asset instanceof AudioBuffer) { /* GC handles it */ }
    this.cache.delete(key);
  }
}
```

---

## Anti-Patterns

| Anti-Pattern | Problem | Solution |
|---|---|---|
| Variable timestep physics | Non-deterministic, tunneling | Fixed timestep with interpolation |
| God object game manager | Unmaintainable, hard to extend | ECS or component-based architecture |
| Polling input every frame | Missed inputs, input lag | Event-driven input with buffering |
| No object pooling | GC spikes cause frame drops | Pool bullets, particles, effects |
| Tight coupling to rendering | Cannot run headless (server, tests) | Separate logic from presentation |
| Sending full state every tick | Bandwidth explosion | Delta compression, interest management |
| No client prediction | Laggy feel for players | Predict locally, reconcile with server |
| Loading all assets upfront | Long initial load time | Lazy loading, streaming, LOD |
