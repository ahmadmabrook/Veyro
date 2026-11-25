import type { ChangeEvent, ReactNode } from "react";

/**
 * A small single- or multi-select drawn as chips — ADM-CRM-04's `INTEREST · OPTIONAL` and
 * ADM-CRM-07's `ReasonPicker`.
 *
 * §23 names eighteen field types and `multiselect` is one of them; nothing in the design
 * system provided it, so the drawing is the specification. The canvas:
 *
 * > INTEREST · OPTIONAL
 * > [Classes] [PT] ( Gym only )
 *
 * with the first two filled in `warm.900` and the third outlined — a selected chip is a
 * filled surface with inverse ink, an unselected one is a 1px border on the canvas. Three
 * options, so a `<select multiple>` would be worse than the chips in every way a reader
 * cares about: it needs a modifier key, it hides the unchosen options, and it is the one
 * control on this screen a receptionist taps while looking at a person.
 *
 * **A fieldset and real checkboxes, not pressable spans.** The chip is the label's
 * appearance; the control underneath is `<input type="checkbox">`, visually hidden and
 * focusable, so the group keeps the semantics the canvas's appearance implies — a legend a
 * screen reader announces once, a checked state, keyboard operation, and a `FormData` entry
 * per selection with no client state at all. A `<span>` with `onClick` would be a form
 * control this app could not submit without JavaScript, on a surface whose sign-in
 * deliberately works without it.
 *
 * **Not `Chip`.** That primitive is "a removable filter, or a small enumerated value" and its
 * own docstring says it is not pressable; this is a form control whose selected state is the
 * value being submitted. The source keeps badge and chip apart for the same kind of reason.
 *
 * **Not `Field`.** The shell renders `<label for>`, which is wrong for a group: a label may
 * name one control and a group of checkboxes is named by a `<legend>`. So this carries the
 * label itself, in the shell's own label type, and takes the optional mark as a word rather
 * than hard-coding one — `rarer` is the shell's rule and the mark is a word that has to come
 * from the catalogue.
 */
export function ChoiceChips({
  name,
  legend,
  mark,
  options,
  defaultSelected = [],
  note,
  single = false,
  required = false,
  onChange,
}: {
  name: string;
  legend: string;
  /** The rarer side's mark, as a word from the catalogue. `undefined` marks nothing. */
  mark?: string;
  options: readonly { value: string; label: string }[];
  defaultSelected?: readonly string[];
  /** A rule the reader needs before choosing, under the group. At most one. */
  note?: ReactNode;
  /**
   * One choice rather than several, drawn identically and submitted as one value.
   *
   * **ADM-CRM-07 names a `ReasonPicker` and this is it.** Its canvas draws four chips --
   * "Too expensive / Joined somewhere else / Location or hours / No longer responding" --
   * in exactly the shape ADM-CRM-04 draws three interests in, and a lead is lost for one
   * reason. A second component would be two spellings of one appearance, which is the
   * duplication-by-divergence this file's own mark note already records.
   *
   * The control becomes `<input type="radio">`, so the group keeps the semantics the
   * appearance implies: arrow keys move within it, one value reaches `FormData`, and the
   * browser enforces the one-of-many rule rather than a client.
   */
  single?: boolean;
  /**
   * Whether a choice is required.
   *
   * **`aria-required` and not the native attribute**, for the reason ADM-MEM-10 and
   * ADM-CRM-04 both paid for: a native constraint refuses the submit before any server sees
   * it, so the message slot a reader would act on never renders and a branch written for it
   * becomes unreachable. The server refuses and says which field.
   */
  required?: boolean;
  /**
   * Told when the choice changes, without taking control of it.
   *
   * **The group stays uncontrolled and the DOM stays the source of truth**, which is what
   * makes it work with JavaScript disabled: the checkboxes feed `FormData` exactly as they
   * did and this is a notification rather than a value. ADM-SCH-03 needs it because the
   * canvas requires an answer *as* the field changes -- "conflicts surface as the coach field
   * changes, not on save" -- and the count on its own button moves with the chips.
   *
   * Reading the group from the event's own form is what keeps the two in step: a callback
   * that maintained its own array would be a second copy of the selection, and the day they
   * disagreed the button would state a count the submit does not send.
   */
  onChange?: (selected: string[]) => void;
}) {
  return (
    <fieldset className="ds-choice-group">
      <legend className="ds-field-label">
        {legend}
        {/* **The same shape the field shell renders**, parentheses included. The canvas draws
            `SOURCE · OPTIONAL` and `INTEREST · OPTIONAL` with one treatment, and this rendered
            "Interest optional" beside "Source (optional)" until somebody read the page: two
            marks for one meaning, on one screen, which is the duplication-by-divergence the
            shared-component rule exists to prevent. */}
        {mark === undefined ? null : (
          <span className="ds-field-mark">{` (${mark})`}</span>
        )}
      </legend>
      <div className="ds-choice-chips">
        {options.map((one) => (
          <label key={one.value} className="ds-choice-chip">
            <input
              type={single ? "radio" : "checkbox"}
              name={name}
              value={one.value}
              defaultChecked={defaultSelected.includes(one.value)}
              aria-required={required ? true : undefined}
              className="ds-visually-hidden"
              {...(onChange === undefined ? {} : {
                onChange: (event: ChangeEvent<HTMLInputElement>) => {
                  const form = event.target.form;
                  if (form === null) return;
                  onChange(
                    [...form.elements]
                      .filter((element): element is HTMLInputElement =>
                        element instanceof HTMLInputElement
                        && element.name === name && element.checked)
                      .map((element) => element.value));
                },
              })}
            />
            <span className="ds-choice-chip-face">{one.label}</span>
          </label>
        ))}
      </div>
      {note === undefined ? null : <p className="ds-choice-note">{note}</p>}
    </fieldset>
  );
}

