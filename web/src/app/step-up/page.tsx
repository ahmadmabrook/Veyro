import Link from "next/link";
import { redirect } from "next/navigation";

import { Banner } from "@/components/ds/banner";
import { t, type Locale, type MessageKey } from "@/i18n/locale";
import { ApiError, api, currentSession } from "@/lib/api";
import { safeNext } from "@/lib/navigation";
import { presentation } from "@/lib/preferences";

import { StepUpForm } from "./step-up-form";
import type { SecondFactor } from "./state";

const ACTION_CLASSES = ["routine", "financial", "privileged", "biometric_sensitive"] as const;

/**
 * Raise a session's assurance, so the fields a level-1 reader is shown as withheld can be read.
 *
 * **This page is the remedy the rest of the app kept naming and did not have.** The Member 360
 * marks an identity field as withheld and says a stronger sign-in would reveal it; until this
 * existed that was a dead end, which is the same shape MOD-007's own review records one layer
 * down -- "there was no endpoint to answer one at all, so it was unanswerable by an honest user
 * and free to skip for an attacker". The endpoint existed; the surface did not use it.
 *
 * Three answers, rendered as three different things because they are three different facts:
 * the session is already strong enough, the level is not reachable by anybody in this build, or
 * here is the one field that will raise it.
 */
export default async function StepUpPage({
  searchParams,
}: {
  searchParams: Promise<{ for?: string; next?: string }>;
}) {
  const { locale } = await presentation();
  const text = (key: MessageKey) => t(locale, key);
  const params = await searchParams;

  const session = await currentSession();
  if (!session) redirect("/login");

  const actionClass = ACTION_CLASSES.includes(
    (params.for ?? "") as (typeof ACTION_CLASSES)[number],
  )
    ? params.for!
    : "financial";
  const next = safeNext(params.next);

  // **Which factor can raise this session is the server's answer, not a guess.** `factors` is
  // on the resolved session, and `policy.assurance_for` reads distinct kinds: a password
  // session needs something that is not a password, and a recovery-code session needs the
  // password. Asking for the wrong one is a refusal the reader cannot act on.
  const held = Array.isArray(session.factors) ? (session.factors as string[]) : [];
  const factor: SecondFactor =
    held.includes("password") && !held.includes("recovery_code")
      ? "recovery_code"
      : "password";

  let asked: { step_up_required: boolean; reachable: boolean };
  try {
    asked = await api<{ step_up_required: boolean; reachable: boolean }>(
      `/auth/require/${actionClass}`,
    );
  } catch (error) {
    return (
      <Shell locale={locale} next={next}>
        <Banner severity="critical">
          {error instanceof ApiError && error.reason === "unreachable"
            ? text("error.network")
            : text("error.unexpected")}
        </Banner>
      </Shell>
    );
  }

  if (!asked.step_up_required) {
    return (
      <Shell locale={locale} next={next}>
        <Banner severity="info">{text("stepUp.alreadyDone")}</Banner>
      </Shell>
    );
  }

  if (!asked.reachable) {
    // Level 3 needs a hardware authenticator MOD-007 cannot verify. Offering a field here
    // would send somebody looking for a key the product cannot check.
    return (
      <Shell locale={locale} next={next}>
        <Banner severity="info">{text("stepUp.unreachable")}</Banner>
      </Shell>
    );
  }

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        gap: "var(--space-4)",
        padding: "var(--space-10) var(--space-4)",
      }}
    >
      <StepUpForm locale={locale} factor={factor} actionClass={actionClass} next={next} />
      <Link href={next}>{text("stepUp.back")}</Link>
    </div>
  );
}

function Shell({
  locale,
  next,
  children,
}: {
  locale: Locale;
  next: string;
  children: React.ReactNode;
}) {
  return (
    <div
      className="stack"
      style={{ padding: "var(--space-6)", maxWidth: "560px", margin: "0 auto" }}
    >
      <h1 style={{ margin: 0 }}>{t(locale, "stepUp.title")}</h1>
      {children}
      <Link href={next}>{t(locale, "stepUp.back")}</Link>
    </div>
  );
}
