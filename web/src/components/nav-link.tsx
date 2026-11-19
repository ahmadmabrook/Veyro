"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

/**
 * A navigation link that marks itself when it is the page you are on.
 *
 * **The only client component in the app, and it exists for one attribute.** A server layout
 * does not know the pathname -- Next does not pass it -- so either every page repeats the
 * nav with its own `active` prop, or one small client component reads `usePathname()`. The
 * first spreads a control across every caller, which is the shape `CLAUDE.md` records as "a
 * check belongs where every caller passes"; the second costs a few bytes of JavaScript for
 * `aria-current`.
 *
 * **Without JavaScript the links still work and only the marker is missing.** That is the
 * honest trade and it is the right way round: navigation is a list of links, which is what an
 * anchor is, and the sign-in path -- the one with credentials in it -- has no client runtime
 * at all.
 */
export function NavLink({ href, children }: { href: string; children: React.ReactNode }) {
  const pathname = usePathname();
  // A section is current when its own page is open or when the page is inside it. `/` would
  // match everything under `startsWith`, so the root is compared exactly.
  const active = href === "/" ? pathname === "/" : pathname.startsWith(href);
  return (
    <Link href={href} aria-current={active ? "page" : undefined} className="nav-link">
      {children}
    </Link>
  );
}
