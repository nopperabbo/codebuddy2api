# Skill: TypeScript Advanced
# Loaded on-demand when working with .ts, .js, .tsx, .jsx files

## Auto-Detect

Trigger this skill when:
- File extensions: `.ts`, `.tsx`, `.js`, `.jsx`, `.mts`, `.cts`
- Config files: `tsconfig.json`, `tsconfig.*.json`
- `package.json` contains: `typescript`, `@types/*`
- Import syntax: `import type`, generic annotations, interface declarations

---

## Decision Tree: Type vs Interface

```
Defining a shape?
├── Object shape (props, API response, config)?
│   ├── Will it be extended/merged? → interface (declaration merging)
│   ├── Used with class implements? → interface
│   └── Simple object type? → Either works (be consistent in project)
├── Union type? → type (interfaces can't do unions)
├── Mapped/conditional type? → type (interfaces can't do this)
├── Function signature? → type (cleaner syntax)
├── Tuple? → type
└── Primitive alias? → type

Rule: Pick one convention per project. If unsure, use `type` — it's more versatile.
```

## Decision Tree: Error Handling

```
Function can fail?
├── Expected failure (validation, not found)? → Return Result<T, E> type
├── Unexpected failure (network, disk)? → Throw typed error, catch at boundary
├── Async operation? → Result type OR try/catch with typed errors
├── Multiple failure modes? → Discriminated union error type
└── Library boundary? → Wrap in try/catch, convert to your error types
```

---

## Strict Mode Patterns

```typescript
// tsconfig.json — non-negotiable settings
{
  "compilerOptions": {
    "strict": true,
    "noUncheckedIndexedAccess": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "exactOptionalPropertyTypes": true,
    "noFallthroughCasesInSwitch": true,
    "forceConsistentCasingInFileNames": true,
    "verbatimModuleSyntax": true
  }
}
```

---

## Type Narrowing

```typescript
// Discriminated unions — the most powerful pattern
type ApiResponse<T> =
  | { status: 'success'; data: T; timestamp: number }
  | { status: 'error'; error: { code: string; message: string } }
  | { status: 'loading' };

function handle<T>(response: ApiResponse<T>) {
  switch (response.status) {
    case 'success': return response.data; // TS knows data exists
    case 'error': throw new AppError(response.error.code);
    case 'loading': return null;
  }
}

// Type predicates — custom narrowing
function isNonNull<T>(value: T | null | undefined): value is T {
  return value != null;
}
const results = items.map(transform).filter(isNonNull); // T[], not (T | null)[]

// Assertion functions — narrow and throw
function assertDefined<T>(value: T | undefined, msg: string): asserts value is T {
  if (value === undefined) throw new Error(msg);
}

// in operator narrowing
type Admin = { role: 'admin'; permissions: string[] };
type User = { role: 'user'; email: string };
function getAccess(person: Admin | User) {
  if ('permissions' in person) return person.permissions; // Admin
}
```

---

## Generics Patterns

```typescript
// Constrained generics
function getProperty<T, K extends keyof T>(obj: T, key: K): T[K] {
  return obj[key];
}

// Generic with default
type Pagination<T, Meta = { total: number; page: number }> = {
  items: T[];
  meta: Meta;
};

// Infer in conditional types
type UnwrapPromise<T> = T extends Promise<infer U> ? U : T;
type Awaited = UnwrapPromise<Promise<string>>; // string

// Generic factory pattern
function createRepository<T extends { id: string }>(tableName: string) {
  return {
    findById: async (id: string): Promise<T | null> => { /* ... */ },
    create: async (data: Omit<T, 'id'>): Promise<T> => { /* ... */ },
    update: async (id: string, data: Partial<T>): Promise<T> => { /* ... */ },
    delete: async (id: string): Promise<void> => { /* ... */ },
  };
}

// Builder pattern with generics
class QueryBuilder<T> {
  where<K extends keyof T>(field: K, value: T[K]): this { /* ... */ return this; }
  orderBy<K extends keyof T>(field: K, dir: 'asc' | 'desc'): this { /* ... */ return this; }
  limit(n: number): this { /* ... */ return this; }
  execute(): Promise<T[]> { /* ... */ }
}
```

---

## Utility Types & Patterns

```typescript
// Built-in utilities you should know
type Partial<T>       // All properties optional
type Required<T>      // All properties required
type Readonly<T>      // All properties readonly
type Pick<T, K>       // Subset of properties
type Omit<T, K>       // All except specified properties
type Record<K, V>     // Object with keys K and values V
type Extract<T, U>    // Members of T assignable to U
type Exclude<T, U>    // Members of T not assignable to U
type NonNullable<T>   // Exclude null and undefined
type ReturnType<T>    // Return type of function
type Parameters<T>    // Parameter types as tuple

// Custom utility: DeepPartial
type DeepPartial<T> = T extends object
  ? { [P in keyof T]?: DeepPartial<T[P]> }
  : T;

// Custom utility: Branded types (nominal typing)
type Brand<T, B> = T & { __brand: B };
type UserId = Brand<string, 'UserId'>;
type OrderId = Brand<string, 'OrderId'>;
const createUserId = (id: string): UserId => id as UserId;

// Custom utility: Strict omit (errors on invalid keys)
type StrictOmit<T, K extends keyof T> = Omit<T, K>;

// Template literal types
type EventName = `on${Capitalize<'click' | 'focus' | 'blur'>}`;
// "onClick" | "onFocus" | "onBlur"
```

