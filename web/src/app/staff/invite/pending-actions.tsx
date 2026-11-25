"use client";

import { useActionState, useState } from "react";

import { Banner } from "@/components/ds/banner";
import { Button } from "@/components/ds/button";
import { Field } from "@/components/ds/field";
import { t, type Locale, type MessageKey } from "@/i18n/locale";

import { resendInvitation, withdrawInvitation } from "./invite-actions";
import { IDLE, type InviteState } from "./invite-state";

/**
 * The canvas's "Resend" on a pending row, and the withdrawal beside it.
 *
 * **A resend is a new invitation and the screen says so**, because it cannot be the same link:
 * only the digest is stored, so the old one necessarily stops working. ADR-0017 D4.
 *
 * **A withdrawal collects a reason**, because the row is the only record there is -- the
 * service refuses a blank one and a form that sent one would be asking the server to say what
 * the screen already knows.
 */
export function PendingActions({
  invitationId, locale,
}: {
  invitationId: string;
  locale: Locale;
}) {
  const text = (key: MessageKey) => t(locale, key);
  const [resent, resend, resending] = useActionState<InviteState, FormData>(
    resendInvitation, IDLE);
  const [gone, withdraw, withdrawing] = useActionState<InviteState, FormData>(
    withdrawInvitation, IDLE);
  const [asking, setAsking] = useState(false);

  // **There is no settled row to guard against, which the browser suite is what found.**
  // A `settled` prop and an em-dash branch were here, written from FD-06's rule that a
  // button answering 409 is worse than its absence -- and `listInvitations` asks the route
  // for what is *waiting*, so an accepted or withdrawn invitation is not in this list at
  // all. The branch could not render, which is this app's "a surface branch no fixture can
  // reach" trap in a guard rather than in a feature; deleted rather than tested harder, and
  // the rule it restated lives in the route's own filter. An **expired** invitation is not
  // settled -- it still holds its address and a fresh link is the remedy -- so these two
  // controls are offered on it, which is what the canvas draws beside `omar.s@nadi.jo`.

  if (resent.message === "resent" && resent.made !== null) {
    return (
      <div className="stack">
        <Banner severity="info">{text("invite.resentMeans")}</Banner>
        <p className="data" dir="ltr" style={{ margin: 0, wordBreak: "break-all" }}>
          {resent.made.token}
        </p>
        <span className="muted">{text("invite.shownOnce")}</span>
      </div>
    );
  }
  if (gone.message === "withdrawn") {
    return <Banner severity="info">{text("invite.withdrawn")}</Banner>;
  }

  return (
    <div className="stack">
      {resent.error === null ? null : (
        <Banner severity="critical">{text(resent.error)}</Banner>
      )}
      {gone.error === null ? null : (
        <Banner severity="critical">{text(gone.error)}</Banner>
      )}
      <form action={resend}>
        <input type="hidden" name="invitation_id" value={invitationId} />
        <Button type="submit" variant="secondary" size="sm"
          state={resending ? "loading" : "default"}
          label={text("invite.resend")} />
      </form>
      {asking ? (
        <form action={withdraw} className="stack">
          <input type="hidden" name="invitation_id" value={invitationId} />
          <Field
            id={`withdraw-${invitationId}`} name="reason" type="text"
            label={text("invite.withdrawReason")} required rarer="optional"
            {...(gone.missing.reason ? {
              message: {
                kind: "error" as const, text: text("invite.withdrawReasonNeeded"),
              },
            } : {})}
          />
          <Button type="submit" variant="destructive" size="sm"
            state={withdrawing ? "loading" : "default"}
            label={text("invite.withdraw")} />
        </form>
      ) : (
        <Button variant="ghost" size="sm" onClick={() => setAsking(true)}
          label={text("invite.withdraw")} />
      )}
    </div>
  );
}
