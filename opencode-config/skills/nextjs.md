# Skill: Next.js
# Loaded on-demand when working with Next.js, App Router, Pages Router

## App Router File Conventions

```
app/
  layout.tsx          # Root layout (required, wraps all pages)
  page.tsx            # Home page (/)
  loading.tsx         # Instant loading UI (Suspense boundary)
  error.tsx           # Error boundary ('use client' required)
  not-found.tsx       # 404 page (triggered by notFound())
  global-error.tsx    # Root error boundary
  dashboard/
    layout.tsx        # Nested layout (persists across child navigations)
    page.tsx          # /dashboard
    @analytics/       # Parallel route (named slot)
      page.tsx
    (.)settings/      # Intercepting route (modal pattern)
      page.tsx
  api/
    users/
      route.ts        # Route handler: GET, POST, PUT, DELETE
```

## Server Components vs Client Components

```tsx
// Server Component (DEFAULT — no directive needed)
// Can: access DB, read files, use secrets, await async, zero JS bundle
async function ProductPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const product = await db.product.findUnique({ where: { id } });
  if (!product) notFound();
  return (
    <div>
      <h1>{product.name}</h1>
      <AddToCartButton productId={id} /> {/* Client component child */}
    </div>
  );
}

// Client Component — interactive, has state/effects/event handlers
'use client';
import { useState, useTransition } from 'react';

function AddToCartButton({ productId }: { productId: string }) {
  const [isPending, startTransition] = useTransition();
  return (
    <button
      disabled={isPending}
      onClick={() => startTransition(() => addToCart(productId))}
    >
      {isPending ? 'Adding...' : 'Add to Cart'}
    </button>
  );
}
```

### Boundary Rules
```
Server Component CAN import Client Component ✅
Client Component CANNOT import Server Component ❌
Client Component CAN render Server Component passed as children/props ✅

// Pattern: pass server content through client wrapper
<ClientTabs>
  <ServerTabContent />  {/* rendered on server, passed as children */}
</ClientTabs>
```

## Server Actions

```tsx
// Inline in Server Component
async function ProfilePage() {
  async function updateProfile(formData: FormData) {
    'use server';
    const name = formData.get('name') as string;
    await db.user.update({ where: { id: session.userId }, data: { name } });
    revalidatePath('/profile');
  }
  return (
    <form action={updateProfile}>
      <input name="name" />
      <button type="submit">Save</button>
    </form>
  );
}

// Separate file for reuse across components
// app/actions.ts
'use server';
import { revalidatePath, revalidateTag } from 'next/cache';

export async function createPost(formData: FormData) {
  const title = formData.get('title') as string;
  await db.post.create({ data: { title } });
  revalidateTag('posts'); // on-demand revalidation
  redirect('/posts');
}

// Client component using server action
'use client';
import { useActionState } from 'react';
import { createPost } from './actions';

function PostForm() {
  const [state, formAction, isPending] = useActionState(createPost, null);
  return (
    <form action={formAction}>
      <input name="title" />
      <button disabled={isPending}>Create</button>
    </form>
  );
}
```

## Data Fetching

```tsx
// Server Component fetch with caching
async function Posts() {
  // Cached by default (equivalent to getStaticProps)
  const posts = await fetch('https://api.example.com/posts', {
    next: { revalidate: 3600 }, // ISR: revalidate every hour
  }).then(r => r.json());

  // No cache (equivalent to getServerSideProps)
  const live = await fetch('https://api.example.com/live', {
    cache: 'no-store',
  }).then(r => r.json());

  return <PostList posts={posts} />;
}

// generateStaticParams — static generation for dynamic routes
// app/posts/[slug]/page.tsx
export async function generateStaticParams() {
  const posts = await db.post.findMany({ select: { slug: true } });
  return posts.map((post) => ({ slug: post.slug }));
}

// Parallel data fetching (avoid waterfalls)
async function Dashboard() {
  const [users, analytics, revenue] = await Promise.all([
    getUsers(),
    getAnalytics(),
    getRevenue(),
  ]);
  return <DashboardView users={users} analytics={analytics} revenue={revenue} />;
}
```

## Route Handlers

