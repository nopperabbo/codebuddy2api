# Skill: Compliance & Governance
# Loaded on-demand when task involves GDPR, SOC2, audit logging, data retention, PII handling, or privacy

## Auto-Detect

Trigger this skill when:
- Task mentions: GDPR, SOC2, compliance, audit, PII, data retention, consent, privacy
- Files: `audit/`, `compliance/`, `privacy-policy.*`, `data-retention.*`
- Patterns: personal data handling, consent management, right to deletion
- `package.json` contains: `audit-log`, `@casl/ability`, data masking libraries

---

## Decision Tree: Compliance Requirements

```
What regulations apply?
+-- Handling EU citizen data?
|   +-- GDPR (General Data Protection Regulation)
|   +-- Key requirements: consent, right to erasure, DPA, breach notification
+-- US healthcare data?
|   +-- HIPAA (Health Insurance Portability and Accountability Act)
|   +-- Key: PHI encryption, access controls, audit trails
+-- US financial data?
|   +-- SOX (Sarbanes-Oxley) + PCI-DSS (payment cards)
|   +-- Key: change management, access reviews, encryption
+-- SaaS selling to enterprises?
|   +-- SOC2 Type II (most commonly requested)
|   +-- Key: security, availability, confidentiality controls
+-- Children's data (under 13)?
|   +-- COPPA (US) / Age-appropriate design code (UK)
|   +-- Key: parental consent, data minimization
+-- California residents?
|   +-- CCPA/CPRA
|   +-- Key: opt-out of sale, right to know, right to delete
```

---

## GDPR Implementation

### Data Classification

```typescript
// Classify all data fields by sensitivity
enum DataClassification {
  PUBLIC = 'public',           // Company name, public profiles
  INTERNAL = 'internal',       // Internal metrics, non-PII
  CONFIDENTIAL = 'confidential', // Business data, contracts
  PII = 'pii',                // Name, email, phone
  SENSITIVE_PII = 'sensitive_pii', // SSN, health data, biometrics
}

interface FieldClassification {
  field: string;
  classification: DataClassification;
  legalBasis: 'consent' | 'contract' | 'legitimate_interest' | 'legal_obligation';
  retentionDays: number;
  encryptAtRest: boolean;
  maskInLogs: boolean;
}

const userFieldClassifications: FieldClassification[] = [
  { field: 'email', classification: DataClassification.PII, legalBasis: 'contract', retentionDays: 365, encryptAtRest: true, maskInLogs: true },
  { field: 'name', classification: DataClassification.PII, legalBasis: 'contract', retentionDays: 365, encryptAtRest: true, maskInLogs: true },
  { field: 'ip_address', classification: DataClassification.PII, legalBasis: 'legitimate_interest', retentionDays: 90, encryptAtRest: false, maskInLogs: true },
  { field: 'preferences', classification: DataClassification.INTERNAL, legalBasis: 'consent', retentionDays: 365, encryptAtRest: false, maskInLogs: false },
];
```

### Consent Management

```typescript
interface ConsentRecord {
  userId: string;
  purpose: string;          // e.g., 'marketing_emails', 'analytics', 'third_party_sharing'
  granted: boolean;
  grantedAt: Date;
  revokedAt?: Date;
  source: string;           // e.g., 'signup_form', 'settings_page', 'cookie_banner'
  version: string;          // Privacy policy version at time of consent
  ipAddress: string;        // Proof of consent
  userAgent: string;
}

class ConsentService {
  // Record consent with full audit trail
  async grantConsent(userId: string, purpose: string, source: string): Promise<void> {
    await this.db.consentRecords.create({
      data: {
        userId,
        purpose,
        granted: true,
        grantedAt: new Date(),
        source,
        version: await this.getCurrentPolicyVersion(),
        ipAddress: this.request.ip,
        userAgent: this.request.headers['user-agent'],
      },
    });

    await this.auditLog.record({
      action: 'consent.granted',
      userId,
      details: { purpose, source },
    });
  }

  // Check consent before processing
  async hasConsent(userId: string, purpose: string): Promise<boolean> {
    const latest = await this.db.consentRecords.findFirst({
      where: { userId, purpose },
      orderBy: { grantedAt: 'desc' },
    });

    return latest?.granted === true && !latest.revokedAt;
  }

  // Revoke consent (GDPR Article 7)
  async revokeConsent(userId: string, purpose: string): Promise<void> {
    await this.db.consentRecords.updateMany({
      where: { userId, purpose, granted: true, revokedAt: null },
      data: { revokedAt: new Date() },
    });

    // Trigger downstream cleanup
    await this.eventBus.publish('consent.revoked', { userId, purpose });
  }
}
```

### Right to Erasure (GDPR Article 17)

