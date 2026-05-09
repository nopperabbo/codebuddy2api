# Skill: Monorepo Management
# Loaded on-demand when task involves Turborepo, Nx, pnpm workspaces, dependency graphs, or CI optimization

## Auto-Detect

Trigger this skill when:
- Task mentions: monorepo, workspace, turborepo, nx, pnpm workspaces, lerna
- Files: `turbo.json`, `nx.json`, `pnpm-workspace.yaml`, `lerna.json`
- Patterns: shared packages, dependency graph, affected builds, task caching
- Root `package.json` contains: `workspaces` field or `turbo`/`nx` dependency

---

## Decision Tree: Monorepo Tool

```
What do you need?
+-- Simple task orchestration + caching?
|   +-- Turborepo (minimal config, fast, works with any package manager)
+-- Full-featured with generators + plugins?
|   +-- Nx (project graph, code generation, module boundaries)
+-- Just workspace linking (no orchestration)?
|   +-- pnpm workspaces / npm workspaces / yarn workspaces
+-- Publishing packages to npm?
|   +-- Changesets (versioning + changelogs + publish)
+-- Legacy, migrating away?
|   +-- Lerna (use Nx-powered Lerna for modern features)

Package manager for monorepos:
+-- Best dependency management? -> pnpm (strict, fast, disk-efficient)
+-- Need broad ecosystem compat? -> npm/yarn
+-- Bun ecosystem? -> Bun workspaces (fast but less mature)
```

---

## Repository Structure

```
my-monorepo/
+-- apps/
|   +-- web/                    # Next.js frontend
|   |   +-- package.json        # name: "@acme/web"
|   |   +-- tsconfig.json       # extends shared config
|   +-- api/                    # Express backend
|   |   +-- package.json        # name: "@acme/api"
|   +-- mobile/                 # React Native app
|       +-- package.json
+-- packages/
|   +-- ui/                     # Shared component library
|   |   +-- package.json        # name: "@acme/ui"
|   |   +-- src/
|   +-- config-typescript/      # Shared tsconfig
|   |   +-- package.json        # name: "@acme/tsconfig"
|   |   +-- base.json
|   +-- config-eslint/          # Shared ESLint config
|   |   +-- package.json
|   +-- database/               # Prisma schema + client
|   |   +-- package.json        # name: "@acme/database"
|   +-- shared/                 # Shared utilities/types
|       +-- package.json        # name: "@acme/shared"
+-- tooling/
|   +-- scripts/                # Build/deploy scripts
+-- turbo.json                  # Task pipeline definition
+-- pnpm-workspace.yaml         # Workspace definition
+-- package.json                # Root (devDependencies only)
+-- .github/workflows/ci.yml
```

---

## Turborepo Configuration

```jsonc
// turbo.json
{
  "$schema": "https://turbo.build/schema.json",
  "globalDependencies": ["**/.env.*local"],
  "globalEnv": ["NODE_ENV", "CI"],
  "tasks": {
    "build": {
      "dependsOn": ["^build"],  // Build dependencies first (topological)
      "outputs": ["dist/**", ".next/**", "!.next/cache/**"],
      "env": ["DATABASE_URL", "NEXT_PUBLIC_*"]
    },
    "test": {
      "dependsOn": ["^build"],
      "outputs": ["coverage/**"],
      "env": ["CI"]
    },
    "lint": {
      "dependsOn": ["^build"],  // Need built types for type-aware linting
      "outputs": []
    },
    "typecheck": {
      "dependsOn": ["^build"],
      "outputs": []
    },
    "dev": {
      "cache": false,           // Never cache dev server
      "persistent": true        // Long-running process
    },
    "db:generate": {
      "cache": false
    },
    "deploy": {
      "dependsOn": ["build", "test", "lint"],
      "outputs": [],
      "cache": false
    }
  }
}
```

```yaml
# pnpm-workspace.yaml
packages:
  - "apps/*"
  - "packages/*"
  - "tooling/*"
```

```jsonc
// Root package.json
{
  "name": "acme-monorepo",
  "private": true,
  "scripts": {
    "build": "turbo run build",
    "dev": "turbo run dev",
    "test": "turbo run test",
    "lint": "turbo run lint",
    "typecheck": "turbo run typecheck",
    "clean": "turbo run clean && rm -rf node_modules",
    "format": "prettier --write \"**/*.{ts,tsx,md}\""
  },
  "devDependencies": {
    "turbo": "^2.0.0",
    "prettier": "^3.0.0"
  },
  "packageManager": "pnpm@9.0.0"
}
```

---

## Dependency Management

```jsonc
// packages/ui/package.json
{
  "name": "@acme/ui",
  "version": "0.0.0",
  "private": true,
  "exports": {
    ".": "./src/index.ts",
    "./button": "./src/button.tsx",
    "./card": "./src/card.tsx"
  },
  "scripts": {
    "build": "tsup src/index.ts --format esm,cjs --dts",
    "dev": "tsup src/index.ts --format esm,cjs --dts --watch",
    "lint": "eslint src/",
    "typecheck": "tsc --noEmit"
  },
  "dependencies": {
    "react": "^18.0.0"
  },
  "devDependencies": {
    "@acme/tsconfig": "workspace:*",
    "tsup": "^8.0.0",
    "typescript": "^5.0.0"
  }
}

// apps/web/package.json — consuming internal package
{
  "name": "@acme/web",
  "dependencies": {
    "@acme/ui": "workspace:*",
    "@acme/shared": "workspace:*",
    "@acme/database": "workspace:*"
  }
}
```

### Internal Package Strategies

