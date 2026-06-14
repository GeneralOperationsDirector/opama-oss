import React, { useState, useEffect } from 'react';
import { useAuth } from '../../contexts/AuthContext';
import Section from '../../shared/atoms/Section';
import Button from '../../shared/atoms/Button';
import { User, Mail, Calendar, Shield, Trash2, Edit, Lock, KeyRound } from 'lucide-react';
import { api } from '../../lib/api';

interface ProfileTabProps {
  onToast?: (message: string, type?: 'success' | 'error' | 'info') => void;
}

interface UserProfile {
  id: number;
  firebase_uid: string | null;
  auth_provider: string;
  email: string | null;
  display_name: string | null;
  created_at: string;
  has_password: boolean;
}

export default function ProfileTab({ onToast }: ProfileTabProps) {
  const { currentUser, logout } = useAuth();
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState(false);
  const [displayName, setDisplayName] = useState('');
  const [saving, setSaving] = useState(false);

  const [showPasswordForm, setShowPasswordForm] = useState(false);
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [passwordSaving, setPasswordSaving] = useState(false);

  useEffect(() => {
    fetchProfile();
  }, []);

  const fetchProfile = async () => {
    setLoading(true);
    try {
      const data = await api<UserProfile>('/auth/me');
      setProfile(data);
      setDisplayName(data.display_name || '');
    } catch (err) {
      onToast?.('Failed to load profile', 'error');
    } finally {
      setLoading(false);
    }
  };

  const handleSaveDisplayName = async () => {
    setSaving(true);
    try {
      await api('/auth/me', {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ display_name: displayName }),
      });

      setProfile((prev) => prev ? { ...prev, display_name: displayName } : null);
      setEditing(false);
      onToast?.('Profile updated successfully', 'success');
    } catch (err) {
      onToast?.('Failed to update profile', 'error');
    } finally {
      setSaving(false);
    }
  };

  const resetPasswordForm = () => {
    setShowPasswordForm(false);
    setCurrentPassword('');
    setNewPassword('');
    setConfirmPassword('');
  };

  const handleSetPassword = async () => {
    if (!newPassword) {
      onToast?.('Enter a new password', 'error');
      return;
    }
    if (newPassword !== confirmPassword) {
      onToast?.('Passwords do not match', 'error');
      return;
    }

    setPasswordSaving(true);
    try {
      await api('/auth/set-password', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          current_password: profile?.has_password ? currentPassword : undefined,
          new_password: newPassword,
        }),
      });

      setProfile((prev) => (prev ? { ...prev, has_password: true } : null));
      resetPasswordForm();
      onToast?.(
        profile?.has_password ? 'Password changed successfully' : 'Password set — your account is now secured',
        'success'
      );
    } catch (err) {
      let detail = err instanceof Error ? err.message : 'Failed to update password';
      try {
        detail = JSON.parse(detail)?.detail ?? detail;
      } catch {
        /* not JSON — use raw message */
      }
      onToast?.(detail, 'error');
    } finally {
      setPasswordSaving(false);
    }
  };

  const handleDeleteAccount = async () => {
    const confirm = window.confirm(
      'Are you sure you want to delete your account? This will permanently delete all your data including inventory, decks, and portfolio. This action cannot be undone.'
    );

    if (!confirm) return;

    const doubleConfirm = window.confirm(
      'This is your last chance. Are you absolutely sure you want to delete your account and all associated data?'
    );

    if (!doubleConfirm) return;

    try {
      await api('/auth/me', {
        method: 'DELETE',
      });

      onToast?.('Account deleted successfully', 'success');
      await logout();
    } catch (err) {
      onToast?.('Failed to delete account', 'error');
    }
  };

  if (loading) {
    return (
      <Section title="Profile" icon={<User />}>
        <div className="flex items-center justify-center py-12">
          <div className="text-gray-500">Loading profile...</div>
        </div>
      </Section>
    );
  }

  if (!profile) {
    return (
      <Section title="Profile" icon={<User />}>
        <div className="flex items-center justify-center py-12">
          <div className="text-gray-500">Failed to load profile</div>
        </div>
      </Section>
    );
  }

  return (
    <div className="space-y-6">
      {/* Profile Information */}
      <Section title="Profile" icon={<User />}>
        <div className="space-y-6">
          {/* User ID & Firebase UID */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="bg-gray-50 rounded-lg p-4 border border-gray-200">
              <div className="flex items-center gap-2 text-sm text-gray-600 mb-1">
                <Shield className="w-4 h-4" />
                <span className="font-medium">User ID</span>
              </div>
              <div className="text-lg font-mono text-gray-900">{profile.id}</div>
            </div>

            <div className="bg-gray-50 rounded-lg p-4 border border-gray-200">
              <div className="flex items-center gap-2 text-sm text-gray-600 mb-1">
                <Calendar className="w-4 h-4" />
                <span className="font-medium">Member Since</span>
              </div>
              <div className="text-lg text-gray-900">
                {new Date(profile.created_at).toLocaleDateString()}
              </div>
            </div>
          </div>

          {/* Email */}
          <div>
            <label className="flex items-center gap-2 text-sm font-medium text-gray-700 mb-2">
              <Mail className="w-4 h-4" />
              Email Address
            </label>
            <div className="bg-gray-50 rounded-lg p-3 border border-gray-200">
              <div className="text-gray-900">{profile.email || 'No email'}</div>
              <div className="text-xs text-gray-500 mt-1">
                {profile.auth_provider === 'firebase'
                  ? 'Managed by Firebase Authentication'
                  : 'Local account — email is optional'}
              </div>
            </div>
          </div>

          {/* Display Name */}
          <div>
            <div className="flex items-center justify-between mb-2">
              <label className="flex items-center gap-2 text-sm font-medium text-gray-700">
                <User className="w-4 h-4" />
                Display Name
              </label>
              {!editing && (
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => setEditing(true)}
                >
                  <Edit className="w-4 h-4" />
                  Edit
                </Button>
              )}
            </div>

            {editing ? (
              <div className="space-y-3">
                <input
                  type="text"
                  value={displayName}
                  onChange={(e) => setDisplayName(e.target.value)}
                  placeholder="Enter your display name"
                  className="w-full px-4 py-2 bg-white border border-gray-300 rounded-lg focus:border-indigo-500 focus:outline-none"
                />
                <div className="flex gap-2">
                  <Button
                    variant="primary"
                    onClick={handleSaveDisplayName}
                    loading={saving}
                  >
                    Save
                  </Button>
                  <Button
                    variant="ghost"
                    onClick={() => {
                      setEditing(false);
                      setDisplayName(profile.display_name || '');
                    }}
                  >
                    Cancel
                  </Button>
                </div>
              </div>
            ) : (
              <div className="bg-gray-50 rounded-lg p-3 border border-gray-200">
                <div className="text-gray-900">
                  {profile.display_name || (
                    <span className="text-gray-400 italic">Not set</span>
                  )}
                </div>
              </div>
            )}
          </div>

          {/* Technical details (for debugging/support) */}
          <details className="mt-4">
            <summary className="cursor-pointer text-sm text-gray-600 hover:text-gray-900">
              Show technical details
            </summary>
            <div className="mt-2 bg-gray-50 rounded-lg p-3 border border-gray-200 space-y-1">
              <div className="text-xs font-mono text-gray-700 break-all">
                <strong>Auth provider:</strong> {profile.auth_provider}
              </div>
              {profile.firebase_uid && (
                <div className="text-xs font-mono text-gray-700 break-all">
                  <strong>Firebase UID:</strong> {profile.firebase_uid}
                </div>
              )}
            </div>
          </details>
        </div>
      </Section>

      {/* Account Settings */}
      <Section title="Account Settings" subtitle="Manage your account preferences">
        <div className="space-y-4">
          {/* Authentication Provider Info */}
          <div className="bg-blue-50 rounded-lg p-4 border border-blue-200">
            <div className="flex items-start gap-3">
              <Shield className="w-5 h-5 text-blue-600 mt-0.5" />
              <div>
                <div className="font-medium text-blue-900">Authentication</div>
                <div className="text-sm text-blue-700 mt-1">
                  {profile.auth_provider === 'firebase' ? (
                    <>
                      Your account is secured with Firebase Authentication.
                      {currentUser?.providerId === 'google.com' && <> Signed in with Google.</>}
                      {currentUser?.providerId === 'password' && <> Signed in with email and password.</>}
                    </>
                  ) : (
                    <>Your account is secured with a local opama username and password.</>
                  )}
                </div>
              </div>
            </div>
          </div>

          {/* Password Change - only for Firebase email/password users */}
          {profile.auth_provider === 'firebase' && currentUser?.providerId === 'password' && (
            <div className="bg-gray-50 rounded-lg p-4 border border-gray-200">
              <div className="flex items-center justify-between">
                <div>
                  <div className="font-medium text-gray-900">Password</div>
                  <div className="text-sm text-gray-600 mt-1">
                    To change your password, use the password reset option on the login screen.
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Password set/change — local accounts only */}
          {profile.auth_provider === 'local' && (
            <div
              className={`rounded-lg p-4 border ${
                profile.has_password ? 'bg-gray-50 border-gray-200' : 'bg-amber-50 border-amber-200'
              }`}
            >
              <div className="flex items-start justify-between gap-3">
                <div className="flex items-start gap-3">
                  {profile.has_password ? (
                    <Lock className="w-5 h-5 text-gray-500 mt-0.5" />
                  ) : (
                    <KeyRound className="w-5 h-5 text-amber-600 mt-0.5" />
                  )}
                  <div>
                    <div className="font-medium text-gray-900">Password</div>
                    <div className="text-sm text-gray-600 mt-1">
                      {profile.has_password
                        ? 'A password is set on this account.'
                        : 'No password set — your account can be signed into by username alone. Set one before exposing opama beyond your local machine.'}
                    </div>
                  </div>
                </div>
                {!showPasswordForm && (
                  <Button variant="ghost" size="sm" onClick={() => setShowPasswordForm(true)}>
                    {profile.has_password ? 'Change password' : 'Set a password'}
                  </Button>
                )}
              </div>

              {showPasswordForm && (
                <div className="mt-4 space-y-3 max-w-sm">
                  {profile.has_password && (
                    <input
                      type="password"
                      value={currentPassword}
                      onChange={(e) => setCurrentPassword(e.target.value)}
                      placeholder="Current password"
                      autoComplete="current-password"
                      className="w-full px-4 py-2 bg-white border border-gray-300 rounded-lg focus:border-indigo-500 focus:outline-none"
                    />
                  )}
                  <input
                    type="password"
                    value={newPassword}
                    onChange={(e) => setNewPassword(e.target.value)}
                    placeholder="New password"
                    autoComplete="new-password"
                    className="w-full px-4 py-2 bg-white border border-gray-300 rounded-lg focus:border-indigo-500 focus:outline-none"
                  />
                  <input
                    type="password"
                    value={confirmPassword}
                    onChange={(e) => setConfirmPassword(e.target.value)}
                    placeholder="Confirm new password"
                    autoComplete="new-password"
                    className="w-full px-4 py-2 bg-white border border-gray-300 rounded-lg focus:border-indigo-500 focus:outline-none"
                  />
                  <div className="flex gap-2">
                    <Button variant="primary" onClick={handleSetPassword} loading={passwordSaving}>
                      {profile.has_password ? 'Change password' : 'Set password'}
                    </Button>
                    <Button variant="ghost" onClick={resetPasswordForm}>
                      Cancel
                    </Button>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </Section>

      {/* Danger Zone */}
      <Section title="Danger Zone" subtitle="Irreversible actions">
        <div className="bg-red-50 rounded-lg p-6 border border-red-200">
          <div className="flex items-start gap-4">
            <Trash2 className="w-6 h-6 text-red-600 mt-1" />
            <div className="flex-1">
              <h3 className="font-semibold text-red-900 text-lg">Delete Account</h3>
              <p className="text-sm text-red-700 mt-1 mb-4">
                Permanently delete your account and all associated data. This includes:
              </p>
              <ul className="text-sm text-red-700 list-disc list-inside space-y-1 mb-4">
                <li>All inventory items</li>
                <li>All decks and deck lists</li>
                <li>Portfolio history and valuations</li>
                <li>Sales records and transaction history</li>
                <li>Wishlist and trade items</li>
              </ul>
              <p className="text-sm font-semibold text-red-900 mb-4">
                ⚠️ This action cannot be undone!
              </p>
              <Button
                variant="secondary"
                onClick={handleDeleteAccount}
                className="bg-red-600 hover:bg-red-700 text-white border-red-600"
              >
                <Trash2 className="w-4 h-4" />
                Delete My Account
              </Button>
            </div>
          </div>
        </div>
      </Section>
    </div>
  );
}
