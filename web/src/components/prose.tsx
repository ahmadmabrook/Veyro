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
export function ProseNote({ children }: { children: string }) {
  return (
    <p className="ds-note">
      <Prose>{children}</Prose>
    </p>
  );
}
