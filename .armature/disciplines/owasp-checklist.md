---
id: owasp-checklist
severity: high
composition-mode: advisory
---

# OWASP Top 10 Checklist

## When to apply

Apply to any feature that handles auth, user input, or external data. Triggered by paths
matching `**/auth*`, `**/api*`, `**/routes*`, `**/views*`.

## Standards

1. **A01 — Broken Access Control.** Verify authorization for the specific resource before
   access (not just authentication). Default-deny. Never trust client-supplied IDs without
   ownership check.

2. **A02 — Cryptographic Failures.** AES-256-GCM for encryption; bcrypt/scrypt/Argon2 for
   passwords. Never roll your own crypto or commit secrets to version control.

3. **A03 — Injection.** Parameterize all queries:
   `cursor.execute("SELECT * FROM users WHERE id = %s", (uid,))` — correct.
   `cursor.execute(f"SELECT ... WHERE id = {uid}")` — injection vulnerability.

4. **A04 — Insecure Design.** Threat-model new features: name trust boundaries, data
   flows, and abuse scenarios. Document in the ADR or design doc before implementation.

5. **A05 — Security Misconfiguration.** Remove default credentials before deployment.
   Disable debug endpoints and verbose errors in production. Config is environment-specific.

6. **A06 — Vulnerable Components.** Run `pip audit` / `npm audit` in CI. Block merges
   with HIGH or CRITICAL CVEs. Pin versions in lock files; update on a defined schedule.

7. **A07 — Auth Failures.** Enforce MFA for admin accounts. Lock out after ≤10 failed
   attempts. Rotate session tokens on privilege escalation. JWT expiry ≤1 hour.

8. **A08 — Integrity Failures.** Verify artifact checksums. Never `pickle.load` or
   `yaml.load` untrusted data (use `yaml.safe_load`). Pin CI action versions to SHA.

9. **A09 — Logging Failures.** Log auth events (success + failure) and authz failures.
   No PII or secrets in logs. Alert on repeated auth failures.

10. **A10 — SSRF.** Allowlist URLs server-side. Block `169.254.0.0/16`, `10.0.0.0/8`,
    `172.16.0.0/12`, `192.168.0.0/16`. Never pass user URLs to `requests.get()` directly.

## Cross-references

- ARMATURE.md §3 (agent behavioral rules)
- `data-handling.md` (PII tagging, logging redaction)
- `error-handling.md` (structured error types for security failures)
