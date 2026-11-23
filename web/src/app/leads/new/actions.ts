"use server";

import { ApiError, api, correlationId } from "@/lib/api";
import { worthChecking } from "@/lib/walk-in";

import { IDLE, type NewLeadState } from "./state";

/**
 * ADM-CRM-04 · ADD LEAD — "Name and phone are enough. Everything else can wait."
 *
 * **Two writes, in this order, and the order is the point.** `POST /people` creates the
 * person with the phone on it in one command -- MOD-014's own reasoning, because a record with
 * no way to reach somebody is one nobody can use and two commands would leave a window where
 * the duplicate detector sees a person with no signals at all. Then `POST /crm/leads` opens
 * the sales record against them, which is the structural requirement ADM-CRM-01 states: "a
 * lead, a trialist and a member are one record at three stages, never three records."
 *
 * **The window between them is reported rather than hidden.** Nothing makes two HTTP writes
 * atomic from a browser, so a person created with no lead is a real outcome -- and a reader
 * told only "that was refused" would type the name again and be stopped by their own
 * duplicate check. The state carries the person's id and the form offers to open it.
 *
 * **`people.person.write` is financial class and `crm.lead.write` is routine**, so this form
 * needs a stepped-up session for its first half and not its second. The page offers the
 * step-up on arrival rather than after a 403, which is the freeze form's pattern and what
 * makes a form of this kind buildable at all.
 *
 * **No duplicate verdict is sent.** The acknowledgement is a decision a person made on this
 * screen about what to do next; the server has no column for it and inventing one would be
 * inventing product. What the server does enforce is its own uniqueness -- one lead per
 * person, by index -- so a second lead for somebody who already has one returns theirs, which
 * is ADM-CRM-04's own behaviour: "that record would open instead of a second one being
 * created."
 *
 * **`use_person` is that sentence as a command, and it skips the first write entirely.** When
 * the duplicate check found somebody and the reader chose them, there is no person to create:
 * the lead goes against the id the panel named, which is one write, needs only the routine
 * `crm.lead.write`, and cannot produce a second record for the same person by construction.
 * The source and the interests carry over, because a reader who filled them in before the
 * match appeared meant them.
 *
 * **The id is the one the panel showed and it is not trusted for anything but the write.** It
 * comes from the submit button's value, so a hand-crafted post can name any person in the
 * tenant -- and that is exactly what `POST /crm/leads` already allows any holder of the
 * permission to do, so this adds no reach. What it does not do is let the id stand in for the
 * name and phone: those fields are not read on this path at all, so nothing is stored about
 * somebody from a form the reader may never have filled.
 */
export async function createLead(
  _previous: NewLeadState, form: FormData,
): Promise<NewLeadState> {
  const name = String(form.get("name") ?? "").trim();
  const phone = String(form.get("phone") ?? "").trim();
  const source = String(form.get("source_id") ?? "").trim();
  const interests = form.getAll("interest").map(String);
  const chosen = String(form.get("use_person") ?? "").trim();
  const echo = { name, phone, source, interests };

  if (chosen.length > 0) return openAgainst(chosen, source, interests, echo);

  const missing: NewLeadState["missing"] = {};
  if (name.length === 0) missing.name = true;
  if (!worthChecking(phone)) missing.phone = true;
  if (Object.keys(missing).length > 0) return { ...IDLE, missing, echo };

  let personId: string;
  try {
    const created = await api<{ person_id: string }>("/people", {
      method: "POST",
      body: {
        legal_name: name,
        // **`lead`, which is the profile kind MOD-014 admits for exactly this.** A person who
        // walked in at an open day is not a member yet, and the kind is what the members list
        // filters by -- so creating them as one would put a stranger in the member count.
        profile_kinds: ["lead"],
        contacts: [{ kind: "phone", value: phone, is_primary: true }],
        correlation_id: correlationId(),
      },
    });
    personId = String(created.person_id);
  } catch (error) {
    return { ...IDLE, error: reasonFor(error), echo };
  }

  try {
    const opened = await openLead(personId, source, interests);
    return {
      ...IDLE,
      createdLeadId: String(opened.lead_id),
      openedExisting: opened.existing === true,
    };
  } catch (error) {
    // **The person exists and the lead does not, and that is what the form says.** The
    // alternative -- a flat refusal -- sends the reader back to type the same name and be
    // stopped by their own duplicate check, which is a worse answer than the true one.
    if (error instanceof ApiError && error.reason === "unreachable") {
      return { ...IDLE, error: "error.network", orphanedPersonId: personId, echo };
    }
    return { ...IDLE, error: "newLead.personOnly", orphanedPersonId: personId, echo };
  }
}

function reasonFor(error: unknown): NewLeadState["error"] {
  if (!(error instanceof ApiError)) return "newLead.refused";
  if (error.reason === "unreachable") return "error.network";
  if (error.status === 429) return "error.tooMany";
  // 403 is the step-up rather than a refusal to act, and the two have different next steps: a
  // reader told "that was refused" goes and asks for a grant they already hold.
  if (error.status === 403) return "newLead.needsStepUp";
  return "newLead.refused";
}

/** The one write the match path makes. */
async function openAgainst(
  personId: string, source: string, interests: string[],
  echo: NewLeadState["echo"],
): Promise<NewLeadState> {
  try {
    const opened = await openLead(personId, source, interests);
    return {
      ...IDLE,
      createdLeadId: String(opened.lead_id),
      openedExisting: opened.existing === true,
    };
  } catch (error) {
    // No person was created here, so there is no orphan to offer: the refusal is about the
    // lead alone and `crm.lead.write` is routine, so a 403 on this path is a denial rather
    // than a step-up.
    if (error instanceof ApiError && error.status === 403) {
      return { ...IDLE, error: "newLead.refused", echo };
    }
    return { ...IDLE, error: reasonFor(error), echo };
  }
}

function openLead(personId: string, source: string, interests: string[]) {
  return api<{ lead_id: string; existing?: boolean }>("/crm/leads", {
    method: "POST",
    body: {
      person_id: personId,
      ...(source.length > 0 ? { source_id: source } : {}),
      ...(interests.length > 0 ? { interests } : {}),
      correlation_id: correlationId(),
    },
  });
}
