import { Withheld } from "@/components/withheld";
import { fill, type Locale, type MessageKey } from "@/i18n/locale";
import { monthYearLabel } from "@/lib/time";
import { knownFrom, recognitionParts, type ContactMatch } from "@/lib/walk-in";

/**
 * The matched record's own line — "**Hala Barakat** · M-03918 · joined Feb 2025".
 *
 * **One component, because two screens show the same match.** ADM-MEM-10 renders it before
 * creating a member and ADM-CRM-04 before creating a lead, over the same
 * `GET /people/contact-match` read and the same two decisions — `recognitionParts` for what a
 * desk recognises somebody by, `knownFrom` for the date. The two screens had a copy each,
 * differing only in which catalogue key spelled "joined", which is a line that must say the
 * same thing in two places and would drift the first time either was edited.
 *
 * **The name may be withheld and the line still has to identify the record.** A legal name is
 * `identity` class, so a routine sales or front-desk session gets the marker — and a panel
 * reading only "Withheld" tells a desk nothing about whether this is the person in front of
 * them. The member number and the date are not identity-class, so they stay.
 */
export function ContactMatchLine({
  locale, match, nameWithheld,
}: {
  locale: Locale;
  match: ContactMatch;
  // Which sentence a withheld name gets. The page decides it from the gate's answer, because
  // only the page knows whether a step-up would lift the mask -- and it differs by screen:
  // creating a *member* is financial class, so that reader can step up, while opening a lead
  // is routine, so a salesperson may hold no identity read at any assurance.
  nameWithheld: MessageKey;
}) {
  const shown = match.preferred_name ?? match.legal_name;
  const withheld = shown === null || shown === "***";
  const parts = recognitionParts(match);
  return (
    <>
      <strong>
        {withheld
          ? <Withheld locale={locale} reason={nameWithheld} />
          : shown}
      </strong>
      {parts.map((part) => (
        <span key={part}> · {part}</span>
      ))}
      <span>
        {" · "}
        {fill(
          locale,
          match.joined_on === null ? "contactMatch.knownSince" : "contactMatch.joined",
          { date: monthYearLabel(knownFrom(match), locale) },
        )}
      </span>
    </>
  );
}
