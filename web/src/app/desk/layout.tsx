import { DeviceStrip } from "@/components/device-strip";
import { presentation } from "@/lib/preferences";

/**
 * The Front Desk surface's own shell.
 *
 * **FD-08 is a strip rather than a screen** -- "it sits above both Front Desk and POS at all
 * times" -- so it belongs in a layout rather than on a page. Every `/desk` route gets it,
 * which is what "always visible" means for the one Front Desk surface this build has.
 */
export default async function DeskLayout({ children }: { children: React.ReactNode }) {
  const { locale } = await presentation();
  return (
    <>
      <DeviceStrip locale={locale} />
      {children}
    </>
  );
}
