/**
 * The core controls, built on layer-2 tokens only.
 *
 * Three rules from the foundations are structural here rather than stylistic:
 *
 *   * **Anything pressable gets `radius.button`; containers and data stay sharp.** "radius.button
 *     is larger than radius.card, which looks wrong in a list and is right on screen."
 *   * **One accent, spent once.** `ink.600` is used on action and selection only, and semantic
 *     colour stays inside status components. A button does not get to be green.
 *   * **The focus ring is system-owned.** No component here sets `outline`, because guardrail
 *     G4 makes it non-configurable: "a tenant cannot ship an unnavigable product."
 *
 * Every control also has to work at `Touch` density, whose minimum target is 44px -- which is
 * why the button and the input are sized in spacing-scale steps that reach it rather than in
 * whatever looked right.
 */

import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode } from "react";

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary";
  /** While true the button is disabled and announces itself as busy. */
  busy?: boolean;
  busyLabel?: string;
};

export function Button({
  variant = "secondary",
  busy = false,
  busyLabel,
  children,
  disabled,
  style,
  ...rest
}: ButtonProps) {
  const primary = variant === "primary";
  return (
    <button
      {...rest}
      // `aria-busy` rather than only a visual change: a screen-reader user otherwise gets no
      // signal that the form is in flight.
      aria-busy={busy || undefined}
      disabled={disabled || busy}
      style={{
        minHeight: "44px",
        padding: "var(--space-2) var(--space-4)",
        borderRadius: "var(--radius-button)",
        border: primary ? "1px solid transparent" : "1px solid var(--color-border-default)",
        background: primary ? "var(--color-action-primary)" : "var(--color-surface-default)",
        color: primary ? "var(--color-text-inverse)" : "var(--color-text-primary)",
        fontFamily: "inherit",
        fontSize: "var(--type-label-size)",
        fontWeight: "var(--type-label-weight)",
        letterSpacing: "var(--type-label-tracking)",
        cursor: busy || disabled ? "default" : "pointer",
        // A disabled control still has to be readable: `color.text.disabled` is warm.500,
        // which the DS permits for "disabled controls" specifically.
        opacity: disabled && !busy ? 0.55 : 1,
        ...style,
      }}
    >
      {busy && busyLabel ? busyLabel : children}
    </button>
  );
}

type FieldProps = {
  id: string;
  label: string;
  hint?: string;
  /** A validation message. Rendered, associated, and announced. */
  error?: string;
  children?: ReactNode;
} & Omit<InputHTMLAttributes<HTMLInputElement>, "id">;

/**
 * A labelled input with its hint and error wired to it.
 *
 * **The label is a real `<label for>` and the error is referenced by `aria-describedby`.** A
 * placeholder is not a label -- it disappears on focus, fails at small sizes and is invisible
 * to a screen reader as a name -- so there is no placeholder-as-label path here.
 */
export function Field({ id, label, hint, error, children, style, ...rest }: FieldProps) {
  const hintId = hint ? `${id}-hint` : undefined;
  const errorId = error ? `${id}-error` : undefined;
  const described = [hintId, errorId].filter(Boolean).join(" ") || undefined;
  return (
    <div className="stack" style={{ gap: "var(--space-1)" }}>
      <label
        htmlFor={id}
        style={{
          fontSize: "var(--type-label-size)",
          fontWeight: "var(--type-label-weight)",
          letterSpacing: "var(--type-label-tracking)",
        }}
      >
        {label}
      </label>
      {hint ? (
        <span
          id={hintId}
          className="muted"
          style={{ fontSize: "var(--type-bodySm-size)", lineHeight: "var(--type-bodySm-line)" }}
        >
          {hint}
        </span>
      ) : null}
      <input
        {...rest}
        id={id}
        aria-describedby={described}
        aria-invalid={error ? true : undefined}
        style={{
          minHeight: "44px",
          padding: "var(--space-2) var(--space-3)",
          background: "var(--color-surface-input)",
          color: "var(--color-text-primary)",
          // Data stays sharp. An input is a container, not a pressable surface.
          borderRadius: "var(--radius-card)",
          border: `1px solid ${error ? "var(--color-border-error)" : "var(--color-border-default)"}`,
          fontFamily: "inherit",
          fontSize: "var(--type-body-size)",
          ...style,
        }}
      />
      {error ? (
        <span
          id={errorId}
          style={{
            color: "var(--color-text-critical)",
            fontSize: "var(--type-bodySm-size)",
            lineHeight: "var(--type-bodySm-line)",
          }}
        >
          {error}
        </span>
      ) : null}
      {children}
    </div>
  );
}

/**
 * A status message. `role="alert"` for an error so it is announced without a focus move.
 *
 * Semantic colour is confined to this component, which is what "one accent, spent once"
 * requires: a page does not get to paint its own error red.
 */
export function Alert({
  tone = "error",
  children,
}: {
  tone?: "error" | "info" | "success";
  children: ReactNode;
}) {
  const colour = {
    error: "var(--color-semantic-error)",
    info: "var(--color-semantic-info)",
    success: "var(--color-semantic-success)",
  }[tone];
  return (
    <div
      role={tone === "error" ? "alert" : "status"}
      style={{
        // A hairline and a start-edge mark rather than a fill: the severity scale is one
        // four-step idea, and a filled panel would say it twice.
        //
        // **Order is load-bearing.** These are an inline style object, so the keys are applied
        // in insertion order and the `border` shorthand resets every longhand that precedes it.
        // Written the other way round the severity mark silently disappeared -- the component
        // looked finished, the token was correct, and the one thing distinguishing an error
        // from a notice was not on screen. Found by looking at a render, not by reading this.
        border: "1px solid var(--color-border-subtle)",
        borderInlineStart: `3px solid ${colour}`,
        borderRadius: "var(--radius-card)",
        padding: "var(--space-3) var(--space-4)",
        background: "var(--color-surface-default)",
        color: "var(--color-text-primary)",
        fontSize: "var(--type-body-size)",
      }}
    >
      {children}
    </div>
  );
}
