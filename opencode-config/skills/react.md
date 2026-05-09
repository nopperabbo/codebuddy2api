# Skill: React Advanced
# Loaded on-demand when working with React, JSX, TSX components

## Auto-Detect

Trigger this skill when:
- File extensions: `.jsx`, `.tsx`, `*.component.tsx`
- `package.json` contains: `react`, `react-dom`, `next`, `@tanstack/react-query`
- Imports from: `react`, `react-dom`, `react-dom/client`
- Directory patterns: `components/`, `hooks/`, `app/` (Next.js App Router)

---

## Decision Tree: State Management

```
Need to store data?
├── Derived from props/other state? → Compute during render (no state needed)
├── Only used by this component? → useState / useReducer
├── Shared by 2-3 nearby components? → Lift state up
├── App-wide UI state (theme, sidebar)? → Zustand (no providers, minimal boilerplate)
├── Server data (API responses)? → TanStack Query (caching, revalidation, dedup)
├── Complex form state? → React Hook Form + Zod
├── URL-driven state? → useSearchParams / nuqs
└── Deeply nested prop threading? → Context (but ONLY for rarely-changing values)
```

## Decision Tree: Component Type

```
Does it need interactivity (state, effects, event handlers)?
├── No → Server Component (default in App Router, no directive needed)
│   ├── Needs data? → async function + direct DB/API call
│   └── Renders children that are interactive? → Pass Client Components as children
└── Yes → Client Component ('use client' directive)
    ├── Needs form submission? → Server Action + useActionState
    ├── Needs optimistic UI? → useOptimistic
    └── Needs pending state? → useTransition or useFormStatus
```

---

## React 19 Patterns

```tsx
// useActionState — replaces useFormState, handles async actions
function CreatePost() {
  const [state, action, isPending] = useActionState(async (prev, formData: FormData) => {
    const result = await createPost(formData);
    if (!result.ok) return { error: result.error };
    redirect('/posts');
  }, { error: null });

  return (
    <form action={action}>
      <input name="title" required />
      {state.error && <p className="text-red-500">{state.error}</p>}
      <button disabled={isPending}>{isPending ? 'Creating...' : 'Create'}</button>
    </form>
  );
}

// use() — read promises/context in render (replaces useContext)
function UserProfile({ userPromise }: { userPromise: Promise<User> }) {
  const user = use(userPromise); // suspends until resolved
  return <h1>{user.name}</h1>;
}

// useOptimistic — instant UI feedback before server confirms
function LikeButton({ likes, postId }: { likes: number; postId: string }) {
  const [optimisticLikes, setOptimisticLikes] = useOptimistic(likes);
  async function handleLike() {
    setOptimisticLikes(prev => prev + 1);
    await likePost(postId);
  }
  return <button onClick={handleLike}>♥ {optimisticLikes}</button>;
}

// ref as prop — no more forwardRef wrapper needed in React 19
function Input({ ref, ...props }: { ref?: React.Ref<HTMLInputElement> }) {
  return <input ref={ref} {...props} />;
}
```

---

## Hooks Best Practices

```tsx
// Custom hook: encapsulate reusable logic
function useDebounce<T>(value: T, delay = 300): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(timer);
  }, [value, delay]);
  return debounced;
}

// useReducer for complex state machines
type State = { status: 'idle' | 'loading' | 'success' | 'error'; data?: Data; error?: string };
type Action = { type: 'fetch' } | { type: 'success'; data: Data } | { type: 'error'; error: string };

function reducer(state: State, action: Action): State {
  switch (action.type) {
    case 'fetch': return { status: 'loading' };
    case 'success': return { status: 'success', data: action.data };
    case 'error': return { status: 'error', error: action.error };
  }
}
```

---

## Performance Patterns

```tsx
// React.memo — only for expensive renders (profile first!)
const ExpensiveList = memo(function ExpensiveList({ items }: { items: Item[] }) {
  return items.map(item => <ExpensiveRow key={item.id} item={item} />);
});

// lazy + Suspense for route-level code splitting
const Dashboard = lazy(() => import('./pages/Dashboard'));
<Suspense fallback={<DashboardSkeleton />}><Dashboard /></Suspense>

// startTransition — mark non-urgent updates (search results, filters)
function Search() {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<Item[]>([]);
  function handleChange(e: ChangeEvent<HTMLInputElement>) {
    setQuery(e.target.value);
    startTransition(() => setResults(filterItems(e.target.value)));
  }
  return <input value={query} onChange={handleChange} />;
}

// useDeferredValue — defer expensive child re-renders
function FilteredList({ filter }: { filter: string }) {
  const deferredFilter = useDeferredValue(filter);
  const items = useMemo(() => expensiveFilter(deferredFilter), [deferredFilter]);
  return <List items={items} />;
}
```

