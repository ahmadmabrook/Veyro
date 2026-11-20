import type { CSSProperties, ReactNode } from "react";

/**
 * The small primitives — §67's taxonomy, the families that are a shape rather than a
 * behaviour: Chip, Avatar, Divider, Skeleton, Spinner, Tooltip.
 *
 * **One file, because the library rule is flat and alphabetical within a group, not one file
 * per export.** §68: "Foundations/ · Primitives/ · Composites/ · DateTime/ · Domain/ ·
 * Patterns/ — flat within each group, alphabetical, no nesting by screen or module." Six
 * components whose whole definition is a shape and a token do not each earn a module; the
 * ones with contracts of their own (Button, Field, StatusBadge, DataGrid) do.
 *
 * **Spinner is here and is deliberately almost unusable.** The DataGrid contract rules out a
 * centred spinner — "layout must not jump when data lands" — and the Button keeps its label
 * while loading, so the only honest place for one is beside a label that is already there.
 * It takes a `label` for that reason: a spinner with no accessible name is a page that says
 * nothing is happening.
 */

/**
 * Chip — a removable filter, or a small enumerated value.
 *
 * Not a Badge: a badge states a status from a fixed vocabulary and is not pressable, a chip
 * is a filter the reader put there and can take away. The source keeps them separate in the
 * taxonomy and so does this.
 */
export function Chip({
  label,
  onRemove,
  removeLabel,
}: {
  label: string;
  onRemove?: () => void;
  /** The accessible name of the remove control, which is not the chip's own label. */
  removeLabel?: string;
}) {
  return (
    <span className="ds-chip">
      {label}
      {onRemove ? (
        <button
          type="button"
          className="ds-chip-remove"
          aria-label={removeLabel ?? `Remove ${label}`}
          onClick={onRemove}
        >
          ✕
        </button>
      ) : null}
    </span>
  );
}

/**
 * Avatar — initials, never a photo this build does not have.
 *
 * A broken image is worse than initials, and there is no object store here, so the component
 * takes a name and derives. It is `aria-hidden` because it sits beside the name it was
 * derived from: announcing "A N" before "Ahmad Nabulsi" is noise.
 */
export function Avatar({ name, size = 28 }: { name: string; size?: number }) {
  const initials = name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => [...part][0] ?? "")
    .join("");
  return (
    <span
      className="ds-avatar"
      aria-hidden="true"
      style={{ inlineSize: `${size}px`, blockSize: `${size}px` }}
    >
      {initials}
    </span>
  );
}

/** Divider — a hairline. `role="separator"` only when it separates rather than decorates. */
export function Divider({ decorative = true }: { decorative?: boolean }) {
  return <hr className="ds-divider" {...(decorative ? { "aria-hidden": "true" } : {})} />;
}

/**
 * Skeleton — a placeholder at the real height of the thing it replaces.
 *
 * `aria-hidden`, because a screen reader should hear the count ("loading…") once rather than
 * five empty rows. The height is required for the same reason the DataGrid's skeleton rows
 * are: a placeholder shorter than its content makes the layout jump when data lands.
 */
export function Skeleton({ height, width }: { height: string; width?: string }) {
  return (
    <span
      className="ds-skeleton"
      aria-hidden="true"
      style={{ blockSize: height, inlineSize: width ?? "100%" }}
    />
  );
}

/** Spinner — beside a label, never instead of one. */
export function Spinner({ label }: { label: string }) {
  return (
    <span className="ds-spinner-wrap" role="status">
      <span className="ds-spinner" aria-hidden="true">◌</span>
      <span>{label}</span>
    </span>
  );
}

/**
 * Tooltip — supplementary only.
 *
 * A tooltip is unreachable on a touch surface and invisible to a reader who never hovers, so
 * nothing it says may be the only place that information exists. The component takes
 * `supplementary` to say that out loud at the call site, and wires `aria-describedby` rather
 * than `aria-label`, because describing is what a tooltip does and naming is what a label
 * does.
 */
export function Tooltip({
  id,
  supplementary,
  children,
  style,
}: {
  id: string;
  /** Text that is additional to what is already on screen, never a substitute for it. */
  supplementary: string;
  children: ReactNode;
  style?: CSSProperties;
}) {
  return (
    <span className="ds-tooltip" style={style}>
      <span aria-describedby={id}>{children}</span>
      <span role="tooltip" id={id} className="ds-tooltip-text">
        {supplementary}
      </span>
    </span>
  );
}
