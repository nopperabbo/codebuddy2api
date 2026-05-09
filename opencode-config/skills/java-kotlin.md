# Skill: Java / Kotlin
# Loaded on-demand when working with .java, .kt, .kts files

---

## Kotlin

```kotlin
// ✅ Kotlin — data classes, null safety, coroutines
data class User(val id: String, val email: String, val name: String)

suspend fun fetchUser(id: String): Result<User> = runCatching {
    httpClient.get("$baseUrl/users/$id").body<User>()
}

// ✅ Sealed classes for exhaustive when
sealed class PaymentResult {
    data class Success(val transactionId: String) : PaymentResult()
    data class Failed(val reason: String) : PaymentResult()
    data object Pending : PaymentResult()
}

fun handle(result: PaymentResult) = when (result) {
    is PaymentResult.Success -> notify(result.transactionId)
    is PaymentResult.Failed -> retry(result.reason)
    is PaymentResult.Pending -> waitAndPoll()
    // Compiler enforces exhaustiveness
}

// ✅ Coroutines for async
val users = coroutineScope {
    val user1 = async { fetchUser("1") }
    val user2 = async { fetchUser("2") }
    listOf(user1.await(), user2.await())
}
```

## Java

```java
// ✅ Java 21+ — records, sealed interfaces, pattern matching
public record User(String id, String email, String name) {}

public sealed interface Result<T> permits Success, Failure {}
public record Success<T>(T data) implements Result<T> {}
public record Failure<T>(String error) implements Result<T> {}

// ✅ Virtual threads (Java 21+)
try (var executor = Executors.newVirtualThreadPerTaskExecutor()) {
    var futures = urls.stream()
        .map(url -> executor.submit(() -> fetch(url)))
        .toList();
    return futures.stream().map(Future::get).toList();
}

// ❌ Avoid: raw types, checked exceptions for control flow, null returns (use Optional)
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