---

## Server Components (RSC)

```tsx
// Server Component — direct data access, zero client JS
async function ProductPage({ params }: { params: { id: string } }) {
  const product = await db.product.findUnique({ where: { id: params.id } });
  if (!product) notFound();
  return (
    <main>
      <h1>{product.name}</h1>
      <p>{product.description}</p>
      <AddToCartButton productId={product.id} /> {/* Client Component */}
    </main>
  );
}

// Streaming with Suspense boundaries
async function Page() {
  return (
    <main>
      <h1>Dashboard</h1>
      <Suspense fallback={<StatsSkeleton />}>
        <Stats /> {/* Streams in when ready */}
      </Suspense>
      <Suspense fallback={<ChartSkeleton />}>
        <RevenueChart /> {/* Independent stream */}
      </Suspense>
    </main>
  );
}
```

---

## Testing Patterns

```tsx
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

// Test behavior, not implementation
test('submits form with validated data', async () => {
  const user = userEvent.setup();
  const onSubmit = vi.fn();
  render(<ContactForm onSubmit={onSubmit} />);

  await user.type(screen.getByLabelText(/email/i), 'test@example.com');
  await user.click(screen.getByRole('button', { name: /submit/i }));

  expect(onSubmit).toHaveBeenCalledWith({ email: 'test@example.com' });
});

// Test async components with MSW for API mocking
// Test error boundaries by throwing in child components
// Test accessibility: screen.getByRole > getByTestId
```

---

## Code Templates

### Component with Error Boundary
```tsx
<ErrorBoundary fallback={<ErrorFallback />}>
  <Suspense fallback={<Loading />}>
    <AsyncComponent />
  </Suspense>
</ErrorBoundary>
```

### TanStack Query Pattern
```tsx
function useProducts(filters: Filters) {
  return useQuery({
    queryKey: ['products', filters],
    queryFn: () => fetchProducts(filters),
    staleTime: 5 * 60 * 1000,
    placeholderData: keepPreviousData,
  });
}
```

---

## Anti-Patterns

| ❌ Don't | ✅ Do Instead |
|----------|---------------|
| `useEffect` to sync derived state | Compute during render |
| `useEffect` to fetch data | TanStack Query / Server Component |
| Index as key for dynamic lists | Stable unique ID (`item.id`) |
| Object literals in JSX props | Hoist to module scope or `useMemo` |
| Prop drilling 4+ levels deep | Composition, Context, or Zustand |
| Giant useEffect doing 3 things | Split into separate effects |
| `any` in component props | Proper TypeScript generics |
| Snapshot-only tests | Behavioral tests with Testing Library |
| `useEffect` + `setState` for transforms | `useMemo` or compute inline |
| Fetching in useEffect without AbortController | Use a data library or add cleanup |

---

## Verification Checklist

Before considering React work done:
- [ ] No `useEffect` for derived state — computed inline or `useMemo`
- [ ] All lists use stable keys (not index)
- [ ] Client Components have `'use client'` directive
- [ ] Server Components have no `useState`/`useEffect`/event handlers
- [ ] Error boundaries wrap async/suspense boundaries
- [ ] Forms use proper validation (Zod + React Hook Form or Server Actions)
- [ ] No prop drilling beyond 2 levels
- [ ] Accessibility: semantic HTML, ARIA labels, keyboard navigation
- [ ] Performance: no unnecessary re-renders (React DevTools Profiler)
- [ ] Tests cover user-facing behavior, not implementation details

---

## MCP Integration

| Tool | Use For |
|------|---------|
| `context7` | Look up React 19 API docs, TanStack Query patterns |
| `playwright` | E2E testing of component interactions |
| `sequential-thinking` | Design complex component hierarchies |
| `grep/glob` | Find existing patterns in codebase before creating new ones |
