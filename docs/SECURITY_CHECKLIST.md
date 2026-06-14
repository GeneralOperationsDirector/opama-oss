# Security Checklist for Production Launch

## ✅ Pre-Launch Security Audit

### 🔴 Critical (Must Fix Before Launch)

- [ ] **Rotate all exposed API keys**
  - [ ] OpenAI API key
  - [ ] eBay API credentials
  - [ ] Any other keys in committed .env files

- [ ] **Check git history for secrets**
  ```bash
  # Search for potential secrets
  git log --all --full-history -- .env.local
  git log --all --full-history -- .env

  # If found, remove from history
  git filter-branch --force --index-filter \
    "git rm --cached --ignore-unmatch .env.local" \
    --prune-empty --tag-name-filter cat -- --all
  ```

- [ ] **Implement Authentication**
  - [ ] User registration endpoint
  - [ ] Login endpoint (JWT or session)
  - [ ] Password hashing (bcrypt, argon2)
  - [ ] Token validation middleware
  - [ ] Protected routes check user ownership

- [ ] **Remove debug endpoints**
  - [ ] Remove `/inventory/backup/db`
  - [ ] Remove `/debug/db-info`
  - [ ] Or add authentication to these endpoints

- [ ] **Environment variable protection**
  - [ ] Verify `.env.local` is in `.gitignore`
  - [ ] Verify `.env` is in `.gitignore`
  - [ ] Create `.env.example` with placeholder values
  - [ ] Document all required env vars

