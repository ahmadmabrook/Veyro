/**
 * ADM-SCH-07's one read, apart from the decisions it feeds.
 *
 * **Separate because the sheet is a client component.** `@/lib/api` reaches `next/headers`,
 * which a client bundle cannot have -- and a module whose exports are pure while its top-level
 * import is not is still impure to a bundler. This build has five recorded instances, and the
 * one this file exists for took every page in the app to a 500 with `tsc` and the linter both
 * green.
 */
import { api } from "@/lib/api";
import type { CancellationPreview, CancellationReason, Remedy } from "@/lib/cancel-class";

export function previewCancellation(
  sessionId: string,
  body: {
    cancellation_reason: CancellationReason;
    reason: string;
    remedy: Remedy;
    to_session_id?: string | null;
    correlation_id: string;
  },
): Promise<CancellationPreview> {
  return api<CancellationPreview>(
    `/scheduling/sessions/${encodeURIComponent(sessionId)}/cancel-preview`,
    { method: "POST", body });
}
