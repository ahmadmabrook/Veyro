import Link from "next/link";
import type { ReactNode } from "react";

/**
 * PipelineColumn and LeadCard — named by ADM-CRM-01's own COMPONENTS line
 * ("PipelineColumn ×5 · LeadCard · Member360Header(lead variant) · AITreatment(ai.600)") and
 * specified nowhere else, so the canvas's drawing is the specification.
 *
 * **Not a Card, and not a DataGrid.** A pipeline column is a *stack* whose header is a count
 * and whose body is a short list with an overflow line — "New · 12 / Rana Sabbagh · open day ·
 * 2d / Omar Zaid · instagram · 4h / +10 more". §31 forbids a card that only draws a border
 * round a block, and a grid would turn five parallel short lists into one table, which is the
 * table view ADM-CRM-02 draws instead. The two views are deliberately different components for
 * the same rows.
 *
 * **The overflow line is a link, not a truncation.** "+10 more" is how the canvas handles a
 * column taller than the viewport, and a column that silently stopped at three would be a
 * count the reader cannot reconcile with the rows under it — which is this app's own
 * one-figure-two-definitions finding at the top of a column.
 *
 * **No severity colour.** A pipeline stage is not a severity: a lead in `new` is not worse
 * than one in `toured`, and painting the columns would make the board read as a problem list.
 * The one mark here is the cold flag on a card, which is an edge-mark for the reason the week
 * grid gives -- a column of tinted cards reads as a column that is wrong.
 */

export function PipelineColumn({
  title,
  count,
  countLabel,
  children,
  overflow,
}: {
  title: string;
  /** Rendered as text beside the title, because a number alone is not a label. */
  count: string;
  /** The accessible name for the count, which a screen reader hears instead of the bare digit. */
  countLabel: string;
  children: ReactNode;
  /** "+10 more", where the column holds more than it draws. */
  overflow?: ReactNode;
}) {
  return (
    <section
      aria-label={countLabel}
      style={{
        display: "flex",
        flexDirection: "column",
        gap: "var(--space-2)",
        minInlineSize: 0,
      }}
    >
      <header
        style={{
          display: "flex",
          alignItems: "baseline",
          gap: "var(--space-2)",
          paddingBlockEnd: "var(--space-2)",
          borderBlockEnd: "1px solid var(--color-border-default)",
        }}
      >
        <span style={{ fontSize: "var(--type-label-size)", lineHeight: "var(--type-label-line)",
          fontWeight: "var(--type-label-weight)",
          color: "var(--color-text-secondary)" }}>
          {title}
        </span>
        <span
          aria-hidden="true"
          style={{ fontSize: "var(--type-label-size)", lineHeight: "var(--type-label-line)",
            color: "var(--color-text-tertiary)" }}
        >
          {count}
        </span>
      </header>
      <ol
        style={{
          listStyle: "none",
          margin: 0,
          padding: 0,
          display: "flex",
          flexDirection: "column",
          gap: "var(--space-2)",
        }}
      >
        {children}
      </ol>
      {overflow ? (
        <p style={{ fontSize: "var(--type-caption-size)",
          lineHeight: "var(--type-caption-line)",
          color: "var(--color-text-tertiary)", margin: 0 }}>
          {overflow}
        </p>
      ) : null}
    </section>
  );
}

export function LeadCard({
  href,
  name,
  meta,
  mark,
}: {
  href: string;
  /** The person's name as MOD-014 gives it, or its withheld marker. Never composed here. */
  name: ReactNode;
  /** "open day · 2d". One line, because the canvas draws one. */
  meta: string;
  /** The cold flag, as an edge-mark rather than a fill. */
  mark?: string;
}) {
  return (
    <li style={{ minInlineSize: 0 }}>
      <Link
        href={href}
        className="ds-lead-card"
        style={{
          display: "block",
          padding: "var(--space-3)",
          background: "var(--color-surface-default)",
          border: "1px solid var(--color-border-default)",
          borderInlineStartWidth: mark ? "3px" : "1px",
          borderInlineStartColor: mark
            ? "var(--color-semantic-warning)"
            : "var(--color-border-default)",
          borderRadius: "var(--radius-card)",
          textDecoration: "none",
          color: "inherit",
        }}
      >
        <span
          style={{
            display: "block",
            fontSize: "var(--type-body-size)",
            lineHeight: "var(--type-body-line)",
            color: "var(--color-text-primary)",
          }}
        >
          {name}
        </span>
        <span
          style={{
            display: "block",
            fontSize: "var(--type-caption-size)",
            lineHeight: "var(--type-caption-line)",
            color: "var(--color-text-secondary)",
            marginBlockStart: "var(--space-1)",
          }}
        >
          {meta}
        </span>
        {mark ? (
          <span
            style={{
              display: "block",
              fontSize: "var(--type-label-size)",
              lineHeight: "var(--type-label-line)",
              fontWeight: "var(--type-label-weight)",
              color: "var(--color-semantic-warning)",
              marginBlockStart: "var(--space-1)",
            }}
          >
            {mark}
          </span>
        ) : null}
      </Link>
    </li>
  );
}
