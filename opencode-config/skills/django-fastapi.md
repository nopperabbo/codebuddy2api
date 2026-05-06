# Skill: Django & FastAPI
# Loaded on-demand when working with Django, FastAPI, DRF

---
# DJANGO
---

## ORM — QuerySets, F/Q Objects, Optimization
```python
# select_related (FK JOIN) vs prefetch_related (M2M separate query)
posts = Post.objects.select_related('author').prefetch_related('tags', 'comments__user').filter(published=True)

# F objects (DB-level ops) and Q objects (complex lookups)
from django.db.models import F, Q, Count, Avg
Product.objects.update(price=F('price') * 1.1)
Post.objects.filter(Q(title__icontains='django') | Q(body__icontains='django'), published=True)

# Annotations
authors = User.objects.annotate(post_count=Count('posts'), avg_rating=Avg('posts__rating')).filter(post_count__gte=5)

# ANTI-PATTERN: Filtering in Python instead of DB
all_posts = list(Post.objects.all())  # BAD — loads everything
filtered = [p for p in all_posts if p.published]  # Use .filter(published=True)
```

## DRF — Serializers, ViewSets, Permissions
```python
class PostSerializer(serializers.ModelSerializer):
    author = UserSerializer(read_only=True)
    class Meta:
        model = Post
        fields = ['id', 'title', 'body', 'author', 'tags', 'created_at']
    def validate_title(self, value):
        if Post.objects.filter(title=value).exclude(pk=self.instance and self.instance.pk).exists():
            raise serializers.ValidationError("Title must be unique.")
        return value
    def create(self, validated_data):
        tags = validated_data.pop('tags', [])
        post = Post.objects.create(author=self.context['request'].user, **validated_data)
        post.tags.set(tags)
        return post

class PostViewSet(viewsets.ModelViewSet):
    serializer_class = PostSerializer
    permission_classes = [IsAuthenticatedOrReadOnly, IsOwnerOrReadOnly]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['category', 'published']
    search_fields = ['title', 'body']
    def get_queryset(self):
        return Post.objects.select_related('author').prefetch_related('tags')
```

## Signals, Celery & Testing
```python
@receiver(post_save, sender=Post)
def on_post_created(sender, instance, created, **kwargs):
    if created: notify_subscribers.delay(instance.pk)

@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def notify_subscribers(self, post_id):
    try: post = Post.objects.get(pk=post_id)
    except Post.DoesNotExist: return
    except Exception as exc: raise self.retry(exc=exc)

class PostAPITest(APITestCase):
    def setUp(self):
        self.user = UserFactory()
        self.client.force_authenticate(user=self.user)
    def test_create_post(self):
        response = self.client.post('/api/posts/', {'title': 'Test', 'body': 'Content'})
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
```

---
# FASTAPI
---

## Pydantic Models, DI & Async Endpoints
```python
from pydantic import BaseModel, Field, field_validator, ConfigDict
from fastapi import FastAPI, Depends, HTTPException, BackgroundTasks, status

class PostCreate(BaseModel):
    title: str = Field(..., min_length=3, max_length=255)
    body: str = Field(..., min_length=50)
    tags: list[str] = Field(default_factory=list, max_length=5)
    @field_validator('title')
    @classmethod
    def title_not_blank(cls, v): return v.strip() or (_ for _ in ()).throw(ValueError('blank'))

class PostResponse(BaseModel):
    id: int; title: str; author_id: int
    model_config = ConfigDict(from_attributes=True)

# Dependency injection chain
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session() as session: yield session

async def get_current_user(token: str = Depends(oauth2_scheme), db: AsyncSession = Depends(get_db)) -> User:
    payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
    user = await db.get(User, payload["sub"])
    if not user: raise HTTPException(status_code=401, detail="Invalid token")
    return user

@app.post("/posts/", response_model=PostResponse, status_code=201)
async def create_post(post: PostCreate, bg: BackgroundTasks, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    db_post = Post(**post.model_dump(), author_id=user.id)
    db.add(db_post); await db.commit(); await db.refresh(db_post)
    bg.add_task(send_notification, user.id, db_post.id)
    return db_post

# ANTI-PATTERN: Blocking sync in async endpoints
@app.get("/bad/")
async def bad(): time.sleep(5)  # BAD — blocks event loop. Use await asyncio.sleep() or run_in_executor
```

## SQLAlchemy 2.0, Alembic & Testing
```python
class Post(Base):
    __tablename__ = "posts"
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(255), index=True)
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    author: Mapped["User"] = relationship(back_populates="posts")
# Alembic: alembic revision --autogenerate -m "add posts" && alembic upgrade head

@pytest.mark.anyio
async def test_create_post():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/posts/", json={"title": "Test", "body": "x" * 50}, headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 201
```

## Anti-Patterns Summary
| Anti-Pattern | Fix |
|---|---|
| Django: Python-side filtering | QuerySet `.filter()`, `F()`, `Q()` |
| Django: No `select_related`/`prefetch_related` | Profile with `django-debug-toolbar` |
| FastAPI: Blocking sync in async | `async def` + async I/O or `run_in_executor` |
| FastAPI: No `response_model` | Always declare — validates output + OpenAPI |
