# Skill: Angular
# Loaded on-demand when working with Angular, .component.ts files

## Standalone Components (Default since Angular 17)

```typescript
// No NgModule needed — components are self-contained
@Component({
  selector: 'app-user-card',
  standalone: true,
  imports: [CommonModule, RouterLink, UserAvatarComponent],
  template: `
    <div class="card">
      <app-user-avatar [src]="user().avatar" />
      <h3>{{ user().name }}</h3>
      <a [routerLink]="['/users', user().id]">View Profile</a>
    </div>
  `,
})
export class UserCardComponent {
  user = input.required<User>(); // signal-based input (Angular 17+)
}

// Bootstrap without NgModule
// main.ts
bootstrapApplication(AppComponent, {
  providers: [
    provideRouter(routes),
    provideHttpClient(withInterceptors([authInterceptor])),
    provideAnimations(),
  ],
});
```

## Signals (Angular 16+)

```typescript
import { signal, computed, effect, untracked } from '@angular/core';

@Component({ /* ... */ })
export class DashboardComponent {
  // Writable signal
  count = signal(0);
  items = signal<Item[]>([]);

  // Computed signal — auto-tracks dependencies, memoized
  total = computed(() => this.items().reduce((sum, i) => sum + i.price, 0));
  isEmpty = computed(() => this.items().length === 0);

  // Signal-based inputs (Angular 17.1+)
  name = input<string>('default');          // optional with default
  id = input.required<string>();            // required
  label = input<string, number>(0, {        // with transform
    transform: (v: number) => `Item #${v}`,
  });

  // Signal-based outputs (Angular 17.1+)
  saved = output<User>();
  deleted = output<string>();

  // model() — two-way binding signal (replaces @Input + @Output pattern)
  value = model<string>('');  // parent uses [(value)]="something"

  // Effect — runs when tracked signals change
  constructor() {
    effect(() => {
      console.log(`Count changed to: ${this.count()}`);
      // Use untracked() to read signals without tracking
      const items = untracked(() => this.items());
    });
  }

  increment() {
    this.count.update(c => c + 1);
    // .set() for direct assignment, .update() for functional
  }
}
```

## Angular 17+ Control Flow

```html
<!-- @if replaces *ngIf -->
@if (user(); as u) {
  <h1>Welcome, {{ u.name }}</h1>
} @else if (loading()) {
  <app-spinner />
} @else {
  <p>Please log in</p>
}

<!-- @for replaces *ngFor — requires track expression -->
@for (item of items(); track item.id) {
  <app-item-card [item]="item" />
} @empty {
  <p>No items found</p>
}

<!-- @switch replaces ngSwitch -->
@switch (status()) {
  @case ('active') { <span class="badge green">Active</span> }
  @case ('inactive') { <span class="badge gray">Inactive</span> }
  @default { <span class="badge">Unknown</span> }
}

<!-- @defer — lazy load heavy components -->
@defer (on viewport) {
  <app-heavy-chart [data]="chartData()" />
} @placeholder {
  <div class="chart-placeholder">Chart loads when scrolled into view</div>
} @loading (minimum 500ms) {
  <app-spinner />
} @error {
  <p>Failed to load chart</p>
}
<!-- Triggers: on viewport, on idle, on interaction, on hover, on timer(5s), when condition -->
```

## Dependency Injection

```typescript
// Service with providedIn (tree-shakable)
@Injectable({ providedIn: 'root' })
export class AuthService {
  private http = inject(HttpClient);
  private router = inject(Router);

  currentUser = signal<User | null>(null);
  isAuthenticated = computed(() => this.currentUser() !== null);

  login(credentials: Credentials) {
    return this.http.post<AuthResponse>('/api/login', credentials).pipe(
      tap(res => this.currentUser.set(res.user)),
    );
  }
}

// inject() function (preferred over constructor injection)
@Component({ /* ... */ })
export class ProfileComponent {
  private auth = inject(AuthService);
  private route = inject(ActivatedRoute);
}

// InjectionToken for non-class dependencies
export const API_URL = new InjectionToken<string>('API_URL');
// Provide: { provide: API_URL, useValue: 'https://api.example.com' }
// Inject: private apiUrl = inject(API_URL);
```

## RxJS Patterns

```typescript
import { switchMap, combineLatest, catchError, retry, debounceTime, distinctUntilChanged } from 'rxjs';

@Component({ /* ... */ })
export class SearchComponent {
  private http = inject(HttpClient);
  private destroyRef = inject(DestroyRef);

  searchControl = new FormControl('');

  // Search with debounce — switchMap cancels previous requests
  results$ = this.searchControl.valueChanges.pipe(
    debounceTime(300),
    distinctUntilChanged(),
    switchMap(query => query
      ? this.http.get<Result[]>(`/api/search?q=${query}`).pipe(
          retry(2),
          catchError(() => of([])),
        )
      : of([])
    ),
  );

  // Combine multiple streams
  vm$ = combineLatest({
    user: this.auth.currentUser$,
    notifications: this.notifications.unread$,
    theme: this.settings.theme$,
  });

  // toSignal: convert Observable to Signal (Angular 16+)
  results = toSignal(this.results$, { initialValue: [] });

  // toObservable: convert Signal to Observable
  count$ = toObservable(this.count);

