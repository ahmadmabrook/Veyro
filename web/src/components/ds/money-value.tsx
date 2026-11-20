import { moneyParts as rawParts } from "@/i18n/conventions.mjs";
import type { Numbering } from "@/i18n/locale";

/**
 * MoneyValue — §39, "seven kinds, never a bare number".
 *
 * > JOD 55.00  neutral · a fact, no colour
 * > JOD 55.00  owed · critical, always with a status word nearby
 * > −JOD 28.00 refunded · sign is explicit, never colour-only
 * > JOD 12.50  wallet credit · labelled "credit", never a negative debt
 * > restricted no permission · never blank, never zero
 * > —          not applicable · em-dash, distinct from zero
 * > JOD 41,280 .00  aggregate · fils de-emphasised, never truncated
 * >
 * > Always three-letter code plus two decimals, tabular figures, end-aligned.
 *
 * Three of those are enforced here rather than left to each call site:
 *
 * **`kind` is required and there is no default.** "Never a bare number" is the rule, and a
 * default would be a bare number with a name. A caller who cannot say which of the seven
 * this is does not know what the figure means.
 *
 * **`restricted` and `notApplicable` take no amount at all**, so there is nothing to leak and
 * nothing to render as zero. The grid's own note: "a blank money cell reads as JOD 0.00 and
 * that is a financial misstatement."
 *
 * **`aggregate` splits the parts**, which is the one kind that cannot be one string: the
 * canvas draws `JOD 41,280 .00` with the major part at 21px and the decimals at 14px in the
 * secondary ink. `moneyParts` gives the pieces from the same table and the same rounding as
 * `formatMoney`, so the two cannot disagree.
 *
 * **The sign is explicit and never colour-only.** A refunded value carries `−` in the text,
 * which is what makes it readable in monochrome and to a colour-blind reader.
 */

export type MoneyKind =
  | "neutral"
  | "owed"
  | "refunded"
  | "credit"
  | "aggregate"
  | "restricted"
  | "notApplicable";

export function MoneyValue({
  kind,
  amountMinor,
  currency,
  numbering = "latn",
  restrictedLabel,
}: {
  kind: MoneyKind;
  /** Required for every kind but `restricted` and `notApplicable`, which carry no figure. */
  amountMinor?: number;
  currency?: string;
  numbering?: Numbering;
  /** The word shown where a figure is withheld. Never blank, never zero. */
  restrictedLabel?: string;
}) {
  if (kind === "restricted") {
    return <span className="ds-money ds-money-restricted">{restrictedLabel}</span>;
  }
  if (kind === "notApplicable") {
    // An em-dash, which is distinct from zero and says so to a screen reader by being a
    // different character rather than a different colour.
    return <span className="ds-money ds-money-na">—</span>;
  }
  if (amountMinor === undefined || currency === undefined) {
    throw new Error(`MoneyValue(${kind}) needs an amount and a currency`);
  }
  const { code, sign, major, minor } = rawParts(amountMinor, currency, numbering);
  // A refund's sign is in the text. `−` (minus) rather than a hyphen: it is the character
  // that aligns with digits in a tabular face.
  const shown = kind === "refunded" && sign === "" ? "−" : sign.replace("-", "−");
  return (
    // **The visible text is the accessible text.** The first version hid the figure with
    // `aria-hidden` and restated it in an `aria-label`, which axe refuses outright: a bare
    // `span` has no role, and `aria-label` on a role-less element is prohibited -- so the
    // figure was in the accessibility tree *nowhere*. The decimals sitting in a nested span
    // change nothing for a screen reader, which reads the run continuously.
    //
    // `dir="ltr"` is what keeps `JOD 30.16` from being re-ordered inside an Arabic
    // paragraph; it is the rendering half of what `isolate` does for a string.
    <span className="ds-money data" data-kind={kind} dir="ltr">
      {code} {shown}
      {major}
      {/* The one kind whose decimals are set smaller. Never dropped: "never truncated". */}
      {kind === "aggregate" ? <span className="ds-money-minor">{minor}</span> : minor}
    </span>
  );
}
