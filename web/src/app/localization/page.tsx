import { redirect } from "next/navigation";

import { Banner } from "@/components/ds/banner";
import { StateChips } from "@/components/ds/choice-chips";
import { NotYet, PageHeader } from "@/components/ds/page-header";
import { monthDay } from "@/i18n/dates";
import { fill, formatMoney, isolate, t, type MessageKey } from "@/i18n/locale";
import { shapeDigits } from "@/i18n/conventions.mjs";
import { currentSession, gate, gateMessage } from "@/lib/api";
import {
  LANGUAGES_KEY,
  NUMERALS_KEY,
  PREVIEW_AMOUNT_MINOR,
  PREVIEW_CURRENCY,
  PREVIEW_DATE,
  isDefaulted,
  previewLocale,
  readDisplayConventions,
} from "@/lib/display";
import { presentation } from "@/lib/preferences";

/**
 * ADM-SET-07 · LOCALIZATION — the two display conventions, and the rules they obey.
 *
 * **Read-only, which is the canvas rather than a limitation of this build.** ADM-SET-06 sits
 * beside it in the same batch and draws an action (`→ Use #1F6E7A`); this one draws no save,
 * no button and no field — two chip groups, two statements and a preview. So the chips are a
 * statement of what is in force rather than a choice, and `StateChips` is the read of what
 * `ChoiceChips` writes. MOD-005's value publication is `config.value.publish`, financial
 * class, which is the same reason the configuration board beside it is read-only.
 *
 * **The preview is rendered, not drawn.** It goes through `monthDay`, `formatMoney` and
 * `shapeDigits` — the functions every other figure in the app goes through — so what a reader
 * checks here is what the product will do, rather than a picture of it. The two things it
 * demonstrates are the two a reader cannot verify any other way: whether `٢١ آب` is the month
 * name their members read, and whether the digits follow the tenant's rule while the money
 * beside them does not.
 *
 * **Three states the canvas does not draw, because its tenant has configured itself.** A
 * tenant that has declared nothing resolves to Latin digits and every catalogue this build
 * has — which is what every page renders today — so each group says whether the value is a
 * decision or a default, in the same words the configuration board uses for
 * `scope_type: "default"`. A tenant that does not offer Arabic gets the sample in English,
 * because a preview of a surface nobody will see demonstrates nothing. And a refused read is
 * a refusal here rather than a silent fallback: ADR-0015 D2 is about a page *rendering
 * figures*, where a gate answer must not be able to put a notice on the screen, and this is
 * the screen whose whole subject is the setting.
 */