```typescript
class DataErasureService {
  // Process deletion request within 30 days (GDPR requirement)
  async processErasureRequest(userId: string): Promise<ErasureReport> {
    const report: ErasureReport = {
      requestId: crypto.randomUUID(),
      userId,
      requestedAt: new Date(),
      systems: [],
    };

    // 1. Identify all systems containing user data
    const systems = await this.dataInventory.getSystemsForUser(userId);

    for (const system of systems) {
      try {
        // Check for legal holds or retention requirements
        const canDelete = await this.checkRetentionRequirements(userId, system);

        if (canDelete) {
          await system.deleteUserData(userId);
          report.systems.push({ name: system.name, status: 'deleted' });
        } else {
          // Anonymize instead of delete (legal obligation exception)
          await system.anonymizeUserData(userId);
          report.systems.push({ name: system.name, status: 'anonymized', reason: 'legal_hold' });
        }
      } catch (error) {
        report.systems.push({ name: system.name, status: 'failed', error: error.message });
      }
    }

    // 2. Notify third-party processors (GDPR Article 17.2)
    await this.notifyProcessors(userId, report);

    // 3. Audit log the erasure (keep minimal record for compliance proof)
    await this.auditLog.record({
      action: 'data.erasure.completed',
      userId: 'REDACTED', // Don't store userId in audit after deletion
      details: { requestId: report.requestId, systemCount: report.systems.length },
    });

    return report;
  }

  // Anonymization (when deletion is not possible)
  async anonymizeUserData(userId: string): Promise<void> {
    const anonymousId = crypto.randomUUID();

    await this.db.$transaction([
      // Replace PII with anonymous values
      this.db.users.update({
        where: { id: userId },
        data: {
          email: `deleted-${anonymousId}@anonymous.invalid`,
          name: 'Deleted User',
          phone: null,
          address: null,
          deletedAt: new Date(),
        },
      }),
      // Keep aggregated data for analytics (no PII)
      this.db.orders.updateMany({
        where: { userId },
        data: { userId: anonymousId },
      }),
    ]);
  }
}
```

---

## Audit Logging

```typescript
// Immutable audit log for compliance
interface AuditEntry {
  id: string;
  timestamp: Date;
  actor: {
    id: string;
    type: 'user' | 'system' | 'admin' | 'api_key';
    ip?: string;
  };
  action: string;           // e.g., 'user.login', 'order.create', 'settings.update'
  resource: {
    type: string;           // e.g., 'user', 'order', 'payment'
    id: string;
  };
  changes?: {
    field: string;
    oldValue: unknown;      // Masked if PII
    newValue: unknown;      // Masked if PII
  }[];
  metadata: {
    userAgent?: string;
    requestId?: string;
    sessionId?: string;
  };
  outcome: 'success' | 'failure' | 'denied';
  reason?: string;          // For denied/failure
}

class AuditLogger {
  // Write-only append (never update or delete audit entries)
  async record(entry: Omit<AuditEntry, 'id' | 'timestamp'>): Promise<void> {
    const fullEntry: AuditEntry = {
      id: crypto.randomUUID(),
      timestamp: new Date(),
      ...entry,
    };

    // Mask PII in changes
    if (fullEntry.changes) {
      fullEntry.changes = fullEntry.changes.map(c => ({
        ...c,
        oldValue: this.maskIfPII(c.field, c.oldValue),
        newValue: this.maskIfPII(c.field, c.newValue),
      }));
    }

    // Write to append-only store (not the main database)
    await this.auditStore.append(fullEntry);

    // For SOC2: also send to SIEM
    if (this.isSecurityEvent(entry.action)) {
      await this.siem.ingest(fullEntry);
    }
  }

  private maskIfPII(field: string, value: unknown): unknown {
    const piiFields = ['email', 'phone', 'ssn', 'address', 'name'];
    if (piiFields.includes(field) && typeof value === 'string') {
      return value.substring(0, 2) + '***' + value.substring(value.length - 2);
    }
    return value;
  }

  private isSecurityEvent(action: string): boolean {
    const securityActions = [
      'user.login', 'user.login_failed', 'user.logout',
      'user.password_changed', 'user.mfa_enabled', 'user.mfa_disabled',
      'admin.role_changed', 'admin.user_deleted',
      'api_key.created', 'api_key.revoked',
      'data.exported', 'data.erasure',
    ];
    return securityActions.some(a => action.startsWith(a));
  }
}
```

---

## Data Retention

