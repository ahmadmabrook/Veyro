"use server";

import { api } from "@/lib/api";
import { worthChecking, type MatchResult } from "@/lib/walk-in";

/**
 * What the duplicate check answers.
 *
 * **`unknown` is its own answer and not a `clear`.** A check the server could not be asked is
 * not a check that passed, and conflating the two turns a network blip into a silent
 * duplicate — "a control consulted once is a control with a window", in a surface. Both forms
 * that use it hold the button for this exactly as they do for a match.
 */
export type DetectionAnswer =
  | { outcome: "match"; result: MatchResult }
  | { outcome: "clear" }
  | { outcome: "unknown" };

/**
 * The duplicate check two screens run "on phone as it is typed, before anything is saved".
 *
 * **One definition, because two screens ask the same question.** ADM-MEM-10 asks it before
 * creating a member and ADM-CRM-04 asks it before creating a lead -- "checked as you typed
 * against members and leads" -- and the answer is the same read: a lead *is* a person, so a
 * number already on a record is already on a record. A second copy of this would be two
 * definitions of "does this number exist", and the day they disagreed one screen would create
 * the duplicate the other prevents.
 *
 * **The raw value goes to the server.** Nothing here normalizes it: `normalize_contact` is
 * MOD-007's normalizer and it is what the write stores and what the match compares, so a
 * spelling rule on this side would be a second one -- the shape MOD-011's review found in a
 * limiter, where eight spellings of one number each got a full budget. The client decides
 * only whether the value is long enough to be worth a request.
 *
 * **Routine, while both writes are not.** `people.person.read` is `data_access` with no
 * financial class, so the check that prevents the duplicate is reachable at an ordinary
 * sign-in; `people.person.write` is financial and needs a step-up. That split is the right way
 * round: a desk can always find out that a record exists, and only creating a second one costs
 * more.
 */
export async function checkPhone(typed: string): Promise<DetectionAnswer> {
  if (!worthChecking(typed)) return { outcome: "clear" };
  try {
    const found = await api<MatchResult>(
      `/people/contact-match?kind=phone&value=${encodeURIComponent(typed)}&limit=5`);
    return found.count === 0 ? { outcome: "clear" } : { outcome: "match", result: found };
  } catch {
    // **Every failure is `unknown`, including a 403.** A reader who cannot run the check has
    // not learned that the number is free, and the form holds the button rather than treating
    // silence as a clear. Which failure it was is not actionable here: the sentence is the
    // same, and the create answers the permission question properly.
    return { outcome: "unknown" };
  }
}
