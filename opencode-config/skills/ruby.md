# Skill: Ruby
# Loaded on-demand when working with .rb, .rake, Gemfile files

---

## Ruby

```ruby
# ✅ Ruby 3.x — type signatures (RBS/Sorbet), pattern matching
# sig { params(email: String, name: String).returns(User) }
def create_user(email:, name:)
  User.create!(email:, name:)
rescue ActiveRecord::RecordInvalid => e
  raise ValidationError, e.message
end

# ✅ Pattern matching (Ruby 3.0+)
case response
in { status: 200, body: { data: Array => items } }
  process_items(items)
in { status: 404 }
  raise NotFoundError
in { status: 500, body: { error: String => msg } }
  raise ServerError, msg
end

# ✅ Frozen string literals for performance
# frozen_string_literal: true

# ❌ Avoid: monkey patching in production, method_missing without respond_to_missing?
```

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
