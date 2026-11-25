import Link from "next/link";
import { redirect } from "next/navigation";

import { Banner } from "@/components/ds/banner";
import { DataGrid } from "@/components/ds/data-grid";
import { MoneyValue } from "@/components/ds/money-value";
import { PageHeader } from "@/components/ds/page-header";
import { Prose, ProseNote } from "@/components/prose";
import { Withheld } from "@/components/withheld";
import { fill, t, type Locale, type MessageKey } from "@/i18n/locale";
import { currentSession, failureMessage, gateAll, gateMessage, gateVerdict } from "@/lib/api";
import { presentation } from "@/lib/preferences";
import { listMembers } from "@/lib/members-reads";
import { isWithheld, withheldRemedy } from "@/lib/people";
import {
  batchVerdict,
  failureName,
  keysInPlay,
  readPublishedTemplate,
  readRecovery,
  methodName,
  reasonName,
  treatmentName,
  treatmentSeverity,
  type PublishedTemplate,
  type RecoveryWorkspace,
  type Treatment,
} from "@/lib/recovery";

/**
 * ADM-PAY-05 · RECOVERY · OPENED FROM THE COMMAND CENTER.
 *
 * The canvas, in full:
 *
 * > **6 failed payments · JOD 312.00** — All retries exhausted · no access blocked
 * > `[Send all 6 links]`
 * > ☑ Ahmad Nabulsi · Card expired · Visa ···4417 · JOD 55.00 · link ready
 * > ☑ Yara Mansour · Card expired · frozen member · JOD 72.00 · review first
 * >
 * > **The message they receive** — "Hi Ahmad — your August payment of JOD 55.00 didn't go
 * > through because your card expired. You can pay here: veyro.link/p/8k2m. You're still
 * > able to train as normal."
 * >
 * > Sent in the member's chosen language. Each link is single-use and member-specific.
 * > **Two of the six have withdrawn marketing consent** — this is a service message, so it
 * > still sends, and the distinction is enforced by the system rather than left to the
 * > sender.
 * >
 * > **Why this is a workspace and not a list:** the six are one decision, not six. Reviewing
 * > each individually is available but is the slower path, and the batch action is the
 * > default because the recommended treatment is identical for all six.
 *
 * **The sort is the screen, and it needed a new read.** The design's own argument for a
 * workspace is that the six are one decision — which is only true once something has
 * established that the recommended treatment *is* identical for all six. The dunning listing
 * could not say that: it returns a stage and an attempt count, and whether a case wants a
 * link or a person depends on why the charge failed and where the member stands, neither of
 * which was in any read. `GET /finance/recovery` pairs each case with the failure that
 * opened it and the membership its invoice cites, and runs `collections.recovery_treatment`
 * over the pair. So this page renders a decision rather than computing one — the rule this
 * repository learned from the integrations board, where the same comparison written twice
 * left a cell disagreeing with the banner above it.
 *
 * **Four things the design draws that this build does not have, each disclosed rather than
 * drawn as though it worked:**
 *
 * - **`Send all 6 links` has no writer.** Nothing in this build sends: MOD-013 authors a
 *   notification and no provider collects it. A button that answered nothing would be worse
 *   than its absence, and a *checkbox* selecting rows for it would be worse still — the
 *   design's ☑ column is a batch selection, so it is not drawn.
 * - **There is no payment link.** `veyro.link/p/8k2m` is a single-use member-specific URL,
 *   and no table in this build holds one. It is named in the foot rather than faked, which
 *   is why the preview shows the template's own `{{ }}` placeholder instead of a URL.
 * - **`Visa ···4417` does not exist anywhere.** Paragraph 1597 keeps card data out of Veyro
 *   entirely, so `payment_method_ref` is a token held by a provider and the instrument's
 *   *kind* is the whole of what can be shown.
 * - **"Two of the six have withdrawn marketing consent" is a count this page does not
 *   make.** The *rule* behind the sentence is real and is rendered: only `coaching` and
 *   `marketing` may be muted by a recipient preference — a CHECK on `ntf_preferences`, not a
 *   convention — so a notice in any other category reaches somebody who opted out of
 *   marketing. The count would need a consent read per payer, which is a request per row on
 *   a page that already composes names in one; and the sentence the design is making is
 *   about the mechanism, which the template's own category states.
 *
 * **The preview is the real template, unrendered.** `templates.render` refuses a variable the
 * template did not declare and requires a value for every one it did, so a preview with no
 * values cannot render at all — and a hand-written example sentence would be the fabricated-
 * evidence shape this codebase has been bitten by. The authored body with its placeholders
 * visible is the truthful thing, and the placeholders are exactly what say which values a
 * sender does not have. Reading it needed a route: `list_templates` returns no body, so the
 * text had no reader anywhere in the build.
 */

