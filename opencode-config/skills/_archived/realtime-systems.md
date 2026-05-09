# Skill: Real-Time Systems
# Loaded on-demand when task involves WebSocket, SSE, CRDT, operational transforms, presence, or real-time sync

## Auto-Detect

Trigger this skill when:
- Task mentions: WebSocket, SSE, real-time, CRDT, presence, pub/sub, live updates, sync
- Files: `ws/`, `socket/`, `realtime/`, `*.gateway.ts`
- Patterns: bidirectional communication, live collaboration, presence indicators
- `package.json` contains: `ws`, `socket.io`, `@supabase/realtime`, `yjs`, `automerge`, `liveblocks`

---

## Decision Tree: Real-Time Transport

```
What's your communication pattern?
+-- Server pushes updates to client (one-way)?
|   +-- Simple text/JSON events? -> Server-Sent Events (SSE)
|   +-- Binary data or high frequency? -> WebSocket
|   +-- Need HTTP/2 multiplexing? -> SSE (works great with HTTP/2)
+-- Bidirectional communication?
|   +-- Chat, gaming, collaboration? -> WebSocket
|   +-- Need fallback for corporate proxies? -> Socket.IO (auto-fallback)
|   +-- gRPC ecosystem? -> gRPC bidirectional streaming
+-- Collaborative editing?
|   +-- Text documents? -> CRDT (Yjs) or OT (ShareDB)
|   +-- Structured data (JSON, trees)? -> CRDT (Automerge)
|   +-- Need undo/redo per user? -> OT (better history model)
+-- Presence (who is online/typing)?
|   +-- Simple presence? -> Heartbeat + pub/sub
|   +-- Cursor positions, selections? -> CRDT awareness protocol
```

---

## WebSocket Server (Production-Ready)

```typescript
import { WebSocketServer, WebSocket } from 'ws';
import { createServer } from 'http';
import { Redis } from 'ioredis';

interface Client {
  ws: WebSocket;
  userId: string;
  rooms: Set<string>;
  lastPing: number;
  isAlive: boolean;
}

class RealtimeServer {
  private clients = new Map<string, Client>();
  private wss: WebSocketServer;
  private pub: Redis;
  private sub: Redis;

  constructor(server: ReturnType<typeof createServer>) {
    this.wss = new WebSocketServer({ server, path: '/ws' });
    this.pub = new Redis(process.env.REDIS_URL!);
    this.sub = new Redis(process.env.REDIS_URL!);

    this.setupSubscription();
    this.setupHeartbeat();
    this.wss.on('connection', this.handleConnection.bind(this));
  }

  private async handleConnection(ws: WebSocket, req: Request): Promise<void> {
    // Authenticate on connection
    const token = new URL(req.url!, 'http://localhost').searchParams.get('token');
    const user = await this.authenticate(token);
    if (!user) {
      ws.close(4001, 'Unauthorized');
      return;
    }

    const client: Client = {
      ws,
      userId: user.id,
      rooms: new Set(),
      lastPing: Date.now(),
      isAlive: true,
    };

    this.clients.set(user.id, client);

    // Handle messages
    ws.on('message', (data) => this.handleMessage(client, data));
    ws.on('pong', () => { client.isAlive = true; });
    ws.on('close', () => this.handleDisconnect(client));
    ws.on('error', (err) => this.handleError(client, err));

    // Send connection acknowledgment
    this.send(ws, { type: 'connected', userId: user.id });
  }

  private async handleMessage(client: Client, raw: Buffer): Promise<void> {
    let message: any;
    try {
      message = JSON.parse(raw.toString());
    } catch {
      this.send(client.ws, { type: 'error', message: 'Invalid JSON' });
      return;
    }

    switch (message.type) {
      case 'join':
        await this.joinRoom(client, message.room);
        break;
      case 'leave':
        await this.leaveRoom(client, message.room);
        break;
      case 'broadcast':
        await this.broadcastToRoom(client, message.room, message.payload);
        break;
      case 'ping':
        this.send(client.ws, { type: 'pong', timestamp: Date.now() });
        break;
    }
  }

  // Horizontal scaling via Redis pub/sub
  private async broadcastToRoom(sender: Client, room: string, payload: unknown): Promise<void> {
    const message = {
      type: 'message',
      room,
      senderId: sender.userId,
      payload,
      timestamp: Date.now(),
    };

    // Publish to Redis for other server instances
    await this.pub.publish(`room:${room}`, JSON.stringify(message));
  }

  private setupSubscription(): void {
    this.sub.psubscribe('room:*');
    this.sub.on('pmessage', (_pattern, channel, data) => {
      const room = channel.replace('room:', '');
      const message = JSON.parse(data);

      // Deliver to local clients in this room
      for (const client of this.clients.values()) {
        if (client.rooms.has(room) && client.userId !== message.senderId) {
          this.send(client.ws, message);
        }
      }
    });
  }

  // Heartbeat to detect dead connections
  private setupHeartbeat(): void {
    setInterval(() => {
      for (const [userId, client] of this.clients) {
        if (!client.isAlive) {
          client.ws.terminate();
          this.clients.delete(userId);
          continue;
        }
        client.isAlive = false;
        client.ws.ping();
      }
    }, 30000); // Every 30 seconds
  }

  private send(ws: WebSocket, data: unknown): void {
    if (ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify(data));
    }
  }
}
```

