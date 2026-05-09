# Skill: Vue.js
# Loaded on-demand when working with .vue files, Vue 3, Nuxt

## Composition API Fundamentals

### Reactivity Primitives
```vue
<script setup lang="ts">
import { ref, reactive, computed, watch, watchEffect, toRefs } from 'vue';

// ref: single values (primitives or objects), access via .value in script
const count = ref(0);
count.value++; // .value required in <script>, auto-unwrapped in <template>

// reactive: objects only, deep reactive, no .value needed
const state = reactive({ name: 'Alice', items: [] as string[] });
state.name = 'Bob'; // direct mutation

// computed: cached derived state, auto-tracks dependencies
const doubled = computed(() => count.value * 2);

// watch: explicit source, access old/new values
watch(count, (newVal, oldVal) => {
  console.log(`Changed from ${oldVal} to ${newVal}`);
}, { immediate: true }); // fire on mount

// watchEffect: auto-tracks all reactive deps used inside
watchEffect(() => {
  document.title = `Count: ${count.value}`;
});

// watch multiple sources
watch([count, () => state.name], ([newCount, newName]) => { /* ... */ });
</script>
```

### Destructuring Pitfall
```ts
// BAD: loses reactivity
const { name, items } = reactive({ name: 'Alice', items: [] });

// GOOD: use toRefs to maintain reactivity
const state = reactive({ name: 'Alice', items: [] });
const { name, items } = toRefs(state);
```

## Composables (Custom Hooks)

```ts
// composables/useFetch.ts
export function useFetch<T>(url: MaybeRefOrGetter<string>) {
  const data = ref<T | null>(null);
  const error = ref<Error | null>(null);
  const loading = ref(false);

  async function execute() {
    loading.value = true;
    error.value = null;
    try {
      const response = await fetch(toValue(url));
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      data.value = await response.json();
    } catch (e) {
      error.value = e as Error;
    } finally {
      loading.value = false;
    }
  }

  watchEffect(() => { toValue(url); execute(); }); // re-fetch on URL change
  return { data, error, loading, execute };
}

// Usage in component
const { data: users, loading } = useFetch<User[]>('/api/users');
```

## Component Patterns

### v-model with Components
```vue
<!-- Parent -->
<CustomInput v-model="searchQuery" v-model:placeholder="hint" />

<!-- CustomInput.vue -->
<script setup lang="ts">
const model = defineModel<string>(); // Vue 3.4+ — replaces modelValue/emit
const placeholder = defineModel<string>('placeholder');
</script>
<template>
  <input v-model="model" :placeholder="placeholder" />
</template>
```

### Slots (Default, Named, Scoped)
```vue
<!-- DataTable.vue -->
<template>
  <table>
    <thead><slot name="header" /></thead>
    <tbody>
      <tr v-for="row in data" :key="row.id">
        <slot name="row" :row="row" :index="row.id" />  <!-- scoped slot -->
      </tr>
    </tbody>
    <tfoot><slot name="footer">Default footer</slot></tfoot>
  </table>
</template>

<!-- Usage -->
<DataTable :data="users">
  <template #header><th>Name</th><th>Email</th></template>
  <template #row="{ row }"><td>{{ row.name }}</td><td>{{ row.email }}</td></template>
</DataTable>
```

### Provide / Inject (Dependency Injection)
```ts
// Parent
const theme = ref<'light' | 'dark'>('light');
provide('theme', theme); // provide reactive ref

// Deep child
const theme = inject<Ref<'light' | 'dark'>>('theme', ref('light')); // with default
```

### Teleport & Suspense
```vue
<Teleport to="body">
  <Modal v-if="showModal" @close="showModal = false" />
</Teleport>

<Suspense>
  <template #default><AsyncComponent /></template>
  <template #fallback><LoadingSpinner /></template>
</Suspense>
```

## Pinia State Management

