# Skill: Flutter & Dart
# Loaded on-demand when working with .dart files, Flutter, widgets

## Widget Tree Fundamentals

```dart
// StatelessWidget — immutable, no internal state
class Greeting extends StatelessWidget {
  const Greeting({super.key, required this.name});
  final String name;

  @override
  Widget build(BuildContext context) => Text('Hello, $name');
}

// StatefulWidget — mutable state, triggers rebuild
class Counter extends StatefulWidget {
  const Counter({super.key});
  @override
  State<Counter> createState() => _CounterState();
}

class _CounterState extends State<Counter> {
  int _count = 0;

  @override
  Widget build(BuildContext context) {
    return ElevatedButton(
      onPressed: () => setState(() => _count++),
      child: Text('Count: $_count'),
    );
  }
}
```

## State Management (Riverpod)

```dart
// Riverpod — preferred for scalable state management
import 'package:flutter_riverpod/flutter_riverpod.dart';

final counterProvider = StateNotifierProvider<CounterNotifier, int>(
  (ref) => CounterNotifier(),
);

class CounterNotifier extends StateNotifier<int> {
  CounterNotifier() : super(0);
  void increment() => state++;
}

// In widget
class MyWidget extends ConsumerWidget {
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final count = ref.watch(counterProvider);
    return Text('$count');
  }
}
```

## Navigation (GoRouter)

```dart
final router = GoRouter(
  routes: [
    GoRoute(path: '/', builder: (_, __) => const HomeScreen()),
    GoRoute(
      path: '/user/:id',
      builder: (_, state) => UserScreen(id: state.pathParameters['id']!),
    ),
  ],
  redirect: (context, state) {
    final loggedIn = /* check auth */;
    if (!loggedIn && state.matchedLocation != '/login') return '/login';
    return null;
  },
);
```

## Layouts

```dart
// Row, Column, Stack — the layout trinity
Column(
  crossAxisAlignment: CrossAxisAlignment.start,
  children: [
    const Text('Title', style: TextStyle(fontSize: 24)),
    const SizedBox(height: 8),
    Row(
      children: [
        Expanded(child: TextField()), // Takes remaining space
        const SizedBox(width: 8),
        ElevatedButton(onPressed: () {}, child: const Text('Send')),
      ],
    ),
  ],
)

// Flexible vs Expanded
// Expanded = Flexible with fit: FlexFit.tight (must fill space)
// Flexible with fit: FlexFit.loose (can be smaller)
```

## Theming

```dart
MaterialApp(
  theme: ThemeData(
    colorScheme: ColorScheme.fromSeed(seedColor: Colors.indigo),
    useMaterial3: true,
    textTheme: const TextTheme(
      headlineMedium: TextStyle(fontWeight: FontWeight.bold),
    ),
  ),
);

// Access in widgets
final color = Theme.of(context).colorScheme.primary;
```

## Models with Freezed + JSON Serializable

```dart
import 'package:freezed_annotation/freezed_annotation.dart';
part 'user.freezed.dart';
part 'user.g.dart';

@freezed
class User with _$User {
  const factory User({
    required String id,
    required String name,
    @Default('') String email,
  }) = _User;

  factory User.fromJson(Map<String, dynamic> json) => _$UserFromJson(json);
}
// Run: dart run build_runner build --delete-conflicting-outputs
```

## Async Patterns

```dart
// Futures
Future<User> fetchUser(String id) async {
  final response = await http.get(Uri.parse('/api/users/$id'));
  return User.fromJson(jsonDecode(response.body));
}

// Streams
Stream<int> countDown(int from) async* {
  for (var i = from; i >= 0; i--) {
    await Future.delayed(const Duration(seconds: 1));
    yield i;
  }
}

// StreamBuilder in UI
StreamBuilder<int>(
  stream: countDown(10),
  builder: (context, snapshot) => Text('${snapshot.data ?? "..."}'),
)
```

## Platform Channels

```dart
const platform = MethodChannel('com.example/native');

Future<String> getBatteryLevel() async {
  final result = await platform.invokeMethod<String>('getBatteryLevel');
  return result ?? 'Unknown';
}
```

## Testing

```dart
// Unit test
test('Counter increments', () {
  final counter = CounterNotifier();
  counter.increment();
  expect(counter.state, 1);
});

// Widget test
testWidgets('displays greeting', (tester) async {
  await tester.pumpWidget(const MaterialApp(home: Greeting(name: 'World')));
  expect(find.text('Hello, World'), findsOneWidget);
});

// Golden test (snapshot)
testWidgets('matches golden', (tester) async {
  await tester.pumpWidget(const MyWidget());
  await expectLater(find.byType(MyWidget), matchesGoldenFile('my_widget.png'));
});
```

## Performance Best Practices

- Use `const` constructors everywhere possible — prevents unnecessary rebuilds.
- Wrap expensive subtrees with `RepaintBoundary` to isolate repaints.
- Profile with Flutter DevTools — check rebuild counts and frame times.
- Avoid `setState` high in the tree; push state down or use Riverpod selectors.
- Use `ListView.builder` (not `ListView(children: [...])`) for long lists.
- Run `flutter analyze` and `dart fix --apply` regularly.
