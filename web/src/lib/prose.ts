/**
 * Prose the backend wrote for a developer, rendered for a reader.
 *
 * **The registry's reasons carry Markdown and a surface was printing it literally.**
 * `SUBJECT_COLUMNS` declares, per column, why erasure has the mechanism it has, and those
 * sentences were written where `**` is emphasis and a backtick is a column name -- in a Python
 * module a developer reads. Rendered as plain text on a page they come out as
 * `**who pays.** The account is the party an invoice is addressed to`, which is punctuation
 * nobody wrote for a reader, in the middle of the one block on that page whose whole job is to
 * be read by somebody who is not a developer.
 *
 * Two choices were available and stripping the markers was the worse one: the emphasis is the
 * summary phrase of each reason -- "**who pays.**", "**who was in the room.**" -- so throwing
 * it away loses the part a skimming reader needs most. This splits instead.
 *
 * **It is not a Markdown parser and must not become one.** It recognises exactly two
 * delimiters, pairs them greedily left to right, and treats anything unmatched as literal
 * text. The input is prose this repository wrote and ships, not anything a tenant supplies, so
 * there is no sanitising question here -- but the moment a caller-supplied string is rendered
 * through this, there is, and that is the line to notice rather than cross.
 */

export type ProseSegment =
  | { kind: "text"; value: string }
  | { kind: "strong"; value: string }
  | { kind: "code"; value: string };

const PATTERN = /\*\*([^*]+)\*\*|`([^`]+)`/g;

export function segments(prose: string): ProseSegment[] {
  const out: ProseSegment[] = [];
  let at = 0;
  for (const match of prose.matchAll(PATTERN)) {
    const index = match.index ?? 0;
    if (index > at) out.push({ kind: "text", value: prose.slice(at, index) });
    if (match[1] !== undefined) out.push({ kind: "strong", value: match[1] });
    else if (match[2] !== undefined) out.push({ kind: "code", value: match[2] });
    at = index + match[0].length;
  }
  if (at < prose.length) out.push({ kind: "text", value: prose.slice(at) });
  return out;
}
