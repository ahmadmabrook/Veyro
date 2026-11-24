import { variance } from "@/lib/cash";
import { isWithheld } from "@/lib/mask";

/**
 * FD-07 — "Shift open and close", and the handover between them.
 *
 * The canvas is an *open*: the previous shift's own figure on the screen ("Kareem left **JOD
 * 50.00** at 16:04"), a float count, the sentence "If your count differs, say so now -- a
 * discrepancy found at open belongs to the previous shift", and the note he left. Underneath
 * it: "The handover note is part of the shift, not a WhatsApp message that leaves with the
 * person who wrote it."
 *
 * **That sentence is why the drawer has three states rather than two.** A till that was
 * emptied has to be funded from the safe and the count is the float going in; a till that
 * still holds money is being handed over and the count is a check on what was left. The
 * server tells them apart by the drawer account's own balance, never by anything a caller
 * sends, and this module reads the same fact so the screen and the command cannot disagree
 * about which act the button performs.
 *
 * `@/lib/cash` holds the money parse and the variance, which this screen shares with
 * ADM-PAY-09 rather than deciding twice.
 */

/** What the last shift to close on this drawer left, and what they passed on. */
export type HandedOver = {
  session_id: string;
  counted_minor: number | null;
  closed_at: string | null;
  closed_by: string | null;
  handover_note: string | null;
  drawer_label: string;
  location_id: string;
};

export type OpenSession = {
  session_id: string;
  opened_at: string;
  opened_by: string;
  opening_float_minor: number;
};

export type Drawer = {
  cash_account_id: string;
  drawer_label: string;
  currency: string;
  /** Derived from that account's own postings, with no figure any caller sent. */
  expected_minor: number;
  open_session: OpenSession | null;
  handed_over: HandedOver | null;
};

export type Drawers = {
  count: number;
  drawers: Drawer[];
  a_drawer_is_an_account_that_has_had_a_session: string;
  expected_is_derived_from_postings: string;
  a_name_is_another_module: string;
};

/**
 * Which of the three acts this drawer is waiting for.
 *
 * **Derived from the standing balance, as the server derives it.** A `handover: true` flag on
 * the request would let a desk choose whether its own count is checked, which is the
 * caller-supplied-control shape every review in this build has found -- and a screen deciding
 * it differently from the command would offer a button the command then refuses.
 */
export type DrawerAct = "close" | "handover" | "fund";

export function actFor(drawer: Drawer): DrawerAct {
  if (drawer.open_session !== null) return "close";
  return drawer.expected_minor === 0 ? "fund" : "handover";
}

/**
 * Which sentence the handover panel says, and it is four rather than one.
 *
 * The canvas draws the first: somebody left a figure at a time. The other three are states a
 * real desk reaches and the canvas does not draw -- a drawer that was banked to nothing, a
 * drawer whose standing money came from a journal rather than a shift, and a drawer nobody
 * has ever closed. Printing the canvas's sentence for any of them would name a person and a
 * figure that are not there, which is the confident wrong answer MOD-014's own Member 360 was
 * bitten by.
 */
export type HandoverCase =
  | { kind: "left"; counted: number; at: string; by: string }
  | { kind: "emptied" }
  | { kind: "unattributed"; standing: number }
  | { kind: "first" };

export function handoverCase(drawer: Drawer): HandoverCase {
  const left = drawer.handed_over;
  if (left === null) {
    return drawer.expected_minor === 0
      ? { kind: "first" }
      : { kind: "unattributed", standing: drawer.expected_minor };
  }
  if (drawer.expected_minor === 0) return { kind: "emptied" };
  // **The figure on the screen is the drawer's balance, not the last count.** They agree
  // whenever the takings were banked and the float left, which is the ordinary shift -- and
  // where they do not, what the next person is counting is the money that is there.
  if (left.counted_minor === null || left.closed_at === null || left.closed_by === null) {
    return { kind: "unattributed", standing: drawer.expected_minor };
  }
  return {
    kind: "left",
    counted: drawer.expected_minor,
    at: left.closed_at,
    by: left.closed_by,
  };
}

