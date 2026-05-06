# Skill: Laravel
# Loaded on-demand when working with Laravel, Eloquent, Blade, Artisan

## Eloquent ORM — Relationships, Scopes, Optimization
```php
// Eager load to prevent N+1 — ALWAYS use with() for relationships in loops
$posts = Post::with(['author', 'comments.user', 'tags'])->paginate(20);
$users = User::with(['posts' => fn ($q) => $q->where('published', true)->withCount('comments')])->get();

// ANTI-PATTERN: N+1 — lazy loading in loops
foreach (Post::all() as $post) { echo $post->author->name; } // query per post!

// Scopes & accessors (Laravel 11+)
public function scopePublished(Builder $query): Builder { return $query->where('published_at', '<=', now()); }
protected function title(): Attribute {
    return Attribute::make(get: fn ($v) => ucfirst($v), set: fn ($v) => strtolower($v));
}

// Query optimization — chunk large datasets, never ->get() unbounded
Post::where('created_at', '<', now()->subYear())->chunkById(1000, fn ($posts) => $posts->each->archive());
$count = Post::count(); // GOOD — not Post::all()->count() which loads all rows
```

## Migrations, Factories & Validation
```php
// Migration with indexes and foreign keys
Schema::create('posts', function (Blueprint $table) {
    $table->id();
    $table->foreignId('user_id')->constrained()->cascadeOnDelete();
    $table->string('slug')->unique();
    $table->timestamp('published_at')->nullable()->index();
    $table->timestamps();
    $table->index(['user_id', 'published_at']); // composite
});

// Form Request — validation + authorization in one class
class StorePostRequest extends FormRequest {
    public function authorize(): bool { return $this->user()->can('create', Post::class); }
    public function rules(): array {
        return [
            'title' => ['required', 'string', 'max:255'],
            'body' => ['required', 'string', 'min:50'],
            'category_id' => ['required', 'exists:categories,id'],
            'tags.*' => ['exists:tags,id'],
        ];
    }
}
```

## API Resources, DI & Events
```php
// API Resource — conditional relationships, computed fields
class PostResource extends JsonResource {
    public function toArray(Request $request): array {
        return [
            'id' => $this->id, 'title' => $this->title,
            'author' => new UserResource($this->whenLoaded('author')),
            'is_owner' => $this->when($request->user(), fn () => $this->user_id === $request->user()->id),
        ];
    }
}

// DI — constructor injection over facades in business logic
class OrderService {
    public function __construct(private readonly PaymentGatewayInterface $gateway, private readonly OrderRepository $orders) {}
}
// ANTI-PATTERN: Facades/app() in domain classes — hides deps, hurts testability

// Queued listener with retry
class SendOrderConfirmation implements ShouldQueue {
    public int $tries = 3;
    public int $backoff = 60;
    public function handle(OrderPlaced $event): void {
        Mail::to($event->order->user)->send(new OrderConfirmationMail($event->order));
    }
}
```

## Caching, Auth & Testing
```php
// Tagged cache with invalidation (Redis required)
$posts = Cache::tags(['posts', "user:{$id}"])->remember("user:{$id}:posts", 3600, fn () => Post::where('user_id', $id)->get());
Cache::tags(["user:{$id}"])->flush();

// Policy-based authorization
class PostPolicy {
    public function update(User $user, Post $post): bool { return $user->id === $post->user_id || $user->isAdmin(); }
}
// Controller: $this->authorize('update', $post);  Blade: @can('update', $post)

// Feature test
class PostApiTest extends TestCase {
    use RefreshDatabase;
    public function test_user_can_create_post(): void {
        $user = User::factory()->create();
        $this->actingAs($user)->postJson('/api/posts', ['title' => 'Test', 'body' => str_repeat('a', 100), 'category_id' => Category::factory()->create()->id])
             ->assertCreated()->assertJsonPath('data.title', 'Test');
        $this->assertDatabaseHas('posts', ['user_id' => $user->id]);
    }
}
```

## Laravel 11+ & Anti-Patterns
- **Slim skeleton**: No `Http/Kernel.php` — middleware in `bootstrap/app.php`
- **Health routing**: `Route::health('/up')` built-in
- **Per-second rate limiting**: `RateLimiter::for('api', fn () => Limit::perSecond(1))`

| Anti-Pattern | Fix |
|---|---|
| N+1 queries | `with()` / `load()` eager loading |
| `Model::all()->count()` | `Model::count()` |
| Fat controllers | Form Requests, Services, Actions |
| Caching without invalidation | Tagged caches, event-driven flush |
| Facades in domain logic | Constructor injection |
