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
