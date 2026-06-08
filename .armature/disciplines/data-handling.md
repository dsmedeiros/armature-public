---
id: data-handling
severity: high
composition-mode: strict
---

# Data Handling

## When to apply

Apply to any code that reads, writes, stores, or transmits user data. Triggered by paths
matching `**/models*`, `**/schema*`, `**/storage*`, `**/data*`, or `**/user*`.

## Standards

1. **Tag PII fields at the definition site.** Every data model field containing personally
   identifiable information must be marked inline:
   ```python
   @dataclass
   class UserRecord:
       user_id: str
       email: str        # PII
       full_name: str    # PII
       created_at: datetime
   ```
   "PII" means: name, email, phone, address, IP address, device ID, or any field that
   alone or in combination identifies a natural person.

2. **Encryption-at-rest checklist (verify before shipping a storage feature):**
   - Database: encryption enabled at the storage layer (confirm in provisioning config)
   - Backups: backup encryption key separate from data encryption key
   - Logs: log storage uses encrypted volumes; log entries do not contain PII (see §4)
   - Temporary files: `/tmp` writes of sensitive data use in-memory alternatives or
     explicitly deleted on process exit

3. **Retention limits: define and enforce, do not just document.** Every data class that
   holds PII must have a corresponding retention policy in the data catalog. Policy must
   specify: maximum age, deletion mechanism (hard delete vs. anonymization), and the
   service responsible for enforcement. Policy not enforced by code or cron is not a policy.

4. **Logging redaction: never log secrets or PII.**
   ```python
   # BAD — logs raw token
   logger.info(f"Auth request: token={request.token}")

   # GOOD — redact before logging
   logger.info("Auth request", extra={"token": "[REDACTED]"})
   ```
   Use a structured logging library with a redaction filter registered for PII field names.
   Test the filter with a dedicated test case that asserts PII fields do not appear in output.

5. **Structured logging required for all data-touching services.** Plain string
   `print()`/`logger.info(f"...")` statements are banned in data-handling code. Use
   `structlog` or `python-json-logger` with field-level control.

## Cross-references

- ARMATURE.md §3 (agent behavioral rules)
- `owasp-checklist.md` (A02 cryptographic failures, A01 access control)
- `error-handling.md` (fail loudly for encryption configuration errors)
