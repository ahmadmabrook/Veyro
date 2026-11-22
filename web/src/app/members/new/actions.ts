"use server";

import { ApiError, api, correlationId } from "@/lib/api";
import { worthChecking, type MatchResult } from "@/lib/walk-in";

import { IDLE, type DetectionAnswer, type WalkInState } from "./state";

/**
 * The duplicate check ADM-MEM-10 runs "on phone as it is typed, before anything is saved".
 *
 * **The raw value goes to the server.** Nothing here normalizes it: `normalize_contact` is
 * MOD-007's normalizer and it is what the write stores and what the match compares, so a
 * spelling rule on this side would be a second one — the shape MOD-011's review found in a
 * limiter, where eight spellings of one number each got a full budget. The client decides
 * only whether the value is long enough to be worth a request.
 *
 * **Routine, while the write is not.** `people.person.read` is `data_access` with no financial
 * class, so the check that prevents the duplicate is reachable at an ordinary front-desk
 * sign-in; `people.person.write` is financial and needs a step-up. That split is the right way
 * round and worth stating: a desk can always find out that a record exists, and only creating
 * a second one costs more.
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
    // same, and the create below answers the permission question properly.
    return { outcome: "unknown" };
  }
}

/**
 * Create the walk-in. `POST /people`, with the contact points in the same command.
 *
 * **One command, because `PersonBody` takes the contacts with the person**: a record with no
 * way to reach somebody is one nobody can use, and two commands would leave a window where
 * the duplicate detector sees a person with no signals at all. That reasoning is MOD-014's
 * own and it is why this form has no second step.
 *
 * **`people.person.write` is financial class, so this needs a stepped-up session** — the
 * freeze form's pattern, and the reason every form of this kind was absent until that screen
 * showed a step-up is a thing a page can offer rather than a wall. A step-up opens a
 * twelve-hour window, so the cost is one recovery code a shift rather than one a walk-in.
 *
 * **It does not send a duplicate verdict.** The acknowledgement is a decision a person made
 * on this screen about what to do next; the server has no column for it and inventing one
 * would be inventing product. What the server does enforce is its own uniqueness: a second
 * contact point with the same value on the *same* person is refused by
 * `ppl_contact_points_distinct`, which is the only duplicate rule that is this build's to keep.
 */
export async function createWalkIn(
  _previous: WalkInState, form: FormData,
): Promise<WalkInState> {
  const name = String(form.get("name") ?? "").trim();
  const phone = String(form.get("phone") ?? "").trim();
  const email = String(form.get("email") ?? "").trim();
  const birthDate = String(form.get("birth_date") ?? "").trim();
  const echo = { name, phone, email, birthDate };

  const missing: WalkInState["missing"] = {};
  if (name.length === 0) missing.name = true;
  if (!worthChecking(phone)) missing.phone = true;
  if (Object.keys(missing).length > 0) return { ...IDLE, missing, echo };

  // **The phone is primary and the email is not.** One of each kind per person may be
  // primary, and the canvas's own field order says which one this desk reached for; a second
  // primary of a kind is refused by `ppl_contact_points_one_primary`, so declaring both
  // primary would be a 409 on the ordinary path.
  const contacts: { kind: string; value: string; is_primary: boolean }[] = [
    { kind: "phone", value: phone, is_primary: true },
  ];
  if (email.length > 0) {
    contacts.push({ kind: "email", value: email, is_primary: true });
  }

  try {
    const created = await api<{ person_id: string }>("/people", {
      method: "POST",
      body: {
        legal_name: name,
        // Sent only when given. `date_of_birth` is nullable and an unknown birth date is not
        // a minor — MOD-014's own uncomfortable and correct direction, since treating every
        // undated person as one would make a guardian mandatory before anybody could read the
        // record of a member who never gave a birthday, which is most walk-ins.
        ...(birthDate.length > 0 ? { date_of_birth: birthDate } : {}),
        contacts,
        correlation_id: correlationId(),
      },
    });
    return { ...IDLE, createdPersonId: String(created.person_id) };
  } catch (error) {
    if (error instanceof ApiError && error.reason === "unreachable") {
      return { ...IDLE, error: "error.network", echo };
    }
    if (error instanceof ApiError && error.status === 429) {
      return { ...IDLE, error: "error.tooMany", echo };
    }
    // 403 is the step-up rather than a refusal to act, and the two have different next
    // steps: a reader told "that was refused" goes and asks for a grant they already hold.
    if (error instanceof ApiError && error.status === 403) {
      return { ...IDLE, error: "walkIn.needsStepUp", echo };
    }
    return { ...IDLE, error: "walkIn.refused", echo };
  }
}
