# Skill: Rust
# Loaded on-demand when working with .rs files

---

## Rust

```rust
// ✅ Error handling with thiserror + anyhow
// Libraries: thiserror (define errors), Applications: anyhow (propagate errors)

// ✅ Builder pattern for complex construction
#[derive(Default)]
struct ServerBuilder {
    port: Option<u16>,
    host: Option<String>,
    tls: bool,
}

impl ServerBuilder {
    fn port(mut self, port: u16) -> Self { self.port = Some(port); self }
    fn host(mut self, host: impl Into<String>) -> Self { self.host = Some(host.into()); self }
    fn tls(mut self) -> Self { self.tls = true; self }
    fn build(self) -> Result<Server, BuildError> { /* ... */ }
}

// ✅ Newtype pattern for type safety
struct UserId(Uuid);
struct OrderId(Uuid);
// Can't mix them up at compile time

// ✅ Prefer iterators, avoid index-based loops
let active_users: Vec<&User> = users.iter()
    .filter(|u| u.is_active())
    .collect();

// ❌ Avoid: unwrap() in prod, unsafe without proof, excessive clone()
```

---

## General Polyglot Rules

Regardless of language:
- **Consistent naming** within the project's convention
- **Small functions** — each does one thing (max ~40 lines)
- **Early returns** — reduce nesting, handle errors first
- **No magic numbers** — use named constants
- **Comments explain WHY, not WHAT** — code should be self-documenting
- **Delete dead code** — don't comment it out, that's what git is for
- **Immutability by default** — mutate only when necessary
- **Parse, don't validate** — transform untyped data into typed structures at boundaries
