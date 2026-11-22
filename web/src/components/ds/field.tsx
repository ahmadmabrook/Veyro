import type { CSSProperties, ReactNode } from "react";

/**
 * The field shell — §23, §24. Eighteen field types, one shell.
 *
 * > All share one shell — label, control, description, message, prefix, suffix, contextual
 * > action — so a new field type is a control swap, not a new component. Message slot holds
 * > exactly one message at a time, priority error > warning > success > description.
 *
 * **That priority is the part a hand-rolled field always gets wrong**, and the pre-directive
 * one did: it rendered a description *and* an error, so a field that was both explained and
 * invalid said two things and the reader read the first. One slot, one message, and the
 * priority is a function rather than a convention.
 *
 * The contracts:
 *
 * - **Accessibility.** "Label is a real label, not a placeholder. Error text referenced by the
 *   field and read on focus. Prefix and suffix are decorative and excluded from the accessible
 *   name." So the message is wired with `aria-describedby`, `aria-invalid` is set from the
 *   message kind, and the prefix carries `aria-hidden`.
 * - **RTL.** "Text aligns to logical start; numbers, phone, currency and IDs are bidi-isolated.
 *   Prefix moves to the inline-start edge." The isolation is per field *type*, not per locale.
 * - **Responsive.** "Full width below bp.sm. Numeric keyboards on number, currency, phone."
 *   `inputMode` is derived from the type rather than passed, because a caller that forgets it
 *   ships a phone field with a QWERTY keyboard.
 *
 * **Required is marked, optional is not — whichever is rarer gets the mark.** So the shell
 * takes `rarer` and marks that side, instead of hard-coding an asterisk on required fields in
 * a form where all but one are required.
 */

export type FieldType =
  | "text" | "number" | "currency" | "phone" | "email" | "password" | "search"
  | "textarea" | "select" | "multiselect" | "combobox" | "autocomplete"
  | "date" | "time" | "daterange" | "stepper" | "slider" | "switch";

export type FieldMessage =
  | { kind: "error"; text: string }
  | { kind: "warning"; text: string }
  | { kind: "success"; text: string }
  | null;

/** error > warning > success > description. Exactly one, always. */
export function visibleMessage(
  message: FieldMessage,
  description?: string,
): { kind: "error" | "warning" | "success" | "description"; text: string } | null {
  if (message) return message;
  if (description) return { kind: "description", text: description };
  return null;
}

/** The types whose values are bidi-isolated regardless of locale. */
const ISOLATED: ReadonlySet<FieldType> = new Set<FieldType>([
  "number", "currency", "phone", "date", "time", "daterange",
]);

/** Numeric keyboards, derived rather than passed. */
const INPUT_MODE: Partial<Record<FieldType, "numeric" | "decimal" | "tel" | "email" | "search">> = {
  number: "numeric",
  currency: "decimal",
  phone: "tel",
  email: "email",
  search: "search",
};

export function Field({
  id,
  name,
  label,
  type = "text",
  description,
  message = null,
  prefix,
  suffix,
  action,
  required,
  rarer = "required",
  marked,
  describedBy,
  defaultValue,
  autoComplete,
  placeholder,
  rows,
  children,
  style,
}: {
  id: string;
  name: string;
  label: string;
  type?: FieldType;
  description?: string;
  message?: FieldMessage;
  /** Decorative: excluded from the accessible name, per the contract. */
  prefix?: string;
  suffix?: string;
  /** The contextual action slot — "Use member's phone", "Clear". */
  action?: ReactNode;
  required?: boolean;
  /** Which side is rarer in this form, and therefore which gets the mark. */
  rarer?: "required" | "optional";
  /**
   * Mark the control without putting anything in the message slot.
   *
   * **For the one case the slot cannot serve: the explanation is a region beside the field.**
   * ADM-MEM-10 draws a phone input bordered in the attention colour with a panel under it
   * whose title *is* the sentence — and putting that sentence in the message slot as well
   * renders it twice, which is the duplication the slot's own rule exists to prevent ("the
   * message slot holds exactly one message"). So the mark and the message are separable, and
   * a caller that marks without a message points `describedBy` at the region that explains
   * it, which is what makes this different from a mark with no explanation at all.
   */
  marked?: "warning" | undefined;
  /** An element outside this shell that explains the control. Required with `marked`. */
  describedBy?: string | undefined;
  defaultValue?: string;
  autoComplete?: string;
  placeholder?: string;
  rows?: number;
  /** A control swap: a select or a combobox renders here instead of the input. */
  children?: ReactNode;
  style?: CSSProperties;
}) {
  const shown = visibleMessage(message, description);
  const ownMessage = shown ? `${id}-message` : undefined;
  // Both, where both exist: a field can carry its own description *and* point at the panel
  // that explains why it is marked.
  const messageId = [ownMessage, describedBy].filter(Boolean).join(" ") || undefined;
  const invalid = shown?.kind === "error";
  const mark =
    (rarer === "required" && required) || (rarer === "optional" && !required);

  return (
    <div className="ds-field" style={style}>
      {/* A real label, not a placeholder: it "disappears on focus, fails at small sizes and is
          invisible to a screen reader when the field is filled". */}
      <label htmlFor={id} className="ds-field-label">
        {label}
        {mark ? (
          <span className="ds-field-mark">
            {rarer === "required" ? " *" : " (optional)"}
          </span>
        ) : null}
      </label>

      {/* **The control carries the message's kind, not only `aria-invalid`.** The source
          states a priority -- error > warning > success > description -- and ADM-MEM-10 draws
          the warning one on the border: a phone number that already has a record is marked on
          the field as well as under it. `aria-invalid` stays error-only, because a warning is
          not an invalid value and announcing it as one would be wrong. */}
      <div className="ds-field-control" data-message={marked ?? shown?.kind}>
        {prefix ? (
          // Decorative and excluded from the accessible name. It sits at the inline-start
          // edge, which mirrors without a direction check.
          <span className="ds-field-affix" aria-hidden="true">{prefix}</span>
        ) : null}
        {children ?? (
          type === "textarea" ? (
            <textarea
              id={id}
              name={name}
              rows={rows ?? 3}
              defaultValue={defaultValue}
              placeholder={placeholder}
              aria-describedby={messageId}
              aria-invalid={invalid || undefined}
              required={required}
              className="ds-field-input"
            />
          ) : (
            <input
              id={id}
              name={name}
              type={HTML_TYPE[type] ?? "text"}
              inputMode={INPUT_MODE[type]}
              dir={ISOLATED.has(type) ? "ltr" : undefined}
              defaultValue={defaultValue}
              placeholder={placeholder}
              autoComplete={autoComplete}
              aria-describedby={messageId}
              aria-invalid={invalid || undefined}
              required={required}
              className="ds-field-input"
            />
          )
        )}
        {suffix ? <span className="ds-field-affix" aria-hidden="true">{suffix}</span> : null}
        {action ? <span className="ds-field-action">{action}</span> : null}
      </div>

      {shown ? (
        <p id={ownMessage} className={`ds-field-message ds-field-message-${shown.kind}`}>
          {shown.text}
        </p>
      ) : null}
    </div>
  );
}

/** Which HTML input type each field type swaps in. The shell does not change. */
const HTML_TYPE: Partial<Record<FieldType, string>> = {
  text: "text",
  number: "text", // text + inputMode, so a leading zero and a grouping separator survive
  currency: "text",
  phone: "tel",
  email: "email",
  password: "password",
  search: "search",
  date: "date",
  time: "time",
};
