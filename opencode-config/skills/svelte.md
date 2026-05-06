# Skill: Svelte
# Loaded on-demand when working with .svelte files, SvelteKit

## Svelte 5 Runes

### Core Runes
```svelte
<script lang="ts">
  // $state: reactive state declaration (replaces let for reactivity)
  let count = $state(0);
  let items = $state<string[]>([]);

  // $state with objects — deep reactivity by default
  let user = $state({ name: 'Alice', age: 30 });
  user.name = 'Bob'; // reactive, triggers update

  // $state.raw: opt out of deep reactivity (better for large immutable data)
  let largeDataset = $state.raw<DataPoint[]>([]);
  largeDataset = [...largeDataset, newPoint]; // must reassign, not mutate

  // $derived: computed values (replaces $: reactive declarations)
  let doubled = $derived(count * 2);

  // $derived.by: complex derivations
  let sorted = $derived.by(() => {
    return [...items].sort((a, b) => a.localeCompare(b));
  });

  // $effect: side effects that auto-track dependencies
  $effect(() => {
    document.title = `Count: ${count}`;
    // cleanup function (runs before re-execution and on destroy)
    return () => console.log('cleaning up');
  });

  // $effect.pre: runs before DOM update (like beforeUpdate)
  $effect.pre(() => {
    scrollContainer.scrollTop = scrollContainer.scrollHeight;
  });
</script>

<button onclick={() => count++}>Count: {count}</button>
<p>Doubled: {doubled}</p>
```

### Component Props (Svelte 5)
```svelte
<!-- Button.svelte -->
<script lang="ts">
  // $props: declare component props with defaults
  let {
    variant = 'primary',
    size = 'md',
    disabled = false,
    onclick,
    children,       // snippet — replaces default slot
    ...restProps    // spread remaining props
  }: {
    variant?: 'primary' | 'secondary' | 'ghost';
    size?: 'sm' | 'md' | 'lg';
    disabled?: boolean;
    onclick?: (e: MouseEvent) => void;
    children?: import('svelte').Snippet;
    [key: string]: unknown;
  } = $props();

  // $bindable: props that support bind: from parent
  let { value = $bindable('') }: { value?: string } = $props();
</script>

<button class="{variant} {size}" {disabled} {onclick} {...restProps}>
  {@render children?.()}
</button>
```

### Snippets (Svelte 5 — replaces slots)
```svelte
<!-- DataTable.svelte -->
<script lang="ts">
  import type { Snippet } from 'svelte';

  let {
    data,
    header,
    row,
  }: {
    data: any[];
    header: Snippet;
    row: Snippet<[item: any, index: number]>;
  } = $props();
</script>

<table>
  <thead>{@render header()}</thead>
  <tbody>
    {#each data as item, i}
      {@render row(item, i)}
    {/each}
  </tbody>
</table>

<!-- Usage -->
<DataTable {data}>
  {#snippet header()}<tr><th>Name</th><th>Email</th></tr>{/snippet}
  {#snippet row(user, i)}<tr><td>{user.name}</td><td>{user.email}</td></tr>{/snippet}
</DataTable>
```

## Stores (Svelte 4 compatible, still valid in 5)

```ts
// stores/cart.ts
import { writable, derived } from 'svelte/store';

export const cartItems = writable<CartItem[]>([]);

export const cartTotal = derived(cartItems, ($items) =>
  $items.reduce((sum, item) => sum + item.price * item.qty, 0)
);

// Custom store with encapsulated logic
function createCounter(initial = 0) {
  const { subscribe, set, update } = writable(initial);
  return {
    subscribe,
    increment: () => update(n => n + 1),
    decrement: () => update(n => n - 1),
    reset: () => set(initial),
  };
}
export const counter = createCounter();

// In Svelte 5, prefer $state in .svelte.ts files for new code
// stores/cart.svelte.ts
export function createCart() {
  let items = $state<CartItem[]>([]);
  let total = $derived(items.reduce((sum, i) => sum + i.price * i.qty, 0));
  return {
    get items() { return items; },
    get total() { return total; },
    add(item: CartItem) { items.push(item); },
    remove(id: string) { items = items.filter(i => i.id !== id); },
  };
}
```

## SvelteKit Patterns