```typescript
// Automated data retention enforcement
class DataRetentionService {
  private policies: RetentionPolicy[] = [
    { dataType: 'session_logs', retentionDays: 90, action: 'delete' },
    { dataType: 'audit_logs', retentionDays: 2555, action: 'archive' }, // 7 years for SOC2
    { dataType: 'user_analytics', retentionDays: 365, action: 'anonymize' },
    { dataType: 'payment_records', retentionDays: 2555, action: 'archive' }, // Tax requirements
    { dataType: 'support_tickets', retentionDays: 730, action: 'delete' },
    { dataType: 'ip_addresses', retentionDays: 90, action: 'delete' },
  ];

  // Run daily via cron
  async enforceRetention(): Promise<RetentionReport> {
    const report: RetentionReport = { processedAt: new Date(), results: [] };

    for (const policy of this.policies) {
      const cutoffDate = new Date();
      cutoffDate.setDate(cutoffDate.getDate() - policy.retentionDays);

      try {
        let affected: number;
        switch (policy.action) {
          case 'delete':
            affected = await this.deleteOlderThan(policy.dataType, cutoffDate);
            break;
          case 'anonymize':
            affected = await this.anonymizeOlderThan(policy.dataType, cutoffDate);
            break;
          case 'archive':
            affected = await this.archiveOlderThan(policy.dataType, cutoffDate);
            break;
        }

        report.results.push({
          dataType: policy.dataType,
          action: policy.action,
          recordsAffected: affected,
          status: 'success',
        });
      } catch (error) {
        report.results.push({
          dataType: policy.dataType,
          action: policy.action,
          recordsAffected: 0,
          status: 'failed',
          error: error.message,
        });
      }
    }

    // Audit the retention run itself
    await this.auditLog.record({
      action: 'retention.enforced',
      actor: { id: 'system', type: 'system' },
      resource: { type: 'retention_policy', id: 'daily_run' },
      outcome: report.results.every(r => r.status === 'success') ? 'success' : 'failure',
    });

    return report;
  }
}
```

---

## SOC2 Controls Checklist

```markdown
## SOC2 Type II — Key Technical Controls

### Access Control (CC6)
- [ ] Role-based access control (RBAC) implemented
- [ ] Principle of least privilege enforced
- [ ] MFA required for all admin access
- [ ] Access reviews conducted quarterly
- [ ] Offboarding removes access within 24 hours
- [ ] Service accounts have minimal permissions

### Change Management (CC8)
- [ ] All changes go through PR review
- [ ] CI/CD pipeline enforces tests before deploy
- [ ] Production access restricted (no direct DB access)
- [ ] Rollback procedures documented and tested
- [ ] Change log maintained (git history + deploy log)

### Monitoring (CC7)
- [ ] Security events logged to SIEM
- [ ] Anomaly detection for login patterns
- [ ] Alert on privilege escalation
- [ ] Incident response plan documented
- [ ] Log retention >= 1 year

### Data Protection (CC6.7)
- [ ] Encryption at rest (AES-256)
- [ ] Encryption in transit (TLS 1.2+)
- [ ] Backup encryption
- [ ] Key rotation policy (90 days)
- [ ] Data classification policy documented

### Availability (A1)
- [ ] Uptime SLA defined and monitored
- [ ] Disaster recovery plan tested annually
- [ ] Backup restoration tested quarterly
- [ ] Capacity planning documented
- [ ] Incident communication plan
```

---

## PII Handling Middleware

```typescript
// Express middleware for PII-aware request handling
function piiProtection() {
  return (req: Request, res: Response, next: NextFunction) => {
    // 1. Strip PII from query parameters (prevent URL logging)
    const sensitiveParams = ['email', 'phone', 'ssn', 'token'];
    for (const param of sensitiveParams) {
      if (req.query[param]) {
        req.query[param] = '[REDACTED]';
        // Log warning: PII in URL is a compliance risk
        logger.warn({ param, path: req.path }, 'PII detected in query parameter');
      }
    }

    // 2. Add data processing headers
    res.setHeader('X-Data-Processing', 'compliant');
    res.setHeader('Cache-Control', 'no-store'); // Don't cache PII responses

    // 3. Override res.json to auto-redact PII in responses
    const originalJson = res.json.bind(res);
    res.json = (body: any) => {
      if (req.headers['x-redact-pii'] === 'true') {
        body = redactPII(body);
      }
      return originalJson(body);
    };

    next();
  };
}

function redactPII(obj: any, depth = 0): any {
  if (depth > 10) return obj; // Prevent infinite recursion
  if (typeof obj !== 'object' || obj === null) return obj;

  const piiKeys = ['ssn', 'socialSecurity', 'creditCard', 'cvv'];
  const result: any = Array.isArray(obj) ? [] : {};

  for (const [key, value] of Object.entries(obj)) {
    if (piiKeys.includes(key)) {
      result[key] = '[REDACTED]';
    } else if (typeof value === 'object') {
      result[key] = redactPII(value, depth + 1);
    } else {
      result[key] = value;
    }
  }

  return result;
}
```

---

## Anti-Patterns

| Anti-Pattern | Problem | Solution |
|---|---|---|
| PII in URLs/query params | Logged by proxies, browsers, analytics | Use POST body or headers for PII |
| Audit logs in main database | Can be modified, no separation of concerns | Append-only store, separate from app DB |
| Consent assumed by default | GDPR violation, fines up to 4% revenue | Explicit opt-in, granular per purpose |
| No data inventory | Cannot respond to DSAR within 30 days | Maintain data map of all PII locations |
| Soft-delete only | Data still exists, not truly erased | Hard delete or cryptographic erasure |
| Logging PII for debugging | Compliance violation, data breach risk | Structured logging with PII redaction |
| Same retention for all data | Over-retention or premature deletion | Per-data-type retention policies |
| Manual compliance checks | Drift, human error, audit failures | Automated compliance verification in CI |
