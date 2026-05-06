# Skill: Auth & Identity
# Loaded on-demand when task involves OAuth2, OIDC, JWT, RBAC, ABAC, session management, MFA, or zero-trust

## Auto-Detect

Trigger this skill when:
- Task mentions: OAuth, OIDC, JWT, authentication, authorization, RBAC, ABAC, MFA, SSO
- Files: `auth/`, `middleware/auth.*`, `*.guard.ts`, `policies/`
- Patterns: login flow, token refresh, permission check, role management
- `package.json` contains: `passport`, `next-auth`, `@auth/*`, `jose`, `jsonwebtoken`

---

## Decision Tree: Auth Architecture

```
What type of application?
├── Server-rendered web app (Next.js, Rails, Laravel)?
│   └── Session-based auth (httpOnly cookies, server-side session store)
├── SPA + API (React/Vue + separate backend)?
│   ├── Same domain? → httpOnly cookie with CSRF token
│   └── Cross-domain? → OAuth2 Authorization Code + PKCE
├── Mobile app?
│   └── OAuth2 Authorization Code + PKCE (no client secret)
├── Machine-to-machine (service accounts)?
│   └── OAuth2 Client Credentials flow
├── Third-party integrations?
│   └── OAuth2 Authorization Code (standard)
└── Microservices internal?
    └── mTLS + JWT propagation (service mesh handles mTLS)
```

## Decision Tree: Token Strategy

```
├── Need stateless verification? → JWT (but understand the tradeoffs)
├── Need instant revocation? → Opaque tokens + token introspection
├── Need both? → Short-lived JWT (5-15 min) + refresh token (opaque, in DB)
├── Need to share identity across services? → JWT claims propagation
└── Need offline access? → Refresh tokens with rotation
```

---

## OAuth2/OIDC Implementation

```typescript
// Authorization Code + PKCE flow (recommended for all clients)
import { generators } from 'openid-client';

class AuthService {
  async initiateLogin(req: Request, res: Response): Promise<void> {
    // Generate PKCE challenge
    const codeVerifier = generators.codeVerifier();
    const codeChallenge = generators.codeChallenge(codeVerifier);
    const state = generators.state();
    const nonce = generators.nonce();

    // Store in session (server-side, NOT in URL)
    req.session.auth = { codeVerifier, state, nonce };

    const authUrl = new URL(`${this.issuer}/authorize`);
    authUrl.searchParams.set('client_id', this.clientId);
    authUrl.searchParams.set('redirect_uri', this.redirectUri);
    authUrl.searchParams.set('response_type', 'code');
    authUrl.searchParams.set('scope', 'openid profile email');
    authUrl.searchParams.set('state', state);
    authUrl.searchParams.set('nonce', nonce);
    authUrl.searchParams.set('code_challenge', codeChallenge);
    authUrl.searchParams.set('code_challenge_method', 'S256');

    res.redirect(authUrl.toString());
  }

  async handleCallback(req: Request): Promise<TokenSet> {
    const { code, state } = req.query;
    const { codeVerifier, state: savedState, nonce } = req.session.auth;

    // Validate state to prevent CSRF
    if (state !== savedState) {
      throw new AuthError('Invalid state parameter');
    }

    // Exchange code for tokens
    const tokenResponse = await fetch(`${this.issuer}/token`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: new URLSearchParams({
        grant_type: 'authorization_code',
        code,
        redirect_uri: this.redirectUri,
        client_id: this.clientId,
        code_verifier: codeVerifier, // PKCE verification
      }),
    });

    const tokens = await tokenResponse.json();

    // Validate ID token
    const claims = await this.verifyIdToken(tokens.id_token, nonce);

    // Clean up session state
    delete req.session.auth;

    return { ...tokens, claims };
  }
}
```

---

## JWT Best Practices

