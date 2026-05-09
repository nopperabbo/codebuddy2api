# Skill: Python
# Loaded on-demand when working with .py, .pyi files

---

## Python

```python
# ✅ Type hints everywhere (Python 3.10+)
def process_items(items: list[str], *, limit: int = 100) -> dict[str, int]:
    ...

# ✅ Pydantic for validation + serialization
from pydantic import BaseModel, Field

class CreateUser(BaseModel):
    email: str = Field(..., pattern=r"^[\w.-]+@[\w.-]+\.\w+$")
    name: str = Field(..., min_length=1, max_length=100)
    age: int | None = Field(None, ge=13, le=150)

# ✅ Async with proper patterns
async def fetch_all(urls: list[str]) -> list[Response]:
    async with aiohttp.ClientSession() as session:
        tasks = [session.get(url) for url in urls]
        return await asyncio.gather(*tasks, return_exceptions=True)

# ✅ Context managers for cleanup
from contextlib import asynccontextmanager

@asynccontextmanager
async def get_db():
    conn = await pool.acquire()
    try:
        yield conn
    finally:
        await pool.release(conn)

# ❌ Avoid: mutable default args, bare except:, import *, global state
```

**Python tooling:** `ruff` (lint+format), `mypy --strict` or `pyright`, `uv` (package manager)

---

## General Polyglot Rules

Regardless of language:
- **Consistent naming** within the project's convention
- **Small functions** — each does one thing (max ~40 lines)
- **Early returns** — reduce nesting, handle errors first
- **No magic numbers** — use named constants
- **Comments explain WHY, not WHAT** — code should be self-documenting
- **Delete dead code** — don't comment it out, that's what git is for
- **Immutability by default** — mutate only when necessary
- **Parse, don't validate** — transform untyped data into typed structures at boundaries
