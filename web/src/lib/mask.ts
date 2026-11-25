import type { GateVerdict } from "@/lib/api";

/**
 * MOD-014's masking marker, in a module that reaches nothing.
 *
 * **`"***"` is a value, not an absence, and the difference is the whole point.** MOD-014's
 * masking replaces a field a caller may not read with this marker at every depth, and its own
 * rule is that "a redacted record still exists": telling a coach a member has no health notes
 * when they have three is worse than telling them there are three they cannot read. So no
 * surface drops a masked value -- `isWithheld` marks it, and the screen renders it as withheld
 * rather than as blank. MOD-027's lead board paid for rendering the marker as though somebody
 * were called that.
 *
 * **It lives here rather than in `@/lib/people` because that module imports `@/lib/api`**, and
 * `api` reaches `next/headers` -- so a *client* component importing anything from it fails the
 * build. `@/lib/shift` is reached by FD-07's open form, and importing the predicate from
 * `people` broke the client/server boundary with `typecheck` and `lint` both green: `build` is
 * the only step that sees it, which is the third time this repository has paid for that and the
 * first where the module being imported was a mixed one rather than a reader.
 *
 * `people.ts` re-exports both names, so the thirteen server pages that already import them are
 * untouched and there is still one definition.
 *
 * **The one import here is `import type`, which is erased**, so nothing in this module reaches
 * `next/headers` at runtime and FD-07's client form still builds. A *value* import from `api`
 * would break it again, with `typecheck` and `lint` green and only `build` objecting -- so
 * check the keyword before adding one, not the module name.
 */

export const MASK = "***";

export function isWithheld(value: unknown): boolean {
  return value === MASK;
}

/**
 * Why a name on a list is withheld, and therefore what the page may offer.
 *
 * **Two pages told every reader the same thing and it was false for most of them.** The
 * members list and the staff list both said the cause was a missing second factor and offered
 * the step-up that lifts it -- unconditionally, because `isWithheld` answers *whether* a value
 * is masked and nothing asked *why*. A legal name is MOD-014's `identity` class, which
 * `member.identity.read` opens, and that permission is `financial` -- so the sentence is right
 * for a session that holds the grant at an assurance it has not reached, and wrong for a role
 * that does not hold it at all. For that reader a step-up changes nothing: they follow the
 * link, present a recovery code they cannot spare, and the names are still withheld.
 *
 * **ADR-0014 is what made the wrong half reachable on `/staff`.** Before it a brand- or
 * location-scoped caller was refused that read outright, so the only readers were tenant-wide
 * ones who hold everything; the club manager the ADR admits holds `people.person.read` and
 * nothing else, and `people.person.read` opens no class at all. So the first reader the gate's
 * new answer let onto that page was shown a remedy that could not work.
 *
 * This is MOD-008's `reachable` finding in a sentence rather than a field -- one boolean over
 * two situations with different remedies -- and it is the same split the schedule board makes
 * for a masked change reason, which is where the shape comes from. The verdict is the gate's,
 * so the page asks about `member.identity.read` and renders what the answer supports.
 *
 * It takes a *verdict* rather than a whole answer because it is a statement about a closed
 * gate: a caller the gate allows has nothing withheld, so the banner does not render and there
 * is no fourth case to write. A branch nothing can reach is this build's most-repeated finding
 * and it is not worth creating one here to look thorough.
 */
export type WithheldRemedy = "step_up" | "not_held" | "no_answer";

export function withheldRemedy(verdict: GateVerdict): WithheldRemedy {
  switch (verdict) {
    case "needs_step_up":
      return "step_up";
    case "gate_failed":
      // Not about the reader's access at all, so it must not read as a refusal -- the whole
      // reason `gateVerdict` has this verdict.
      return "no_answer";
    // `unreachable_level` cannot occur for a `financial` permission, which maps to AAL 2 and is
    // reachable by a password or a recovery code. It lands here rather than with `step_up`
    // because if it ever did occur a step-up would not open it, which is what this value means.
    default:
      return "not_held";
  }
}