  // Cleanup with takeUntilDestroyed
  constructor() {
    this.someObservable$.pipe(
      takeUntilDestroyed(this.destroyRef),
    ).subscribe(value => { /* ... */ });
  }
}
```

## Reactive Forms

```typescript
@Component({ /* ... */ })
export class RegistrationComponent {
  private fb = inject(NonNullableFormBuilder);

  form = this.fb.group({
    name: ['', [Validators.required, Validators.minLength(2)]],
    email: ['', [Validators.required, Validators.email]],
    password: ['', [Validators.required, Validators.minLength(8)]],
    address: this.fb.group({
      street: [''],
      city: ['', Validators.required],
      zip: ['', [Validators.required, Validators.pattern(/^\d{5}$/)]],
    }),
    tags: this.fb.array<FormControl<string>>([]),
  });

  addTag(tag: string) {
    this.form.controls.tags.push(this.fb.control(tag));
  }

  onSubmit() {
    if (this.form.invalid) {
      this.form.markAllAsTouched(); // show all validation errors
      return;
    }
    const value = this.form.getRawValue(); // fully typed
    this.userService.register(value).subscribe();
  }
}
```

```html
<form [formGroup]="form" (ngSubmit)="onSubmit()">
  <input formControlName="name" />
  @if (form.controls.name.errors?.['required'] && form.controls.name.touched) {
    <span class="error">Name is required</span>
  }

  <div formGroupName="address">
    <input formControlName="city" />
    <input formControlName="zip" />
  </div>

  <button type="submit" [disabled]="form.invalid">Register</button>
</form>
```

## Routing

```typescript
export const routes: Routes = [
  { path: '', component: HomeComponent },
  {
    path: 'dashboard',
    canActivate: [() => inject(AuthService).isAuthenticated()],
    loadComponent: () => import('./dashboard.component').then(m => m.DashboardComponent),
    children: [
      {
        path: 'settings',
        loadComponent: () => import('./settings.component'),
        resolve: { settings: () => inject(SettingsService).load() },
      },
    ],
  },
  {
    path: 'admin',
    canMatch: [() => inject(AuthService).isAdmin()],
    loadChildren: () => import('./admin/admin.routes').then(m => m.ADMIN_ROUTES),
  },
  { path: '**', component: NotFoundComponent },
];
```

## HttpClient & Interceptors

```typescript
// Functional interceptor (Angular 15+)
export const authInterceptor: HttpInterceptorFn = (req, next) => {
  const auth = inject(AuthService);
  const token = auth.token();
  if (token) {
    req = req.clone({ setHeaders: { Authorization: `Bearer ${token}` } });
  }
  return next(req).pipe(
    catchError(err => {
      if (err.status === 401) auth.logout();
      return throwError(() => err);
    }),
  );
};

// Register: provideHttpClient(withInterceptors([authInterceptor, loggingInterceptor]))
```

## Change Detection

```typescript
@Component({
  changeDetection: ChangeDetectionStrategy.OnPush, // ALWAYS use for performance
  // With signals, OnPush works automatically — signals notify the framework
})
export class OptimizedComponent {
  // Signals + OnPush = optimal change detection
  data = signal<Data | null>(null);

  // For Observable-based code with OnPush, use async pipe
  // {{ data$ | async }} — auto-subscribes and triggers change detection
}
```

## State Management (NgRx SignalStore)

```typescript
export const TodoStore = signalStore(
  withState<TodoState>({ items: [], filter: 'all', loading: false }),
  withComputed(({ items, filter }) => ({
    filteredItems: computed(() => {
      const f = filter();
      return f === 'all' ? items() : items().filter(i => i.status === f);
    }),
    count: computed(() => items().length),
  })),
  withMethods((store, http = inject(HttpClient)) => ({
    async loadAll() {
      patchState(store, { loading: true });
      const items = await firstValueFrom(http.get<Todo[]>('/api/todos'));
      patchState(store, { items, loading: false });
    },
    setFilter(filter: TodoFilter) {
      patchState(store, { filter });
    },
  })),
);

// Usage: inject(TodoStore) in component
```

## Testing

```typescript
describe('UserService', () => {
  let service: UserService;
  let httpMock: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    service = TestBed.inject(UserService);
    httpMock = TestBed.inject(HttpTestingController);
  });

  it('fetches users', () => {
    service.getUsers().subscribe(users => expect(users).toHaveLength(2));
    const req = httpMock.expectOne('/api/users');
    expect(req.request.method).toBe('GET');
    req.flush([{ id: '1' }, { id: '2' }]);
  });

  afterEach(() => httpMock.verify());
});

// Component test
it('renders user name', async () => {
  const fixture = TestBed.createComponent(UserCardComponent);
  fixture.componentRef.setInput('user', { name: 'Alice', id: '1' });
  fixture.detectChanges();
  expect(fixture.nativeElement.textContent).toContain('Alice');
});
```

## Anti-Patterns

```
- BAD: using NgModules for new Angular 17+ projects — use standalone components
- BAD: manual subscribe without cleanup — use takeUntilDestroyed or async pipe
- BAD: Default change detection everywhere — always use OnPush
- BAD: fat components with business logic — extract to services
- BAD: nested subscribes — use switchMap, concatMap, mergeMap
- BAD: any types in templates — use strict typing with FormBuilder
- BAD: *ngIf/*ngFor in Angular 17+ — use @if/@for control flow
- BAD: class-based guards/resolvers — use functional guards with inject()
- BAD: importing entire RxJS — import operators individually
- BAD: not using track in @for — causes full DOM re-render
```