```typescript
import { SignJWT, jwtVerify, errors } from 'jose';

// Token creation — minimal claims, short expiry
async function createAccessToken(user: User, permissions: string[]): Promise<string> {
  const secret = new TextEncoder().encode(process.env.JWT_SECRET);

  return new SignJWT({
    sub: user.id,
    email: user.email,
    permissions, // Keep minimal — don't embed entire user object
    // NEVER include: password, PII, sensitive data
  })
    .setProtectedHeader({ alg: 'HS256', typ: 'JWT' })
    .setIssuedAt()
    .setExpirationTime('15m')  // Short-lived! 5-15 minutes max
    .setIssuer('https://api.example.com')
    .setAudience('https://api.example.com')
    .setJti(crypto.randomUUID()) // Unique ID for revocation tracking
    .sign(secret);
}

// Token verification — always validate ALL claims
async function verifyAccessToken(token: string): Promise<JWTPayload> {
  const secret = new TextEncoder().encode(process.env.JWT_SECRET);

  try {
    const { payload } = await jwtVerify(token, secret, {
      issuer: 'https://api.example.com',
      audience: 'https://api.example.com',
      algorithms: ['HS256'],
      maxTokenAge: '15m', // Reject even if exp is valid but token is old
    });

    // Check revocation list (for logout/compromise)
    if (await isRevoked(payload.jti)) {
      throw new AuthError('Token has been revoked');
    }

    return payload;
  } catch (error) {
    if (error instanceof errors.JWTExpired) {
      throw new AuthError('Token expired', { code: 'TOKEN_EXPIRED' });
    }
    throw new AuthError('Invalid token', { code: 'TOKEN_INVALID' });
  }
}

// Refresh token rotation — detect reuse attacks
async function refreshTokens(refreshToken: string): Promise<TokenPair> {
  const stored = await db.refreshTokens.findUnique({ where: { token: refreshToken } });

  if (!stored) {
    throw new AuthError('Invalid refresh token');
  }

  if (stored.used) {
    // Token reuse detected! Possible theft — revoke entire family
    await db.refreshTokens.updateMany({
      where: { familyId: stored.familyId },
      data: { revoked: true },
    });
    throw new AuthError('Refresh token reuse detected — all sessions revoked');
  }

  // Mark as used
  await db.refreshTokens.update({ where: { id: stored.id }, data: { used: true } });

  // Issue new pair
  const newRefreshToken = crypto.randomUUID();
  await db.refreshTokens.create({
    data: {
      token: newRefreshToken,
      userId: stored.userId,
      familyId: stored.familyId, // Same family for reuse detection
      expiresAt: addDays(new Date(), 30),
    },
  });

  const accessToken = await createAccessToken(stored.user, stored.user.permissions);
  return { accessToken, refreshToken: newRefreshToken };
}
```

---

## RBAC Implementation

```typescript
// Role-Based Access Control with hierarchical roles
interface Role {
  name: string;
  permissions: Permission[];
  inherits?: string[]; // Role hierarchy
}

interface Permission {
  resource: string;  // e.g., 'orders', 'users', 'reports'
  actions: Action[]; // e.g., ['read', 'create', 'update', 'delete']
  conditions?: Condition[]; // Optional: ABAC-style conditions
}

type Action = 'create' | 'read' | 'update' | 'delete' | 'manage';

// Permission resolution with inheritance
class RBACService {
  private roles: Map<string, Role>;

  resolvePermissions(roleName: string): Permission[] {
    const role = this.roles.get(roleName);
    if (!role) return [];

    const inherited = (role.inherits || [])
      .flatMap(parent => this.resolvePermissions(parent));

    return [...inherited, ...role.permissions];
  }

  can(user: User, action: Action, resource: string, context?: Record<string, unknown>): boolean {
    const permissions = user.roles.flatMap(r => this.resolvePermissions(r));

    return permissions.some(p => {
      if (p.resource !== resource && p.resource !== '*') return false;
      if (!p.actions.includes(action) && !p.actions.includes('manage')) return false;

      // Evaluate conditions (ABAC extension)
      if (p.conditions) {
        return p.conditions.every(c => this.evaluateCondition(c, user, context));
      }
      return true;
    });
  }

  private evaluateCondition(condition: Condition, user: User, context?: Record<string, unknown>): boolean {
    switch (condition.type) {
      case 'ownership':
        return context?.ownerId === user.id;
      case 'department':
        return user.department === condition.value;
      case 'time-based':
        return isWithinBusinessHours();
      default:
        return false;
    }
  }
}

// Middleware usage
function authorize(resource: string, action: Action) {
  return (req: Request, res: Response, next: NextFunction) => {
    if (!rbac.can(req.user, action, resource, { ownerId: req.params.userId })) {
      return res.status(403).json({
        error: 'Forbidden',
        message: `You don't have permission to ${action} ${resource}`,
      });
    }
    next();
  };
}

