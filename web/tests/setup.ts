import { vi } from "vitest";

import "@testing-library/jest-dom/vitest";

/**
 * The app router, which jsdom has none of.
 *
 * **A client component calling `useRouter` throws "invariant expected app router to be
 * mounted"**, and the throw is in the *component*, so it fails every test that renders
 * anything containing it -- three login-form tests went red the moment the sign-in page grew
 * a passkey button, for a reason that has nothing to do with what they assert. Next ships no
 * test harness for the app router, so the hook is stubbed here rather than in each file.
 *
 * **It is a stub and not a fake.** `push` records nothing and navigates nowhere: a component
 * test that wanted to assert a navigation would be asserting Next's behaviour rather than
 * this app's, and the one place a navigation after a sign-in is worth proving is a browser
 * against a real server -- which `tests/e2e/passkey.spec.ts` does, because the thing that can
 * go wrong there is a page rendered from a router cache that predates the session cookie.
 */
vi.mock("next/navigation", async (importOriginal) => {
  const actual = await importOriginal<typeof import("next/navigation")>();
  return {
    ...actual,
    useRouter: () => ({
      push: () => {},
      replace: () => {},
      refresh: () => {},
      back: () => {},
      forward: () => {},
      prefetch: () => {},
    }),
  };
});
