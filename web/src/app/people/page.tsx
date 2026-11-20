import Link from "next/link";
import { redirect } from "next/navigation";

import { Banner } from "@/components/ds/banner";
import { DataGrid } from "@/components/ds/data-grid";
import { formatInteger, t, type MessageKey } from "@/i18n/locale";
import { ApiError, currentSession, gate } from "@/lib/api";
import { listDuplicateCandidates, type DuplicateCandidate } from "@/lib/people";
import { presentation } from "@/lib/preferences";
import { utcStamp } from "@/lib/time";

/**
 * The way into a person's record, and an honest statement that there is no search.
 *
 * **PPL-01 has no list route and that is deliberate on the server's side.** Paragraph 4218
 * puts a permission-aware search index with a mandatory query pre-filter in ENG-01, which is
 * not built, and MOD-014's own notes say a `LIKE` scan presented as search would be a read
 * path with no freshness contract and no pre-filter. So this page does not invent one: it says
 * so, and it offers the one place the module does find people by a value -- the duplicate
 * queue, which draws its candidates through the indexes.
 *
 * **The score is shown with its signals, never alone.** An operator asked to merge two records
 * is being asked to destroy one of them; `dedup.WEIGHTS` is the whole table and there is no
 * fuzzy matching anywhere in it, so every signal is a named exact match.
 */
export default async function PeoplePage() {
  const { locale } = await presentation();
  const text = (key: MessageKey) => t(locale, key);

  if (!(await currentSession())) redirect("/login");

  const may = await gate("people.duplicate.review");
  let candidates: DuplicateCandidate[] = [];
  let failed: MessageKey | null = null;
  if (may.allowed) {
    try {
      candidates = await listDuplicateCandidates();
    } catch (error) {
      failed = error instanceof ApiError && error.reason === "unreachable"
        ? "error.network"
        : "error.unexpected";
    }
  }

  return (
    <div className="stack">
      <h1 style={{ margin: 0 }}>{text("people.title")}</h1>
      <p className="muted" style={{ margin: 0 }}>
        {text("people.lead")}
      </p>
      <section className="panel stack">
        <h2 id="duplicates-heading" style={{ margin: 0 }}>
          {text("people.duplicates")}
        </h2>
        {failed ? <Banner severity="critical">{text(failed)}</Banner> : null}
        {!may.allowed ? (
          <Banner severity="info">
            {may.reachable ? text("gate.denied") : text("gate.unreachable")}
          </Banner>
        ) : candidates.length === 0 ? (
          <Banner severity="info">{text("people.noDuplicates")}</Banner>
        ) : (
          <DataGrid
            caption={text("people.duplicates")}
labelledBy="duplicates-heading"
            rows={candidates}
            rowKey={(candidate) => candidate.candidate_id}
            columns={[
              {
                header: text("people.signals"),
                kind: "text",
                // **Priority 1, above the score.** An operator asked to merge two records is
                // being asked to destroy one of them, and `AUTO_MERGE_THRESHOLD` is null
                // precisely because a number is not enough -- so the reasons are the column
                // that survives every width and the score is the one that drops.
                priority: 1,
                render: (candidate) => candidate.signals.join(", "),
              },
              {
                header: text("people.candidate"),
                kind: "person",
                priority: 1,
                render: (candidate) => (
                  <span className="stack">
                    <Link href={`/people/${candidate.lower_person_id}`}>
                      {text("people.open")} 1
                    </Link>
                    <Link href={`/people/${candidate.higher_person_id}`}>
                      {text("people.open")} 2
                    </Link>
                  </span>
                ),
              },
              {
                header: text("people.score"),
                kind: "text",
                priority: 2,
                render: (candidate) => (
                  <span className="data">{formatInteger(candidate.score, "latn")}</span>
                ),
              },
              {
                header: text("people.detected"),
                kind: "date",
                priority: 3,
                render: (candidate) => (
                  <span className="data" dir="ltr">{utcStamp(candidate.detected_at)}</span>
                ),
              },
            ]}
          />
        )}
      </section>
    </div>
  );
}


