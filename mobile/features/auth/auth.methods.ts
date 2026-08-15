import type { ComponentType } from 'react';
import { PhoneLoginForm } from './components/PhoneLoginForm';

// SS-071: the typed sign-in method registry. app/(auth)/login.tsx renders
// from this array and holds no method-specific code itself — adding a
// second entry (SS-072's email/password, or a later Google SSO) is an
// addition here plus one new form component, never an edit to login.tsx.
//
// AuthMethodId is deliberately a shared, exported union (not a
// per-screen string literal) — see docs/tickets/SS-071-design.md's
// "Forward-compatibility with BL-172" section: a future "linked methods"
// list on Profile reuses this same vocabulary rather than inventing a
// second, drift-prone one.
export type AuthMethodId = 'phone_otp'; // SS-072 adds 'email_password'

export interface AuthMethodDescriptor {
  id: AuthMethodId;
  /** Chooser button copy — only rendered when 2+ methods are registered. */
  label: string;
  /** Self-contained form; renders its own success/error/loading UI. */
  Component: ComponentType;
}

export const AUTH_METHODS: readonly AuthMethodDescriptor[] = [
  {
    id: 'phone_otp',
    label: 'Continue with mobile number',
    Component: PhoneLoginForm,
  },
];
