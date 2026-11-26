import { Withheld } from "@/components/withheld";
import type { Locale, MessageKey } from "@/i18n/locale";
import { nameOf, type NamedPerson } from "@/lib/desk";

/**
 * A member's name where a list has only their id.
 *
 * **It exists because two screens render the same cell and one of them was printing a
 * truncated uuid.** The roster on a session showed `person_id.slice(0, 8)` for every row,
 * on both the booked list and the waitlist -- an internal identifier in normal product UI,
 * on the screen a coach opens to see who is coming. FD-06 had already solved it with
 * `GET /people/names`, the batch that keeps a composed roster from asking one row at a
 * time, and had the cell as a local component; a second copy here would be two screens
 * able to word one withheld name two ways.
 *
 * **A withheld name still identifies the row.** MOD-014's rule is that a redacted record
 * still exists, so the marker renders with the member number beside it where there is one:
 * a list of identical markers is a list a desk cannot work from, and the number is the
 * human-facing handle a tenant already uses out loud.
 *
 * **Which sentence a withheld name gets is the page's to decide**, not this component's:
 * `member.identity.read` is financial class, so a step-up lifts the mask for a session
 * holding the grant at too low an assurance and does nothing at all for a reader who does
 * not hold it. Only the page has the gate's answer, so the key travels as a prop.
 */
export function PersonName({ locale, person, nameWithheld }: {
  locale: Locale;
  person: NamedPerson | undefined;
  nameWithheld: MessageKey;
}) {
  const shown = nameOf(person);
  if (shown !== null) return <strong>{shown}</strong>;
  return (
    <strong>
      <Withheld locale={locale} reason={nameWithheld} />
      {person?.member_number ? (
        <span className="muted"> · {person.member_number}</span>
      ) : null}
    </strong>
  );
}
