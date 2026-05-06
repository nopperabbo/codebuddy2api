# Skill: Spring Boot
# Loaded on-demand when working with Spring Boot, Spring Framework, Java backend

## Dependency Injection & Configuration
```java
// GOOD: Constructor injection — immutable, testable, no @Autowired needed
@Service
public class OrderService {
    private final OrderRepository orderRepo;
    private final PaymentGateway gateway;
    public OrderService(OrderRepository orderRepo, PaymentGateway gateway) {
        this.orderRepo = orderRepo;
        this.gateway = gateway;
    }
}
// ANTI-PATTERN: @Autowired field injection — hides deps, untestable without Spring context

// Type-safe config
@ConfigurationProperties(prefix = "app.mail")
public record MailProperties(String from, String replyTo, int maxRetries) {}
```

## Spring Data JPA — Repositories, Specifications, Projections
```java
public interface PostRepository extends JpaRepository<Post, Long>, JpaSpecificationExecutor<Post> {
    @EntityGraph(attributePaths = {"author", "tags"})
    Page<Post> findAll(Pageable pageable);

    @Query("SELECT p FROM Post p JOIN FETCH p.author WHERE p.category.id = :catId")
    List<Post> findByCategoryWithAuthor(@Param("catId") Long categoryId);
}

// Dynamic filtering with Specifications
public class PostSpecs {
    public static Specification<Post> hasCategory(Long id) {
        return (root, q, cb) -> id == null ? null : cb.equal(root.get("category").get("id"), id);
    }
    public static Specification<Post> titleContains(String kw) {
        return (root, q, cb) -> kw == null ? null : cb.like(cb.lower(root.get("title")), "%" + kw.toLowerCase() + "%");
    }
}
// Usage: postRepo.findAll(hasCategory(1L).and(titleContains("spring")), pageable);

// Projection — fetch only needed columns
public interface PostSummary { Long getId(); String getTitle(); @Value("#{target.author.name}") String getAuthorName(); }
```

## Spring Security — JWT & SecurityFilterChain
```java
@Configuration @EnableWebSecurity
public class SecurityConfig {
    @Bean
    public SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        return http.csrf(c -> c.disable())
            .sessionManagement(sm -> sm.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/auth/**").permitAll()
                .requestMatchers("/api/admin/**").hasRole("ADMIN")
                .anyRequest().authenticated())
            .oauth2ResourceServer(o -> o.jwt(Customizer.withDefaults()))
            .build();
    }
}
```

## Controllers, Validation & Exception Handling
```java
@RestController @RequestMapping("/api/v1/posts")
public class PostController {
    private final PostService postService;
    public PostController(PostService postService) { this.postService = postService; }

    @GetMapping
    public Page<PostDto> list(@RequestParam(defaultValue = "0") int page, @RequestParam(defaultValue = "20") int size) {
        return postService.findAll(PageRequest.of(page, size, Sort.by("createdAt").descending()));
    }

    @PostMapping @ResponseStatus(HttpStatus.CREATED)
    public PostDto create(@Valid @RequestBody CreatePostRequest req, @AuthenticationPrincipal UserDetails user) {
        return postService.create(req, user.getUsername());
    }
}

public record CreatePostRequest(@NotBlank @Size(max = 255) String title, @NotBlank @Size(min = 50) String body, @NotNull Long categoryId) {}

@RestControllerAdvice
public class GlobalExceptionHandler {
    @ExceptionHandler(ResourceNotFoundException.class) @ResponseStatus(HttpStatus.NOT_FOUND)
    public ErrorResponse handleNotFound(ResourceNotFoundException ex) { return new ErrorResponse(404, ex.getMessage()); }

    @ExceptionHandler(MethodArgumentNotValidException.class) @ResponseStatus(HttpStatus.BAD_REQUEST)
    public ErrorResponse handleValidation(MethodArgumentNotValidException ex) {
        var errors = ex.getBindingResult().getFieldErrors().stream()
            .collect(Collectors.toMap(FieldError::getField, FieldError::getDefaultMessage, (a, b) -> a));
        return new ErrorResponse(400, "Validation failed", errors);
    }
}
```

## Caching, Scheduling & Actuator
```java
@Service @CacheConfig(cacheNames = "posts")
public class PostService {
    @Cacheable(key = "#id") public PostDto findById(Long id) { /* ... */ }
    @CacheEvict(key = "#id") public PostDto update(Long id, UpdatePostRequest req) { /* ... */ }
    @CacheEvict(allEntries = true) @Scheduled(fixedRate = 3600000) public void evictCache() {}
}
```
```yaml
management.endpoints.web.exposure.include: health,info,metrics,prometheus  # Actuator
```

## Flyway & Testing
```sql
-- V1__create_posts.sql
CREATE TABLE posts (id BIGSERIAL PRIMARY KEY, title VARCHAR(255) NOT NULL, author_id BIGINT REFERENCES users(id) ON DELETE CASCADE, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
```
```java
@SpringBootTest @AutoConfigureMockMvc
class PostControllerIT {
    @Autowired MockMvc mockMvc;
    @Test @WithMockUser(roles = "USER")
    void shouldCreatePost() throws Exception {
        mockMvc.perform(post("/api/v1/posts").contentType(APPLICATION_JSON)
            .content("""{"title":"Test","body":"%s","categoryId":1}""".formatted("a".repeat(50))))
            .andExpect(status().isCreated()).andExpect(jsonPath("$.title").value("Test"));
    }
}

@DataJpaTest // Slice test — JPA only, no web layer
class PostRepositoryTest {
    @Autowired TestEntityManager em;
    @Autowired PostRepository postRepo;
    @Test void shouldFindPublished() {
        em.persist(new Post("Published", true));
        assertThat(postRepo.findByPublishedTrue()).hasSize(1);
    }
}
```

## Anti-Patterns Summary
| Anti-Pattern | Fix |
|---|---|
| Field injection | Constructor injection |
| N+1 in JPA | `@EntityGraph`, `JOIN FETCH` |
| No validation on DTOs | `@Valid` + Bean Validation |
| Blocking in WebFlux | `subscribeOn(Schedulers.boundedElastic())` |
| Hardcoded config | `@ConfigurationProperties` + profiles |
| No migration tool | Flyway or Liquibase from day one |
| Monolithic test context | `@WebMvcTest`, `@DataJpaTest` slices |
