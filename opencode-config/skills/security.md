# Skill: Security Advanced
# Loaded on-demand when task involves auth, input validation, secrets, vulnerabilities, CORS, CSP, or security review

## Auto-Detect

Trigger this skill when:
- Files: `auth.ts`, `middleware.ts`, `*.guard.ts`, `cors.ts`, `helmet.*`
- `package.json` contains: `bcrypt`, `jsonwebtoken`, `passport`, `helmet`, `cors`, `csurf`, `express-rate-limit`
- Code patterns: `jwt.sign`, `jwt.verify`, `hash`, `encrypt`, `sanitize`, `csrf`
- Task mentions: security audit, penetration test, vulnerability, hardening, OWASP

---

## Decision Tree: Authentication Strategy

```
What type of application?
├── SPA + API (same domain)?
│   └── HTTP-only secure cookies with session ID
│       └── Store session in Redis/DB, not memory
├── SPA + API (cross-domain)?
│   └── OAuth2 Authorization Code + PKCE
│       └── Access token in memory, refresh via HTTP-only cookie
├── Mobile app?
│   └── OAuth2 + PKCE with secure storage (Keychain/Keystore)
├── Server-to-server?
│   └── mTLS or API keys with rotation
├── Third-party integrations?
│   └── OAuth2 with scoped permissions
└── Microservices internal?
    └── JWT (short-lived, signed by auth service) + service mesh mTLS
```

## Decision Tree: JWT vs Session

```
JWT when:
├── Stateless required (serverless, edge)
├── Cross-service auth (microservices)
├── Short-lived tokens only (< 15 min)
└── You accept: can't revoke instantly, larger payload

Session when:
├── Need instant revocation (logout, ban)
├── Single server or sticky sessions available
├── Sensitive operations (banking, healthcare)
└── You accept: server-side storage, scaling complexity
```

---

## OWASP Top 10 Checklist (2021)

| # | Risk | Check | Prevention |
|---|------|-------|-----------|
| 1 | **Broken Access Control** | Every endpoint checks authorization? | Deny by default, resource-level checks |
| 2 | **Cryptographic Failures** | Sensitive data encrypted at rest + transit? | AES-256-GCM, TLS 1.3, no MD5/SHA1 |
| 3 | **Injection** | All queries parameterized? | ORM/prepared statements, never string concat |
| 4 | **Insecure Design** | Threat model exists? | Abuse cases in requirements, rate limiting |
| 5 | **Security Misconfiguration** | Default creds removed? Headers set? | Automated config scanning, minimal permissions |
| 6 | **Vulnerable Components** | Dependencies audited? | `npm audit`, Snyk/Dependabot in CI |
| 7 | **Auth Failures** | MFA available? Brute-force protected? | Rate limiting, account lockout, MFA |
| 8 | **Data Integrity Failures** | CI/CD pipeline secured? | Signed commits, artifact verification |
| 9 | **Logging Failures** | Auth events logged? Anomalies detected? | Structured logs, SIEM integration |
| 10 | **SSRF** | User URLs validated? | Allowlist domains, block internal IPs |

---

## Input Validation Patterns

```typescript
import { z } from 'zod';

// Validate ALL external input at the boundary
const CreateUserInput = z.object({
  email: z.string().email().max(254).toLowerCase(),
  name: z.string().min(1).max(100).trim(),
  password: z.string().min(12).regex(/[A-Z]/).regex(/[0-9]/).regex(/[^A-Za-z0-9]/),
  age: z.number().int().min(13).max(150).optional(),
});

// Sanitize for specific contexts
function sanitizeHtml(input: string): string {
  return input
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#x27;');
}

// File upload validation
const FileSchema = z.object({
  mimetype: z.enum(['image/jpeg', 'image/png', 'image/webp', 'application/pdf']),
  size: z.number().max(10 * 1024 * 1024), // 10MB max
  originalname: z.string().regex(/^[a-zA-Z0-9._-]+$/), // no path traversal chars
});
```

---

## SQL Injection Prevention

```typescript
// ❌ NEVER — string concatenation
const query = `SELECT * FROM users WHERE id = '${userId}'`;

// ✅ Parameterized queries
const user = await db.query('SELECT * FROM users WHERE id = $1', [userId]);

// ✅ ORM with type safety
const user = await prisma.user.findUnique({ where: { id: userId } });

// ✅ Query builder
const user = await knex('users').where('id', userId).first();

// ⚠️ Even with ORMs, watch for raw queries
// ❌ prisma.$queryRawUnsafe(`SELECT * FROM users WHERE name = '${name}'`)
// ✅ prisma.$queryRaw`SELECT * FROM users WHERE name = ${name}`
```

---

## XSS Prevention

```typescript
// Content Security Policy — strongest XSS defense
const cspHeader = {
  'Content-Security-Policy': [
    "default-src 'self'",
    "script-src 'self' 'nonce-{RANDOM}'", // nonce per request
    "style-src 'self' 'unsafe-inline'",   // or use nonce for styles too
    "img-src 'self' data: https:",
    "font-src 'self'",
    "connect-src 'self' https://api.example.com",
    "frame-ancestors 'none'",
    "base-uri 'self'",
    "form-action 'self'",
  ].join('; ')
};

// React auto-escapes JSX — but watch for:
// ❌ dangerouslySetInnerHTML={{ __html: userInput }}
// ❌ href={`javascript:${userInput}`}
// ❌ eval(userInput)

// ✅ Use DOMPurify for rich text that MUST render HTML
import DOMPurify from 'dompurify';
const clean = DOMPurify.sanitize(userHtml, { ALLOWED_TAGS: ['b', 'i', 'a', 'p'] });
```

