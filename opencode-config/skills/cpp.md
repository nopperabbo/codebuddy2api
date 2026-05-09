# Skill: C / C++
# Loaded on-demand when working with .c, .cpp, .h, .hpp files

## Modern C++ (C++17/20/23)

```cpp
#include <optional>
#include <variant>
#include <string_view>
#include <expected>  // C++23

// std::optional — nullable value without pointers
std::optional<int> findIndex(std::string_view haystack, char needle) {
    if (auto pos = haystack.find(needle); pos != std::string_view::npos)
        return static_cast<int>(pos);
    return std::nullopt;
}

// std::variant — type-safe union
using JsonValue = std::variant<int, double, std::string, bool, std::nullptr_t>;

// std::expected (C++23) — Result type
std::expected<User, Error> parseUser(std::string_view json);

// Structured bindings
auto [key, value] = myMap.extract(myMap.begin());

// if-init statements
if (auto it = cache.find(key); it != cache.end()) {
    return it->second;
}
```

## RAII & Smart Pointers

```cpp
#include <memory>

// unique_ptr — sole ownership, zero overhead
auto widget = std::make_unique<Widget>(42);
// Transfer ownership
auto other = std::move(widget); // widget is now nullptr

// shared_ptr — shared ownership, reference counted
auto shared = std::make_shared<Config>();
auto copy = shared; // refcount = 2

// weak_ptr — non-owning observer, breaks cycles
std::weak_ptr<Config> observer = shared;
if (auto locked = observer.lock()) {
    // safe to use locked
}

// RAII pattern — resource tied to object lifetime
class FileHandle {
    FILE* fp_;
public:
    explicit FileHandle(const char* path) : fp_(fopen(path, "r")) {
        if (!fp_) throw std::runtime_error("Failed to open file");
    }
    ~FileHandle() { if (fp_) fclose(fp_); }

    FileHandle(const FileHandle&) = delete;
    FileHandle& operator=(const FileHandle&) = delete;
    FileHandle(FileHandle&& o) noexcept : fp_(std::exchange(o.fp_, nullptr)) {}
};
```

## Move Semantics

```cpp
class Buffer {
    std::unique_ptr<uint8_t[]> data_;
    size_t size_;
public:
    Buffer(size_t n) : data_(std::make_unique<uint8_t[]>(n)), size_(n) {}

    // Move constructor — steal resources
    Buffer(Buffer&& other) noexcept
        : data_(std::move(other.data_)), size_(std::exchange(other.size_, 0)) {}

    // Move assignment
    Buffer& operator=(Buffer&& other) noexcept {
        data_ = std::move(other.data_);
        size_ = std::exchange(other.size_, 0);
        return *this;
    }
};
```

## Concepts & Ranges (C++20)

```cpp
#include <concepts>
#include <ranges>

// Concept — constrain template parameters
template<typename T>
concept Numeric = std::integral<T> || std::floating_point<T>;

template<Numeric T>
T clamp(T value, T lo, T hi) { return std::max(lo, std::min(value, hi)); }

// Ranges — composable algorithms
auto results = numbers
    | std::views::filter([](int n) { return n % 2 == 0; })
    | std::views::transform([](int n) { return n * n; })
    | std::views::take(10);
```

## Coroutines (C++20)

```cpp
#include <coroutine>

// Generator pattern (simplified)
Generator<int> fibonacci() {
    int a = 0, b = 1;
    while (true) {
        co_yield a;
        auto next = a + b;
        a = b;
        b = next;
    }
}
```

## CMake Build System

```cmake
cmake_minimum_required(VERSION 3.20)
project(myapp LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)  # For clang-tidy / LSP

add_executable(myapp src/main.cpp src/engine.cpp)
target_include_directories(myapp PRIVATE include)

# Fetch dependencies
include(FetchContent)
FetchContent_Declare(fmt GIT_REPOSITORY https://github.com/fmtlib/fmt GIT_TAG 10.1.1)
FetchContent_MakeAvailable(fmt)
target_link_libraries(myapp PRIVATE fmt::fmt)

# Sanitizers (debug builds)
target_compile_options(myapp PRIVATE
    $<$<CONFIG:Debug>:-fsanitize=address,undefined -fno-omit-frame-pointer>)
target_link_options(myapp PRIVATE
    $<$<CONFIG:Debug>:-fsanitize=address,undefined>)
```

## Testing (GoogleTest)

```cpp
#include <gtest/gtest.h>

TEST(BufferTest, MoveTransfersOwnership) {
    Buffer a(1024);
    Buffer b(std::move(a));
    EXPECT_EQ(b.size(), 1024);
    EXPECT_EQ(a.size(), 0);
}

TEST(ClampTest, ClampsToRange) {
    EXPECT_EQ(clamp(5, 0, 10), 5);
    EXPECT_EQ(clamp(-1, 0, 10), 0);
    EXPECT_EQ(clamp(15, 0, 10), 10);
}
```

## Common Pitfalls & Static Analysis

```bash
# Sanitizers — catch bugs at runtime
# ASan: buffer overflow, use-after-free
# UBSan: undefined behavior (signed overflow, null deref)
# TSan: data races in multithreaded code
clang++ -fsanitize=address,undefined -g main.cpp -o main

# Static analysis
clang-tidy src/*.cpp --checks='*,-llvmlibc-*'
cppcheck --enable=all --std=c++20 src/

# Valgrind — memory leak detection
valgrind --leak-check=full ./main
```

## Best Practices

- **Prefer value semantics** — pass by value or const ref, return by value (NRVO applies).
- **Never use raw `new`/`delete`** — use `make_unique`/`make_shared`.
- **Use `string_view`** for read-only string parameters (avoids copies).
- **Mark functions `noexcept`** when they cannot throw (enables move optimizations).
- **Use `constexpr`** for compile-time computation where possible.
- **Avoid `reinterpret_cast`** — it's almost always undefined behavior.
- **Enable warnings**: `-Wall -Wextra -Wpedantic -Werror` in CI.