---

## Result Type & Error Handling

```typescript
// Result type — explicit error handling without exceptions
type Result<T, E = Error> =
  | { ok: true; value: T }
  | { ok: false; error: E };

// Helper constructors
const Ok = <T>(value: T): Result<T, never> => ({ ok: true, value });
const Err = <E>(error: E): Result<never, E> => ({ ok: false, error });

// Usage
async function parseConfig(path: string): Result<Config, 'NOT_FOUND' | 'INVALID_JSON'> {
  const content = await readFile(path).catch(() => null);
  if (!content) return Err('NOT_FOUND');
  try {
    return Ok(JSON.parse(content));
  } catch {
    return Err('INVALID_JSON');
  }
}

// Consuming Result
const result = await parseConfig('./config.json');
if (!result.ok) {
  switch (result.error) {
    case 'NOT_FOUND': console.error('Config file missing'); break;
    case 'INVALID_JSON': console.error('Config is malformed'); break;
  }
  process.exit(1);
}
// result.value is Config here — fully narrowed
```

---

## Zod Validation

```typescript
import { z } from 'zod';

// Schema = runtime validation + static type inference
const UserSchema = z.object({
  id: z.string().uuid(),
  email: z.string().email(),
  name: z.string().min(1).max(100),
  role: z.enum(['admin', 'user', 'moderator']),
  createdAt: z.coerce.date(),
  metadata: z.record(z.unknown()).optional(),
});

type User = z.infer<typeof UserSchema>; // Static type derived from schema

// Validate at boundaries (API handlers, env vars, config files)
const EnvSchema = z.object({
  DATABASE_URL: z.string().url(),
  PORT: z.coerce.number().int().min(1).max(65535).default(3000),
  NODE_ENV: z.enum(['development', 'production', 'test']),
  API_KEY: z.string().min(32),
});
export const env = EnvSchema.parse(process.env);

// Transform + validate
const CreateUserInput = UserSchema.omit({ id: true, createdAt: true }).extend({
  password: z.string().min(8).regex(/[A-Z]/).regex(/[0-9]/),
});
```

---

## Anti-Patterns

| ❌ Don't | ✅ Do Instead |
|----------|---------------|
| `any` | `unknown` + type narrowing |
| `@ts-ignore` / `@ts-expect-error` without comment | Fix the type or add explanation |
| `as` type assertions | Type guards or discriminated unions |
| `enum` (runtime overhead, quirks) | `as const` objects or union types |
| `!` non-null assertion | Proper null checks or `assertDefined` |
| Barrel files (`index.ts` re-exports) at scale | Direct imports (better tree-shaking) |
| `Function` type | Specific signature: `(args: T) => R` |
| `Object` / `{}` type | `Record<string, unknown>` or specific shape |
| Mutable global state | Dependency injection or module-scoped |
| `eval()` or `new Function()` | Never. No exceptions. |

---

## Code Templates

### API Route Handler (type-safe)
```typescript
import { z } from 'zod';

const ParamsSchema = z.object({ id: z.string().uuid() });
const BodySchema = z.object({ name: z.string().min(1) });

export async function PUT(req: Request, { params }: { params: { id: string } }) {
  const { id } = ParamsSchema.parse(params);
  const body = BodySchema.parse(await req.json());
  const updated = await db.user.update({ where: { id }, data: body });
  return Response.json(updated);
}
```

### Exhaustive Switch
```typescript
function assertNever(x: never): never {
  throw new Error(`Unexpected value: ${x}`);
}
```

---

## Verification Checklist

Before considering TypeScript work done:
- [ ] `strict: true` in tsconfig — no exceptions
- [ ] Zero `any` types (search codebase: `grep -r ": any"`)
- [ ] All external data validated at boundaries (Zod or equivalent)
- [ ] Error cases handled explicitly (Result type or try/catch)
- [ ] No type assertions (`as`) without justification comment
- [ ] Generics used where code is duplicated across types
- [ ] Discriminated unions for state machines / API responses
- [ ] `noUncheckedIndexedAccess` enabled for array/object safety
- [ ] Exported types have JSDoc comments
- [ ] `tsc --noEmit` passes with zero errors

---

## MCP Integration

| Tool | Use For |
|------|---------|
| `context7` | Look up TypeScript compiler options, Zod API, utility types |
| `sequential-thinking` | Design complex type hierarchies and generics |
| `grep` | Find `any` types, `@ts-ignore`, type assertion patterns |
| `bash` | Run `tsc --noEmit` to verify type safety |