export const dynamic = "force-dynamic";

export default async function RecoveryPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const { locale } = await presentation();
  const text = (key: MessageKey) => t(locale, key);
  void (await searchParams);

  if (!(await currentSession())) redirect("/login?next=/payments/recovery");

  const [mayRecovery, mayPeople, mayTemplates, mayNames] = await gateAll([
    "finance.dunning.read",
    "people.person.read",
    "notifications.template.read",
    // For the withheld marker's remedy, not for any read. See `@/lib/mask`.
    "member.identity.read",
  ] as const);
  // **The remedy has to match the cause.** A legal name is MOD-014's `identity` class and
  // `member.identity.read` opens it; that permission is `financial`, so a step-up lifts the
  // mask for a session holding the grant at too low an assurance and does nothing for a role
  // that does not hold it. The row said "step up" to both until now. See `@/lib/mask`.
  const remedy = withheldRemedy(gateVerdict(mayNames));
  const nameWithheld: MessageKey = remedy === "step_up"
    ? "member.withheldIdentity"
    : "member.withheldIdentityNoRemedy";

  if (!mayRecovery.allowed) {
    return (
      <Shell locale={locale}>
        <Banner severity="info">{text(gateMessage(mayRecovery))}</Banner>
      </Shell>
    );
  }

  let workspace: RecoveryWorkspace;
  try {
    workspace = await readRecovery();
  } catch (error) {
    return (
      <Shell locale={locale}>
        <Banner severity="critical">{text(failureMessage(error))}</Banner>
      </Shell>
    );
  }

  // The MEMBER column, composed through MOD-014's own gate. One request for the page rather
  // than one per row, which is the payments ledger's shape.
  const names = mayPeople.allowed
    ? await listMembers({ limit: 200 })
      .then((page) => new Map(page.people.map((p) => [p.person_id, p.legal_name])))
      .catch(() => null)
    : null;

  // The messages the *stages* in this set would send. One read per distinct key, which is
  // one in the ordinary case and is bounded by the five stages in any case. A key with no
  // published template is a real state — a tenant that has not authored the notice — so the
  // failure is kept per key rather than failing the page.
  const keys = keysInPlay(workspace);
  // **No locale is passed, deliberately.** The message goes in the *member's* chosen
  // language, and nothing on this read says what that is — so asking for the reader's own
  // would preview a different row from the one the member receives, and on an Arabic screen
  // would show "nobody authored this" for a tenant that has only published English. The
  // newest published version of the key is what exists; the note below says the member's
  // language is a different published template rather than a translation of this one.
  const templates = mayTemplates.allowed
    ? await Promise.all(keys.map(async (key) => [
      key,
      await readPublishedTemplate(key).catch(() => null),
    ] as const)).then((pairs) => new Map(pairs))
    : null;

  const atRisk = workspace.at_risk[0] ?? null;
  const verdict = batchVerdict(workspace);

  return (
    <Shell
      locale={locale}
      figures={
        workspace.count === 0 ? (
          text("recovery.noneOpen")
        ) : (
          <>
            {fill(locale, "recovery.failedCount", { count: workspace.count })}
            {atRisk === null ? null : (
              <>
                {" · "}
                {/* `owed` — money the tenant is chasing, which is the kind this figure is
                    and the reason it is red in the canvas. */}
                <MoneyValue
                  kind="owed"
                  amountMinor={atRisk.amount_minor}
                  currency={atRisk.currency}
                />
              </>
            )}
            {" · "}
            {/* **Both clauses are derived on the server, not typed here.** "All retries
                exhausted" is true when no case is still waiting on an automatic attempt,
                and "no access blocked" when every stage recommends `none`. A header that
                asserted either could contradict its own rows. */}
            {text(workspace.all_retries_exhausted
              ? "recovery.retriesExhausted"
              : "recovery.retriesRemain")}
            {" · "}
            {text(workspace.no_access_blocked
              ? "recovery.noAccessBlocked"
              : "recovery.accessAffected")}
          </>
        )
      }
    >
      {workspace.count === 0 ? (
        <Banner severity="info">{text("recovery.empty")}</Banner>
      ) : (
        <>
          {/* **The one sentence that makes this a workspace**, and it is a claim the page
              can only make when it is true. With a mixed set the recommended treatment is
              not identical, so the batch argument does not hold and the page says which
              rows differ instead of implying one button would do. */}
          <Banner severity={verdict.kind === "mixed" ? "attention" : "info"}>
            {verdict.kind === "one_decision"
              ? fill(locale, verdictKey(verdict.treatment), { count: verdict.count })
              : verdict.kind === "mixed"
                ? fill(locale, "recovery.mixedSet", {
                  link: verdict.link, review: verdict.review, retry: verdict.retry,
                })
                : text("recovery.empty")}
          </Banner>

          <section className="page-section" aria-labelledby="recovery-heading">
            <h2 id="recovery-heading" className="ds-visually-hidden">
              {text("recovery.listTitle")}
            </h2>

            {/* **A list of withheld names needs the remedy on the list.** The members list
                learned this from an independent tester who clicked the marker looking for
                a way through and found none, and it matters more here: this screen's whole
                left column is who to contact, so every row reading "withheld" makes the
                workspace unusable rather than merely terse. Shown only when something is
                actually withheld. */}
            {workspace.cases.some(
              (one) => isWithheld(names?.get(one.payer_person_id) ?? ""),
            ) ? (
              <p className="ds-note">
                {remedy === "step_up" ? (
                  <>
                    {text("recovery.namesWithheld")}{" "}
                    <Link
                      href={`/step-up?for=financial&action=member.identity.read&next=${
                        encodeURIComponent("/payments/recovery")}`}
                    >
                      {text("member.raiseSession")}
                    </Link>
                  </>
                ) : remedy === "no_answer" ? (
                  text("member.namesWithheldNoAnswer")
                ) : (
                  text("member.namesWithheldNotHeld")
                )}
              </p>
            ) : null}
            <DataGrid
              caption={text("recovery.listTitle")}
              labelledBy="recovery-heading"
              countLabel={fill(locale, "recovery.rowCount", { count: workspace.count })}
              density="compact"
              rows={workspace.cases}
              rowKey={(one) => one.case_id}
              rowSeverity={(one) => treatmentSeverity(one.treatment)}
              columns={[
                {
                  header: text("recovery.member"),
                  kind: "person",
                  priority: 1,
                  render: (one) => {
                    const name = names?.get(one.payer_person_id);
                    const failure = failureName(one.failure_code);
                    return (
                      <>
                        {names === null ? (
                          <span className="data" dir="ltr">
                            {one.payer_person_id.slice(0, 8)}
                          </span>
                        ) : name === undefined ? (
                          <span className="muted">{text("recovery.notOnThisPage")}</span>
                        ) : isWithheld(name) ? (
                          <Withheld locale={locale} reason={nameWithheld} />
                        ) : (
                          <Link href={`/people/${one.payer_person_id}`}>{name}</Link>
                        )}
                        {/* The canvas's second line: the reason, in mono, under the name.
                            A code the build has not declared falls through to the code
                            itself rather than to "other" — this is the field somebody
                            acts on. */}
                        <div
                          className="muted data"
                          style={{ fontSize: "var(--type-caption-size)" }}
                          dir="ltr"
                        >
                          {failure === null
                            ? one.failure_code
                            : text(failure)}
                        </div>
                      </>
                    );
                  },
                },
                {
                  header: text("recovery.amount"),
                  kind: "money",
                  priority: 1,
                  render: (one) => (
                    <MoneyValue
                      kind="owed"
                      amountMinor={one.outstanding_minor}
                      currency={one.currency}
                    />
                  ),
                },
                {
                  header: text("recovery.wants"),
                  kind: "status",
                  priority: 1,
                  render: (one) => {
                    const name = treatmentName(one.treatment);
                    const why = reasonName(one.treatment_reason);
                    return (
                      <>
                        <span
                          {...(one.treatment === "review"
                            ? { className: "ds-wants-review" }
                            : {})}
                        >
                          {name === null ? one.treatment : text(name)}
                        </span>
                        <div className="muted" style={{ fontSize: "var(--type-caption-size)" }}>
                          {why === null ? one.treatment_reason : text(why)}
                        </div>
                      </>
                    );
                  },
                },
                {
                  header: text("recovery.method"),
                  kind: "text",
                  priority: 3,
                  // **The instrument, as a word.** The canvas puts "Visa ···4417" beside the
                  // failure; this build has no card detail at all, so the kind is the whole
                  // of it — and it belongs in a column of its own rather than appended to
                  // the failure, where "Card expired · card" repeats the noun the failure
                  // already named.
                  render: (one) => {
                    const named = methodName(one.method);
                    return named === null ? (
                      <span className="data" dir="ltr">{one.method ?? "—"}</span>
                    ) : (
                      text(named)
                    );
                  },
                },
                {
                  header: text("recovery.charges"),
                  kind: "text",
                  priority: 3,
                  // **The figure the header's claim rests on.** "All retries exhausted" is
                  // derived from this count against the retry budget, so a reader checking
                  // that sentence has nothing to check it with unless the count is here.
                  // It is charges *presented against the invoice*, not the case's dunning
                  // steps and not one intent's own column — a retry in this build is a new
                  // intent, so that column sits at one however many times the card is
                  // tried. Priority 3, so it is the first to drop on a phone: the claim is
                  // in the header and this is the working.
                  render: (one) => (
                    <span className="data">{one.charges_presented}</span>
                  ),
                },
              ]}
            />
          </section>

          {/* "The message they receive". */}
          <section className="page-section" aria-labelledby="preview-heading">
            <h2 id="preview-heading" style={{ margin: 0 }}>
              {text("recovery.previewTitle")}
            </h2>
            {templates === null ? (
              <Banner severity="info">{text(gateMessage(mayTemplates))}</Banner>
            ) : (
              keys.map((key) => (
                <Preview
                  key={key}
                  locale={locale}
                  templateKey={key}
                  template={templates.get(key) ?? null}
                />
              ))
            )}
            <ProseNote>{text("recovery.serviceMessage")}</ProseNote>
          </section>
        </>
      )}

      {/* What this screen cannot do. */}
      <section className="page-section">
        <h2 style={{ margin: 0 }}>{text("recovery.notYet")}</h2>
        <dl className="facts">
          <dt className="muted">{text("recovery.sendTitle")}</dt>
          <dd style={{ margin: 0 }}><Prose>{text("recovery.sendWhy")}</Prose></dd>
          <dt className="muted">{text("recovery.linkTitle")}</dt>
          <dd style={{ margin: 0 }}><Prose>{text("recovery.linkWhy")}</Prose></dd>
          <dt className="muted">{text("recovery.cardTitle")}</dt>
          <dd style={{ margin: 0 }}><Prose>{text("recovery.cardWhy")}</Prose></dd>
          <dt className="muted">{text("recovery.consentTitle")}</dt>
          <dd style={{ margin: 0 }}><Prose>{text("recovery.consentWhy")}</Prose></dd>
        </dl>
      </section>
    </Shell>
  );
}

