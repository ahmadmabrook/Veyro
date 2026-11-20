import type { ReactNode } from "react";

/**
 * AITreatment — the container every machine interpretation in this product lives in.
 *
 * Two things make it a component rather than a styled box, and both are guardrails:
 *
 * **G7: Veyro owns the colour it says it in.** `color.semantic.ai` is system-owned in both
 * themes and is explicitly out of scope for `brand.accent`:
 *
 * > A tenant brand on an AI panel would make inference look like a first-party assertion;
 * > Veyro is accountable for what its AI says, so Veyro owns the colour it says it in.
 *
 * That was filed as `DS-CL-02` after the foundation audit found the panel's border inheriting
 * the tenant accent, and closed by locking the hue to a system indigo. So the border and the
 * header wash here are `--color-semantic-ai-*` and nothing on this component takes a colour
 * from a caller.
 *
 * **The eyebrow is required.** "VEYRO INTERPRETATION · NOT A CONFIRMED FIGURE" sits above the
 * panel on canvas 1, and a panel without it is a machine reading presented as a fact. It is a
 * required prop for the same reason `Card`'s `kind` is: a caller who cannot supply one is
 * holding something that should not be in this container.
 *
 * **The withheld state.** Canvas 5: "Veyro is not offering a revenue interpretation while the
 * underlying figures are stale. It will return when the pipeline catches up." The reasoning
 * generalises past stale data — "an interpretation built on stale inputs is the one thing
 * worse than no interpretation" — and in this build the reason is stronger still: no module
 * produces an interpretation at all. The panel renders, because the design puts a titled
 * block there and an absent one would make the page read as a different screen, and because
 * the sentence is worth reading.
 */

export function AITreatment({
  eyebrow,
  children,
  withheld,
}: {
  /** Required. "Veyro interpretation · not a confirmed figure". */
  eyebrow: string;
  children: ReactNode;
  /** Whether this is the withheld state rather than an interpretation. */
  withheld?: boolean;
}) {
  return (
    <section className="ds-ai" data-withheld={withheld ? "true" : "false"}>
      {/* `role="note"` rather than a heading: this is an aside about the figures above it,
          and promoting it to a heading would put a machine reading into the document outline
          beside the facts. */}
      <p className="ds-ai-eyebrow">{eyebrow}</p>
      <div className="ds-ai-body">{children}</div>
    </section>
  );
}
