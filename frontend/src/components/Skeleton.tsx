/**
 * Skeleton placeholders.
 *
 * A spinner says "something is happening"; a skeleton says "this is what is
 * coming, and it will land here" — the page keeps its shape, nothing jumps when
 * the data arrives, and on a phone the wait stops feeling like a stall. Every
 * skeleton here mirrors the real layout it stands in for, including the
 * mobile-card / desktop-table split the list pages use.
 *
 * These are plain markup with no hooks, so a server component (a route's
 * `loading.tsx`) can render them directly.
 */
import React from "react";

/** One shimmering block. `className` carries the size. */
export function Skeleton({ className = "" }: { className?: string }) {
  return <div className={`skeleton ${className}`} aria-hidden="true" />;
}

/** A few lines of text, the last one short like a real paragraph. */
export function SkeletonText({ lines = 2, className = "" }: { lines?: number; className?: string }) {
  return (
    <div className={`space-y-2 ${className}`} aria-hidden="true">
      {Array.from({ length: lines }).map((_, i) => (
        <div key={i} className={`skeleton h-3 rounded-md ${i === lines - 1 ? "w-2/3" : "w-full"}`} />
      ))}
    </div>
  );
}

/** Wraps a skeleton block so screen readers announce the wait once. */
export function SkeletonRegion({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div role="status" aria-live="polite" aria-busy="true">
      <span className="sr-only">{label}</span>
      {children}
    </div>
  );
}

/** The four-up metric row at the top of the dashboard and most modules. */
export function StatCardsSkeleton({ count = 4 }: { count?: number }) {
  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4">
      {Array.from({ length: count }).map((_, i) => (
        <div key={i} className="bg-white border border-slate-100 rounded-2xl p-4 sm:p-5 shadow-sm">
          <div className="flex items-start justify-between mb-3 sm:mb-4">
            <Skeleton className="w-10 h-10 rounded-xl" />
            <Skeleton className="h-2.5 w-16 rounded-full" />
          </div>
          <Skeleton className="h-7 w-24 rounded-lg" />
          <Skeleton className="h-2.5 w-20 rounded-full mt-2.5" />
        </div>
      ))}
    </div>
  );
}

/** A panel with a title and a chart-sized body. */
export function ChartSkeleton({ className = "", bars = 7 }: { className?: string; bars?: number }) {
  // Fixed heights rather than random ones: a skeleton that reshuffles on every
  // render reads as movement, which is the opposite of what it is for.
  const heights = ["45%", "70%", "35%", "85%", "55%", "75%", "40%", "65%"];
  return (
    <div className={`bg-white border border-slate-100 rounded-2xl p-4 sm:p-6 shadow-sm ${className}`}>
      <div className="flex items-center justify-between mb-5">
        <div className="space-y-2">
          <Skeleton className="h-4 w-32 rounded-md" />
          <Skeleton className="h-2.5 w-40 rounded-full" />
        </div>
        <Skeleton className="h-6 w-16 rounded-full" />
      </div>
      <div className="h-[200px] sm:h-[220px] flex items-end gap-2 sm:gap-3">
        {Array.from({ length: bars }).map((_, i) => (
          <div key={i} className="flex-1 flex flex-col justify-end h-full">
            <div className="skeleton w-full rounded-t-lg" style={{ height: heights[i % heights.length] }} aria-hidden="true" />
          </div>
        ))}
      </div>
    </div>
  );
}

