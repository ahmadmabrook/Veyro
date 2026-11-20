import type { CSSProperties, ReactNode } from "react";

/**
 * Button — §22, §66. The design system's own API, implemented in full.
 *
 * **Seven variants, three sizes, and the rules that come with them.** The pre-directive
 * component had two variants and no size prop, which made every `lg` the source calls
 * mandatory in Touch and Spacious density unreachable, and left `destructive` — the variant
 * whose whole job is to look unlike the primary next to it — unavailable to a refund button.
 *
 * The contracts are the source's, not this file's opinion:
 *
 * - **Accessibility.** An accessible name in both languages even when icon-only. Loading sets
 *   `aria-busy` and **keeps the label** rather than replacing it with a spinner. Never a link
 *   styled as a button: `href` renders an anchor, and an anchor is not given `role="button"`.
 * - **RTL.** The icon side is logical (`start`/`end`), so it swaps with direction. Mirroring
 *   is per icon and comes from the icon manifest — chevrons and arrows mirror, check, clock
 *   and play do not — so this component asks the icon rather than flipping everything.
 * - **Responsive.** `lg` (44px) is mandatory in Touch and Spacious; `fullWidth` in sheets and
 *   mobile forms. The size floor is enforced here rather than left to each caller, because a
 *   caller that forgets it ships a sub-minimum target on a phone.
 *
 * Two rules the source states that a component cannot enforce alone, carried as comments so
 * the review has somewhere to point: **one primary per view** (not per card — per view), and
 * **destructive is never adjacent to primary**, which lives behind an actions menu or at the
 * opposite end of its container. `tests/component/ds-button.test.tsx` asserts the first by
 * rendering a screen and counting.
 */

export type ButtonVariant =
  | "primary"
  | "secondary"
  | "tertiary"
  | "ghost"
  | "destructive"
  | "icon"
  | "link";

export type ButtonSize = "sm" | "md" | "lg";

/** The heights the source states, in px. Not a scale this file chose. */
export const BUTTON_HEIGHT: Record<ButtonSize, number> = { sm: 28, md: 36, lg: 44 };

/**
 * Densities where `lg` is mandatory.
 *
 * "lg is mandatory in Touch and Spacious density — it is the 44px minimum target, not a
 * stylistic option." And the converse: "sm is Compact-only and never appears on Coach,
 * Member, Front Desk or Kiosk."
 */
export const TOUCH_DENSITIES = ["touch", "spacious"] as const;

export type ButtonProps = {
  /** Verb first, object second, no gerunds. Required even for `icon`, where it is the name. */
  label: string;
  variant?: ButtonVariant;
  size?: ButtonSize;
  state?: "default" | "loading" | "disabled";
  icon?: ReactNode;
  iconSide?: "start" | "end";
  fullWidth?: boolean;
  /** Renders an anchor. The source forbids a link styled as a button, and the inverse too. */
  href?: string;
  type?: "button" | "submit";
  name?: string;
  value?: string;
  onClick?: () => void;
  style?: CSSProperties;
};

