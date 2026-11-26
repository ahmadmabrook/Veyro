import { t, type Locale, type MessageKey } from "@/i18n/locale";

/**
 * What a screen does not offer yet, in one line.
 *
 * **This replaces nineteen titled sections of explanation.** The design's own character line
 * is specific: where something cannot be derived, the surface says which fact is missing "in
 * the operator's language, in one line, in the place the figure would have been", and it
 * "never explains itself to engineers on a working screen". What the screens shipped instead
 * was a `<h2>` and a definition list of two-sentence justifications -- 11,457 characters of
 * it across twenty-six screens, a third of the account page and more than half of the reports
 * index. A gym owner opening the members list was reading why a search index is hard.
 *
 * So the names stay and the reasons go. A reader needs to know not to go looking for a
 * control; why it is absent is this repository's business, and
 * `contracts/ui/design-compliance.md` is where it already lives.
 *
 * **The heading is hidden rather than deleted, and that is a correction to this component's
 * first version.** It rendered a bare `<p>`, reasoning that "a heading creates a landmark and
 * a promise that what follows is worth reading, and neither is true of an absence". The first
 * half of that is right about a *sighted* reader and wrong about everybody else: a screen
 * reader navigates by landmark, so deleting the heading did not make the section quieter for
 * them, it made it unreachable -- they get to the end of the content and find an unannounced
 * sentence with no way to skip it or find it again. A visually-hidden heading costs a sighted
 * reader nothing and gives that reader the section back.
 *
 * **One phrasing, not five.** The sections this replaced were titled "What this screen does
 * not do", "...does not do yet", "What this screen cannot do", "What this report does not do"
 * and "What this grid does not do" -- one concept said five ways, which is the duplication
 * this system rules out everywhere else. `common.notYetTitle` is the one.
 */
export function NotYet({ locale, items }: { locale: Locale; items: MessageKey[] }) {
  if (items.length === 0) return null;
  return (
    <section className="ds-notyet-section" aria-labelledby="not-yet">
      <h2 id="not-yet" className="ds-visually-hidden">{t(locale, "common.notYetTitle")}</h2>
      <p className="ds-notyet">
        <span className="ds-notyet-lead">{t(locale, "common.notYet")}</span>
        {items.map((key) => t(locale, key)).join(" · ")}
      </p>
    </section>
  );
}
