import type { ReactNode } from "react";

/**
 * The page header every Admin screen has, and the rule it exists to hold.
 *
 * **The design's header is a title and a line of figures. Never a paragraph.** Every drawn
 * canvas does the same thing:
 *
 * > **Members** — 4,812 active · 312 expired · 68 frozen · all locations
 * > **The week, with one problem in it** — 54 classes · 1 without a coach ·
 * >   Khalda · 18–24 August · 78% average fill
 * > **Money, and the one place friction is correct** — JOD 41,280.00 collected ·
 * >   1–19 August · all locations · 6 failed, 3 refunded, 2 disputed
 * > **Three things need you this morning** — Wednesday 19 August · all locations ·
 * >   data through 08:38
 *
 * Every screen in this app led with a paragraph explaining what the screen was instead --
 * fifteen of them, each a sentence or three of prose above the data. That is a different
 * product: it reads as documentation with a table under it, and the figures a manager opens
 * the page for are pushed below the fold by an explanation they only need once.
 *
 * **The explanations are not deleted.** What a screen cannot do still belongs on the screen,
 * at the foot, where it answers a question rather than delaying one -- which is where the
 * Command Center and the members list already put theirs. What a screen *is* belongs in the
 * file's own comments, for the next person to edit it.
 *
 * The canvas's measurements: `display:flex;gap:16px;align-items:flex-end;flex-wrap:wrap`,
 * the text column `flex:1;min-width:280px`, the title at `type.h1` and the figures at
 * `type.bodySm` in the secondary ink.
 */

export function PageHeader({
  title,
  figures,
  actions,
  id,
}: {
  /**
   * The page's name. A node rather than a string, because a title is sometimes composed --
   * a record's own name beside a withheld marker, a heading whose count is `.data`. It was
   * `string`, and three screens hand-rolled the whole component's markup rather than widen
   * it, which is the §8 deviation this type was making unavoidable.
   */
  title: ReactNode;
  /**
   * The figures line: counts, scope, freshness. Nodes rather than a string so a count can be
   * `.data` and a money figure can be a `MoneyValue`.
   *
   * Optional, because a screen with nothing to count has nothing to say here -- and an
   * invented sentence would be the prose this component exists to remove.
   */
  figures?: ReactNode;
  /** The end of the row: a period toggle, an "Add member" button. */
  actions?: ReactNode;
  id?: string;
}) {
  return (
    <header className="ds-page-head">
      <div className="ds-page-head-text">
        <h1 id={id} style={{ margin: 0 }}>{title}</h1>
        {figures === undefined ? null : (
          <p className="ds-page-figures">{figures}</p>
        )}
      </div>
      {actions === undefined ? null : <div className="ds-page-head-end">{actions}</div>}
    </header>
  );
}

/**
 * What a screen cannot do yet, at the foot.
 *
 * Every entry is a label and the product's own reason. The rule behind it is ADM-MEM-05's:
 * a control that does nothing is worse than one that is absent, and an empty cell reads as a
 * fact about the subject -- so what is missing is named rather than drawn.
 */
/* **`NotYet` has gone from this file.** It drew a titled section with a definition list --
   a name and a two-sentence justification per absence -- and `src/components/not-yet.tsx`
   replaced it with one line of names. Two components under one name is the duplication this
   system rules out everywhere else, and nine screens were still on this one after the first
   pass took eighteen off it. */