// Route usage
router.get('/orders', authorize('orders', 'read'), listOrders);
router.post('/orders', authorize('orders', 'create'), createOrder);
router.delete('/orders/:id', authorize('orders', 'delete'), deleteOrder);
```

---

## Session Management

```typescript
// Secure session configuration
const sessionConfig = {
  name: '__Host-session', // __Host- prefix enforces secure + same-origin
  secret: process.env.SESSION_SECRET, // 256-bit random, rotated regularly
  resave: false,
  saveUninitialized: false,
  cookie: {
    httpOnly: true,      // Not accessible via JavaScript
    secure: true,        // HTTPS only
    sameSite: 'lax',     // CSRF protection (use 'strict' for sensitive apps)
    maxAge: 3600000,     // 1 hour
    path: '/',
    domain: undefined,   // Let browser set to current domain
  },
  store: new RedisStore({
    client: redisClient,
    prefix: 'sess:',
    ttl: 3600,           // Match cookie maxAge
    disableTouch: false, // Extend on activity
  }),
  rolling: true,         // Reset expiry on each request
};

// Session fixation prevention
app.post('/login', async (req, res) => {
  const user = await authenticate(req.body);
  if (!user) return res.status(401).json({ error: 'Invalid credentials' });

  // Regenerate session ID after authentication (prevent fixation)
  req.session.regenerate((err) => {
    if (err) return res.status(500).json({ error: 'Session error' });
    req.session.userId = user.id;
    req.session.createdAt = Date.now();
    req.session.ip = req.ip;
    req.session.userAgent = req.headers['user-agent'];
    res.json({ success: true });
  });
});
```

---

## MFA Implementation

```typescript
import { authenticator } from 'otplib';
import QRCode from 'qrcode';

class MFAService {
  // Setup: Generate secret and QR code
  async setupTOTP(user: User): Promise<{ secret: string; qrCode: string }> {
    const secret = authenticator.generateSecret();

    // Store encrypted, NOT yet verified
    await db.users.update({
      where: { id: user.id },
      data: { mfaSecret: encrypt(secret), mfaVerified: false },
    });

    const otpauth = authenticator.keyuri(user.email, 'MyApp', secret);
    const qrCode = await QRCode.toDataURL(otpauth);

    return { secret, qrCode };
  }

  // Verify: Confirm setup with a valid code
  async verifySetup(user: User, code: string): Promise<boolean> {
    const secret = decrypt(user.mfaSecret);
    const isValid = authenticator.verify({ token: code, secret });

    if (isValid) {
      // Generate backup codes
      const backupCodes = Array.from({ length: 10 }, () =>
        crypto.randomBytes(4).toString('hex')
      );

      await db.users.update({
        where: { id: user.id },
        data: {
          mfaVerified: true,
          backupCodes: await hashBackupCodes(backupCodes),
        },
      });

      return true; // Show backup codes to user ONCE
    }
    return false;
  }

  // Login: Validate TOTP code
  async validateCode(user: User, code: string): Promise<boolean> {
    const secret = decrypt(user.mfaSecret);

    // Check TOTP (with 1-step window for clock drift)
    const isValid = authenticator.verify({
      token: code,
      secret,
      window: 1,
    });

    if (isValid) {
      // Prevent replay attacks
      if (await this.isCodeUsed(user.id, code)) {
        return false;
      }
      await this.markCodeUsed(user.id, code);
      return true;
    }

    // Check backup codes
    return this.validateBackupCode(user, code);
  }
}
```

---

## Zero-Trust Architecture

```
Principles:
1. Never trust, always verify — even internal traffic
2. Least privilege — minimum permissions for the task
3. Assume breach — design as if attacker is already inside
4. Verify explicitly — authenticate every request, every time

Implementation layers:
├── Network: mTLS between all services (service mesh)
├── Identity: Every request carries verified identity (JWT/mTLS cert)
├── Device: Device posture check before access (MDM integration)
├── Application: Per-request authorization (not just at gateway)
└── Data: Encrypt at rest + in transit, field-level access control
```

---

## Anti-Patterns

| Anti-Pattern | Problem | Solution |
|---|---|---|
| JWT as session (long-lived) | Can't revoke, grows stale | Short-lived JWT (15m) + refresh token |
| Storing JWT in localStorage | XSS can steal tokens | httpOnly cookie or in-memory only |
| Symmetric JWT in microservices | Every service can forge tokens | Asymmetric (RS256/ES256), only auth service signs |
| Role check in every handler | Scattered, inconsistent, easy to miss | Centralized middleware/guard + declarative |
| No refresh token rotation | Stolen refresh token = permanent access | Rotate on use, detect reuse |
| Password in JWT claims | Exposed to anyone who decodes | Never put secrets in JWT payload |
| Shared secrets across envs | Dev leak compromises production | Unique secrets per environment |
| No rate limit on auth endpoints | Brute force attacks | Rate limit + account lockout + CAPTCHA |
| MFA bypass for "convenience" | Defeats the purpose | MFA on all sensitive operations, no exceptions |
| Trusting client-side role checks | Trivially bypassed | Always enforce on server side |
