import Link from "next/link";

import { t, type Locale, type MessageKey } from "@/i18n/locale";

/**
 * A value the reader may not see, rendered as withheld rather than as blank.
 *
 * **MOD-014's own rule: a redacted record still exists.** Telling a coach that a member has no
 * health notes when they have three is worse than telling them there are three they cannot
 * read, and paragraph 10280's "minimum necessary" is not zero knowledge that the context
 * exists. An empty cell is indistinguishable from "there was nothing here", which is the one
 * reading that is always wrong.
 *
 * The reason is part of the rendering, because the two reasons a field is withheld here have
 * different remedies and one of them has none: an identity field needs a stronger sign-in,
 * and a health field cannot be read by anybody in this build -- `member.health.read` is
 * `biometric_sensitive`, which maps to assurance level 3, which needs a hardware authenticator
 * MOD-007 cannot verify. Offering a step-up for the second would send somebody looking for a
 * key the product cannot check.
 */
export function Withheld({ locale, reason }: { locale: Locale; reason: MessageKey }) {
  return (
    <span>
      <span
        className="withheld"
        // The marker is not the whole message: a screen-reader user gets the reason, and a
        // sighted reader gets it from the title and from the legend on the section.
        title={t(locale, reason)}
      >
        {t(locale, "member.withheld")}
      </span>
      <span className="sr-only"> — {t(locale, reason)}</span>
    </span>
  );
}

/**
 * A withheld name that is still a link to the record it names.
 *
 * **A row whose name is withheld had no link at all**, so on an ordinary sign-in -- the
 * front desk's own credential -- the members list and the staff list were dead ends: every
 * name was marked and not one row could be opened. The name is what the mask withholds; the
 * row's identity is not secret, and the record behind it is the page that explains the
 * withholding and offers the step-up.
 *
 * **Found by an independent tester**, which is what that layer is for: it was told to open a
 * person's record from the list, found the cell unclickable, went looking for another way
 * through and was stopped by a step-up it had no recovery code for. The same agent found the
 * missing step-up offer on the members list a session earlier, by clicking the marker looking
 * for a way through. Twice now, the same reader behaviour against the same cell.
 *
 * `label` is what distinguishes this row, built from what is *not* withheld -- a member
 * number, a job title, a start date. A link whose only name is "Withheld" is one a
 * screen-reader user cannot tell from the next; it is appended to the name rather than
 * replacing it, because a name that drops the visible text is its own accessibility
 * violation.
 */
export function WithheldLink({
  locale, reason, href, label,
}: { locale: Locale; reason: MessageKey; href: string; label: string }) {
  // **No `aria-label`.** An element named through its content must have that content in its
  // accessible name -- WCAG's `label-content-name-mismatch`, which axe rates serious and
  // which the first version broke on every row of two lists: an `aria-label` *replaces* the
  // name, so the visible "Withheld" vanished from it. The detail rides inside the link
  // instead, where it adds to the name rather than replacing it.
  return (
    <Link href={href}>
      <Withheld locale={locale} reason={reason} />
      <span className="sr-only"> — {label}</span>
    </Link>
  );
}
