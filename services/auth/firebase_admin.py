"""
Firebase Admin SDK initialization and utilities.

This module initializes the Firebase Admin SDK for server-side authentication.
"""

import firebase_admin
from firebase_admin import credentials, auth
import os

# Initialize Firebase Admin SDK
# For development, we use Application Default Credentials
# For production, set FIREBASE_SERVICE_ACCOUNT_KEY environment variable
# with path to service account JSON file

_app = None


def init_firebase_admin():
    """
    Initialize Firebase Admin SDK.

    For token verification, Firebase Admin SDK can work without credentials
    by fetching public keys from Firebase. This is suitable for development.

    For production or when accessing other Firebase services (Firestore, etc.),
    set FIREBASE_SERVICE_ACCOUNT_KEY environment variable with path to
    service account JSON file.
    """
    global _app

    if _app is not None:
        return _app

    try:
        service_account_path = os.getenv("FIREBASE_SERVICE_ACCOUNT_KEY")
        firebase_project_id = os.getenv("FIREBASE_PROJECT_ID", "")

        if service_account_path and os.path.exists(service_account_path):
            # Use service account key file
            cred = credentials.Certificate(service_account_path)
            _app = firebase_admin.initialize_app(cred)
            print(f"✓ Firebase Admin initialized with service account for project: {firebase_project_id}")
        else:
            # For development: Initialize with project ID only
            # This works for token verification using Google's public keys
            print("⚠️  No service account key found. Attempting credential-less initialization...")
            print(f"   Project ID: {firebase_project_id}")

            try:
                # Try credential-less initialization (works in some environments)
                _app = firebase_admin.initialize_app(options={
                    'projectId': firebase_project_id,
                })
                print(f"✓ Firebase Admin initialized for project: {firebase_project_id}")
            except Exception as init_error:
                print(f"⚠️  Credential-less initialization failed: {init_error}")
                print("   Firebase Admin requires a service account key for local development.")
                print("   Download the key from Firebase Console and set FIREBASE_SERVICE_ACCOUNT_KEY")
                raise ValueError(
                    "Firebase Admin initialization failed. Service account key required. "
                    "See backend logs for instructions."
                )

    except ValueError as ve:
        # If already initialized, get the default app
        if "already exists" in str(ve).lower():
            _app = firebase_admin.get_app()
            print("✓ Firebase Admin already initialized")
        else:
            raise
    except Exception as e:
        print(f"❌ Firebase Admin initialization failed: {e}")
        print("\n" + "="*60)
        print("FIREBASE SETUP REQUIRED:")
        print("="*60)
        print("1. Go to: https://console.firebase.google.com/")
        print(f"2. Select project: {os.getenv('FIREBASE_PROJECT_ID', '<your Firebase project>')}")
        print("3. Settings → Service Accounts")
        print("4. Click 'Generate New Private Key'")
        print("5. Save as: firebase-service-account.json")
        print("6. Set environment variable:")
        print("   FIREBASE_SERVICE_ACCOUNT_KEY=/path/to/firebase-service-account.json")
        print("="*60 + "\n")
        _app = None
        # Don't raise - let the app start but auth will fail with helpful errors

    return _app


import time

# In-memory cache: token -> (claims_dict, expiry_timestamp)
# Cache for 5 minutes so revoked tokens or disabled accounts take effect promptly.
# (Firebase tokens are valid for 1 hour but we don't trust them that long.)
_token_cache: dict[str, tuple[dict, float]] = {}
_CACHE_TTL = 5 * 60  # seconds


def _verify_via_rest(id_token: str) -> dict:
    """
    Verify a Firebase ID token using the Firebase Auth REST API.
    Requires only the Web API Key — no service account needed.
    """
    import requests as req

    api_key = os.getenv("FIREBASE_WEB_API_KEY", "")
    if not api_key:
        raise ValueError("FIREBASE_WEB_API_KEY env var not set")

    url = f"https://identitytoolkit.googleapis.com/v1/accounts:lookup?key={api_key}"
    resp = req.post(url, json={"idToken": id_token}, timeout=10)

    if resp.status_code != 200:
        raise ValueError(f"Token rejected by Firebase: {resp.text}")

    users = resp.json().get("users", [])
    if not users:
        raise ValueError("No user returned by Firebase token lookup")

    u = users[0]
    return {
        "uid": u["localId"],
        "email": u.get("email"),
        "name": u.get("displayName"),
    }


def verify_id_token(id_token: str) -> dict:
    """
    Verify a Firebase ID token and return the decoded claims.

    Tries the Admin SDK first (works when a service account key is configured).
    Falls back to the Firebase REST API (works with just the Web API Key).
    Results are cached for 55 minutes to avoid a network round-trip on every request.
    """
    # Check cache first
    cached = _token_cache.get(id_token)
    if cached:
        claims, expiry = cached
        if time.time() < expiry:
            return claims
        else:
            del _token_cache[id_token]

    # Try Admin SDK path first
    if _app is not None:
        try:
            claims = auth.verify_id_token(id_token)
            _token_cache[id_token] = (claims, time.time() + _CACHE_TTL)
            return claims
        except Exception as e:
            print(f"⚠️  Admin SDK verification failed, trying REST: {e}")

    # REST fallback — works without a service account
    try:
        claims = _verify_via_rest(id_token)
        _token_cache[id_token] = (claims, time.time() + _CACHE_TTL)
        return claims
    except ValueError:
        raise
    except Exception as e:
        raise ValueError(f"Invalid Firebase ID token: {e}")


def get_user_by_uid(uid: str):
    """
    Get user data from Firebase by UID.

    Args:
        uid: Firebase user UID

    Returns:
        UserRecord: Firebase user record
    """
    if _app is None:
        init_firebase_admin()

    return auth.get_user(uid)
