import type { ReactNode } from "react";

/**
 * A small multi-select drawn as chips — ADM-CRM-04's `INTEREST · OPTIONAL`.
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
}: {
  name: string;
  legend: string;
  /** The rarer side's mark, as a word from the catalogue. `undefined` marks nothing. */
  mark?: string;
  options: readonly { value: string; label: string }[];
  defaultSelected?: readonly string[];
  /** A rule the reader needs before choosing, under the group. At most one. */
  note?: ReactNode;
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
              type="checkbox"
              name={name}
              value={one.value}
              defaultChecked={defaultSelected.includes(one.value)}
              className="ds-visually-hidden"
            />
            <span className="ds-choice-chip-face">{one.label}</span>
          </label>
        ))}
      </div>
      {note === undefined ? null : <p className="ds-choice-note">{note}</p>}
    </fieldset>
  );
}
