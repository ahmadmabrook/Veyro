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
 */

export const MASK = "***";

export function isWithheld(value: unknown): boolean {
  return value === MASK;
}