---

## Server-Sent Events (SSE)

```typescript
// SSE is simpler than WebSocket for server-to-client push
import { Router } from 'express';

const router = Router();

router.get('/events', authenticate, (req, res) => {
  // SSE headers
  res.writeHead(200, {
    'Content-Type': 'text/event-stream',
    'Cache-Control': 'no-cache',
    'Connection': 'keep-alive',
    'X-Accel-Buffering': 'no', // Disable nginx buffering
  });

  // Send initial connection event
  res.write(`event: connected\ndata: ${JSON.stringify({ userId: req.user.id })}\n\n`);

  // Keep-alive every 15 seconds (prevents proxy timeouts)
  const keepAlive = setInterval(() => {
    res.write(': keepalive\n\n');
  }, 15000);

  // Subscribe to user-specific events
  const unsubscribe = eventBus.subscribe(req.user.id, (event) => {
    res.write(`id: ${event.id}\nevent: ${event.type}\ndata: ${JSON.stringify(event.data)}\n\n`);
  });

  // Cleanup on disconnect
  req.on('close', () => {
    clearInterval(keepAlive);
    unsubscribe();
  });
});

// Client-side with auto-reconnect (built into EventSource)
// const es = new EventSource('/events');
// es.addEventListener('order_update', (e) => { ... });
// EventSource automatically reconnects with Last-Event-ID header
```

---

## CRDT (Conflict-Free Replicated Data Types)

```typescript
import * as Y from 'yjs';
import { WebsocketProvider } from 'y-websocket';

// Yjs for collaborative editing
class CollaborativeDocument {
  private doc: Y.Doc;
  private provider: WebsocketProvider;

  constructor(roomId: string) {
    this.doc = new Y.Doc();

    // Connect to sync server
    this.provider = new WebsocketProvider(
      'wss://sync.example.com',
      roomId,
      this.doc,
      { connect: true }
    );

    // Awareness (presence: cursors, selections, user info)
    this.provider.awareness.setLocalStateField('user', {
      name: currentUser.name,
      color: currentUser.color,
    });
  }

  // Shared types — automatically synced across all clients
  getText(): Y.Text {
    return this.doc.getText('content');
  }

  getMap(): Y.Map<unknown> {
    return this.doc.getMap('metadata');
  }

  getArray(): Y.Array<unknown> {
    return this.doc.getArray('items');
  }

  // Observe changes
  observeChanges(callback: (events: Y.YEvent<any>[]) => void): void {
    this.doc.on('update', (update: Uint8Array, origin: any) => {
      if (origin !== 'local') {
        // Remote change received
        callback(Y.decodeUpdate(update));
      }
    });
  }

  // Undo/redo per user
  createUndoManager(scope: Y.Text | Y.Array<any> | Y.Map<any>): Y.UndoManager {
    return new Y.UndoManager(scope, {
      trackedOrigins: new Set(['local']),
      captureTimeout: 500, // Group changes within 500ms
    });
  }
}

// Server-side: Yjs sync protocol with persistence
import { Server } from 'y-websocket/bin/utils';

const yjsServer = new Server({
  // Persist document state
  async onUpdate(docName: string, update: Uint8Array): Promise<void> {
    await db.documents.upsert({
      where: { name: docName },
      update: { content: Buffer.from(Y.mergeUpdates([existingUpdate, update])) },
      create: { name: docName, content: Buffer.from(update) },
    });
  },

  // Load persisted state on connect
  async onLoad(docName: string): Promise<Uint8Array | null> {
    const doc = await db.documents.findUnique({ where: { name: docName } });
    return doc?.content ?? null;
  },
});
```

---

## Presence System

```typescript
// Lightweight presence with Redis
class PresenceService {
  private readonly PRESENCE_TTL = 60; // seconds
  private readonly HEARTBEAT_INTERVAL = 30; // seconds

  constructor(private readonly redis: Redis) {}

  // User comes online
  async setPresence(userId: string, metadata: PresenceMetadata): Promise<void> {
    const key = `presence:${userId}`;
    await this.redis.setex(key, this.PRESENCE_TTL, JSON.stringify({
      ...metadata,
      lastSeen: Date.now(),
    }));

    // Notify subscribers
    await this.redis.publish('presence:updates', JSON.stringify({
      type: 'online',
      userId,
      metadata,
    }));
  }

  // Heartbeat to maintain presence
  async heartbeat(userId: string): Promise<void> {
    const key = `presence:${userId}`;
    await this.redis.expire(key, this.PRESENCE_TTL);
  }

  // Get who is in a room
  async getRoomPresence(roomId: string): Promise<PresenceInfo[]> {
    const members = await this.redis.smembers(`room:${roomId}:members`);
    const pipeline = this.redis.pipeline();

    for (const userId of members) {
      pipeline.get(`presence:${userId}`);
    }

    const results = await pipeline.exec();
    return results
      .filter(([err, val]) => !err && val)
      .map(([, val]) => JSON.parse(val as string));
  }

  // Cursor/selection sharing
  async updateCursor(userId: string, roomId: string, cursor: CursorPosition): Promise<void> {
    await this.redis.publish(`room:${roomId}:cursors`, JSON.stringify({
      userId,
      cursor,
      timestamp: Date.now(),
    }));
  }
}

interface CursorPosition {
  line: number;
  column: number;
  selection?: { startLine: number; startCol: number; endLine: number; endCol: number };
}
```

