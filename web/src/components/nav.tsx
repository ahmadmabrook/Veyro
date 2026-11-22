import { RailGroup, RailItem } from "@/components/ds/chrome";
import type { IconName } from "@/components/ds/icon";
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
 * a step-up cannot: AAL 3 is reached by signing in with a passkey, not by raising a session.
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
export type NavItem = {
  href: string;
  label: MessageKey;
  allowed: boolean;
  /** The group heading this item sits under: OPERATE, PEOPLE, MONEY, DELIVER, SETTINGS. */
  group: MessageKey;
  icon: IconName;
  /** "4,812" beside Members. Absent where there is nothing to count. */
  count?: string;
};

/**
 * **Grouped, which is what makes a rail of thirteen readable.** The canvas puts its items
 * under four mono, tracked, uppercase headings, and a flat list of fifteen links is a list
 * rather than a shape. The groups render in the order their first permitted item appears,
 * and a group whose every item is refused does not render at all -- a heading over nothing
 * is the same defect as a section heading over an empty panel.
 */
export function AppNav({ locale, items }: { locale: Locale; items: NavItem[] }) {
  const visible = items.filter((item) => item.allowed);
  if (visible.length === 0) return null;
  const groups: { label: MessageKey; items: NavItem[] }[] = [];
  for (const item of visible) {
    const last = groups[groups.length - 1];
    if (last !== undefined && last.label === item.group) last.items.push(item);
    else groups.push({ label: item.group, items: [item] });
  }
  return (
    <ul className="ds-rail-list" aria-label={t(locale, "nav.label")}>
      {groups.map((group) => (
        <RailGroup
          key={group.label}
          id={`rail-${group.label.replace(".", "-")}`}
          label={t(locale, group.label)}
        >
          {group.items.map((item) => (
            <li key={item.href}>
              <NavLink href={item.href}>
                <RailItem
                  icon={item.icon}
                  label={t(locale, item.label)}
                  {...(item.count === undefined ? {} : { count: item.count })}
                />
              </NavLink>
            </li>
          ))}
        </RailGroup>
      ))}
    </ul>
  );
}
