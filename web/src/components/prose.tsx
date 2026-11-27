import { segments } from "@/lib/prose";

/**
 * Backend prose with its emphasis kept, rendered for a reader.
 *
 * See `src/lib/prose.ts` for why this exists: the registry's reasons were written where `**`
 * is emphasis and a backtick is a column name, and a page printing them literally shows
 * punctuation nobody wrote for a reader -- in the one block whose job is to be read by
 * somebody who is not a developer.
 */
export function Prose({ children }: { children: string }) {
  return (
    <>
      {segments(children).map((segment, index) =>
        segment.kind === "strong" ? (
          <strong key={index}>{segment.value}</strong>
        ) : segment.kind === "code" ? (
          <span key={index} className="data" dir="ltr">
            {segment.value}
          </span>
        ) : (
          <span key={index}>{segment.value}</span>
        ),
      )}
    </>
  );
}

/**
 * `Prose` in a paragraph of its own.
 *
 * **`Prose` is a fragment of inline spans, and that is easy to miss.** Every existing call
 * site puts it inside a block that already exists -- a `dd`, a grid cell -- so it had never
 * needed a wrapper. Used bare at the top level of a page it renders as a run of inline text,
 * and four of them in a row become one paragraph: "...add up to the invoiced total.The design
 * breaks this down by club." Found by looking at the page.
 *
 * So the block form exists rather than a comment telling the next caller to remember a `<p>`.
 */
/**
 * **Why this is a block and `Prose` is not.** `Prose` renders a run of inline spans, and a
 * `.page-section` is a column flex container -- so used bare, every emphasised and
 * backticked run becomes its own flex item on its own line: eight blocks where one paragraph
 * belongs. It was found by looking at a page rather than by any assertion, and the e2e test
 * that measured it (several runs sharing a vertical position) has since lost its subject,
 * because no note in this app carries three emphasised runs any more. Write a multi-run note
 * with this, not with `Prose`.
 */
export function ProseNote({ children }: { children: string }) {
  return (
    <p className="ds-note">
      <Prose>{children}</Prose>
    </p>
  );
}
