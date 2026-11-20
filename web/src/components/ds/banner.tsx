import type { CSSProperties, ReactNode } from "react";

import type { Severity } from "./status-badge";

/**
 * Banner — §29, §31–§36. Page-level, and the ARIA role is the whole decision.
 *
 * **`role=status` for info and success, `role=alert` only for critical. Never both.** The
 * contract says so in as many words, and gives the reason: "an alert interrupts, and most
 * banners should not". The pre-directive `Alert` component had one role for every tone, so an
 * informational line about a default value interrupted a screen reader exactly as loudly as a
 * payment outage.
 *
 * **A critical banner is not dismissible while the condition holds.** The worked example is a
 * payment provider outage: "Payments are not processing at Khalda. The provider has been
 * unreachable since 09:14. Card payments will fail; cash and wallet still work. Queued orders
 * are held, not lost." Three things in it — what is broken, what still works, what happened to
 * work in flight — and none of them is dismissible while it is true.
 *
 * **It stacks above content at every breakpoint**, and a global banner is fixed and does not
 * scroll away. The severity bar sits on the logical start edge, so it mirrors without a
 * direction check.
 */

export function Banner({
  severity,
  title,
  children,
  actions,
  dismissible,
  onDismiss,
  global,
  style,
}: {
  severity: Severity;
  title?: string;
  children: ReactNode;
  actions?: ReactNode;
  /**
   * Ignored for `critical`, deliberately. A banner that can be dismissed while the condition
   * holds is a banner that stops being true without anything changing, and the source makes
   * non-dismissibility part of the critical contract rather than a caller's choice.
   */
  dismissible?: boolean;
  onDismiss?: () => void;
  /** Fixed above the shell and does not scroll away. The Console's incident slot. */
  global?: boolean;
  style?: CSSProperties;
}) {
  const critical = severity === "critical";
  const canDismiss = dismissible && !critical;
  return (
    <div
      role={critical ? "alert" : "status"}
      className={`ds-banner ds-banner-${severity}`}
      style={{
        display: "flex",
        alignItems: "flex-start",
        gap: "var(--space-3)",
        padding: "var(--space-3)",
        background: "var(--color-surface-default)",
        color: "var(--color-text-primary)",
        border: "1px solid var(--color-border-default)",
        borderInlineStart: `3px solid ${EDGE[severity]}`,
        borderRadius: "var(--radius-card)",
        ...(global
          ? { position: "sticky", insetBlockStart: 0, zIndex: 20 }
          : null),
        ...style,
      }}
    >
      <div style={{ flex: 1, minInlineSize: 0 }}>
        {title ? (
          <div
            style={{
              fontSize: "var(--type-h3-size)",
              fontWeight: "var(--type-h3-weight)",
              lineHeight: "var(--type-h3-line)",
              marginBlockEnd: "var(--space-1)",
            }}
          >
            {title}
          </div>
        ) : null}
        <div style={{ fontSize: "var(--type-body-size)", lineHeight: "var(--type-body-line)" }}>
          {children}
        </div>
        {actions ? (
          <div style={{ display: "flex", gap: "var(--space-2)", marginBlockStart: "var(--space-3)" }}>
            {actions}
          </div>
        ) : null}
      </div>
      {canDismiss ? (
        <button
          type="button"
          onClick={onDismiss}
          aria-label="Dismiss"
          style={{
            background: "transparent",
            border: 0,
            color: "var(--color-text-secondary)",
            cursor: "pointer",
            padding: "var(--space-1)",
            lineHeight: 1,
          }}
        >
          ✕
        </button>
      ) : null}
    </div>
  );
}

const EDGE: Record<Severity, string> = {
  neutral: "var(--color-border-default)",
  info: "var(--color-semantic-info)",
  attention: "var(--color-semantic-warning)",
  critical: "var(--color-semantic-error)",
};