/**
 * What a count still owes before the button can be pressed.
 *
 * **A reason, and somewhere for the difference to go.** The server refuses a short handover
 * with neither, so offering the button without them would be a control the module answers 422
 * to -- FD-06's rule. `needsEntity` is about the posting rather than the reason: a difference
 * has to land in suspense under a legal entity, and a screen that cannot read either says so
 * rather than letting somebody type a reason into a form that cannot submit.
 */
export type CountOwes = {
  gap: number | null;
  needsReason: boolean;
  needsPosting: boolean;
};

export function countOwes(drawer: Drawer, countedMinor: number | null): CountOwes {
  const act = actFor(drawer);
  if (countedMinor === null) return { gap: null, needsReason: false, needsPosting: false };
  if (act === "fund") {
    // Funding an empty drawer is not a comparison: the money is being put in, and what the
    // posting needs is the account it comes from rather than a reason.
    return { gap: null, needsReason: false, needsPosting: countedMinor > 0 };
  }
  const gap = variance(drawer.expected_minor, countedMinor);
  const short = gap !== null && gap !== 0;
  return { gap, needsReason: short, needsPosting: short };
}

/**
 * Whether the press can be made at all, given what the page could read.
 *
 * Kept apart from `countOwes` because the two refusals have different remedies: a missing
 * reason is the person's to type, and a chart this session may not read is not.
 */
export function mayPress(
  owes: CountOwes,
  { reason, hasPosting }: { reason: string; hasPosting: boolean },
): boolean {
  if (owes.needsReason && reason.trim() === "") return false;
  if (owes.needsPosting && !hasPosting) return false;
  return true;
}


/**
 * Which account each posting field carries, per act.
 *
 * **Extracted from the form's JSX because a mutation could not be seen there.** The two
 * conditionals were inline and identical in shape, so sending the safe on a handover -- which
 * the command refuses outright, making the ordinary press impossible -- changed a hidden field
 * that no test pressed. A decision in a hidden input is still a decision about what the
 * request says, and the honest place for it is here where a case can reach it.
 *
 * **Each account only on the act that draws on it.** A handover draws nothing, so naming the
 * safe there is a field the command refuses rather than ignores; a funded open has no
 * difference to post, so suspense would be a field validated and thrown away.
 */
export function accountsFor(
  act: DrawerAct, { safe, suspense }: { safe: string; suspense: string },
): { floatSource: string; suspense: string } {
  return act === "fund"
    ? { floatSource: safe, suspense: "" }
    : { floatSource: "", suspense };
}


/** An identity's link to a person, as `GET /people/by-identity` answers. */
export type IdentityLink = { identity_id: string; person_id: string };

/**
 * Whose name to put on an actor, or `null` where there is none to put.
 *
 * **Three different absences, and a surface has to treat them alike while a test has to tell
 * them apart.** An identity with no person is the ordinary staff case -- staff hold
 * permissions and do not have to be anybody in particular. A person this session may not read
 * comes back as a *marker* rather than a null, which MOD-027's board paid for by rendering it
 * as though somebody were called that. And a person with no recorded legal name is simply
 * unnamed.
 *
 * **Extracted from the page because a mutation could not be seen there.** The composition was
 * an inline closure, and the fixture's drawer actors are linked to no person at all -- so the
 * withheld branch was unreachable from a browser and removing it changed nothing any spec
 * could observe. A branch no fixture can reach is this build's recurring vacuity.
 */
export function nameOf(
  identityId: string,
  links: readonly IdentityLink[],
  names: ReadonlyMap<string, { legal_name: string | null }>,
): string | null {
  const link = links.find((one) => one.identity_id === identityId);
  if (link === undefined) return null;
  const named = names.get(link.person_id);
  if (named === undefined || named.legal_name === null) return null;
  return isWithheld(named.legal_name) ? null : named.legal_name;
}
