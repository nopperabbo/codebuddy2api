# Skill: PHP
# Loaded on-demand when working with .php files

---

## PHP

```php
// ✅ PHP 8.2+ — strict types, enums, readonly
declare(strict_types=1);

enum OrderStatus: string {
    case Pending = 'pending';
    case Paid = 'paid';
    case Shipped = 'shipped';
    case Cancelled = 'cancelled';
}

readonly class CreateUserDTO {
    public function __construct(
        public string $email,
        public string $name,
        public ?int $age = null,
    ) {}
}

// ✅ Named arguments for clarity
$user = User::create(
    email: $dto->email,
    name: $dto->name,
    role: Role::User,
);

// ✅ Match expression over switch
$label = match($status) {
    OrderStatus::Pending => 'Awaiting payment',
    OrderStatus::Paid => 'Processing',
    OrderStatus::Shipped => 'On the way',
    OrderStatus::Cancelled => 'Cancelled',
};

// ❌ Avoid: @ error suppression, extract(), eval(), dynamic variable names
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
