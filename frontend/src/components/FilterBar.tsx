"use client";
/**
 * The filter strip, and what it becomes on a phone.
 *
 * Every list module in the CRM carries the same shape of toolbar: a search box
 * and then a run of selects and date ranges. On a desktop they sit on one row
 * and that is fine. On a phone that row was a sideways scroller — the second
 * filter was half off the screen, the fourth was not visibly there at all, and
 * nothing told you which ones were currently narrowing the list.
 *
 * Below `lg` this renders instead:
 *   - the search box, full width, where it always was;
 *   - one "Filters" button carrying a count of how many are set;
 *   - a bottom sheet holding the filters stacked and full width, with a label
 *     over each one, a "Clear all" and an "Apply".
 *
 * From `lg` up nothing changes: the wrappers collapse to `display: contents`
 * and the controls lay out on the toolbar row exactly as they did.
 *
 * The controls inside are the page's own — the same state, the same handlers —
 * so a change in the sheet narrows the list immediately and "Apply" is the
 * confirmation that closes it. Nothing is staged and nothing can be lost by
 * dismissing the sheet.
 */
import { useEffect, useId, useState, type ReactNode } from "react";

function FunnelIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor"
         strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3" />
    </svg>
  );
}

function CloseIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor"
         strokeWidth="2.4" strokeLinecap="round" aria-hidden="true">
      <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
    </svg>
  );
}

/**
 * One filter with its name over it.
 *
 * On a desktop the wrapper disappears (`display: contents`) and the label with
 * it, because the control's own first option already says what it is ("All
 * Priorities"). Stacked in the sheet that reading breaks down — five rounded
 * boxes in a column need a heading each — so the label appears there.
 */
export function FilterField({ label, children, className = "" }: {
  label: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={`filterbar-field ${className}`}>
      <span className="filterbar-field-label">{label}</span>
      {children}
    </div>
  );
}

export default function FilterBar({
  search,
  children,
  activeCount = 0,
  onClear,
  resultCount,
  labelled = false,
  className = "",
}: {
  /** The search field. It stays on the page on a phone; only filters move. */
  search?: ReactNode;
  /** The filter controls, ideally each wrapped in a <FilterField>. */
  children: ReactNode;
  /** How many filters are currently narrowing the list — drives the badge. */
  activeCount?: number;
  /** Resets every filter this bar holds. */
  onClear?: () => void;
  /** Rows matching right now, shown on the Apply button so the sheet can be
   *  judged before it is dismissed. */
  resultCount?: number;
  /** Keep each field's label on a desktop too. For the boards that were built
   *  with labels over their selects — taking them away is not a mobile fix. */
  labelled?: boolean;
  className?: string;
}) {
  const [open, setOpen] = useState(false);
  const panelId = useId();

  // The sheet is the only thing that should scroll while it is up, and Escape
  // should put it away — the same contract the nav drawer already has.
  useEffect(() => {
    if (!open) return;
    document.documentElement.classList.add("drawer-open");
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    window.addEventListener("keydown", onKey);
    return () => {
      document.documentElement.classList.remove("drawer-open");
      window.removeEventListener("keydown", onKey);
    };
  }, [open]);

  // A resize past `lg` while the sheet is up would leave the page scroll-locked
  // behind a sheet that CSS has already turned back into an inline row.
  useEffect(() => {
    if (!open) return;
    const mq = window.matchMedia("(min-width: 1024px)");
    const onChange = () => { if (mq.matches) setOpen(false); };
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, [open]);

  return (
    <div className={`filterbar ${labelled ? "filterbar-labelled" : ""} ${className}`}>
      {/* Without a search box there is nothing on this row but the button, and
          on a desktop the button is not there either — so it must not reserve
          the width a search box would have had. */}
      <div className={`filterbar-head ${search ? "" : "filterbar-head-bare"}`}>
        {search ? <div className="filterbar-search">{search}</div> : null}
        <button
          type="button"
          onClick={() => setOpen(true)}
          className={`filterbar-trigger ${activeCount > 0 ? "has-filters" : ""}`}
          aria-expanded={open}
          aria-controls={panelId}
        >
          <FunnelIcon />
          <span>Filters</span>
          {activeCount > 0 && <span className="filterbar-count">{activeCount}</span>}
        </button>
      </div>

      {open && <div className="filterbar-scrim" onClick={() => setOpen(false)} aria-hidden="true" />}

      {/* One element, two lives: the toolbar row on a desktop, the sheet on a
          phone. It only answers to a screen reader as a dialog while it is one. */}
      <div id={panelId} className={`filterbar-panel ${open ? "open" : ""}`}
           role={open ? "dialog" : undefined}
           aria-modal={open ? true : undefined}
           aria-label={open ? "Filters" : undefined}>
        <div className="filterbar-panel-head">
          <div>
            <p className="filterbar-panel-title">Filters</p>
            <p className="filterbar-panel-sub">
              {activeCount > 0 ? `${activeCount} applied` : "None applied"}
            </p>
          </div>
          <button type="button" onClick={() => setOpen(false)}
                  className="filterbar-close" aria-label="Close filters">
            <CloseIcon />
          </button>
        </div>

        <div className="filterbar-controls">{children}</div>

        <div className="filterbar-panel-foot">
          <button type="button" onClick={onClear} disabled={!onClear || activeCount === 0}
                  className="filterbar-clear">
            Clear all
          </button>
          <button type="button" onClick={() => setOpen(false)} className="filterbar-apply">
            {typeof resultCount === "number" ? `Apply · ${resultCount}` : "Apply"}
          </button>
        </div>
      </div>
    </div>
  );
}
