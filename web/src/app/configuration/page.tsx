import { redirect } from "next/navigation";

import { Banner } from "@/components/ds/banner";
import { MetricCell, MetricRow } from "@/components/ds/metric-cell";
import { PageHeader } from "@/components/ds/page-header";
import { DataGrid } from "@/components/ds/data-grid";
import { fill, formatInteger, t, type MessageKey } from "@/i18n/locale";
import { ApiError, currentSession, gate, gateMessage } from "@/lib/api";
import {
  evaluateFlags,
  flagReason,
  isUnset,
  listDefinitions,
  readResolved,
} from "@/lib/configuration";
import { numerals } from "@/lib/display";
import { presentation } from "@/lib/preferences";

/**
 * What this tenant has configured, and what its feature flags say.
 *
 * **Three things on this page are answers with a reason attached, and the reason is the point.**
 *
 *   * A resolved value carries the scope it came from. `default` means nobody set it, which is
 *     a different fact from a tenant that published the same value on purpose -- and the two
 *     are indistinguishable if only the value is rendered. The version is `null` in exactly
 *     that case, because there is no published version behind a default.
 *   * A flag's variant carries why. `off` could be a kill switch somebody engaged, a flag
 *     nobody enabled, or a targeting rule that deliberately sent this subject to the control
 *     arm, and an operator in an incident needs to know which. A kill switch outranks every
 *     rule, which is what makes it the one worth marking.
 *   * A rule's id is not a reason. `rule:0f3a…` tells a reader nothing; "a targeting rule
 *     matched" is the answer, and the id stays in the data for somebody debugging.
 *
 * **A flag is evaluated per subject, and there is no route that lists flags without evaluating
 * them.** So this board is "what these flags say for one subject" rather than "what flags
 * exist", which the page says rather than leaving somebody to infer that a flag they cannot
 * see is absent. The subject defaults to the reader's own identity -- derived, not accepted --
 * and a link may name another.
 */
