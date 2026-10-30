# Owner Control Plane

## Purpose

Customer signing keys are authority anchors. Enrolling, rotating, or revoking one is a privileged owner operation, not an ordinary customer or worker action.

The `OwnerKeyControl` application service is the only intended application boundary for these operations. It authenticates a credential through an injected `CredentialAuthenticator`, checks the verified principal's owner-key-administration role and expiry, and derives the audit actor from the verified subject. Callers cannot choose the audit actor independently.

## Trust boundary

```text
HTTP / CLI / future UI
        |
        | bearer credential
        v
CredentialAuthenticator (trusted identity adapter)
        |
        | verified issuer, subject, roles, expiry, session
        v
OwnerKeyControl
        |
        | owner:key_admin required
        v
TrustedCustomerKeyRegistry
        |
        v
Append-only key lifecycle audit
```

The authenticator is security-critical. A production adapter MUST validate credential signature, issuer, audience, expiry, not-before, key rotation, revocation/session state, and required authentication assurance. It must map roles from trusted identity-provider claims or an independently controlled authorization store. It must never accept role, subject, issuer, or actor identity from request body or untrusted headers.

The repository currently has no HTTP API or production identity provider. Therefore this commit defines and tests the application boundary and adapter contract; it does NOT claim that production authentication, MFA, OIDC integration, session revocation, or network-level access control is deployed. The included test authenticator is test-only.

## Authorization rules

- Only a principal carrying `owner:key_admin` can enroll, rotate, or revoke customer keys.
- Customer, worker, and read-only principals are denied.
- Missing, invalid, malformed, or expired credentials fail closed.
- Audit actor identity is always `principal.subject`.
- The key registry retains its low-level methods for internal use and migration compatibility. Production entrypoints must expose the control service, not the registry directly.

## Operational requirements before production

1. Select an identity provider and define owner account recovery.
2. Implement a production authenticator with strict issuer and audience pinning.
3. Require phishing-resistant MFA (prefer WebAuthn/passkeys) for key administration.
4. Add session revocation and step-up authentication for rotation/revocation.
5. Keep registry database access private to the service process.
6. Add rate limits, alerting, backup/restore tests, and external security review.

## Known limitation

The registry's SHA-256 audit chain is tamper-evident, not tamper-proof. An attacker able to rewrite the entire database and recompute the chain may forge local history. Production needs an independently protected checkpoint or external append-only/WORM audit sink.
