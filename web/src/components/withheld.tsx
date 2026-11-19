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
