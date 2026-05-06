# Skill: Developer Tooling
# Loaded on-demand when task involves LSP, linting/formatting, project structure, or code generation

---

## 8.1 LSP Integration

When working with code, be aware of LSP capabilities:
- **Diagnostics** — respect compiler/linter errors shown by the language server
- **Go to definition** — use it to understand code before modifying
- **Find references** — check all usages before renaming or removing
- **Code actions** — prefer LSP-suggested fixes when available
- **Formatting** — defer to the project's configured formatter
- **Rename symbol** — use LSP rename, not find-and-replace
- **Inlay hints** — type information without explicit annotations
- **Semantic highlighting** — understand token types from LSP

---

## 8.2 Linting & Formatting

- **Format on save** — never commit unformatted code
- **Lint rules are law** — fix warnings, don't disable rules without justification
- **Pre-commit hooks** — lint-staged + husky for automatic enforcement

**Recommended toolchains:**
| Language | Formatter | Linter | Type Checker |
|----------|-----------|--------|-------------|
| TypeScript | Prettier / Biome | ESLint / Biome | tsc --noEmit |
| Python | Black / Ruff | Ruff | mypy / pyright |
| Rust | rustfmt | clippy | cargo check |
| Go | gofmt / goimports | golangci-lint | go vet |
| C# | dotnet format | Roslyn analyzers | dotnet build |
| Java | google-java-format | SpotBugs / PMD | javac |
| Kotlin | ktlint | detekt | kotlinc |
| Swift | swift-format | SwiftLint | swiftc |

---

## 8.3 Project Structure

- **Flat over nested** — avoid deep directory hierarchies (max 3-4 levels)
- **Colocate related files** — tests next to source, styles next to components
- **Consistent naming** — pick a convention and stick to it
- **Feature-based** over layer-based for large apps:

```
# ✅ Feature-based (scales well)
src/
  features/
    auth/
      components/
      hooks/
      api.ts
      types.ts
    dashboard/
      ...
  shared/
    components/
    utils/

# ❌ Layer-based (becomes unwieldy)
src/
  components/    ← 200 files
  hooks/         ← 100 files
  utils/         ← 50 files
```

---

## 8.4 Code Generation

- **OpenAPI/Swagger** → generate client SDKs and types (`openapi-typescript`, `orval`)
- **Prisma/Drizzle** → generate type-safe database client from schema
- **GraphQL Codegen** → generate types and hooks from `.graphql` files
- **Protobuf** → generate gRPC clients and types from `.proto` files
- **Always regenerate, never hand-edit** generated code
- **Commit generated code** if it's needed at runtime; gitignore if build-time only
