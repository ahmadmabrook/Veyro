"use client";

import { useEffect, useState } from "react";

/**
 * Toast — §34. Confirmation only, and the undo window is the component.
 *
 * > Toasts confirm; they never inform. 30-second undo window, one at a time, never carrying
 * > information the user must act on — if it matters after it disappears, it is not a toast.
 * > Reduced motion: appears without slide.
 *
 * **This is the distinction the account page got wrong**, and it is a real one rather than a
 * naming quibble. "Revoked." is a *confirmation of an event*; a Banner is a *condition*. The
 * page rendered the first as the second, so a message about something that had already
 * finished sat on the screen as though it were still true, with no way to undo it inside the
 * window the source gives for exactly that.
 *
 * Three rules are enforced here rather than left to callers:
 *
 * - **One at a time.** A second toast replaces the first; a stack of confirmations is a
 *   reader deciding which one is still relevant.
 * - **Undo stays keyboard-reachable for the full thirty seconds** and is not dismissed by
 *   pointer movement — the accessibility contract says so in as many words, because a toast
 *   that vanishes when the mouse passes over it is an undo nobody can reach.
 * - **Polite live region.** A confirmation does not interrupt; only a genuine alert does, and
 *   that is a Banner.
 *
 * It renders nothing when there is nothing to confirm, so a page can mount it unconditionally.
 */

export const UNDO_WINDOW_MS = 30_000;

export type ToastMessage = {
  /** What happened, in the past tense. Never something the reader must act on. */
  text: string;
  /** Present only when the action is reversible inside the window. */
  undo?: { label: string; onUndo: () => void };
};

export function Toast({ message, onDismiss }: { message: ToastMessage | null; onDismiss?: () => void }) {
  // **Derived, not copied into state.** The first version assigned the incoming message to
  // state inside the effect, which is a synchronous setState in an effect: a cascading render
  // on every message, and the kind of thing that works until a parent re-renders for another
  // reason. What is state here is only which message has been dismissed; what is shown is a
  // comparison, so a new message replaces the old one without anything being assigned.
  const [dismissed, setDismissed] = useState<ToastMessage | null>(null);
  const shown = message && message !== dismissed ? message : null;

  useEffect(() => {
    if (!message) return;
    // One at a time, and the window restarts with each message because the effect re-runs.
    const timer = setTimeout(() => {
      setDismissed(message);
      onDismiss?.();
    }, UNDO_WINDOW_MS);
    return () => clearTimeout(timer);
  }, [message, onDismiss]);

  if (!shown) return null;

  return (
    <div
      // Polite, not assertive: "an alert interrupts, and most banners should not" applies
      // doubly to a confirmation of something that already succeeded.
      role="status"
      aria-live="polite"
      className="ds-toast"
    >
      <span>{shown.text}</span>
      {shown.undo ? (
        <button
          type="button"
          className="ds-toast-undo"
          onClick={() => {
            shown.undo?.onUndo();
            setDismissed(shown);
          }}
        >
          {shown.undo.label}
        </button>
      ) : null}
    </div>
  );
}