```
Strategy 1: Just-in-Time Transpilation (recommended for apps)
- No build step for internal packages
- Consumer (Next.js/Vite) transpiles on import
- Configure: next.config.js transpilePackages: ['@acme/ui']
- Fastest DX, instant changes

Strategy 2: Pre-built packages (for publishable libraries)
- Build with tsup/unbuild
- Publish to npm or private registry
- Use when: external consumers, need CJS+ESM, complex build

Strategy 3: TypeScript project references
- tsc --build with composite projects
- Incremental compilation
- Use when: large codebase, need fast type checking
```

---

## Affected Builds (CI Optimization)

```yaml
# .github/workflows/ci.yml
name: CI
on:
  pull_request:
    branches: [main]

jobs:
  detect-changes:
    runs-on: ubuntu-latest
    outputs:
      packages: ${{ steps.filter.outputs.changes }}
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0  # Need full history for comparison

      - name: Detect affected packages
        id: filter
        uses: dorny/paths-filter@v3
        with:
          filters: |
            web:
              - 'apps/web/**'
              - 'packages/ui/**'
              - 'packages/shared/**'
            api:
              - 'apps/api/**'
              - 'packages/database/**'
              - 'packages/shared/**'
            packages:
              - 'packages/**'

  build:
    needs: detect-changes
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: pnpm/action-setup@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 20
          cache: 'pnpm'

      - run: pnpm install --frozen-lockfile

      # Turborepo remote caching
      - name: Build affected
        run: pnpm turbo run build test lint --filter="...[origin/main]"
        env:
          TURBO_TOKEN: ${{ secrets.TURBO_TOKEN }}
          TURBO_TEAM: ${{ vars.TURBO_TEAM }}

  # Only deploy if relevant app changed
  deploy-web:
    needs: [detect-changes, build]
    if: needs.detect-changes.outputs.packages == 'web' || contains(needs.detect-changes.outputs.packages, 'web')
    runs-on: ubuntu-latest
    steps:
      - run: echo "Deploy web app"
```

### Turborepo Filter Syntax

```bash
# Build only packages affected since main
turbo run build --filter="...[origin/main]"

# Build specific package and its dependencies
turbo run build --filter="@acme/web..."

# Build specific package and its dependents
turbo run build --filter="...@acme/ui"

# Build everything except one package
turbo run build --filter="!@acme/mobile"

# Build only packages in apps/ directory
turbo run build --filter="./apps/*"
```

---

## Versioning with Changesets

```bash
# Install
pnpm add -Dw @changesets/cli @changesets/changelog-github

# Initialize
pnpm changeset init
```

```jsonc
// .changeset/config.json
{
  "$schema": "https://unpkg.com/@changesets/config@3.0.0/schema.json",
  "changelog": ["@changesets/changelog-github", { "repo": "acme/monorepo" }],
  "commit": false,
  "fixed": [],
  "linked": [["@acme/ui", "@acme/shared"]],  // Version together
  "access": "restricted",
  "baseBranch": "main",
  "updateInternalDependencies": "patch",
  "ignore": ["@acme/web", "@acme/api"]  // Don't version apps
}
```

```bash
# Developer workflow
pnpm changeset              # Create a changeset (interactive)
pnpm changeset version      # Bump versions + update changelogs
pnpm changeset publish      # Publish to npm
```

---

## Task Caching

```typescript
// How Turborepo caching works:
// 1. Hash inputs: source files + env vars + dependencies
// 2. Check cache (local ~/.turbo/cache or remote)
// 3. If hit: restore outputs from cache (instant)
// 4. If miss: run task, store outputs in cache

// Debugging cache misses
// turbo run build --dry=json  (shows what would run)
// turbo run build --summarize (shows cache hit/miss reasons)

// Remote caching setup (Vercel)
// turbo login
// turbo link

// Self-hosted remote cache (Docker)
// docker run -p 3000:3000 ducktors/turborepo-remote-cache
```

---

## Shared Configuration

```typescript
// packages/config-typescript/base.json
{
  "$schema": "https://json.schemastore.org/tsconfig",
  "compilerOptions": {
    "strict": true,
    "esModuleInterop": true,
    "skipLibCheck": true,
    "forceConsistentCasingInFileNames": true,
    "resolveJsonModule": true,
    "isolatedModules": true,
    "moduleDetection": "force",
    "declaration": true,
    "declarationMap": true,
    "sourceMap": true
  }
}

// packages/config-typescript/nextjs.json
{
  "extends": "./base.json",
  "compilerOptions": {
    "target": "ES2017",
    "lib": ["dom", "dom.iterable", "esnext"],
    "module": "esnext",
    "moduleResolution": "bundler",
    "jsx": "preserve",
    "noEmit": true,
    "plugins": [{ "name": "next" }]
  }
}

// apps/web/tsconfig.json
{
  "extends": "@acme/tsconfig/nextjs.json",
  "compilerOptions": {
    "paths": {
      "@/*": ["./src/*"]
    }
  },
  "include": ["next-env.d.ts", "**/*.ts", "**/*.tsx"],
  "exclude": ["node_modules"]
}
```

---

## Anti-Patterns

| Anti-Pattern | Problem | Solution |
|---|---|---|
| Everything in one package.json | No isolation, version conflicts | Proper workspace packages with clear boundaries |
| Circular dependencies | Build failures, infinite loops | Strict dependency direction (apps -> packages) |
| No task caching | CI takes 30+ minutes | Turborepo/Nx with remote caching |
| Building everything on every PR | Wasted CI time and money | Affected/filtered builds based on changes |
| Shared node_modules hoisting issues | Phantom dependencies | pnpm strict mode (no hoisting) |
| No internal package boundaries | Spaghetti imports across packages | Module boundary rules (Nx) or lint rules |
| Publishing internal packages to npm | Unnecessary complexity | Use workspace:* protocol for internal deps |
| Monolithic CI pipeline | One failure blocks everything | Parallel jobs per package/app |