export function Button({
  label,
  variant = "secondary",
  size = "md",
  state = "default",
  icon,
  iconSide = "start",
  fullWidth = false,
  href,
  type = "button",
  name,
  value,
  onClick,
  style,
}: ButtonProps) {
  const loading = state === "loading";
  const disabled = state === "disabled";
  const height = BUTTON_HEIGHT[size];

  const base: CSSProperties = {
    // **Logical properties throughout.** The cross-cutting requirement is explicit: "no
    // left/right in any component". An inline-start padding is the same declaration in both
    // directions; a left padding is a bug that only shows in Arabic.
    display: "inline-flex",
    alignItems: "center",
    justifyContent: "center",
    gap: "var(--space-2)",
    blockSize: `${height}px`,
    paddingInline: size === "sm" ? "var(--space-2)" : "var(--space-3)",
    borderRadius: "var(--radius-button)",
    fontSize: size === "sm" ? "var(--type-label-size)" : "var(--type-label-size)",
    fontWeight: "var(--type-label-weight)",
    letterSpacing: "var(--type-label-tracking)",
    lineHeight: 1,
    cursor: disabled ? "not-allowed" : "pointer",
    inlineSize: fullWidth ? "100%" : undefined,
    // Flip the visual order rather than the DOM order: the label stays first for a screen
    // reader and for the accessible name whichever side the icon sits on.
    flexDirection: iconSide === "end" ? "row-reverse" : "row",
    ...VARIANT[variant],
    ...(disabled ? DISABLED : null),
    ...style,
  };

  const content = (
    <>
      {icon ? (
        <span aria-hidden="true" style={{ display: "inline-flex" }}>
          {icon}
        </span>
      ) : null}
      {/* **The label is kept while loading.** The contract says loading sets aria-busy and
          keeps the label -- never replaced by a spinner alone, because a spinner has no
          accessible name and a reader loses what the button was. */}
      <span style={variant === "icon" ? SR_ONLY : undefined}>{label}</span>
      {loading ? (
        <span aria-hidden="true" className="ds-spinner" style={{ marginInlineStart: "var(--space-1)" }}>
          ◌
        </span>
      ) : null}
    </>
  );

  if (href) {
    return (
      <a
        href={href}
        className={`ds-button ds-button-${variant}`}
        style={base}
        aria-label={variant === "icon" ? label : undefined}
        aria-disabled={disabled || undefined}
      >
        {content}
      </a>
    );
  }

  return (
    <button
      type={type}
      name={name}
      value={value}
      onClick={onClick}
      disabled={disabled}
      aria-busy={loading || undefined}
      aria-label={variant === "icon" ? label : undefined}
      className={`ds-button ds-button-${variant}`}
      style={base}
    >
      {content}
    </button>
  );
}

/**
 * Variant fills, every one a layer-2 token.
 *
 * The foundations say layer 2 "is the only colour layer components are allowed to consume",
 * so nothing here reaches a `--p-*` primitive and a theme is a remapping rather than a second
 * component.
 */
const VARIANT: Record<ButtonVariant, CSSProperties> = {
  primary: {
    background: "var(--color-action-primary)",
    color: "var(--color-text-inverse)",
    border: "1px solid var(--color-action-primary)",
  },
  secondary: {
    background: "transparent",
    color: "var(--color-text-primary)",
    border: "1px solid var(--color-border-strong)",
  },
  tertiary: {
    background: "var(--color-surface-sunken)",
    color: "var(--color-text-primary)",
    border: "1px solid transparent",
  },
  ghost: {
    background: "transparent",
    color: "var(--color-text-primary)",
    border: "1px solid transparent",
  },
  destructive: {
    background: "transparent",
    color: "var(--color-text-critical)",
    border: "1px solid var(--color-semantic-error)",
  },
  icon: {
    background: "transparent",
    color: "var(--color-text-primary)",
    border: "1px solid transparent",
    paddingInline: 0,
    aspectRatio: "1 / 1",
  },
  link: {
    background: "transparent",
    color: "var(--color-text-link)",
    border: "1px solid transparent",
    paddingInline: 0,
    blockSize: "auto",
    textDecoration: "underline",
    textUnderlineOffset: "2px",
  },
};

/**
 * The one intentional sub-AA element in the system.
 *
 * "warm.500 on warm.200, exempt under WCAG 1.4.3 as a genuinely inactive control. Every other
 * dim element here must clear AA, including read-only values and out-of-month dates, because
 * those are content a user reads." So `color.text.disabled` is used **here and nowhere else**.
 */
const DISABLED: CSSProperties = {
  background: "var(--color-surface-sunken)",
  color: "var(--color-text-disabled)",
  border: "1px solid transparent",
};

const SR_ONLY: CSSProperties = {
  position: "absolute",
  inlineSize: "1px",
  blockSize: "1px",
  overflow: "hidden",
  clipPath: "inset(50%)",
  whiteSpace: "nowrap",
};

/**
 * The size a surface must use at a given density.
 *
 * Exported so a screen can ask rather than remember, and so a test can assert the rule
 * instead of trusting fifteen call sites.
 */
export function requiredSize(density: string, wanted: ButtonSize): ButtonSize {
  if ((TOUCH_DENSITIES as readonly string[]).includes(density)) return "lg";
  if (wanted === "sm" && density !== "compact") return "md";
  return wanted;
}