export default async function ConfigurationPage({
  searchParams,
}: {
  searchParams: Promise<{ subject?: string }>;
}) {
  const { locale } = await presentation();
  // **The tenant's numerals** -- ADR-0015. Every quantity on this page follows
  // `localization.numerals`; an identifier does not, and neither does money. One read for the
  // whole render: `conventions()` is React's per-request memo and the layout starts it.
  const numbering = await numerals();
  const text = (key: MessageKey) => t(locale, key);

  const session = await currentSession();
  if (!session) redirect("/login");

  const [mayConfig, mayFlags] = await Promise.all([
    gate("config.definition.read"),
    gate("config.flag.read"),
  ]);

  const params = await searchParams;
  // **Derived unless a link names one.** A subject is what a rollout bucket is computed from,
  // so "the flags say off" is only meaningful beside whose flags they are.
  const subject = params.subject?.trim() || session.identity_id;

  const [definitions, resolved, flags] = await Promise.all([
    mayConfig.allowed ? listDefinitions().catch(toNull) : null,
    mayConfig.allowed ? readResolved().catch(toNull) : null,
    mayFlags.allowed ? evaluateFlags(subject).catch(toNull) : null,
  ]);

  const killSwitches = Object.values(flags ?? {})
    .filter((decision) => flagReason(decision) === "kill_switch").length;
  const unset = Object.values(resolved ?? {}).filter(isUnset).length;

  return (
    <div className="stack">
      <PageHeader title={text("config.title")}
        figures={
          <>
            {fill(locale, "config.unsetCounted", { count: unset }, numbering)}
            {killSwitches === 0
              ? null
              : <> {"\u00b7 "}{fill(locale, "config.killCounted", { count: killSwitches }, numbering)}</>}
          </>
        }
       />

      {/* **How many keys and how many flags, at the size of a figure.** Both were a 14px
          line under the title -- the size of a footnote for the two counts this board is a
          board of. What stays in that line is the pair that qualifies them: how many values
          nobody set, and a kill switch where there is one.
          **A refused or unread count is not a zero.** The registry and the flags are
          separate permissions and either read can fail, and `?? 0` rendered both as nothing
          declared -- which at this size would read as a tenant with no configuration rather
          than as an answer this session did not get. */}
      <MetricRow label={text("config.title")}>
        {mayConfig.allowed && definitions !== null ? (
          <MetricCell
            label={text("config.registry")}
            value={formatInteger(definitions.length, numbering)}
          />
        ) : (
          <MetricCell
            label={text("config.registry")}
            freshness="unavailable"
            unavailableBecause={mayConfig.allowed
              ? text("error.unexpected")
              : text(gateMessage(mayConfig))}
          />
        )}
        {mayFlags.allowed && flags !== null ? (
          <MetricCell
            label={text("config.flags")}
            value={formatInteger(Object.keys(flags).length, numbering)}
          />
        ) : (
          <MetricCell
            label={text("config.flags")}
            freshness="unavailable"
            unavailableBecause={mayFlags.allowed
              ? text("error.unexpected")
              : text(gateMessage(mayFlags))}
          />
        )}
      </MetricRow>

      <section className="page-section">
        <h2 id="config-heading" style={{ margin: 0 }}>
          {text("config.registry")}
        </h2>
        {!mayConfig.allowed ? (
          <Banner severity="info">
            {text(gateMessage(mayConfig))}
          </Banner>
        ) : definitions === null || resolved === null ? (
          <Banner severity="critical">{text("error.unexpected")}</Banner>
        ) : definitions.length === 0 ? (
          <Banner severity="info">{text("config.noDefinitions")}</Banner>
        ) : (
          <>
            <DataGrid
              caption={text("config.registry")}
              countLabel={fill(locale, "grid.count.configValues", { count: definitions.length }, numbering)}
              labelledBy="config-heading"
              rows={definitions}
              rowKey={(definition) => definition.definition_id}
              columns={[
                {
                  header: text("config.key"),
                  kind: "text",
                  priority: 1,
                  render: (definition) => (
                    <>
                      <span className="data" dir="ltr">{definition.config_key}</span>
                      {definition.description !== null ? (
                        <div className="muted" style={{ fontSize: "var(--type-label-size)" }}>
                          {definition.description}
                        </div>
                      ) : null}
                    </>
                  ),
                },
                {
                  header: text("config.value"),
                  kind: "text",
                  priority: 1,
                  // A definition with no resolved entry cannot happen -- `/config/resolved`
                  // is built from the same registry -- but rendering `undefined` as a value
                  // would be the one answer that is always wrong, so it says so instead.
                  render: (definition) => {
                    const entry = resolved[definition.config_key];
                    return entry === undefined ? (
                      <span className="muted">{text("error.unexpected")}</span>
                    ) : (
                      <span className="data" dir="ltr">{JSON.stringify(entry.value)}</span>
                    );
                  },
                },
                {
                  header: text("config.scope"),
                  kind: "text",
                  // **Priority 1 beside the value.** A default is not a setting: an unset key
                  // reads back as its own default, and without the scope a tenant that
                  // published the same value on purpose is indistinguishable from one that
                  // never touched it.
                  priority: 1,
                  render: (definition) => {
                    const entry = resolved[definition.config_key];
                    if (entry === undefined) return null;
                    return isUnset(entry) ? (
                      <span className="muted">{text("config.unset")}</span>
                    ) : (
                      <>
                        {entry.scope_type}
                        {entry.version !== null ? (
                          <span className="muted">
                            {" · v"}
                            <span className="data">
                              {/* A version is cited, not counted: Latin. ADR-0015. */}
                              {formatInteger(entry.version, "latn")}
                            </span>
                          </span>
                        ) : null}
                      </>
                    );
                  },
                },
                {
                  header: text("config.owner"),
                  kind: "text",
                  priority: 3,
                  render: (definition) => (
                    <span className="data" dir="ltr">{definition.owner_module}</span>
                  ),
                },
              ]}
            />
            <p className="muted" style={{ margin: 0 }}>
              {text("config.unsetExplained")}
            </p>
          </>
        )}
      </section>

      <section className="page-section">
        <h2 id="flags-heading" style={{ margin: 0 }}>
          {text("config.flags")}
        </h2>
        <p className="muted" style={{ margin: 0 }}>
          {text("config.flagsLead")}{" "}
          <span className="data" dir="ltr">
            {subject}
          </span>
        </p>
        {!mayFlags.allowed ? (
          <Banner severity="info">
            {text(gateMessage(mayFlags))}
          </Banner>
        ) : flags === null ? (
          <Banner severity="critical">{text("error.unexpected")}</Banner>
        ) : Object.keys(flags).length === 0 ? (
          <Banner severity="info">{text("config.noFlags")}</Banner>
        ) : (
          <>
            <DataGrid
              caption={text("config.flags")}
              countLabel={null}
              labelledBy="flags-heading"
              rows={Object.entries(flags)}
              rowKey={([key]) => key}
              // A kill switch outranks every rule: it is a deliberate stop rather than a
              // rollout, which is the distinction MOD-005's evaluator is built on.
              rowSeverity={([, decision]) =>
                flagReason(decision) === "kill_switch" ? "critical" : null
              }
              columns={[
                {
                  header: text("config.flag"),
                  kind: "text",
                  priority: 1,
                  render: ([key]) => <span className="data" dir="ltr">{key}</span>,
                },
                {
                  header: text("config.variant"),
                  kind: "text",
                  priority: 1,
                  render: ([, decision]) => (
                    <span className="data" dir="ltr">{decision.variant}</span>
                  ),
                },
                {
                  header: text("config.why"),
                  kind: "text",
                  // Priority 1: `off` is four different facts, and the variant alone cannot
                  // tell a kill switch from a flag nobody enabled.
                  priority: 1,
                  render: ([, decision]) => text(FLAG_REASON[flagReason(decision)]),
                },
              ]}
            />
            {Object.values(flags).some(
              (decision) => flagReason(decision) === "kill_switch",
            ) ? (
              <Banner severity="critical">{text("config.killSwitchEngaged")}</Banner>
            ) : null}
            <p className="muted" style={{ margin: 0 }}>
              {text("config.noFlagList")}
            </p>
          </>
        )}
      </section>
    </div>
  );
}

/**
 * Why a flag resolved the way it did, as a sentence rather than a rule id.
 *
 * `rule:0f3a…` tells a reader nothing; "a targeting rule matched" is the answer, and the id
 * stays in the data for whoever is debugging.
 */
const FLAG_REASON: Record<ReturnType<typeof flagReason>, MessageKey> = {
  kill_switch: "config.reason.killSwitch",
  disabled: "config.reason.disabled",
  rule: "config.reason.rule",
  default: "config.reason.default",
};

function toNull(error: unknown): null {
  if (error instanceof ApiError) return null;
  throw error;
}


