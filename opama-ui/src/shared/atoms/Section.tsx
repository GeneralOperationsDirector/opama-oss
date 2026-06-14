/**
 * Section
 * -------
 * Lightweight content wrapper with a title row and body.
 *
 * Defaults match the original:
 * - Rounded, bordered card with subtle blur
 * - Title row with optional icon
 *
 * Enhancements (all optional):
 * - <section role="region" aria-labelledby="…"> for a11y landmarks
 * - Customizable heading level (defaults to h2)
 * - Right-aligned `actions` slot (buttons, links, etc.)
 * - `subtitle` for a small descriptive line under the title
 * - `dense` to slightly reduce padding
 */

import React, { forwardRef, useId } from "react";

type Props = {
  title: string;
  icon?: React.ReactNode;
  children: React.ReactNode;

  /** Right-aligned area in the header row (buttons, filters, etc.). */
  actions?: React.ReactNode;

  /** Optional small descriptive line under the title. */
  subtitle?: React.ReactNode;

  /** Custom id for the region; used to bind aria-labelledby. */
  id?: string;

  /** Extra classes appended to the container. */
  className?: string;

  /** Heading level for the title (defaults to 2 ⇒ <h2>). */
  level?: 2 | 3 | 4 | 5 | 6;

  /** Slightly tighter padding when true. */
  dense?: boolean;
};

const Section = forwardRef<HTMLElement, Props>(function Section(
  { title, icon, children, actions, subtitle, id, className = "", level = 2, dense = false },
  ref
) {
  const autoId = useId();
  const regionId = id || `section-${autoId}`;
  const headingId = `${regionId}-heading`;
  const HeadingTag = (`h${level}` as keyof JSX.IntrinsicElements);

  return (
    <section
      ref={ref}
      id={regionId}
      role="region"
      aria-labelledby={headingId}
      className={[
        "bg-white/70 backdrop-blur rounded-2xl shadow border border-slate-200",
        dense ? "p-4" : "p-5",
        className,
      ].join(" ")}
    >
      <div className="flex items-center justify-between gap-2 mb-4">
        <div className="flex items-center gap-2 min-w-0">
          {icon}
          <HeadingTag id={headingId} className="text-xl font-semibold truncate">
            {title}
          </HeadingTag>
        </div>
        {actions ? <div className="shrink-0">{actions}</div> : null}
      </div>

      {subtitle ? <p className="text-sm text-slate-600 mb-3">{subtitle}</p> : null}

      {children}
    </section>
  );
});

export default Section;
