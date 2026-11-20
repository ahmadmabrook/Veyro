import type { CSSProperties, ReactNode } from "react";

/**
 * Card — §31. Six kinds, and a prohibition.
 *
 * **"A card that only draws a border around a paragraph is deleted — 'cardification' of every
 * screen is explicitly prohibited."** That is the rule this file exists to enforce, and it is
 * the rule the pre-directive surfaces broke most: every page wrapped every block in a
 * `.panel`, including blocks that were one sentence of prose. `kind` is required and there is
 * no default, so a caller has to say which of the six this is — and if none of them fits, the
 * answer is that it is not a card.
 *
 * The six are the source's: informational, interactive, summary, media, person, booking.
 * `person` and `booking` are the hooks for the Step 4 domain families (PersonRow,
 * BookingCard), which compose a card rather than reimplementing one.
 *
 * **No shadow on a row.** The common-mistakes checklist names "a shadow on a table row"
 * explicitly, so elevation is available to overlays and not to anything that sits in a list.
 */

export type CardKind =
  | "informational"
  | "interactive"
  | "summary"
  | "media"
  | "person"
  | "booking";

export function Card({
  kind,
  title,
  children,
  actions,
  style,
}: {
  /** Required. The six kinds are the whole vocabulary; there is no seventh and no default. */
  kind: CardKind;
  title?: string;
  children: ReactNode;
  actions?: ReactNode;
  style?: CSSProperties;
}) {
  const interactive = kind === "interactive";
  return (
    <section
      className={`ds-card ds-card-${kind}`}
      style={{
        display: "flex",
        flexDirection: "column",
        gap: "var(--space-3)",
        padding: "var(--space-4)",
        background: "var(--color-surface-default)",
        border: "1px solid var(--color-border-default)",
        // Containers stay sharp. `radius.card` is deliberately smaller than `radius.button`:
        // the foundations say data stays sharp and anything pressable gets an affordance.
        borderRadius: "var(--radius-card)",
        cursor: interactive ? "pointer" : undefined,
        ...style,
      }}
    >
      {title ? (
        <h2
          style={{
            margin: 0,
            fontSize: "var(--type-h3-size)",
            lineHeight: "var(--type-h3-line)",
            fontWeight: "var(--type-h3-weight)",
            letterSpacing: "var(--type-h3-tracking)",
          }}
        >
          {title}
        </h2>
      ) : null}
      {children}
      {actions ? (
        <div style={{ display: "flex", gap: "var(--space-2)", flexWrap: "wrap" }}>{actions}</div>
      ) : null}
    </section>
  );
}
