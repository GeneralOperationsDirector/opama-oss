import React, { useEffect, useState } from 'react';
import { useAuth } from '../../contexts/AuthContext';
import { api } from '../../lib/api';
import { ShieldAlert, X } from 'lucide-react';

/**
 * Password guardrail for local accounts (locked decision #2 in the
 * auth_provider_plan memory): a passwordless local account gets a soft,
 * dismissible banner nudge. Once the instance looks reachable beyond
 * localhost (non-loopback CORS_ORIGINS — see /auth/config.instance_exposed),
 * that escalates to a "Secure this instance" modal with a session-scoped
 * snooze. Both checks reset each browser session via sessionStorage so the
 * nudge returns next time rather than going silent forever.
 */

interface AuthConfig {
  provider: string;
  instance_exposed: boolean;
}

interface MeProfile {
  auth_provider: string;
  has_password: boolean;
}

const BANNER_DISMISSED_KEY = 'opama_guardrail_banner_dismissed';
const MODAL_SNOOZED_KEY = 'opama_guardrail_modal_snoozed';

export default function AuthGuardrail({ onOpenProfile }: { onOpenProfile: () => void }) {
  const { currentUser, authProvider } = useAuth();
  const [exposed, setExposed] = useState(false);
  const [hasPassword, setHasPassword] = useState(true);
  const [ready, setReady] = useState(false);
  const [bannerDismissed, setBannerDismissed] = useState(
    () => sessionStorage.getItem(BANNER_DISMISSED_KEY) === '1'
  );
  const [modalSnoozed, setModalSnoozed] = useState(
    () => sessionStorage.getItem(MODAL_SNOOZED_KEY) === '1'
  );

  useEffect(() => {
    if (!currentUser || authProvider !== 'local') {
      setReady(true);
      return;
    }
    let cancelled = false;
    Promise.all([api<AuthConfig>('/auth/config'), api<MeProfile>('/auth/me')])
      .then(([config, profile]) => {
        if (cancelled) return;
        setExposed(config.instance_exposed);
        setHasPassword(profile.has_password);
        setReady(true);
      })
      .catch(() => setReady(true));
    return () => {
      cancelled = true;
    };
  }, [currentUser, authProvider]);

  if (!ready || !currentUser || authProvider !== 'local' || hasPassword) return null;

  const dismissBanner = () => {
    sessionStorage.setItem(BANNER_DISMISSED_KEY, '1');
    setBannerDismissed(true);
  };
  const snoozeModal = () => {
    sessionStorage.setItem(MODAL_SNOOZED_KEY, '1');
    setModalSnoozed(true);
  };

  if (exposed && !modalSnoozed) {
    return (
      <div className="fixed inset-0 z-[100] bg-slate-900/50 flex items-center justify-center p-4">
        <div className="bg-white rounded-2xl shadow-xl max-w-md w-full p-6">
          <div className="flex items-start gap-3">
            <div className="w-10 h-10 rounded-full bg-amber-100 flex items-center justify-center shrink-0">
              <ShieldAlert className="w-5 h-5 text-amber-600" />
            </div>
            <div>
              <h3 className="font-semibold text-slate-900 text-lg">Secure this instance</h3>
              <p className="text-sm text-slate-600 mt-1.5">
                opama looks reachable beyond your local machine, but this account has no
                password set. Anyone who reaches it can sign in as you by username alone.
              </p>
            </div>
          </div>
          <div className="flex gap-2 mt-5">
            <button
              onClick={onOpenProfile}
              className="flex-1 px-4 py-2 rounded-lg bg-indigo-600 text-white text-sm font-medium hover:bg-indigo-700 transition-colors"
            >
              Set a password now
            </button>
            <button
              onClick={snoozeModal}
              className="px-4 py-2 rounded-lg border border-slate-300 text-slate-600 text-sm font-medium hover:bg-slate-50 transition-colors"
            >
              Remind me later
            </button>
          </div>
        </div>
      </div>
    );
  }

  if (!exposed && !bannerDismissed) {
    return (
      <div className="bg-amber-50 border-b border-amber-200">
        <div className="max-w-6xl mx-auto px-4 py-2.5 flex items-center justify-between gap-3 text-sm">
          <div className="flex items-center gap-2 text-amber-800 min-w-0">
            <ShieldAlert className="w-4 h-4 shrink-0" />
            <span className="truncate">
              This account has no password — set one before exposing opama beyond your local machine.
            </span>
          </div>
          <div className="flex items-center gap-3 shrink-0">
            <button onClick={onOpenProfile} className="font-medium text-amber-900 hover:underline">
              Set a password
            </button>
            <button onClick={dismissBanner} aria-label="Dismiss" className="text-amber-600 hover:text-amber-800">
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>
      </div>
    );
  }

  return null;
}
