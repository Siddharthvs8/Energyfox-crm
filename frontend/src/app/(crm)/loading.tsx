import { PageSkeleton } from "@/components/Skeleton";

/**
 * The wait between tapping a module and its page rendering.
 *
 * Every CRM page is a client component that fetches in an effect, so without a
 * boundary here the app shows the previous screen — or nothing — while the
 * route's code loads. This is the default; modules whose shape is worth
 * matching more closely have their own `loading.tsx` beside their page.
 */
export default function Loading() {
  return <PageSkeleton />;
}
