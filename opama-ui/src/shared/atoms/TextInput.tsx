/**
 * TextInput (atom)
 * ----------------
 * Default export remains a *plain input element* with your original styles,
 * so existing call sites continue to work unchanged.
 *
 * Enhancements:
 * - Stronger typing + ref forwarding (good for forms, focusing, etc.)
 * - Optional `invalid` prop wires to `aria-invalid` + error styling hook
 *
 * Bonus:
 * - Named export `TextField` — a tiny wrapper rendering label + input + hint/error
 *   with proper a11y wiring (`aria-describedby`). Use it where you want a full field.
 */

import React, { forwardRef, useId } from "react";

/** Props for the bare input. */
export type TextInputProps = React.InputHTMLAttributes<HTMLInputElement> & {
  /** Marks the input invalid for a11y & styling; you can still pass className for colors. */
  invalid?: boolean;
};

/** Bare input (drop-in replacement) */
const TextInput = forwardRef<HTMLInputElement, TextInputProps>(function TextInput(
  { className = "", invalid, ...props },
  ref
) {
  const cls = [
    "px-3 py-2 rounded-xl border w-full outline-none focus:ring-2 focus:ring-indigo-400",
    invalid ? "aria-[invalid=true]:ring-rose-400 focus:ring-rose-400" : "",
    className,
  ]
    .filter(Boolean)
    .join(" ");

  return <input ref={ref} {...props} className={cls} aria-invalid={invalid || undefined} />;
});

export default TextInput;

/** ------------------------------------------------------------------ */
/** TextField: labeled field wrapper with hint & error (optional)      */
/** ------------------------------------------------------------------ */

export type TextFieldProps = TextInputProps & {
  /** Visible label content (if omitted, only the input renders). */
  label?: React.ReactNode;
  /** Optional helper text below the input. */
  hint?: React.ReactNode;
  /** Optional error text below the input (sets `invalid=true`). */
  error?: React.ReactNode;
  /** Extra props for the <label>. */
  labelProps?: React.LabelHTMLAttributes<HTMLLabelElement>;
};

/**
 * TextField
 * Renders a label + TextInput + hint/error with proper associations.
 * Keeps styling minimal so it blends with your design system.
 */
export const TextField = forwardRef<HTMLInputElement, TextFieldProps>(function TextField(
  { id, label, hint, error, labelProps, invalid, className, ...inputProps },
  ref
) {
  const autoId = useId();
  const inputId = id ?? `ti-${autoId}`;
  const hintId = hint ? `${inputId}-hint` : undefined;
  const errId = error ? `${inputId}-error` : undefined;
  const describedBy = [hintId, errId].filter(Boolean).join(" ") || undefined;

  return (
    <div className="space-y-1">
      {label ? (
        <label
          {...labelProps}
          htmlFor={inputId}
          className={["block text-sm font-medium", labelProps?.className || ""].join(" ")}
        >
          {label}
          {inputProps.required ? <span className="text-rose-600 ml-0.5" aria-hidden>*</span> : null}
        </label>
      ) : null}

      <TextInput
        {...inputProps}
        id={inputId}
        ref={ref}
        className={className}
        invalid={invalid || !!error}
        aria-describedby={describedBy}
      />

      {hint ? (
        <div id={hintId} className="text-xs text-slate-500">
          {hint}
        </div>
      ) : null}

      {error ? (
        <div id={errId} className="text-xs text-rose-600">
          {error}
        </div>
      ) : null}
    </div>
  );
});
