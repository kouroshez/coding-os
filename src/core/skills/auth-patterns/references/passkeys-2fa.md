# Passkeys + 2FA — Implementation Patterns

The two strong-auth methods worth implementing in 2026. Passkeys are the new default; TOTP 2FA is the universal fallback.

## Passkeys (WebAuthn / FIDO2)

A passkey is an asymmetric keypair bound to a (user, relying-party) pair. The private key never leaves the user's device (or its synced password manager — iCloud Keychain, Google Password Manager, 1Password). The server only stores the public key.

Phishing-proof: the browser/OS verifies the relying-party origin before signing. A fake site can't trick the device into producing a valid signature.

### Database Schema

```sql
CREATE TABLE passkey_credentials (
    credential_id     BYTEA       PRIMARY KEY,           -- WebAuthn credential id (raw bytes)
    user_id           TEXT        NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    public_key        BYTEA       NOT NULL,              -- COSE-encoded key
    sign_count        BIGINT      NOT NULL DEFAULT 0,    -- replay defense (some authenticators)
    transports        TEXT[]      NOT NULL DEFAULT '{}', -- "internal", "hybrid", "usb", "nfc", "ble"
    aaguid            UUID,                              -- authenticator make/model
    backup_eligible   BOOLEAN     NOT NULL DEFAULT false,
    backup_state      BOOLEAN     NOT NULL DEFAULT false,
    nickname          TEXT,                              -- user-given name ("MacBook", "iPhone")
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_used_at      TIMESTAMPTZ
);

CREATE INDEX idx_passkey_user ON passkey_credentials(user_id);

-- Per-flow challenge storage (short-lived):
CREATE TABLE webauthn_challenges (
    challenge   BYTEA       PRIMARY KEY,
    user_id     TEXT        NOT NULL,
    purpose     TEXT        NOT NULL CHECK (purpose IN ('register', 'authenticate')),
    expires_at  TIMESTAMPTZ NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### Registration Flow

```
1. Client: POST /auth/passkey/register/begin
   Body: { user_id }   (user already authenticated via existing method)

2. Server:
   - Generate random 32-byte challenge
   - Store in webauthn_challenges with purpose='register', exp=NOW()+5min
   - Return:
     {
       rp:        { id: "app.com", name: "My App" },
       user:      { id: <random user-handle>, name: "user@example.com", displayName: "Name" },
       challenge: <b64url>,
       pubKeyCredParams: [
         { type: "public-key", alg: -7 },   // ES256
         { type: "public-key", alg: -8 },   // EdDSA
         { type: "public-key", alg: -257 }, // RS256
       ],
       authenticatorSelection: {
         residentKey: "preferred",
         userVerification: "preferred",
       },
       attestation: "none",                 // skip attestation unless you have a reason
       timeout: 60000,
     }

3. Client (browser/RN): navigator.credentials.create({ publicKey: ... })
   On RN: use react-native-passkey (Expo) or expo-secure-store-based bridge.

4. Server: POST /auth/passkey/register/finish
   Body: { credential, transports }

5. Server validates:
   - Lookup challenge, verify not expired, mark used.
   - Verify clientDataJSON.type === "webauthn.create"
   - Verify clientDataJSON.challenge matches
   - Verify clientDataJSON.origin === expected origin
   - Verify rpIdHash inside attestationObject matches SHA-256("app.com")
   - Extract + store public key + credential id + transports + flags.

   Use simplewebauthn (Node) / py_webauthn (Python) / go-webauthn (Go).
   Never roll your own.
```

### Authentication Flow

```
1. Client: POST /auth/passkey/authenticate/begin
   Body: { user_identifier?: "user@example.com" }   // optional — true username-less is supported

2. Server:
   - Lookup user (if identifier provided)
   - Get list of registered credential IDs for this user
   - Generate challenge, store with purpose='authenticate', exp=NOW()+5min
   - Return:
     {
       challenge: <b64url>,
       rpId: "app.com",
       allowCredentials: [
         { type: "public-key", id: <cred_id>, transports: [...] },
         ...
       ],
       userVerification: "preferred",
       timeout: 60000,
     }

