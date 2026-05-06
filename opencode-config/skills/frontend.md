# Skill: UI/UX & Frontend
# Loaded on-demand when task involves accessibility, responsive design, state management, component patterns, performance, or i18n

---

## 6. UI/UX & Frontend

### 6.1 Accessibility (WCAG 2.1 AA)

**Non-negotiable requirements:**
- All images have `alt` text (decorative images: `alt=""`)
- All form inputs have associated `<label>` elements
- Color is never the only way to convey information
- Minimum contrast ratio: 4.5:1 for normal text, 3:1 for large text
- All interactive elements are keyboard-accessible (Tab, Enter, Escape)
- Focus indicators are visible — never `outline: none` without replacement
- Page has proper heading hierarchy (h1 -> h2 -> h3, no skipping)
- ARIA attributes used correctly — prefer semantic HTML over ARIA
- Screen reader announcements for dynamic content (`aria-live`)
- Skip navigation link for keyboard users
- Reduced motion support: `prefers-reduced-motion` media query

### 6.2 Responsive Design

- **Mobile-first** — design for small screens, enhance for larger
- Use relative units (`rem`, `em`, `%`, `vw/vh`) over fixed pixels
- Test at breakpoints: 320px, 768px, 1024px, 1440px
- Touch targets minimum 44x44px
- No horizontal scrolling on any viewport width
- Images are responsive: `max-width: 100%; height: auto;`
- Use `<picture>` with `srcset` for art direction and resolution switching
- Container queries for component-level responsiveness

### 6.3 State Management

**Frontend state categories:**

| Type | Where | Examples |
|------|-------|---------|
| **Server state** | React Query / SWR / TanStack Query | API data, user profile |
| **UI state** | Local component state | Modal open, dropdown expanded |
| **Form state** | React Hook Form / Formik | Input values, validation |
| **URL state** | Router / search params | Filters, pagination, tabs |
| **Global app state** | Zustand / Redux / signals | Theme, auth, feature flags |

**Rules:**
- Don't put server data in global state — use a data-fetching library
- Derive state instead of syncing — compute from source of truth
- Colocate state — keep it as close to where it's used as possible
- URL is state — shareable, bookmarkable, back-button friendly

### 6.4 Component Patterns

- **Single Responsibility** — one component, one purpose
- **Props down, events up** — unidirectional data flow
- **Composition over inheritance** — use slots/children, not deep hierarchies
- **Controlled components** for forms — state lives in the parent
- **Loading, error, empty states** — every data-fetching component handles all three
- **Skeleton screens** over spinners for perceived performance
- **Optimistic updates** — update UI immediately, rollback on failure
- **Virtualization** for long lists (>100 items) — react-virtual, tanstack-virtual

### 6.5 Performance (Core Web Vitals)

| Metric | Target | How |
|--------|--------|-----|
| **LCP** (Largest Contentful Paint) | < 2.5s | Optimize images, preload critical resources, SSR |
| **INP** (Interaction to Next Paint) | < 200ms | Minimize main thread work, use `startTransition` |
| **CLS** (Cumulative Layout Shift) | < 0.1 | Set dimensions on images/embeds, avoid dynamic injection |

**Advanced optimizations:**
- Code splitting: route-based + component-based lazy loading
- Bundle size budget: < 200KB initial JS (gzipped)
- Tree shaking: use ESM imports, avoid barrel files
- Image optimization: WebP/AVIF, responsive sizes, lazy loading
- Font optimization: `font-display: swap`, subset, preload
- Prefetch/preload: anticipate next navigation
- Service Worker: offline support, cache strategies (stale-while-revalidate)

### 6.6 Internationalization (i18n)

- **Externalize all strings** — never hardcode user-facing text
- **ICU MessageFormat** for pluralization and gender: `{count, plural, one {# item} other {# items}}`
- **RTL support** — use logical properties (`margin-inline-start` not `margin-left`)
- **Date/time** — always use `Intl.DateTimeFormat` with user's locale and timezone
- **Numbers/currency** — `Intl.NumberFormat` with locale-aware formatting
- **Don't concatenate translated strings** — word order varies by language
- **Pseudo-localization** for testing — catches hardcoded strings and layout issues
