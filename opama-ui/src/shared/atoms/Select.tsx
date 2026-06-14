/**
 * Select (atom)
 * -------------
 * Default export remains a plain <select> with your original styles,
 * so existing call sites keep working unchanged.
 *
 * Enhancements:
 * - Stronger typing + ref forwarding
 * - Optional `invalid` prop → sets `aria-invalid` and enables error styling hooks
 *
 * Bonus:
 * - Named export `SelectField` — label + select + hint/error with proper a11y wiring
 */

import React, { forwardRef, useId } from "react";

export type SelectProps = React.SelectHTMLAttributes<HTMLSelectElement> & {
  /** Marks the field invalid for a11y & styling; you can still pass className for colors. */
  invalid?: boolean;
};

/** Bare select (drop-in replacement) */
const Select = forwardRef<HTMLSelectElement, SelectProps>(function Select(
  { className = "", invalid, ...props },
  ref
) {
  const cls = [
    "px-3 py-2 rounded-xl border w-full outline-none focus:ring-2 focus:ring-indigo-400",
    // Hook for red focus ring if desired when invalid
    invalid ? "aria-[invalid=true]:ring-rose-400 focus:ring-rose-400" : "",
    className,
  ]
    .filter(Boolean)
    .join(" ");

  return <select ref={ref} {...props} className={cls} aria-invalid={invalid || undefined} />;
});

export default Select;

/* ------------------------------------------------------------------ */
/* SelectField: labeled field wrapper with hint & error (optional)     */
/* ------------------------------------------------------------------ */

export type SelectFieldProps = SelectProps & {
  /** Visible label content (if omitted, only the select renders). */
  label?: React.ReactNode;
  /** Optional helper text below the select. */
  hint?: React.ReactNode;
  /** Optional error text below the select (sets `invalid=true`). */
  error?: React.ReactNode;
  /** Extra props for the <label>. */
  labelProps?: React.LabelHTMLAttributes<HTMLLabelElement>;
};

export const SelectField = forwardRef<HTMLSelectElement, SelectFieldProps>(function SelectField(
  { id, label, hint, error, labelProps, invalid, className, ...selectProps },
  ref
) {
  const autoId = useId();
  const selectId = id ?? `sel-${autoId}`;
  const hintId = hint ? `${selectId}-hint` : undefined;
  const errId = error ? `${selectId}-error` : undefined;
  const describedBy = [hintId, errId].filter(Boolean).join(" ") || undefined;

  return (
    <div className="space-y-1">
      {label ? (
        <label
          {...labelProps}
          htmlFor={selectId}
          className={["block text-sm font-medium", labelProps?.className || ""].join(" ")}
        >
          {label}
          {selectProps.required ? <span className="text-rose-600 ml-0.5" aria-hidden>*</span> : null}
        </label>
      ) : null}

      <Select
        {...selectProps}
        id={selectId}
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