/** The activity / notification feed panel. */
export function FeedSkeleton({ rows = 4, className = "" }: { rows?: number; className?: string }) {
  return (
    <div className={`bg-white border border-slate-100 rounded-2xl p-4 sm:p-6 shadow-sm ${className}`}>
      <div className="flex items-center justify-between mb-5">
        <Skeleton className="h-4 w-32 rounded-md" />
        <Skeleton className="h-6 w-14 rounded-full" />
      </div>
      <div className="space-y-4">
        {Array.from({ length: rows }).map((_, i) => (
          <div key={i} className="flex items-start gap-3">
            <Skeleton className="w-9 h-9 rounded-xl flex-shrink-0" />
            <div className="flex-1 space-y-2 pt-0.5">
              <Skeleton className="h-3 w-full rounded-md" />
              <Skeleton className="h-2.5 w-24 rounded-full" />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

/**
 * A list of records: stacked cards on a phone, table rows from `lg` up — the
 * same split the Leads and Calls pages use, so the skeleton and the real thing
 * occupy the same space at every width.
 */
export function RecordListSkeleton({ rows = 6, columns = 5 }: { rows?: number; columns?: number }) {
  return (
    <div className="bg-white border border-slate-200/60 rounded-2xl shadow-sm overflow-hidden">
      {/* Phone */}
      <div className="lg:hidden p-3 space-y-2.5">
        {Array.from({ length: rows }).map((_, i) => (
          <div key={i} className="record-card">
            <div className="flex items-start gap-3">
              <Skeleton className="w-9 h-9 rounded-xl flex-shrink-0" />
              <div className="flex-1 space-y-2">
                <Skeleton className="h-3.5 w-1/2 rounded-md" />
                <Skeleton className="h-2.5 w-2/5 rounded-full" />
              </div>
              <Skeleton className="h-4 w-16 rounded-md flex-shrink-0" />
            </div>
            <div className="flex gap-1.5 mt-3">
              <Skeleton className="h-5 w-20 rounded-md" />
              <Skeleton className="h-5 w-16 rounded-md" />
            </div>
            <Skeleton className="h-9 w-full rounded-xl mt-2.5" />
          </div>
        ))}
      </div>

      {/* Desktop */}
      <div className="hidden lg:block">
        <div className="flex items-center gap-4 px-4 py-3 border-b border-slate-100 bg-slate-50/80">
          {Array.from({ length: columns }).map((_, i) => (
            <Skeleton key={i} className={`h-2.5 rounded-full ${i === 0 ? "w-40" : "flex-1"}`} />
          ))}
        </div>
        {Array.from({ length: rows }).map((_, i) => (
          <div key={i} className="flex items-center gap-4 px-4 py-4 border-b border-slate-50">
            <div className="flex items-center gap-3 w-40 flex-shrink-0">
              <Skeleton className="w-8 h-8 rounded-lg flex-shrink-0" />
              <div className="flex-1 space-y-1.5">
                <Skeleton className="h-3 w-full rounded-md" />
                <Skeleton className="h-2 w-2/3 rounded-full" />
              </div>
            </div>
            {Array.from({ length: columns - 1 }).map((_, c) => (
              <Skeleton key={c} className="h-4 flex-1 rounded-md" />
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}

/** A grid of cards — boards, team lists, product catalogues. */
export function CardGridSkeleton({ count = 6, className = "" }: { count?: number; className?: string }) {
  return (
    <div className={`grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-4 ${className}`}>
      {Array.from({ length: count }).map((_, i) => (
        <div key={i} className="bg-white border border-slate-100 rounded-2xl p-4 shadow-sm">
          <div className="flex items-center gap-3 mb-4">
            <Skeleton className="w-10 h-10 rounded-xl flex-shrink-0" />
            <div className="flex-1 space-y-2">
              <Skeleton className="h-3.5 w-2/3 rounded-md" />
              <Skeleton className="h-2.5 w-1/3 rounded-full" />
            </div>
          </div>
          <SkeletonText lines={2} />
          <Skeleton className="h-8 w-full rounded-xl mt-4" />
        </div>
      ))}
    </div>
  );
}

/** The search-and-filters strip that sits above every list. */
export function ToolbarSkeleton() {
  return (
    <div className="space-y-2.5">
      <Skeleton className="h-11 w-full sm:max-w-md rounded-xl" />
      <div className="flex gap-2.5 overflow-hidden">
        {[172, 172, 150, 150].map((w, i) => (
          <div key={i} className="skeleton h-10 rounded-xl flex-shrink-0" style={{ width: w }} aria-hidden="true" />
        ))}
      </div>
    </div>
  );
}

/**
 * The default wait for any module: page heading, toolbar, list. Used by the
 * route-level `loading.tsx` files, where the module is not known yet.
 */
export function PageSkeleton({ stats = false }: { stats?: boolean }) {
  return (
    <SkeletonRegion label="Loading page">
      <div className="p-4 sm:p-6 lg:p-8 max-w-[1440px] space-y-5">
        <div className="flex items-center justify-between gap-4">
          <div className="space-y-2">
            <Skeleton className="h-5 w-40 rounded-md" />
            <Skeleton className="h-2.5 w-24 rounded-full" />
          </div>
          <Skeleton className="h-10 w-28 rounded-xl" />
        </div>
        {stats && <StatCardsSkeleton />}
        <ToolbarSkeleton />
        <RecordListSkeleton rows={5} />
      </div>
    </SkeletonRegion>
  );
}

/** A record's own page: header card, two-column body. */
export function DetailSkeleton() {
  return (
    <SkeletonRegion label="Loading record">
      <div className="p-4 sm:p-6 lg:p-8 max-w-[1200px]">
        <Skeleton className="h-3 w-40 rounded-full mb-6" />
        <div className="bg-white rounded-2xl border border-slate-100 p-4 sm:p-6 mb-5 sm:mb-6">
          <div className="flex flex-col md:flex-row justify-between gap-4">
            <div className="flex items-center gap-3 sm:gap-4">
              <Skeleton className="w-14 h-14 sm:w-16 sm:h-16 rounded-2xl flex-shrink-0" />
              <div className="space-y-2">
                <Skeleton className="h-6 w-44 rounded-md" />
                <Skeleton className="h-3 w-28 rounded-full" />
                <div className="flex gap-2 pt-1">
                  <Skeleton className="h-5 w-16 rounded-md" />
                  <Skeleton className="h-5 w-20 rounded-md" />
                </div>
              </div>
            </div>
            <div className="flex flex-wrap gap-2">
              <Skeleton className="h-9 w-20 rounded-xl" />
              <Skeleton className="h-9 w-28 rounded-xl" />
              <Skeleton className="h-9 w-24 rounded-xl" />
            </div>
          </div>
        </div>
        <div className="grid lg:grid-cols-3 gap-4 sm:gap-6">
          <div className="lg:col-span-2 space-y-4 sm:space-y-6">
            {[0, 1].map(i => (
              <div key={i} className="bg-white rounded-2xl border border-slate-100 p-4 sm:p-6">
                <Skeleton className="h-4 w-40 rounded-md mb-4" />
                <div className="grid sm:grid-cols-2 gap-4">
                  {Array.from({ length: 4 }).map((_, j) => (
                    <div key={j} className="space-y-2">
                      <Skeleton className="h-2.5 w-16 rounded-full" />
                      <Skeleton className="h-3.5 w-32 rounded-md" />
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
          <FeedSkeleton rows={5} />
        </div>
      </div>
    </SkeletonRegion>
  );
}

/** The small inline spinner for buttons that are mid-request. */
export function Spinner({ className = "" }: { className?: string }) {
  return (
    <span
      className={`inline-block w-4 h-4 border-2 border-current border-t-transparent rounded-full animate-spin ${className}`}
      aria-hidden="true"
    />
  );
}