---

## CORS Configuration

```typescript
// ✅ Production CORS — explicit origins
import cors from 'cors';

app.use(cors({
  origin: (origin, callback) => {
    const allowed = ['https://app.example.com', 'https://admin.example.com'];
    if (!origin || allowed.includes(origin)) callback(null, true);
    else callback(new Error('CORS blocked'));
  },
  methods: ['GET', 'POST', 'PUT', 'DELETE', 'PATCH'],
  allowedHeaders: ['Content-Type', 'Authorization'],
  credentials: true,
  maxAge: 86400,
}));

// ❌ NEVER in production
cors({ origin: '*' })                    // allows any origin
cors({ origin: true })                   // reflects request origin
cors({ origin: /.*\.example\.com/ })     // regex can be bypassed (evil-example.com)
```

---

## Secrets Management

```typescript
// ✅ Validate env vars at startup — fail fast
import { z } from 'zod';

const EnvSchema = z.object({
  DATABASE_URL: z.string().url().startsWith('postgres'),
  JWT_SECRET: z.string().min(64),
  API_KEY: z.string().min(32),
  ENCRYPTION_KEY: z.string().length(64), // 256-bit hex
});

const env = EnvSchema.parse(process.env); // Crashes immediately if invalid
export { env };

// Rules:
// - Never log secrets (redact in error handlers)
// - Never commit secrets (.env in .gitignore, use .env.example)
// - Rotate secrets on schedule (90 days max)
// - Use secret managers in production (Vault, AWS Secrets Manager, GCP Secret Manager)
// - Different secrets per environment (dev ≠ staging ≠ prod)
```

---

## Rate Limiting

```typescript
import rateLimit from 'express-rate-limit';

// Global rate limit
app.use(rateLimit({ windowMs: 15 * 60 * 1000, max: 100 }));

// Strict limit on auth endpoints
app.use('/api/auth', rateLimit({
  windowMs: 15 * 60 * 1000,
  max: 5,
  message: { error: 'Too many attempts. Try again in 15 minutes.' },
  standardHeaders: true,
  legacyHeaders: false,
  keyGenerator: (req) => req.ip + ':' + req.body?.email, // per IP+email
}));

// Progressive delays on failed login
// 1st fail: immediate, 2nd: 1s, 3rd: 2s, 4th: 4s, 5th: lockout 15min
```

---

## Security Headers

```typescript
import helmet from 'helmet';

app.use(helmet({
  contentSecurityPolicy: { /* see CSP section */ },
  strictTransportSecurity: { maxAge: 31536000, includeSubDomains: true, preload: true },
  referrerPolicy: { policy: 'strict-origin-when-cross-origin' },
  frameguard: { action: 'deny' },
  noSniff: true,
  xssFilter: true,
}));

// Additional headers
app.use((req, res, next) => {
  res.setHeader('Permissions-Policy', 'camera=(), microphone=(), geolocation=()');
  res.setHeader('X-Content-Type-Options', 'nosniff');
  next();
});
```

---

## Anti-Patterns

| ❌ Don't | ✅ Do Instead |
|----------|---------------|
| Store JWT in localStorage | HTTP-only secure cookie or memory |
| `cors({ origin: '*' })` with credentials | Explicit origin allowlist |
| MD5/SHA1 for passwords | bcrypt/scrypt/argon2 with salt |
| Roll your own crypto | Use established libraries (libsodium, Web Crypto API) |
| Trust client-side validation alone | Always validate server-side |
| Log full request bodies | Redact sensitive fields |
| Hardcode secrets in code | Environment variables + secret manager |
| `eval()` or `new Function()` with user input | Never execute user-provided code |
| Disable HTTPS in production | TLS 1.3 everywhere, HSTS preload |
| Single shared API key for all clients | Per-client keys with scoped permissions |

---

## Verification Checklist

Before considering security work done:
- [ ] All inputs validated with schema (Zod/Joi) at API boundary
- [ ] SQL queries parameterized — zero string concatenation
- [ ] Auth checks on every protected endpoint (middleware)
- [ ] Passwords hashed with bcrypt/argon2 (cost factor ≥ 12)
- [ ] CORS configured with explicit origins (no wildcards)
- [ ] Security headers set (CSP, HSTS, X-Frame-Options, etc.)
- [ ] Secrets in env vars, not in code — `.env` in `.gitignore`
- [ ] Rate limiting on auth and public endpoints
- [ ] No sensitive data in JWT payload or logs
- [ ] Dependencies audited (`npm audit` / Snyk in CI)
- [ ] File uploads validated (type, size, name sanitized)
- [ ] Error messages don't leak internal details to clients

---

## MCP Integration

| Tool | Use For |
|------|---------|
| `context7` | Look up OWASP guidelines, library-specific security docs |
| `grep` | Search for `eval`, `innerHTML`, string concat in queries, hardcoded secrets |
| `bash` | Run `npm audit`, security scanners, `git log` for secret exposure |
| `sequential-thinking` | Threat modeling, attack surface analysis |
| `playwright` | Test auth flows, CORS behavior, CSP enforcement |
