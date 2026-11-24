import type { MessageKey } from "@/i18n/locale";
import type { TrialCard } from "@/lib/leads";

/**
 * ADM-CRM-05's one sentence, chosen from what the trial shows.
 *
 * **Not `useSentence`.** `use` followed by a capital is reserved for a React hook and
 * `react-hooks/rules-of-hooks` enforces it, so the first name made the linter report a
 * hook called in an async server component and in a loop -- three errors about a
 * function that is neither. The name says usage, which is also what it is about.
 *
 * **The canvas writes it out**: *"Four visits, four classes, all spin. She has used the trial
 * more than most — this is a conversion, not a chase."* That is a claim about use joined to a
 * claim about what to do next, and only the first half is a fact the server answers -- so the
 * band chooses the sentence and the figures sit beside it rather than inside it.
 *
 * **"All spin" is not here.** The canvas names the class somebody kept taking, and nothing in
 * this build counts classes by what they were: `attended_between` is a count, and a sentence
 * naming a class the read did not identify would be the confident wrong answer MOD-014's own
 * 360 was bitten by.
 */
export function usageSentence(card: Extract<TrialCard, { on_trial: true }>): MessageKey {
  if (card.engagement === "high") return "trial.usedItWell";
  if (card.engagement === "none") return "trial.notUsed";
  return "trial.usedItSome";
}

/**
 * The urgency line above it — "Her trial ends tomorrow".
 *
 * **Three states, not two.** The canvas draws the tomorrow one, and the day it ends is the
 * sharper of the two and would otherwise read as "1 day left"; every other day is the count.
 * The server decides which, because `ends_tomorrow` is a date comparison in the tenant's own
 * frame and a browser comparing against its own clock counts in the wrong one.
 */
export function urgencyKey(card: Extract<TrialCard, { on_trial: true }>): MessageKey {
  if (card.ends_tomorrow) return "trial.endsTomorrow";
  if (card.days_left <= 1) return "trial.endsToday";
  return "trial.running";
}