export default async function LocalizationPage() {
  const { locale } = await presentation();
  const text = (key: MessageKey) => t(locale, key);

  const session = await currentSession();
  if (!session) redirect("/login");

  const mayDisplay = await gate("config.display.read");
  const conventions = mayDisplay.allowed
    ? await readDisplayConventions().catch(() => null)
    : null;

  if (conventions === null) {
    return (
      <div className="stack">
        <PageHeader title={text("localization.title")} />
        <Banner severity="info" title={text("localization.conventions")}>
          {text(mayDisplay.allowed ? "error.unexpected" : gateMessage(mayDisplay))}
        </Banner>
      </div>
    );
  }

  const previewLoc = previewLocale(conventions);
  const numeralsDefaulted = isDefaulted(conventions, NUMERALS_KEY);
  const languagesDefaulted = isDefaulted(conventions, LANGUAGES_KEY);

  return (
    <div className="stack">
      <PageHeader
        title={text("localization.title")}
        figures={
          <>
            {/* **The first figure in this product that follows the tenant's numeral setting,
                and it reads oddly on purpose.** An English reader on an `arab` tenant sees
                `٢ languages offered`, because `conventions.mjs` is explicit that numbering is
                never derived from locale -- "a tenant must not get Arabic-Indic digits merely
                because a string was Arabic", and the rule runs the other way too. The canvas
                says the same thing from the front: "Arabic-Indic for counts, dates and times.
                One rule per tenant, never mixed and never decided per component." Passing
                `latn` here to make the English line look ordinary would be deciding it per
                component, which is the one thing the rule forbids -- so the figure above the
                chips obeys the chip that is filled, which is also the only demonstration on
                this screen that the setting reaches anything at all. */}
            {fill(locale, "localization.languagesCounted",
                  { count: conventions.languages_offered.length }, conventions.numerals)}
            {" · "}
            {text(conventions.numerals === "arab" ? "localization.arab" : "localization.latn")}
          </>
        }
      />

      <section className="page-section">
        {/* No id: nothing on this screen is named by it, and an id a reader could
            follow to nothing is a declaration with no reader. */}
        <h2>{text("localization.conventions")}</h2>

        <div className="ds-convention-groups">
          {/* **Both languages are drawn, and the offered ones are filled.** The canvas shows
              two filled chips because its tenant offers both; a one-language tenant is the
              state that needs the unoffered chip drawn, and leaving it out would make the
              group read as a list of one rather than as a choice of two. */}
          <StateChips
            id="languages-label"
            legend={text("localization.languages")}
            inUse={text("localization.inUse")}
            options={LANGUAGE_NAMES.map((one) => ({
              value: one.code,
              label: one.autonym,
              on: conventions.languages_offered.includes(one.code),
            }))}
          />
          {/* **The samples are produced by the function they demonstrate.** `0123` and `٠١٢٣`
              are the same four digits through `shapeDigits`, which is what every figure in
              this app is shaped by — a pair of literals would be a second spelling of the one
              thing this screen exists to show. */}
          <StateChips
            id="numerals-label"
            legend={text("localization.numerals")}
            inUse={text("localization.inUse")}
            options={[
              { value: "latn", label: shapeDigits("0123", "latn") as string,
                on: conventions.numerals === "latn" },
              { value: "arab", label: shapeDigits("0123", "arab") as string,
                on: conventions.numerals === "arab" },
            ]}
          />
        </div>

        {languagesDefaulted && numeralsDefaulted ? (
          <p className="ds-note">{text("localization.defaulted")}</p>
        ) : null}

        {/* **The `JOD 41,280.00` inside this sentence is a literal, and that is correct
            rather than a missed call site.** Every other figure in this app goes through
            `formatMoney`; this one is a quotation of the canvas inside prose, and it can
            never need shaping, because the rule the sentence states is that money keeps
            Latin digits whatever the numeral setting is. A figure that cannot move is a
            figure a catalogue may hold. */}
        <div className="ds-rule-panel">
          <p style={{ margin: 0 }}>{text("localization.moneyRule")}</p>
        </div>

        <div className="ds-rule-panel">
          <p className="ds-field-label" style={{ margin: 0 }}>{text("localization.preview")}</p>
          {/* **The sample's own direction, which is not the page's.** An English-locale owner
              checking their tenant's Arabic rendering is the ordinary case, so the line is
              marked `dir` and `lang` for what it is rather than inheriting the document's. */}
          <p
            className="ds-preview-line"
            dir={previewLoc === "ar" ? "rtl" : "ltr"}
            lang={previewLoc}
            style={{ margin: 0 }}
          >
            {fill(previewLoc, "localization.previewSentence", {
              // Isolated because a date beside Arabic text re-orders without it, which is the
              // same bidi rule money already carries — `isolate` is the one implementation.
              on: isolate(monthDay(PREVIEW_DATE, previewLoc, conventions.numerals), "auto"),
              // **The tenant's numerals are deliberately not passed here.** `money_numerals`
              // is the server's own statement of the rule, so the page reads it rather than
              // remembering a constant — ADR-0015 D6.
              amount: formatMoney(PREVIEW_AMOUNT_MINOR, PREVIEW_CURRENCY,
                                  conventions.money_numerals, previewLoc),
            })}
          </p>
          <p className="ds-note" style={{ marginBlockStart: "var(--space-2)" }}>
            {text(previewLoc === "ar"
              ? "localization.previewLanguage"
              : "localization.previewLanguageEnglish")}
          </p>
        </div>

        <p className="ds-note">{text("localization.oneRule")}</p>
        <p className="ds-note">{text("localization.monthNames")}</p>
      </section>

      <NotYet title={text("localization.notYet")}>
        <dt>{text("localization.notYetWrite")}</dt>
        <dd>{text("localization.notYetWriteWhy")}</dd>
        <dt>{text("localization.notYetReach")}</dt>
        <dd>{text("localization.notYetReachWhy")}</dd>
        <dt>{text("localization.notYetReceipt")}</dt>
        <dd>{text("localization.notYetReceiptWhy")}</dd>
      </NotYet>
    </div>
  );
}

/**
 * A language's own name, which is the same string in every locale.
 *
 * **Not a catalogue entry.** "English" and "العربية" are autonyms — a reader picking a
 * language reads its name in that language, which is what the canvas draws and what every
 * language switcher does. Putting them in the message catalogue would ask a translator to
 * translate a name that must not be translated, and `MESSAGE_KEYS`' parity check could not see
 * that it had been.
 */
const LANGUAGE_NAMES = [
  { code: "en", autonym: "English" },
  { code: "ar", autonym: "العربية" },
] as const;