3. Client: navigator.credentials.get({ publicKey: ... })

4. Server: POST /auth/passkey/authenticate/finish
   Body: { assertion }

5. Server:
   - Lookup credential by id
   - Verify signature using stored public key against (clientDataJSON || authenticatorData)
   - Verify challenge, origin, rpId hash
   - Verify userPresent flag (always required); userVerified if you require strong auth
   - If sign_count > 0 in stored, verify new signCount > stored (replay defense)
   - Update last_used_at, sign_count
   - Issue session token → return as in any sign-in flow.
```

### Production Tips

- **Display name + nickname** for each credential — users with multiple devices need to know which to deregister.
- **At least 2 passkeys per account** before allowing the user to disable password — single credential = single point of lockout.
- **Re-auth required** to add or remove a passkey (fresh-session ≤5 min OR password re-prompt).
- **Don't use attestation** unless you actually have a policy that needs it (e.g., enterprise device-bound). Most consumer apps: `attestation: "none"`.
- **`backupEligible` / `backupState`** flags tell you whether the credential is sync'd via iCloud/Google. Synced credentials = lower lockout risk; consider skipping the "add a 2nd passkey" prompt for them.
- **TOTP fallback** for users who can't / won't use passkeys. NEVER passwords-only.

### Client Library Choices

- **Web** — browser native (`navigator.credentials`), wrapped by `simplewebauthn/browser`.
- **React Native (Expo)** — `expo-passkey` or `react-native-passkey`. Both call into native APIs (ASAuthorization on iOS, CredentialManager on Android 14+).
- **React Native (bare)** — `react-native-passkey` or DIY native module using AuthenticationServices (iOS) and Credential Manager (Android).

Both platforms require **associated domains** setup:

- iOS: `apple-app-site-association` file at `https://app.com/.well-known/apple-app-site-association`.
- Android: `assetlinks.json` at `https://app.com/.well-known/assetlinks.json`.

Without these, the OS refuses to bind passkeys to your origin.

## TOTP 2FA — Universal Fallback

For users who can't (or won't) use passkeys. RFC 6238.

### Schema

```sql
CREATE TABLE totp_secrets (
    user_id            TEXT        PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    secret_encrypted   BYTEA       NOT NULL,                -- envelope encrypted via KMS
    enrolled_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_used_at       TIMESTAMPTZ
);

CREATE TABLE totp_backup_codes (
    id            BIGSERIAL    PRIMARY KEY,
    user_id       TEXT         NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    code_hash     TEXT         NOT NULL,                  -- Argon2id hash
    used_at       TIMESTAMPTZ,                            -- NULL = unused
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_backup_codes_user_unused
    ON totp_backup_codes(user_id) WHERE used_at IS NULL;
```

### Enrollment

```python
import secrets
import base64
import pyotp
from cryptography.fernet import Fernet  # or your KMS wrapper

def begin_totp_enrollment(user, account_email):
    secret = pyotp.random_base32()                              # 32 chars, 160-bit entropy
    encrypted = kms_encrypt(secret.encode())                     # envelope encrypt
    # Store as PENDING — only commit on first valid verification
    pending_store.put(user.id, encrypted, ttl_seconds=600)
    uri = pyotp.TOTP(secret).provisioning_uri(
        name=account_email, issuer_name="MyApp",
    )
    return {"uri": uri, "qr_payload": uri}                       # render QR on client


def confirm_totp_enrollment(user, code):
    encrypted = pending_store.get(user.id)
    if not encrypted: raise EnrollmentExpired
    secret = kms_decrypt(encrypted).decode()
    if not pyotp.TOTP(secret).verify(code, valid_window=1):
        raise InvalidCode
    db.execute("INSERT INTO totp_secrets (user_id, secret_encrypted) VALUES ($1, $2)",
               user.id, encrypted)
    pending_store.delete(user.id)
    return generate_backup_codes(user)
```

