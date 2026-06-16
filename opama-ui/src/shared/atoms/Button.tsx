/**
 * Button (atom)
 * -------------
 * Default export remains a styled <button>. Existing usages keep working.
 *
 * Enhancements (all optional):
 * - `variant`: "primary" | "secondary" | "ghost" | "danger"
 * - `size`: "sm" | "md" | "lg"
 * - `loading`: shows a spinner, disables the button, sets aria-busy
 * - `block`: full-width button (w-full + centered content)
 * - Ref-forwarding + a11y-friendly disabled styles
 */

import React, { forwardRef } from "react";

export type ButtonProps = React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "ghost" | "danger";
  size?: "sm" | "md" | "lg";
  loading?: boolean;
  block?: boolean;
};

const VARIANT: Record<NonNullable<ButtonProps["variant"]>, string> = {
  primary:
    "bg-indigo-600 text-white hover:bg-indigo-700",
  secondary:
    "bg-slate-100 text-slate-900 hover:bg-slate-200 border border-slate-300",
  ghost:
    "bg-transparent text-slate-700 hover:bg-slate-50 border border-slate-200",
  danger:
    "bg-rose-600 text-white hover:bg-rose-700",
};

const SIZE: Record<NonNullable<ButtonProps["size"]>, string> = {
  sm: "px-3 py-1.5 text-sm",
  md: "px-4 py-2 text-sm",
  lg: "px-5 py-3 text-base",
};

const Spinner = () => (
  <svg
    className="animate-spin h-4 w-4"
    viewBox="0 0 24 24"
    aria-hidden="true"
  >
    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
    <path className="opacity-75" d="M4 12a8 8 0 018-8" fill="currentColor" />
  </svg>
);

/** Drop-in button with variants/sizes/loading. */
const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  {
    children,
    className = "",
    variant = "primary",
    size = "md",
    loading = false,
    disabled,
    block = false,
    ...rest
  },
  ref
) {
  const cls = [
    "inline-flex items-center gap-2 rounded-xl font-medium shadow",
    SIZE[size],
    VARIANT[variant],
    block ? "w-full justify-center" : "",
    "active:scale-[.99] transition",
    "disabled:opacity-60 disabled:cursor-not-allowed",
    className,
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <button
      ref={ref}
      {...rest}
      className={cls}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
    >
      {loading ? <Spinner /> : null}
      {children}
    </button>
  );
});

export default Button;
