# Skill: Go
# Loaded on-demand when working with .go files

---

## Go

```go
// ✅ Functional options pattern
type ServerOption func(*Server)

func WithPort(port int) ServerOption {
    return func(s *Server) { s.port = port }
}

func NewServer(opts ...ServerOption) *Server {
    s := &Server{port: 8080} // defaults
    for _, opt := range opts {
        opt(s)
    }
    return s
}

// ✅ Error wrapping with context
if err != nil {
    return fmt.Errorf("fetching user %s: %w", userID, err)
}

// ✅ Graceful shutdown
ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGTERM, syscall.SIGINT)
defer stop()

go func() { server.ListenAndServe() }()
<-ctx.Done()
server.Shutdown(context.Background())

// ✅ Table-driven tests with subtests
// ❌ Avoid: init(), global mutable state, panic in libraries, naked goroutines
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