- [ ] **HTTPS enforcement**
  - [ ] Configure SSL certificate (Let's Encrypt)
  - [ ] Force HTTPS redirect in nginx
  - [ ] Set HSTS headers
  - [ ] Update CORS to allow HTTPS origin only

### 🟡 High Priority (Fix in First Week)

- [ ] **Rate Limiting**
  - [ ] Install `slowapi` or `fastapi-limiter`
  - [ ] Add rate limits to all endpoints
  - [ ] Stricter limits on expensive operations:
    - `/ai/chat` - 10 requests/hour per user
    - `/suggest/*` - 30 requests/hour per user
    - Auth endpoints - 5 failures/hour per IP

- [ ] **Input Validation**
  - [ ] Validate all Pydantic models
  - [ ] Add max length constraints on strings
  - [ ] Validate numeric ranges (quantity > 0, limit <= 500)
  - [ ] Sanitize user-generated content (deck names, notes)

- [ ] **CORS Configuration**
  - [ ] Move allowed origins to environment variable
  ```python
  # In .env
  CORS_ORIGINS=https://yourdomain.com,https://www.yourdomain.com

  # In main.py
  import os
  allowed_origins = os.getenv("CORS_ORIGINS", "").split(",")
  app.add_middleware(CORSMiddleware, allow_origins=allowed_origins, ...)
  ```

- [ ] **SQL Injection Prevention**
  - [x] Already using SQLModel (parameterized queries) ✅
  - [ ] Verify no raw SQL in codebase
  ```bash
  # Check for raw SQL
  grep -r "execute\(" app/ --include="*.py"
  grep -r "session.exec" app/ --include="*.py"
  ```

- [ ] **Error Handling**
  - [ ] Don't expose stack traces to users
  - [ ] Log errors server-side only
  - [ ] Return generic error messages
  ```python
  # Bad
  except Exception as e:
      raise HTTPException(500, detail=str(e))

  # Good
  except Exception as e:
      logger.error(f"Error in endpoint: {e}")
      raise HTTPException(500, detail="Internal server error")
  ```

### 🟢 Medium Priority (Fix in First Month)

- [ ] **Session Management**
  - [ ] Set secure session cookie flags
  ```python
  # httpOnly, secure, sameSite
  response.set_cookie(
      key="session",
      value=token,
      httponly=True,
      secure=True,  # HTTPS only
      samesite="strict",
      max_age=3600
  )
  ```

- [ ] **Content Security Policy (CSP)**
  - [ ] Add CSP headers to prevent XSS
  ```nginx
  # In nginx config
  add_header Content-Security-Policy "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline';" always;
  ```

- [ ] **API Key Rotation Policy**
  - [ ] Document key rotation process
  - [ ] Set up key rotation schedule (every 90 days)
  - [ ] Implement graceful key rotation (support 2 keys simultaneously)

- [ ] **Database Security**
  - [ ] Use read-only database user for read endpoints
  - [ ] Restrict database user permissions
  - [ ] Enable PostgreSQL SSL connections
  - [ ] Regular backups with encryption

- [ ] **Dependency Security**
  - [ ] Run `pip audit` for Python packages
  ```bash
  pip install pip-audit
  pip-audit
  ```
  - [ ] Run `npm audit` for frontend
  ```bash
  cd opama-ui
  npm audit
  npm audit fix
  ```
  - [ ] Set up Dependabot alerts on GitHub

- [ ] **Logging & Monitoring**
  - [ ] Don't log sensitive data (passwords, tokens, API keys)
  - [ ] Implement structured logging (JSON format)
  - [ ] Send logs to external service (CloudWatch, Datadog)
  - [ ] Set up alerts for:
    - Failed login attempts (>5 in 10 minutes)
    - 500 errors (>10 in 5 minutes)
    - High OpenAI costs (>$10/hour)

### 🔵 Low Priority (Nice to Have)

- [ ] **Security Headers**
  ```nginx
  # In nginx config
  add_header X-Frame-Options "SAMEORIGIN" always;
  add_header X-Content-Type-Options "nosniff" always;
  add_header X-XSS-Protection "1; mode=block" always;
  add_header Referrer-Policy "strict-origin-when-cross-origin" always;
  ```

- [ ] **API Versioning**
  - [ ] Version your API (`/api/v1/...`)
  - [ ] Maintain backward compatibility
  - [ ] Deprecation notices

- [ ] **Penetration Testing**
  - [ ] Run OWASP ZAP scan
  - [ ] Test for common vulnerabilities
  - [ ] Fix any findings

- [ ] **Compliance**
  - [ ] GDPR compliance (if serving EU users)
    - Data export endpoint
    - Data deletion endpoint
    - Privacy policy
    - Cookie consent
  - [ ] CCPA compliance (if serving California users)

---

## 🛡️ Security Best Practices

### Code Review Checklist

Before merging any PR, check:

- [ ] No hardcoded secrets (API keys, passwords)
- [ ] All user inputs are validated
- [ ] Errors don't leak sensitive info
- [ ] New endpoints are authenticated
- [ ] Rate limiting is applied
- [ ] SQL queries use parameterization
- [ ] File uploads are validated (if applicable)

### Development Workflow

1. **Never commit secrets**
   - Use `.env.local` for local development
   - Use secret manager in production

2. **Use pre-commit hooks**
   ```bash
   # Install pre-commit
   pip install pre-commit

   # Add to .pre-commit-config.yaml
   repos:
   - repo: https://github.com/Yelp/detect-secrets
     rev: v1.4.0
     hooks:
     - id: detect-secrets
   ```

3. **Regular security updates**
   - Update dependencies monthly
   - Subscribe to security advisories
   - Monitor CVE databases

4. **Principle of Least Privilege**
   - Database users have minimal permissions
   - API keys have minimal scopes
   - User roles limit access

---

## 📋 Testing Security

### Automated Security Tests

```python
# test_security.py
import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_protected_endpoint_without_auth():
    """Verify protected endpoints reject unauthenticated requests"""
    response = client.get("/inventory/1")
    assert response.status_code == 401

def test_user_cannot_access_other_user_data():
    """Verify user can only access their own data"""
    # Login as user 1
    login1 = client.post("/auth/login", json={"email": "user1@example.com", "password": "pass"})
    token1 = login1.json()["access_token"]

    # Try to access user 2's inventory
    response = client.get("/inventory/2", headers={"Authorization": f"Bearer {token1}"})
    assert response.status_code == 403

def test_rate_limiting():
    """Verify rate limiting works"""
    for i in range(101):
        response = client.get("/cards")
    assert response.status_code == 429  # Too Many Requests

def test_sql_injection():
    """Verify SQL injection is prevented"""
    malicious_input = "1' OR '1'='1"
    response = client.get(f"/cards/{malicious_input}")
    # Should return 404, not 200 with all cards
    assert response.status_code == 404

def test_xss_prevention():
    """Verify XSS is prevented in user content"""
    malicious_name = "<script>alert('XSS')</script>"
    response = client.post(
        "/decks",
        json={"name": malicious_name, "user_id": 1, "format": "standard"}
    )
    # Name should be sanitized
    assert "<script>" not in response.json()["name"]
```

### Manual Security Testing

1. **Test authentication flows**
   - Try accessing protected endpoints without token
   - Try using expired tokens
   - Try accessing other users' data

2. **Test rate limiting**
   - Make 100+ requests rapidly
   - Verify 429 response

3. **Test input validation**
   - Send malformed JSON
   - Send extremely long strings
   - Send negative numbers where positive expected

4. **Test error messages**
   - Verify no stack traces exposed
   - Verify no database errors exposed

---

## 🚨 Incident Response Plan

If a security breach occurs:

1. **Immediate Response**
   - [ ] Rotate all API keys immediately
   - [ ] Force logout all users (invalidate all tokens)
   - [ ] Take affected services offline if necessary

2. **Investigation**
   - [ ] Check logs for suspicious activity
   - [ ] Identify scope of breach (what data was accessed)
   - [ ] Document timeline of events

3. **Remediation**
   - [ ] Fix vulnerability
   - [ ] Deploy patch
   - [ ] Verify fix works

4. **Communication**
   - [ ] Notify affected users (if PII exposed)
   - [ ] Post incident report
   - [ ] Update security practices

5. **Prevention**
   - [ ] Conduct post-mortem
   - [ ] Update security checklist
   - [ ] Add tests to prevent recurrence

---

## 📞 Resources

- **OWASP Top 10:** https://owasp.org/www-project-top-ten/
- **FastAPI Security:** https://fastapi.tiangolo.com/tutorial/security/
- **CWE Top 25:** https://cwe.mitre.org/top25/
- **Python Security Best Practices:** https://snyk.io/blog/python-security-best-practices/
- **React Security:** https://snyk.io/blog/10-react-security-best-practices/

---

## ✍️ Sign-off

Before launching to production, the following people must review and approve:

- [ ] Lead Developer: _______________
- [ ] Security Engineer: _______________
- [ ] DevOps Engineer: _______________

**Date of last security audit:** _______________
**Next scheduled audit:** _______________