---

## Pub/Sub Architecture

```typescript
// Event-driven pub/sub with fan-out
interface PubSubMessage {
  channel: string;
  event: string;
  data: unknown;
  metadata: {
    publishedAt: number;
    publisherId: string;
    messageId: string;
  };
}

class PubSubService {
  private subscriptions = new Map<string, Set<(msg: PubSubMessage) => void>>();

  // Channel patterns for flexible routing
  // "orders.*" matches "orders.created", "orders.updated"
  // "user.123.*" matches "user.123.typing", "user.123.online"

  subscribe(pattern: string, handler: (msg: PubSubMessage) => void): () => void {
    if (!this.subscriptions.has(pattern)) {
      this.subscriptions.set(pattern, new Set());
    }
    this.subscriptions.get(pattern)!.add(handler);

    // Return unsubscribe function
    return () => {
      this.subscriptions.get(pattern)?.delete(handler);
    };
  }

  async publish(channel: string, event: string, data: unknown): Promise<void> {
    const message: PubSubMessage = {
      channel,
      event,
      data,
      metadata: {
        publishedAt: Date.now(),
        publisherId: this.instanceId,
        messageId: crypto.randomUUID(),
      },
    };

    // Match against all subscription patterns
    for (const [pattern, handlers] of this.subscriptions) {
      if (this.matchPattern(pattern, channel)) {
        for (const handler of handlers) {
          try {
            handler(message);
          } catch (error) {
            this.logger.error({ error, pattern, channel }, 'Handler error');
          }
        }
      }
    }
  }

  private matchPattern(pattern: string, channel: string): boolean {
    const regex = new RegExp('^' + pattern.replace(/\*/g, '[^.]+') + '$');
    return regex.test(channel);
  }
}
```

---

## Real-Time Sync Architecture

```
Client A          Server           Client B
   |                |                  |
   |-- mutation --> |                  |
   |                |-- validate -->   |
   |                |-- persist -->    |
   |                |-- broadcast ---> |
   |<-- ack -----  |                  |
   |                |                  |
   
Optimistic updates:
1. Client applies change locally (instant UI)
2. Client sends mutation to server
3. Server validates, persists, broadcasts
4. Server ACKs to sender (confirm or reject)
5. If rejected: client rolls back local change
6. Other clients receive and apply
```

```typescript
// Optimistic update with rollback
class OptimisticSync<T> {
  private pendingMutations: Map<string, { original: T; mutation: Mutation }> = new Map();

  async applyOptimistic(mutation: Mutation): Promise<void> {
    const mutationId = crypto.randomUUID();
    const original = this.getState(mutation.entityId);

    // Apply locally immediately
    this.pendingMutations.set(mutationId, { original, mutation });
    this.applyLocally(mutation);

    try {
      // Send to server
      const result = await this.sendToServer({ ...mutation, mutationId });
      this.pendingMutations.delete(mutationId);

      // Apply server-confirmed state (may differ from optimistic)
      if (result.state) {
        this.setState(mutation.entityId, result.state);
      }
    } catch (error) {
      // Rollback on failure
      this.pendingMutations.delete(mutationId);
      this.setState(mutation.entityId, original);
      this.notifyRollback(mutation, error);
    }
  }
}
```

---

## Anti-Patterns

| Anti-Pattern | Problem | Solution |
|---|---|---|
| WebSocket for everything | Overkill for simple notifications | SSE for server-push, WebSocket only for bidirectional |
| No reconnection strategy | Users lose connection silently | Exponential backoff + state reconciliation on reconnect |
| Sending full state on every change | Bandwidth waste, slow | Send deltas/patches, use CRDTs for merging |
| No heartbeat/ping | Dead connections consume resources | Ping/pong every 30s, terminate unresponsive |
| Single WebSocket server | Cannot scale horizontally | Redis pub/sub or NATS for cross-instance messaging |
| No message ordering guarantee | UI shows stale data | Sequence numbers + client-side reordering |
| Presence without TTL | Ghost users shown as online | TTL-based presence with heartbeat renewal |
| No backpressure | Slow clients get overwhelmed | Buffer with drop policy or flow control |
