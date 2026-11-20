import { NavLink } from "@/components/nav-link";
import { t, type Locale, type MessageKey } from "@/i18n/locale";

/**
 * The sections this session may open, and only those — rendered as the Admin rail.
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
 *
 * **It is a rail, not a strip.** §21 specifies three layers of Admin navigation -- global
 * chrome, a rail of eight composed from role and scope with an "All areas" directory, and a
 * secondary nav capped at seven -- and `LAYOUTS` sizes the rail at 240 expanded and 56
 * collapsed. What shipped before was a horizontal row of fifteen links wrapping onto three
 * lines, which is neither of those and which no part of the design source describes.
 *
 * **The rail of eight is not implemented and the gap is deliberate.** The source says it is
 * "generated, never a static tree with disabled rows -- a receptionist and an accountant get
 * different rails, not the same rail greyed differently", and the generation input is role
 * *and scope*. This build has the role half (the gate answers per item) and not the scope half
 * (every `permit` call here is tenant-wide, which MOD-014 records as its own gap), and there
 * is no "All areas" directory because there is no second level to put in one. So the rail
 * renders every permitted section rather than a composed eight, which is recorded in
 * `contracts/ui/design-compliance.md` rather than approximated with a cut-off at eight that
 * would hide pages a reader can open.
 */
export type NavItem = { href: string; label: MessageKey; allowed: boolean };

export function AppNav({ locale, items }: { locale: Locale; items: NavItem[] }) {
  const visible = items.filter((item) => item.allowed);
  if (visible.length === 0) return null;
  return (
    <ul className="ds-rail-list" aria-label={t(locale, "nav.label")}>
      {visible.map((item) => (
        <li key={item.href}>
          <NavLink href={item.href}>
            {/* The label is hidden at the collapsed width and present at every other, which is
                what "collapses to icons" means for a rail whose items have no icons yet: the
                accessible name survives the collapse because it is the link's own text. */}
            <span className="ds-rail-label">{t(locale, item.label)}</span>
          </NavLink>
        </li>
      ))}
    </ul>
  );
}