/**
 * The same chips, read-only — which of a closed set of values is in force.
 *
 * **Beside `ChoiceChips` rather than in a file of its own, because the appearance is one
 * appearance.** A selected chip is a filled surface with inverse ink and an unselected one is
 * a 1px border on the canvas; that rule is drawn identically on ADM-CRM-04's `INTEREST`, on
 * ADM-CRM-07's `ReasonPicker` and on ADM-SET-07's `NUMERALS`, and the stylesheet carries it
 * once for both components. Two files would be two spellings of one drawing, which is the
 * duplication-by-divergence this build keeps finding.
 *
 * **Not a form control, and not a disabled one.** ADM-SET-07 draws no save and no action --
 * unlike ADM-SET-06 beside it, which draws `→ Use #1F6E7A` -- so the chips there are a
 * statement of what is in force rather than a choice: MOD-005's value publication is
 * `config.value.publish`, financial class, and the whole surface is read-only for that reason.
 * A disabled checkbox would be a control a reader tries, and `Chip` is the wrong primitive in
 * the other direction -- its own docstring says it is "a removable filter, or a small
 * enumerated value" and gives no in-force state at all.
 *
 * **The in-force value says so in words, because colour is never the only signal.** A filled
 * chip is the sighted reading; `inUse` is a word from the catalogue, rendered visually hidden
 * on the one chip that carries it, so the list reads as "0123, ٠١٢٣ in use" rather than as two
 * values a screen reader cannot tell apart. The unselected ones carry nothing: which one is in
 * force is the distinction, and "not in use" on every other chip is noise.
 */
export function StateChips({
  id,
  legend,
  inUse,
  options,
}: {
  /**
   * The label's own id, so the list is named by it.
   *
   * **Passed rather than derived from the legend**, which is `DataGrid`'s `labelledBy` rule:
   * an id built from translated text is an id that changes with the reader's language and
   * breaks on a space. The caller knows what the group is; the component does not.
   */
  id: string;
  legend: string;
  /** The word for the value in force, from the catalogue. */
  inUse: string;
  options: readonly { value: string; label: string; on: boolean }[];
}) {
  return (
    <div className="ds-state-group">
      <p className="ds-field-label" id={id}>{legend}</p>
      <ul className="ds-choice-chips" aria-labelledby={id}>
        {options.map((one) => (
          <li key={one.value}>
            <span className="ds-state-chip" data-on={one.on ? "true" : "false"}>
              {one.label}
              {one.on ? <span className="ds-visually-hidden">{` — ${inUse}`}</span> : null}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