```ts
// app/api/users/route.ts
import { NextRequest, NextResponse } from 'next/server';

export async function GET(request: NextRequest) {
  const searchParams = request.nextUrl.searchParams;
  const page = parseInt(searchParams.get('page') ?? '1');
  const users = await db.user.findMany({ skip: (page - 1) * 20, take: 20 });
  return NextResponse.json(users);
}

export async function POST(request: NextRequest) {
  const body = await request.json();
  const user = await db.user.create({ data: body });
  return NextResponse.json(user, { status: 201 });
}
```

## Middleware

```ts
// middleware.ts (root level — runs on EVERY request)
import { NextResponse } from 'next/server';
import type { NextRequest } from 'next/server';

export function middleware(request: NextRequest) {
  const token = request.cookies.get('session')?.value;
  if (!token && request.nextUrl.pathname.startsWith('/dashboard')) {
    return NextResponse.redirect(new URL('/login', request.url));
  }
  // Add headers, rewrite, etc.
  const response = NextResponse.next();
  response.headers.set('x-request-id', crypto.randomUUID());
  return response;
}

export const config = {
  matcher: ['/dashboard/:path*', '/api/:path*'], // limit scope
};
```

## Parallel & Intercepting Routes

```tsx
// app/layout.tsx — parallel routes via named slots
export default function Layout({
  children,
  analytics,  // @analytics/page.tsx
  modal,      // @modal/(.)photo/[id]/page.tsx
}: {
  children: React.ReactNode;
  analytics: React.ReactNode;
  modal: React.ReactNode;
}) {
  return (
    <>
      {children}
      {analytics}
      {modal}
    </>
  );
}

// Intercepting route: (.) same level, (..) one level up, (...) root
// Used for modal patterns — clicking link shows modal, direct URL shows full page
```

## Metadata API

```tsx
// Static metadata
export const metadata: Metadata = {
  title: 'My App',
  description: 'Built with Next.js',
  openGraph: { title: 'My App', images: ['/og.png'] },
};

// Dynamic metadata
export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { id } = await params;
  const product = await getProduct(id);
  return {
    title: product.name,
    description: product.description,
    openGraph: { images: [product.image] },
  };
}
```

## Image & Font Optimization

```tsx
import Image from 'next/image';
import { Inter } from 'next/font/google';

const inter = Inter({ subsets: ['latin'], display: 'swap' });

// Image: automatic optimization, lazy loading, responsive
<Image
  src="/hero.jpg"
  alt="Hero"
  width={1200}
  height={600}
  priority          // above-the-fold: disable lazy loading
  placeholder="blur" // requires static import or blurDataURL
/>

// Remote images: configure in next.config.ts
// images: { remotePatterns: [{ protocol: 'https', hostname: 'cdn.example.com' }] }
```

## Rendering Strategies

```ts
// SSG (default): pages built at build time, cached at CDN
// ISR: SSG + revalidation — next: { revalidate: seconds }
// SSR: cache: 'no-store' or export const dynamic = 'force-dynamic'
// CSR: 'use client' + useEffect/SWR/TanStack Query

// Per-route config
export const dynamic = 'force-dynamic';     // always SSR
export const revalidate = 3600;             // ISR interval
export const fetchCache = 'default-cache';  // caching strategy
```

## Environment Variables

```
# .env.local (gitignored, local dev)
DATABASE_URL=postgres://...          # server-only (no prefix)
NEXT_PUBLIC_API_URL=https://api...   # exposed to client (NEXT_PUBLIC_ prefix)

# Access
process.env.DATABASE_URL             // server only
process.env.NEXT_PUBLIC_API_URL      // both server and client
```

## Anti-Patterns

```
- BAD: 'use client' on every component — push client boundary as low as possible
- BAD: fetching data in client useEffect when server fetch works — use Server Components
- BAD: importing server-only code in client components — use 'server-only' package
- BAD: large client bundles — audit with @next/bundle-analyzer
- BAD: not using loading.tsx — users see blank page during navigation
- BAD: fetch in layout.tsx without deduplication awareness — Next.js auto-dedupes fetch
- BAD: using Pages Router patterns (getServerSideProps) in App Router
- BAD: putting secrets in NEXT_PUBLIC_ variables — they're exposed to the browser
- BAD: not handling params as Promise in Next.js 15 — params are now async
```
