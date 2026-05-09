# Skill: Swift & iOS
# Loaded on-demand when working with .swift files, SwiftUI, UIKit

## SwiftUI View & State

```swift
import SwiftUI

struct ProfileView: View {
    @State private var isEditing = false          // Local state
    @Binding var username: String                  // Two-way binding from parent
    @ObservedObject var viewModel: ProfileVM       // External observable (not owned)
    @StateObject var localVM = ProfileVM()         // Owned observable (created here)
    @EnvironmentObject var auth: AuthService       // Injected via environment

    var body: some View {
        VStack(spacing: 16) {
            Text("Hello, \(username)")
                .font(.title)
            Toggle("Edit Mode", isOn: $isEditing)
            if isEditing {
                TextField("Username", text: $username)
                    .textFieldStyle(.roundedBorder)
            }
        }
        .padding()
    }
}

// Inject environment object at root
@main
struct MyApp: App {
    @StateObject private var auth = AuthService()

    var body: some Scene {
        WindowGroup {
            ContentView()
                .environmentObject(auth)
        }
    }
}
```

## MVVM Architecture

```swift
@MainActor
class ProfileVM: ObservableObject {
    @Published var user: User?
    @Published var isLoading = false
    @Published var error: String?

    private let repository: UserRepository

    init(repository: UserRepository = .live) {
        self.repository = repository
    }

    func loadUser(id: String) async {
        isLoading = true
        defer { isLoading = false }
        do {
            user = try await repository.fetchUser(id: id)
        } catch {
            self.error = error.localizedDescription
        }
    }
}
```

## Async/Await & Actors

```swift
// Structured concurrency
func fetchDashboard() async throws -> Dashboard {
    async let profile = api.fetchProfile()
    async let posts = api.fetchPosts()
    async let notifications = api.fetchNotifications()
    return Dashboard(
        profile: try await profile,
        posts: try await posts,
        notifications: try await notifications
    )
}

// Actor — thread-safe mutable state
actor ImageCache {
    private var cache: [URL: UIImage] = [:]

    func image(for url: URL) -> UIImage? { cache[url] }
    func store(_ image: UIImage, for url: URL) { cache[url] = image }
}

// AsyncSequence
for await event in eventStream {
    handleEvent(event)
}
```

## Networking with URLSession + Codable

```swift
struct User: Codable, Identifiable {
    let id: String
    let name: String
    let email: String
}

func fetchUser(id: String) async throws -> User {
    let url = URL(string: "https://api.example.com/users/\(id)")!
    let (data, response) = try await URLSession.shared.data(from: url)

    guard let http = response as? HTTPURLResponse, http.statusCode == 200 else {
        throw APIError.invalidResponse
    }

    return try JSONDecoder().decode(User.self, from: data)
}

enum APIError: LocalizedError {
    case invalidResponse
    case decodingFailed

    var errorDescription: String? {
        switch self {
        case .invalidResponse: return "Server returned an invalid response"
        case .decodingFailed: return "Failed to decode response"
        }
    }
}
```

## SwiftData (iOS 17+)

```swift
import SwiftData

@Model
class Task {
    var title: String
    var isComplete: Bool
    var createdAt: Date

    init(title: String, isComplete: Bool = false) {
        self.title = title
        self.isComplete = isComplete
        self.createdAt = .now
    }
}

// In App
@main
struct MyApp: App {
    var body: some Scene {
        WindowGroup { ContentView() }
            .modelContainer(for: Task.self)
    }
}

// In View
struct TaskList: View {
    @Query(sort: \Task.createdAt, order: .reverse) var tasks: [Task]
    @Environment(\.modelContext) var context

    var body: some View {
        List(tasks) { task in
            Text(task.title)
        }
    }

    func addTask(_ title: String) {
        context.insert(Task(title: title))
    }
}
```

## Protocols & Extensions

```swift
protocol Repository {
    associatedtype Entity: Identifiable
    func fetch(id: Entity.ID) async throws -> Entity
    func save(_ entity: Entity) async throws
}

extension Array where Element: Numeric {
    var sum: Element { reduce(0, +) }
}

// Property wrapper
@propertyWrapper
struct Clamped<Value: Comparable> {
    var wrappedValue: Value { didSet { wrappedValue = min(max(wrappedValue, range.lowerBound), range.upperBound) } }
    let range: ClosedRange<Value>

    init(wrappedValue: Value, _ range: ClosedRange<Value>) {
        self.range = range
        self.wrappedValue = min(max(wrappedValue, range.lowerBound), range.upperBound)
    }
}
```

## Testing

```swift
import XCTest
@testable import MyApp

final class ProfileVMTests: XCTestCase {
    @MainActor
    func testLoadUser() async {
        let mockRepo = MockUserRepository(user: .sample)
        let vm = ProfileVM(repository: mockRepo)

        await vm.loadUser(id: "1")

        XCTAssertEqual(vm.user?.name, "Alice")
        XCTAssertFalse(vm.isLoading)
        XCTAssertNil(vm.error)
    }
}
```

## Best Practices

- Prefer `@StateObject` for owned objects, `@ObservedObject` for passed-in objects.
- Use `@MainActor` on ViewModels to ensure UI updates on main thread.
- Prefer `async let` for concurrent independent work over `TaskGroup` for simple cases.
- Use `Result` type for error handling in callbacks; `throws` for async functions.
- Mark views with `@ViewBuilder` for conditional composition.
- Test ViewModels with dependency injection; mock protocols, not concrete types.
- Follow Apple's accessibility guidelines: add `.accessibilityLabel()` to all interactive elements.