### Route Structure
```
src/routes/
  +layout.ts          # shared data loading
  +layout.svelte      # shared UI wrapper
  +page.ts            # client/universal load
  +page.server.ts     # server-only load + form actions
  +page.svelte        # page component
  +error.svelte       # error boundary
  users/
    [id]/
      +page.server.ts # dynamic route with param
      +page.svelte
  api/
    users/
      +server.ts      # API endpoint (GET, POST, etc.)
```

### Load Functions
```ts
// +page.server.ts — runs only on server, has access to DB, secrets
import type { PageServerLoad, Actions } from './$types';

export const load: PageServerLoad = async ({ params, locals, depends }) => {
  depends('app:users'); // custom invalidation key
  const user = await db.user.findUnique({ where: { id: params.id } });
  if (!user) throw error(404, 'User not found');
  return { user };
};

// +page.ts — runs on server AND client (universal load)
import type { PageLoad } from './$types';
export const load: PageLoad = async ({ fetch, params }) => {
  const res = await fetch(`/api/users/${params.id}`); // uses SvelteKit fetch
  return { user: await res.json() };
};
```

### Form Actions
```ts
// +page.server.ts
export const actions: Actions = {
  create: async ({ request, locals }) => {
    const data = await request.formData();
    const name = data.get('name') as string;
    if (!name) return fail(400, { name, missing: true });
    await db.user.create({ data: { name } });
    throw redirect(303, '/users');
  },
  delete: async ({ request }) => {
    const data = await request.formData();
    await db.user.delete({ where: { id: data.get('id') as string } });
  },
};
```

```svelte
<!-- +page.svelte -->
<script lang="ts">
  import { enhance } from '$app/forms';
  let { data, form } = $props(); // typed from $types
</script>

<form method="POST" action="?/create" use:enhance>
  <input name="name" value={form?.name ?? ''} />
  {#if form?.missing}<p class="error">Name is required</p>{/if}
  <button>Create</button>
</form>
```

### Hooks
```ts
// src/hooks.server.ts
export const handle: Handle = async ({ event, resolve }) => {
  const session = await getSession(event.cookies);
  event.locals.user = session?.user ?? null;
  return resolve(event);
};

export const handleError: HandleServerError = async ({ error, event }) => {
  console.error(error);
  return { message: 'Internal server error' };
};
```

## Transitions & Animations

```svelte
<script>
  import { fly, fade, slide } from 'svelte/transition';
  import { flip } from 'svelte/animate';
  let visible = $state(true);
</script>

{#if visible}
  <div transition:fly={{ y: 200, duration: 300 }}>Flies in/out</div>
  <div in:fade out:slide>Different in/out transitions</div>
{/if}

{#each items as item (item.id)}
  <div animate:flip={{ duration: 300 }}>{item.name}</div>
{/each}
```

## Context API

```ts
// Set in parent
import { setContext } from 'svelte';
setContext('theme', { mode: 'dark', toggle: () => { /* ... */ } });

// Get in child (any depth)
import { getContext } from 'svelte';
const theme = getContext<{ mode: string; toggle: () => void }>('theme');
```

## SSR / SSG / SPA Modes

```ts
// +page.ts or +layout.ts
export const prerender = true;  // SSG: generate at build time
export const ssr = false;       // SPA: client-only rendering
export const csr = true;        // default: client-side hydration

// Per-route or in +layout.ts for entire subtree
// adapter-static for full SSG, adapter-node for SSR, adapter-auto for Vercel/Cloudflare
```

## Testing

```ts
import { render, screen } from '@testing-library/svelte';
import userEvent from '@testing-library/user-event';
import Counter from './Counter.svelte';

test('increments count on click', async () => {
  render(Counter, { props: { initial: 0 } });
  const button = screen.getByRole('button');
  await userEvent.click(button);
  expect(button).toHaveTextContent('1');
});
```

## Anti-Patterns

```
- BAD: using $: reactive declarations in Svelte 5 — use $derived and $effect runes
- BAD: mutating $state.raw objects — must reassign entirely
- BAD: $effect for derived state — use $derived instead
- BAD: putting side effects in $derived — use $effect
- BAD: circular $effect dependencies — will cause infinite loops
- BAD: accessing $state outside .svelte or .svelte.ts files — runes require compiler
- BAD: using on:click in Svelte 5 — use onclick attribute instead
- BAD: <slot /> in Svelte 5 — use {@render children?.()} with snippets
```
