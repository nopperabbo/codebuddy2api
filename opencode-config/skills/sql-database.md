# Skill: SQL & Database
# Loaded on-demand when working with SQL, database design, migrations, queries

## Schema Design

```sql
-- Normalization: eliminate redundancy, enforce integrity
CREATE TABLE users (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email       TEXT NOT NULL UNIQUE,
    name        TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE posts (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    author_id   BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title       TEXT NOT NULL,
    body        TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','published','archived')),
    published_at TIMESTAMPTZ,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Denormalization trade-off: add computed/cached columns for read-heavy paths
ALTER TABLE users ADD COLUMN post_count INT NOT NULL DEFAULT 0;
-- Maintain via trigger or application logic — accept write overhead for read speed
```

## Indexing Strategy

```sql
-- B-tree (default) — equality and range queries
CREATE INDEX idx_posts_author ON posts(author_id);

-- Composite index — column order matters (leftmost prefix rule)
CREATE INDEX idx_posts_status_date ON posts(status, published_at DESC);
-- Supports: WHERE status = 'published' ORDER BY published_at DESC
-- Does NOT support: WHERE published_at > '2024-01-01' alone

-- Partial index — index only relevant rows
CREATE INDEX idx_posts_published ON posts(published_at DESC)
    WHERE status = 'published';

-- GIN index — for JSONB, arrays, full-text search
CREATE INDEX idx_posts_tags ON posts USING GIN (tags);

-- Expression index
CREATE INDEX idx_users_email_lower ON users(lower(email));
```

## Query Optimization

```sql
-- ALWAYS check query plans
EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)
SELECT p.title, u.name
FROM posts p
JOIN users u ON u.id = p.author_id
WHERE p.status = 'published'
ORDER BY p.published_at DESC
LIMIT 20;

-- Key things to look for:
-- Seq Scan on large tables → needs index
-- Nested Loop with high row counts → consider Hash/Merge Join
-- Sort with high cost → add index matching ORDER BY
-- Buffers shared read (high) → data not in cache

-- CTEs (Common Table Expressions) — readable subqueries
WITH recent_posts AS (
    SELECT id, author_id, title, published_at
    FROM posts
    WHERE status = 'published' AND published_at > now() - INTERVAL '7 days'
)
SELECT u.name, count(*) AS post_count
FROM recent_posts rp
JOIN users u ON u.id = rp.author_id
GROUP BY u.name
ORDER BY post_count DESC;

-- Window functions — analytics without GROUP BY
SELECT
    title,
    published_at,
    ROW_NUMBER() OVER (ORDER BY published_at DESC) AS rank,
    LAG(published_at) OVER (ORDER BY published_at) AS prev_published,
    SUM(view_count) OVER (
        ORDER BY published_at
        ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
    ) AS rolling_7day_views
FROM posts
WHERE status = 'published';
```

## Transactions & Isolation Levels

```sql
-- Default: READ COMMITTED — each statement sees committed data at statement start
BEGIN;
UPDATE accounts SET balance = balance - 100 WHERE id = 1;
UPDATE accounts SET balance = balance + 100 WHERE id = 2;
COMMIT;

-- SERIALIZABLE — strongest isolation, prevents all anomalies
BEGIN ISOLATION LEVEL SERIALIZABLE;
-- ... operations ...
COMMIT;
-- Be prepared to retry on serialization failures

-- Deadlock prevention: always lock rows in consistent order
-- Bad:  TX1 locks A then B, TX2 locks B then A → deadlock
-- Good: Both lock A first, then B
SELECT * FROM accounts WHERE id IN (1, 2) ORDER BY id FOR UPDATE;
```

## Migrations (Expand-Contract for Zero Downtime)

```sql
-- Phase 1: EXPAND — add new column, keep old one
ALTER TABLE users ADD COLUMN display_name TEXT;
-- Backfill (in batches to avoid long locks)
UPDATE users SET display_name = name WHERE display_name IS NULL AND id BETWEEN 1 AND 10000;

-- Phase 2: MIGRATE — application writes to both columns
-- Deploy code that writes to both `name` and `display_name`

-- Phase 3: CONTRACT — drop old column (after all reads migrated)
ALTER TABLE users DROP COLUMN name;

-- NEVER in production:
-- ALTER TABLE big_table ADD COLUMN x INT NOT NULL DEFAULT 0;  -- locks table (pre-PG11)
-- Use NOT VALID constraint + VALIDATE CONSTRAINT separately
ALTER TABLE users ADD CONSTRAINT chk_email CHECK (email ~ '@') NOT VALID;
ALTER TABLE users VALIDATE CONSTRAINT chk_email;  -- non-blocking scan
```

## PostgreSQL Specifics

```sql
-- JSONB — structured data in a column
CREATE TABLE events (
    id    BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    type  TEXT NOT NULL,
    data  JSONB NOT NULL DEFAULT '{}'
);

SELECT data->>'name' AS name, data->'address'->>'city' AS city
FROM events
WHERE data @> '{"type": "signup"}';  -- containment operator (uses GIN index)

-- Full-text search
ALTER TABLE posts ADD COLUMN search_vector tsvector
    GENERATED ALWAYS AS (to_tsvector('english', title || ' ' || body)) STORED;
CREATE INDEX idx_posts_search ON posts USING GIN (search_vector);

SELECT title, ts_rank(search_vector, query) AS rank
FROM posts, to_tsquery('english', 'database & optimization') AS query
WHERE search_vector @@ query
ORDER BY rank DESC;

-- pg_stat_statements — find slow queries
SELECT query, calls, mean_exec_time, total_exec_time
FROM pg_stat_statements
ORDER BY total_exec_time DESC
LIMIT 20;
```

## Connection Pooling & Replication

```
# PgBouncer config (connection pooler)
[databases]
mydb = host=127.0.0.1 port=5432 dbname=mydb

[pgbouncer]
pool_mode = transaction          # Release connection after each transaction
max_client_conn = 1000
default_pool_size = 25

# Replication patterns:
# - Streaming replication: real-time, async or sync
# - Logical replication: selective table replication
# - Read replicas: route SELECT to replicas, writes to primary
```

## Backup Strategies

```bash
# Logical backup (portable, slower restore)
pg_dump -Fc mydb > mydb.dump
pg_restore -d mydb mydb.dump

# Physical backup (fast, full cluster)
pg_basebackup -D /backup/base -Ft -z -P

# Continuous archiving (point-in-time recovery)
# archive_mode = on
# archive_command = 'cp %p /archive/%f'
```

## Best Practices

- **Always use parameterized queries** — never interpolate user input into SQL.
- **Add indexes based on query patterns**, not schema structure. Use `EXPLAIN ANALYZE`.
- **Use `BIGINT` for primary keys** — `INT` runs out faster than you think.
- **Prefer `TIMESTAMPTZ`** over `TIMESTAMP` — always store timezone-aware times.
- **Batch large updates** — `UPDATE ... WHERE id BETWEEN x AND y` to avoid long locks.
- **Monitor with `pg_stat_statements`** — find and fix the top 5 slowest queries.
- **Test migrations on a copy of production data** before deploying.
- **Use `SELECT ... FOR UPDATE SKIP LOCKED`** for job queue patterns.
