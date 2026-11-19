import { NavLink } from "@/components/nav-link";
import { t, type Locale, type MessageKey } from "@/i18n/locale";

/**
 * The sections this session may open, and only those.
 *
 * **The gate decides, not a role list.** Each item names the read permission its page needs
 * and the layout asks `GET /authz/check` about the caller's own session -- so a navigation
 * entry is present exactly when following it would work. The alternative, a hard-coded menu
 * with pages that answer 403, teaches people that half the product is broken; the other
 * alternative, reading a permission list and deciding here, is MOD-014's "a grant is not a
 * session" finding, because a permission held on a session too weak for the action is not a
 * permission the action will accept.
 *
 * An item the session cannot use is **absent rather than disabled**. A disabled control is a
 * promise that something could be unlocked, and for `privileged` actions in this build
 * nothing can: AAL 3 needs a hardware factor MOD-007 cannot verify.
 */
export type NavItem = { href: string; label: MessageKey; allowed: boolean };

export function AppNav({ locale, items }: { locale: Locale; items: NavItem[] }) {
  const visible = items.filter((item) => item.allowed);
  if (visible.length === 0) return null;
  return (
    <nav aria-label={t(locale, "nav.label")} className="app-nav">
      <ul>
        {visible.map((item) => (
          <li key={item.href}>
            <NavLink href={item.href}>{t(locale, item.label)}</NavLink>
          </li>
        ))}
      </ul>
    </nav>
  );
}
