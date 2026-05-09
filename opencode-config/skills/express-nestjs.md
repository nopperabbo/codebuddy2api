# Skill: Express.js & NestJS
# Loaded on-demand when working with Express, NestJS, Node.js APIs

---
# EXPRESS.JS
---

## Middleware, Error Handling & Validation
```typescript
import express from 'express';
import helmet from 'helmet';
import cors from 'cors';
import rateLimit from 'express-rate-limit';

const app = express();
// Order: security → parsing → auth → routes → error handler
app.use(helmet());
app.use(cors({ origin: process.env.ALLOWED_ORIGINS?.split(','), credentials: true }));
app.use(rateLimit({ windowMs: 15 * 60 * 1000, max: 100 }));
app.use(express.json({ limit: '10kb' }));

// Async wrapper — eliminates try/catch in every route
const asyncHandler = (fn: Function) => (req: Request, res: Response, next: NextFunction) =>
  Promise.resolve(fn(req, res, next)).catch(next);

app.get('/api/posts', asyncHandler(async (req, res) => {
  res.json({ data: await postService.findAll(req.query) });
}));

// Centralized error handler — MUST have 4 params
app.use((err: Error, req: Request, res: Response, _next: NextFunction) => {
  const status = err instanceof AppError ? err.statusCode : 500;
  if (status === 500) logger.error(err.stack);
  res.status(status).json({ error: { message: status === 500 ? 'Internal Server Error' : err.message } });
});

// Zod validation middleware
import { z } from 'zod';
const validate = (schema: z.ZodSchema) => (req: Request, res: Response, next: NextFunction) => {
  const result = schema.safeParse({ body: req.body, query: req.query, params: req.params });
  if (!result.success) return res.status(400).json({ errors: result.error.flatten().fieldErrors });
  next();
};
```

## Router Organization & Graceful Shutdown
```typescript
const router = Router();
router.get('/', asyncHandler(postController.list));
router.post('/', authenticate, validate(createPostSchema), asyncHandler(postController.create));
router.put('/:id', authenticate, authorize('post:update'), asyncHandler(postController.update));

// Graceful shutdown — handle SIGTERM/SIGINT
const server = app.listen(PORT);
const shutdown = (signal: string) => {
  server.close(async () => { await db.disconnect(); process.exit(0); });
  setTimeout(() => process.exit(1), 10_000);
};
['SIGTERM', 'SIGINT'].forEach(s => process.on(s, () => shutdown(s)));
```

---
# NESTJS
---

## Modules, Controllers, Services & DI
```typescript
@Module({
  imports: [TypeOrmModule.forFeature([Post])],
  controllers: [PostsController],
  providers: [PostsService],
  exports: [PostsService],
})
export class PostsModule {}

@Controller('posts')
@UseGuards(JwtAuthGuard)
export class PostsController {
  constructor(private readonly postsService: PostsService) {}

  @Get()
  @ApiOperation({ summary: 'List posts' })
  findAll(@Query() query: PaginationDto) { return this.postsService.findAll(query); }

  @Post()
  @HttpCode(HttpStatus.CREATED)
  create(@Body() dto: CreatePostDto, @CurrentUser() user: User) { return this.postsService.create(dto, user); }
}
```

## Guards, Interceptors & Exception Filters
```typescript
// Role guard
@Injectable()
export class RolesGuard implements CanActivate {
  constructor(private reflector: Reflector) {}
  canActivate(ctx: ExecutionContext): boolean {
    const roles = this.reflector.get<string[]>('roles', ctx.getHandler());
    return !roles || roles.some(r => ctx.switchToHttp().getRequest().user.roles.includes(r));
  }
}

// Transform interceptor — wraps response with metadata
@Injectable()
export class TransformInterceptor<T> implements NestInterceptor<T> {
  intercept(ctx: ExecutionContext, next: CallHandler) {
    const now = Date.now();
    return next.handle().pipe(map(data => ({ data, meta: { duration: `${Date.now() - now}ms` } })));
  }
}
```

## TypeORM, WebSockets & Testing
```typescript
@Entity()
export class Post {
  @PrimaryGeneratedColumn('uuid') id: string;
  @Column({ length: 255 }) @Index() title: string;
  @ManyToOne(() => User, u => u.posts, { onDelete: 'CASCADE' }) author: User;
  @ManyToMany(() => Tag, { eager: true }) @JoinTable() tags: Tag[];
  @CreateDateColumn() createdAt: Date;
}

// WebSocket gateway
@WebSocketGateway({ cors: true, namespace: '/chat' })
export class ChatGateway {
  @WebSocketServer() server: Server;
  @SubscribeMessage('message')
  handleMessage(@MessageBody() data: ChatMessage) { this.server.to(data.room).emit('message', data); }
}

// Testing — Test.createTestingModule with mocked providers
const module = await Test.createTestingModule({
  providers: [PostsService, { provide: getRepositoryToken(Post), useValue: { find: jest.fn(), save: jest.fn() } }],
}).compile();
const service = module.get(PostsService);
```

## Anti-Patterns Summary
| Anti-Pattern | Fix |
|---|---|
| Express: No async error handling | `asyncHandler` wrapper or `express-async-errors` |
| Express: Business logic in routes | Extract to service layer |
| Express: Missing security middleware | Always add helmet, cors, rate-limit |
| NestJS: Circular dependencies | `forwardRef()`, restructure modules |
| NestJS: Fat controllers | Services + DTOs + pipes |
| Both: No graceful shutdown | Handle SIGTERM/SIGINT, drain connections |
