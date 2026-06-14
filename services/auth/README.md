# Auth (`services/auth`)

Token verification and the `get_current_user` dependency that every protected
endpoint across opama depends on.

- **Not part of the plugin system** — no `plugin.yaml`. Always loaded by
  `app/main.py` before any plugin router, because plugins depend on
  `get_current_user`.
- Mounted at `/auth` (`router.py`)
- `middleware.py` — `get_current_user`, `get_optional_user`, `require_admin`
  dependencies
- `providers/` — pluggable backends selected by `AUTH_PROVIDER`:
  - `local_provider.py` — username/(optional) password accounts, the
    self-hosted OSS default. Issues/verifies its own signed tokens
    (`issue_token`, `credential_for`, `LOCAL_AUTH_SECRET`).
  - `firebase_provider.py` — Firebase ID token verification (Admin SDK,
    falling back to the REST API) for cloud/multi-tenant deployments.
  - `base.py` — shared provider interface; `provider_name()` reports which is
    active.
- `firebase_admin.py` — `init_firebase_admin()`, called once at startup when
  `AUTH_PROVIDER=firebase`.

## Endpoints

```
GET    /auth/config        # { provider, instance_exposed } — drives frontend AuthModal
GET    /auth/me            # current user profile
PATCH  /auth/me            # update profile (display name, etc.)
DELETE /auth/me            # delete account
POST   /auth/login         # local provider only
POST   /auth/register       # local provider only
POST   /auth/set-password  # local provider only — escalates a passwordless account
```

Firebase-mode login/signup happens client-side via the Firebase JS SDK
(`createUserWithEmailAndPassword`/`signInWithEmailAndPassword`); the backend
only verifies the resulting ID token on each request.

## Dependencies

- `services.shared.database.get_session`
- `services.shared.models.User`
- `services.shared.audit.write_audit_log`

Every other plugin depends on `services.auth.middleware.get_current_user` (or
`get_optional_user`/`require_admin`). This makes `auth` the one module that
cannot be disabled or relocated independently without breaking everything
else — it is intentionally excluded from `ENABLED_PLUGINS` filtering.

## Status

Core, in-tree, always loaded. Not a repo-split candidate.
