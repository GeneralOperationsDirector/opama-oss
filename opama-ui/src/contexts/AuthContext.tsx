import React, { createContext, useContext, useEffect, useState } from 'react';
import {
  signInWithEmailAndPassword,
  createUserWithEmailAndPassword,
  signOut,
  onAuthStateChanged,
  GoogleAuthProvider,
  signInWithPopup,
  type User as FirebaseUser,
} from 'firebase/auth';
import { auth } from '../lib/firebase';
import {
  getAuthProviderName,
  getStoredLocalToken,
  setStoredLocalToken,
  type AuthProviderName,
} from '../lib/authToken';
import { API_BASE } from '../lib/api';

/**
 * Unified user shape exposed to the app regardless of which auth provider is
 * active. Firebase accounts are mapped onto this from the Firebase `User`;
 * local accounts are mapped from the `/auth/me` profile response.
 *
 * `providerId` mirrors Firebase's `providerData[0].providerId` ("google.com" |
 * "password") and is undefined for local accounts — ProfileTab uses it to
 * render provider-specific account info.
 */
export interface AppUser {
  uid: string;
  email: string | null;
  displayName: string | null;
  providerId?: string;
}

interface LocalProfile {
  id: number;
  email: string | null;
  display_name: string | null;
}

interface TokenResponse {
  token: string;
  user: LocalProfile;
}

function fromFirebaseUser(user: FirebaseUser): AppUser {
  return {
    uid: user.uid,
    email: user.email,
    displayName: user.displayName,
    providerId: user.providerData?.[0]?.providerId,
  };
}

function fromLocalProfile(profile: LocalProfile): AppUser {
  return {
    uid: String(profile.id),
    email: profile.email,
    displayName: profile.display_name,
  };
}

async function postJSON<T>(path: string, body: unknown): Promise<T> {
  const r = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!r.ok) {
    const text = await r.text().catch(() => `${r.status} ${r.statusText}`);
    let detail = text;
    try {
      detail = JSON.parse(text)?.detail ?? text;
    } catch {
      /* not JSON — use raw text */
    }
    throw new Error(detail || 'Request failed');
  }
  return (await r.json()) as T;
}

async function fetchLocalProfile(token: string): Promise<LocalProfile> {
  const r = await fetch(`${API_BASE}/auth/me`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!r.ok) throw new Error('Failed to load profile');
  return (await r.json()) as LocalProfile;
}

interface AuthContextType {
  currentUser: AppUser | null;
  loading: boolean;
  /** Which provider this instance runs — drives AuthModal's field choices. */
  authProvider: AuthProviderName;
  /** Firebase mode: (email, password). Local mode: (username, password — password optional). */
  login: (identifier: string, password: string) => Promise<void>;
  signup: (identifier: string, password: string) => Promise<void>;
  loginWithGoogle: () => Promise<void>;
  logout: () => Promise<void>;
  getIdToken: () => Promise<string | null>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [currentUser, setCurrentUser] = useState<AppUser | null>(null);
  const [loading, setLoading] = useState(true);
  const [provider, setProvider] = useState<AuthProviderName | null>(null);

  // 1. Resolve which provider this instance runs (cached after first call).
  useEffect(() => {
    let cancelled = false;
    getAuthProviderName().then((p) => {
      if (!cancelled) setProvider(p);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  // 2. Wire up the matching auth flow once the provider is known.
  useEffect(() => {
    if (provider === null) return;

    if (provider === 'firebase') {
      const unsubscribe = onAuthStateChanged(auth, (user) => {
        setCurrentUser(user ? fromFirebaseUser(user) : null);
        setLoading(false);
      });
      return unsubscribe;
    }

    // Local mode: restore the session from a stored token, if any.
    let cancelled = false;
    (async () => {
      const token = getStoredLocalToken();
      if (token) {
        try {
          const profile = await fetchLocalProfile(token);
          if (!cancelled) setCurrentUser(fromLocalProfile(profile));
        } catch {
          setStoredLocalToken(null);
        }
      }
      if (!cancelled) setLoading(false);
    })();
    return () => {
      cancelled = true;
    };
  }, [provider]);

  const signup = async (identifier: string, password: string) => {
    if (provider === 'firebase') {
      await createUserWithEmailAndPassword(auth, identifier, password);
      return;
    }
    const data = await postJSON<TokenResponse>('/auth/register', {
      username: identifier,
      password: password || undefined,
    });
    setStoredLocalToken(data.token);
    setCurrentUser(fromLocalProfile(data.user));
  };

  const login = async (identifier: string, password: string) => {
    if (provider === 'firebase') {
      await signInWithEmailAndPassword(auth, identifier, password);
      return;
    }
    const data = await postJSON<TokenResponse>('/auth/login', {
      username: identifier,
      password: password || undefined,
    });
    setStoredLocalToken(data.token);
    setCurrentUser(fromLocalProfile(data.user));
  };

  const loginWithGoogle = async () => {
    if (provider !== 'firebase') {
      throw new Error('Google sign-in is not available on this instance');
    }
    const googleProvider = new GoogleAuthProvider();
    await signInWithPopup(auth, googleProvider);
  };

  const logout = async () => {
    if (provider === 'firebase') {
      await signOut(auth);
      return;
    }
    setStoredLocalToken(null);
    setCurrentUser(null);
  };

  const getIdToken = async (): Promise<string | null> => {
    if (provider === 'firebase') {
      if (!currentUser) return null;
      return (await auth.currentUser?.getIdToken()) ?? null;
    }
    return getStoredLocalToken();
  };

  const value: AuthContextType = {
    currentUser,
    loading,
    authProvider: provider ?? 'local',
    login,
    signup,
    loginWithGoogle,
    logout,
    getIdToken,
  };

  return (
    <AuthContext.Provider value={value}>
      {!loading && children}
    </AuthContext.Provider>
  );
}
