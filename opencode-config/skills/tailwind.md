# Skill: Tailwind CSS
# Loaded on-demand when working with Tailwind CSS, utility-first CSS

## Utility-First Workflow

```html
<!-- Utility-first: compose styles directly in markup -->
<button class="bg-blue-600 hover:bg-blue-700 text-white font-semibold
               py-2 px-4 rounded-lg shadow-md transition-colors duration-200
               focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2
               disabled:opacity-50 disabled:cursor-not-allowed">
  Submit
</button>

<!-- Prefer component abstraction over @apply -->
<!-- Good: React/Vue component wrapping utility classes -->
<!-- Avoid: .btn { @apply bg-blue-600 text-white py-2 px-4 rounded-lg; } -->
```

## Responsive Design

```html
<!-- Mobile-first breakpoints: sm(640) md(768) lg(1024) xl(1280) 2xl(1536) -->
<div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
  <div class="p-4">Card</div>
</div>

<!-- Stack on mobile, row on desktop -->
<div class="flex flex-col md:flex-row md:items-center gap-4">
  <img class="w-full md:w-48 h-48 object-cover rounded-lg" src="..." alt="..." />
  <div class="flex-1">
    <h2 class="text-lg md:text-2xl font-bold">Title</h2>
    <p class="text-sm md:text-base text-gray-600">Description</p>
  </div>
</div>

<!-- Container with responsive padding -->
<div class="container mx-auto px-4 sm:px-6 lg:px-8">...</div>
```

## Dark Mode

```html
<!-- Class strategy (recommended — user-controlled) -->
<!-- tailwind.config.js: darkMode: 'class' -->
<div class="bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-100">
  <p class="text-gray-600 dark:text-gray-400">Adapts to dark mode</p>
  <div class="border border-gray-200 dark:border-gray-700 rounded-lg p-4">
    Card content
  </div>
</div>

<!-- Toggle dark mode -->
<script>
  document.documentElement.classList.toggle('dark');
</script>
```

## Custom Theme Configuration

```js
// tailwind.config.js
/** @type {import('tailwindcss').Config} */
export default {
  content: ['./src/**/*.{js,ts,jsx,tsx,html,vue,svelte}'],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        brand: {
          50:  '#eff6ff',
          500: '#3b82f6',
          600: '#2563eb',
          900: '#1e3a5f',
        },
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'monospace'],
      },
      spacing: {
        '18': '4.5rem',
        '88': '22rem',
      },
      animation: {
        'fade-in': 'fadeIn 0.3s ease-in-out',
        'slide-up': 'slideUp 0.3s ease-out',
      },
      keyframes: {
        fadeIn: { '0%': { opacity: '0' }, '100%': { opacity: '1' } },
        slideUp: { '0%': { transform: 'translateY(10px)', opacity: '0' },
                   '100%': { transform: 'translateY(0)', opacity: '1' } },
      },
    },
  },
  plugins: [
    require('@tailwindcss/forms'),
    require('@tailwindcss/typography'),
  ],
};
```

## Arbitrary Values & Modifiers

```html
<!-- Arbitrary values — escape hatch for one-off styles -->
<div class="top-[117px] w-[calc(100%-2rem)] bg-[#1a1a2e] text-[13px]">
  Custom values
</div>

<!-- Important modifier — override specificity -->
<div class="!mt-0">Forces margin-top: 0</div>

<!-- Group modifier — style children based on parent state -->
<div class="group cursor-pointer">
  <h3 class="group-hover:text-blue-600 transition-colors">Hover parent</h3>
  <p class="group-hover:text-gray-900">Child reacts</p>
</div>

<!-- Peer modifier — style based on sibling state -->
<input class="peer" type="checkbox" />
<label class="peer-checked:text-blue-600">Checked!</label>

<!-- Data attributes -->
<div data-active="true" class="data-[active=true]:bg-blue-100">Active</div>
```

## Common Layout Patterns

```html
<!-- Centering (multiple approaches) -->
<div class="flex items-center justify-center min-h-screen">Centered</div>
<div class="grid place-items-center min-h-screen">Also centered</div>

<!-- Sticky header + scrollable content -->
<div class="h-screen flex flex-col">
  <header class="sticky top-0 z-10 bg-white border-b px-4 py-3">Nav</header>
  <main class="flex-1 overflow-y-auto p-6">Scrollable content</main>
</div>

<!-- Card component -->
<div class="bg-white dark:bg-gray-800 rounded-xl shadow-lg overflow-hidden
            border border-gray-100 dark:border-gray-700
            hover:shadow-xl transition-shadow duration-300">
  <img class="w-full h-48 object-cover" src="..." alt="..." />
  <div class="p-6">
    <h3 class="text-lg font-semibold text-gray-900 dark:text-white">Title</h3>
    <p class="mt-2 text-gray-600 dark:text-gray-400 line-clamp-2">Description...</p>
    <div class="mt-4 flex items-center justify-between">
      <span class="text-sm text-gray-500">3 min read</span>
      <button class="text-blue-600 hover:text-blue-800 text-sm font-medium">
        Read more &rarr;
      </button>
    </div>
  </div>
</div>

<!-- Responsive grid with auto-fill -->
<div class="grid grid-cols-[repeat(auto-fill,minmax(280px,1fr))] gap-6">
  <!-- Cards auto-wrap based on available space -->
</div>
```

## Animation Utilities

```html
<!-- Built-in animations -->
<div class="animate-spin h-5 w-5 border-2 border-blue-600 border-t-transparent rounded-full"></div>
<div class="animate-pulse bg-gray-200 h-4 rounded w-3/4"></div>
<div class="animate-bounce">↓</div>

<!-- Transition utilities -->
<button class="transform hover:scale-105 active:scale-95
               transition-all duration-200 ease-in-out">
  Click me
</button>
```

## Tailwind with React/Vue/Svelte

```tsx
// React — extract components, not @apply classes
function Badge({ children, variant = 'default' }: BadgeProps) {
  const variants = {
    default: 'bg-gray-100 text-gray-800',
    success: 'bg-green-100 text-green-800',
    danger:  'bg-red-100 text-red-800',
  };

  return (
    <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full
                      text-xs font-medium ${variants[variant]}`}>
      {children}
    </span>
  );
}

// Use clsx or tailwind-merge for conditional classes
import { twMerge } from 'tailwind-merge';
import clsx from 'clsx';

function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

<div className={cn('p-4 rounded', isActive && 'bg-blue-100', className)} />
```

## Performance

```js
// content config — ensures unused classes are purged
content: [
  './src/**/*.{js,ts,jsx,tsx}',
  './index.html',
  // Include component libraries that use Tailwind classes
  './node_modules/@mylib/ui/dist/**/*.js',
],

// JIT mode is default since Tailwind v3 — generates only used classes
// Result: tiny CSS bundles in production
```

## Best Practices

- **Component abstraction over `@apply`** — extract React/Vue/Svelte components, not CSS classes.
- **Use `tailwind-merge`** to safely merge/override conflicting classes from props.
- **Mobile-first** — write base styles for mobile, add `sm:`, `md:`, `lg:` for larger screens.
- **Consistent spacing** — stick to the default scale (4, 6, 8, 12, 16...) for visual rhythm.
- **Use semantic color names** in config (`brand`, `surface`, `muted`) not raw colors in markup.
- **Avoid deeply nested arbitrary values** — if you need many, extend the theme instead.
- **Install `@tailwindcss/typography`** for prose content (`class="prose"` on article bodies).
- **Use `prettier-plugin-tailwindcss`** to auto-sort class order consistently.