### Verification

```python
def verify_totp(user, code):
    encrypted = db.fetch_one("SELECT secret_encrypted FROM totp_secrets WHERE user_id = $1", user.id)
    if not encrypted: return False
    secret = kms_decrypt(encrypted["secret_encrypted"]).decode()
    return pyotp.TOTP(secret).verify(code, valid_window=1)        # ±30s
```

Rate limit: 5 attempts per 5 minutes per user. Lock account on 10 failed attempts in 15 minutes (with admin/email recovery).

### Backup Codes

```python
import argon2

def generate_backup_codes(user, n=10):
    plaintext = [secrets.token_urlsafe(8).replace("_", "").replace("-", "").upper()[:8] for _ in range(n)]
    ph = argon2.PasswordHasher()
    rows = [(user.id, ph.hash(code)) for code in plaintext]
    db.execute_many("INSERT INTO totp_backup_codes (user_id, code_hash) VALUES ($1, $2)", rows)
    return plaintext  # show ONCE; user MUST save


def consume_backup_code(user, code):
    rows = db.fetch_all(
        "SELECT id, code_hash FROM totp_backup_codes WHERE user_id = $1 AND used_at IS NULL",
        user.id,
    )
    ph = argon2.PasswordHasher()
    for row in rows:
        try:
            ph.verify(row["code_hash"], code)
            db.execute("UPDATE totp_backup_codes SET used_at = NOW() WHERE id = $1", row["id"])
            return True
        except argon2.exceptions.VerifyMismatchError:
            continue
    return False
```

Format: 8-character base32-like alphanumeric (e.g., `K8FH2NQR`). Easy to type, hard to brute force, distinct from real codes.

### Recovery

If user loses both phone (no TOTP) and backup codes:

1. They contact support.
2. Identity verified out-of-band (KYC, gov ID, manager approval, etc.) — DO NOT make this easy.
3. Support agent triggers a 24-48 hour cooling-off period during which the account is frozen.
4. After the cool-off, a unique recovery link is emailed.
5. User completes recovery; ALL sessions and devices revoked; ALL credentials reset.

This is where attackers attack. The cool-off + out-of-band check is the single most important defense.

## When to Skip 2FA

- Don't skip for: any account with payment, PII, or write access to shared resources.
- DO skip the prompt for: low-value accounts where forcing 2FA would crater conversion (early product). Offer it as opt-in.
- Once enabled, 2FA cannot be silently disabled — always require fresh-session + email confirmation.

## Step-Up Authentication

Some operations need stronger auth than the session provides (e.g., transferring money, deleting account, disabling 2FA):

- Re-prompt for password OR passkey OR TOTP.
- Mark the session as "fresh" with a timestamp.
- Operation requires `fresh_at > NOW() - INTERVAL '5 min'`.
- After the operation, fresh marker decays.

```sql
ALTER TABLE sessions ADD COLUMN fresh_until TIMESTAMPTZ;

-- When user re-authenticates for a sensitive op:
UPDATE sessions SET fresh_until = NOW() + INTERVAL '5 minutes' WHERE id = $1;

-- Sensitive endpoint guard:
SELECT 1 FROM sessions WHERE id = $1 AND fresh_until > NOW();
-- → 0 rows → 401, prompt for re-auth
```

## Source Material

- *FIDO Alliance — Passkey UX Guidelines* (current, updated 2025).
- *WebAuthn Level 3* spec (W3C 2024 candidate recommendation).
- *RFC 6238* — TOTP.
- *OWASP Authentication Cheat Sheet*.
- *RFC 9800* — Passkey-related threat model (2024 draft).
- `simplewebauthn` (TS), `py_webauthn` (Python), `go-webauthn` (Go) — battle-tested libs.