```ts
// stores/useCartStore.ts
export const useCartStore = defineStore('cart', () => {
  const items = ref<CartItem[]>([]);
  const total = computed(() => items.value.reduce((sum, i) => sum + i.price * i.qty, 0));

  function addItem(product: Product) {
    const existing = items.value.find(i => i.id === product.id);
    if (existing) existing.qty++;
    else items.value.push({ ...product, qty: 1 });
  }

  function removeItem(id: string) {
    items.value = items.value.filter(i => i.id !== id);
  }

  return { items, total, addItem, removeItem };
});

// Component usage
const cart = useCartStore();
cart.addItem(product);
// Destructure with storeToRefs to keep reactivity
const { items, total } = storeToRefs(cart);
```

## Vue Router Patterns

```ts
// Lazy-loaded routes
const routes = [
  { path: '/', component: () => import('./views/Home.vue') },
  {
    path: '/dashboard',
    component: () => import('./views/Dashboard.vue'),
    meta: { requiresAuth: true },
    children: [
      { path: 'settings', component: () => import('./views/Settings.vue') },
    ],
  },
];

// Navigation guard
router.beforeEach((to) => {
  if (to.meta.requiresAuth && !useAuthStore().isAuthenticated) {
    return { path: '/login', query: { redirect: to.fullPath } };
  }
});
```

## Performance Optimization

```vue
<script setup>
import { shallowRef, triggerRef } from 'vue';

// shallowRef: only track .value replacement, not deep mutations
const largeList = shallowRef<Item[]>([]);
largeList.value = [...largeList.value, newItem]; // triggers update
// largeList.value.push(newItem); triggerRef(largeList); // manual trigger
</script>

<template>
  <!-- v-once: render once, never update -->
  <footer v-once>{{ staticContent }}</footer>

  <!-- v-memo: skip re-render unless deps change -->
  <div v-for="item in list" :key="item.id" v-memo="[item.selected]">
    <HeavyComponent :item="item" />
  </div>
</template>
```

## Nuxt 3 Patterns

```vue
<!-- pages/users/[id].vue -->
<script setup lang="ts">
// Auto-imported composables — no import needed
const route = useRoute();

// useFetch: SSR-friendly, auto-deduped, cached
const { data: user, pending, error } = await useFetch<User>(`/api/users/${route.params.id}`);

// useAsyncData: when you need custom fetching logic
const { data } = await useAsyncData('stats', () => $fetch('/api/stats'));
</script>

<!-- server/api/users/[id].get.ts — server route -->
<script lang="ts">
export default defineEventHandler(async (event) => {
  const id = getRouterParam(event, 'id');
  return await db.user.findUnique({ where: { id } });
});
</script>
```

## Testing

```ts
import { mount } from '@vue/test-utils';
import { describe, it, expect, vi } from 'vitest';
import Counter from './Counter.vue';

describe('Counter', () => {
  it('increments on click', async () => {
    const wrapper = mount(Counter, { props: { initial: 0 } });
    await wrapper.find('button').trigger('click');
    expect(wrapper.text()).toContain('1');
  });

  it('emits update event', async () => {
    const wrapper = mount(Counter);
    await wrapper.find('button').trigger('click');
    expect(wrapper.emitted('update')).toHaveLength(1);
    expect(wrapper.emitted('update')![0]).toEqual([1]);
  });
});
```

## Anti-Patterns

```ts
// BAD: mutating props directly
props.items.push(newItem);
// GOOD: emit event to parent
emit('add-item', newItem);

// BAD: Options API mixins (composition conflicts, unclear source)
// GOOD: composables — explicit, typed, traceable

// BAD: reactive() for primitives — use ref()
// BAD: forgetting .value in script — causes silent bugs
// BAD: watch without cleanup for async operations
// BAD: using Vuex in new Vue 3 projects — use Pinia
// BAD: v-if + v-for on same element — v-if takes precedence in Vue 3, use <template> wrapper
```
