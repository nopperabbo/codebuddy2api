# Skill: C# / .NET
# Loaded on-demand when working with .cs, .csproj, .sln files

---

## C# / .NET

```csharp
// ✅ Nullable reference types (C# 8+)
#nullable enable
string? name = GetName(); // explicitly nullable
int length = name?.Length ?? 0;

// ✅ Records for immutable data
public record CreateUserRequest(string Email, string Name, int? Age);

// ✅ Async/await with cancellation
public async Task<User> GetUserAsync(int id, CancellationToken ct = default)
{
    var user = await _db.Users.FindAsync(id, ct);
    return user ?? throw new NotFoundException($"User {id} not found");
}

// ✅ Dependency injection (built-in)
builder.Services.AddScoped<IUserRepository, UserRepository>();
builder.Services.AddSingleton<ICacheService, RedisCacheService>();

// ✅ Minimal APIs (ASP.NET Core 7+)
app.MapGet("/users/{id}", async (int id, IUserService svc) =>
    await svc.GetByIdAsync(id) is User user
        ? Results.Ok(user)
        : Results.NotFound());

// ❌ Avoid: public fields, mutable statics, catching Exception (catch specific)
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