/**
 * Which sentence a single-treatment set gets.
 *
 * Three, not one with the treatment interpolated: "all six want the member asked" and "all
 * six want somebody to look first" are different instructions, and a sentence built by
 * dropping a noun into a frame reads as a template in either language and translates badly
 * into neither.
 */
function verdictKey(treatment: Treatment): MessageKey {
  switch (treatment) {
    case "link":
      return "recovery.oneDecision";
    case "review":
      return "recovery.allReview";
    case "retry":
      return "recovery.allRetry";
  }
}

/**
 * One template, as authored.
 *
 * **Unrendered on purpose.** The placeholders are the honest part: they say which values a
 * sender would have to supply, and this build cannot supply the one the design's example
 * fills in. A rendered example with a made-up link would read as a message that exists.
 */
function Preview({
  locale,
  templateKey,
  template,
}: {
  locale: Locale;
  templateKey: string;
  template: PublishedTemplate | null;
}) {
  const text = (key: MessageKey) => t(locale, key);
  if (template === null) {
    return (
      <Banner severity="attention">
        {fill(locale, "recovery.noTemplate", { key: templateKey })}
      </Banner>
    );
  }
  return (
    <div className="ds-panel">
      <div className="ds-panel-head">
        <p className="ds-panel-title">
          {template.subject === null
            ? text("recovery.noSubject")
            : template.subject}
        </p>
        <p className="muted" style={{ margin: 0, fontSize: "var(--type-caption-size)" }}>
          <span className="data" dir="ltr">{template.template_key}</span>
          {" · "}
          <span className="data" dir="ltr">{template.channel}</span>
          {" · "}
          <span className="data" dir="ltr">{template.locale}</span>
          {" · "}
          {/* **The category is the control, so it is rendered rather than summarised.** It
              is what decides whether a recipient's opt-out can stop this message at all. */}
          <span className="data" dir="ltr">{template.category}</span>
        </p>
      </div>
      <div className="ds-panel-body">
        {/* The canvas's white inset. `pre-wrap`, because a template's own line breaks are
            part of the message somebody authored. */}
        <p className="ds-message" dir="auto">{template.body}</p>
      </div>
      <p className="ds-panel-note">
        {text("recovery.placeholders")}{" "}
        <span className="data" dir="ltr">{template.variables.join(", ")}</span>
      </p>
    </div>
  );
}

function Shell({
  locale,
  children,
  figures,
}: {
  locale: Locale;
  children: React.ReactNode;
  figures?: React.ReactNode;
}) {
  return (
    <div className="stack">
      <PageHeader
        title={t(locale, "recovery.heading")}
        {...(figures ? { figures } : {})}
      />
      {children}
    </div>
  );
}
