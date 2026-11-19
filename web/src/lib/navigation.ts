/**
 * Where a flow may send the reader back to, and nowhere else.
 *
 * **A `next` parameter is attacker-controllable by construction**: it arrives in a link, and a
 * link is the one thing a reader can be handed. A redirect that followed it anywhere would be
 * an open redirect on the sign-in and step-up paths -- the two places in this product where
 * somebody has just typed a credential, which is exactly where a redirect to a lookalike host
 * is worth the most.
 *
 * So the rule is a whitelist of shape rather than a blacklist of hosts: a same-origin path, and
 * nothing else. Four things are refused and each one is a real bypass of a naive
 * `startsWith("/")` check:
 *
 *   * `//evil.test` is protocol-relative -- a browser reads it as an absolute URL on another
 *     host, and it starts with a slash;
 *   * `/\evil.test` is the same trick with a backslash, which browsers normalise to `/`;
 *   * `https://evil.test` is refused by the leading-slash rule, and `/https://evil.test` by
 *     the scheme check, because a path that merely *contains* a scheme is nothing this app
 *     ever produces;
 *   * a control character or a newline is refused outright: those are what split a header or
 *     smuggle a second location in an environment less careful than this one.
 *
 * The fallback is the landing page. A refused `next` is never an error the reader sees: being
 * sent somewhere safe is the correct outcome, and an error message here would only teach
 * somebody which of their probes got through.
 */
export const HOME = "/";

export function safeNext(raw: string | null | undefined): string {
  if (typeof raw !== "string") return HOME;
  const candidate = raw.trim();
  if (candidate.length === 0 || candidate.length > 512) return HOME;
  if (!candidate.startsWith("/")) return HOME;
  if (candidate.startsWith("//") || candidate.startsWith("/\\")) return HOME;
  if (candidate.includes("://") || candidate.includes("\\")) return HOME;
  if (/[\u0000-\u001f\u007f]/.test(candidate)) return HOME;
  return candidate;
}
