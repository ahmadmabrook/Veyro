/**
 * A signed change, in the tone its direction earns.
 *
 * **One definition, because there were two.** `MetricCell` drew it inside a figure's
 * comparison line and the revenue report drew the same thing in a table column by writing
 * `className="ds-metric-delta data"` by hand -- a screen reaching into a component's own
 * class names, which is the §8 deviation and the shape this project keeps finding. The two
 * agreed on the day the second was written and nothing kept them agreeing.
 *
 * **The tone is the direction's, never the value's.** Canvas 3's note, during an outage:
 * "Why the metrics stay neutral: 48 people in the building is a fact, not a problem, and
 * colouring it red during an unrelated outage teaches staff to distrust the colour." So a
 * delta carries `up` or `down` and the figure beside it carries nothing.
 *
 * **`dir="ltr"` is not decoration.** An arrow and a signed percentage are a Latin run, and
 * in an Arabic page the bidi algorithm moves the arrow to the far side of the number, so
 * "↓ 7.8%" reads as "7.8% ↓" and points at the wrong thing.
 */
export function Delta({ text, tone }: { text: string; tone: "up" | "down" }) {
  return (
    <span className="ds-metric-delta data" data-tone={tone} dir="ltr">
      {text}
    </span>
  );
}
