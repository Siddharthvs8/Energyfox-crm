"use client";
/**
 * Filters that survive a refresh.
 *
 * A list page held its filters in component state, so anything that reloaded
 * the page dropped every one of them and the list was back to everything: F5,
 * a phone putting the tab to sleep while a call was made from it, the browser
 * reopening. They are kept in localStorage instead, per page and per signed-in
 * user, until they are changed or cleared. Clearing sets each one back to its
 * default, and a default is not stored, so a cleared page saves nothing.
 *
 * In place of useState for each filter the page should remember:
 *
 *   const memory = useFilterMemory("leads");
 *   const [status, setStatus] = useRemembered(memory, "status", "all");
 *   useEffect(() => { if (memory.ready) fetchLeads(); }, [memory.ready, status]);
 *
 * `ready` is false only for the first render of a page that came as HTML from
 * the server. That HTML could not read the browser's storage, so it holds the
 * defaults, and the first render has to match it; the saved filters arrive in
 * the render straight after. A page must not load its list before then: it
 * would load the unfiltered list as well, and whichever reply came back last
 * would fill the page.
 */
import { useCallback, useState, useSyncExternalStore, type Dispatch, type SetStateAction } from "react";
import { APP_SLUG } from "@/lib/config";

type Saved = Readonly<Record<string, unknown>>;

const NOTHING_SAVED: Saved = Object.freeze({});

// Each storage key's filters, read from localStorage once per page load and
// kept in step with every change after that. This tab's copy is the one that
// counts: filters changed in another tab are picked up at the next reload, not
// pushed into a list someone is working through here.
const cache = new Map<string, Saved>();
const listeners = new Set<() => void>();

// Per user as well as per page: people share the office computers, and one
// person's filters — someone else's name in Assignee — would otherwise empty
// the list of the next person to sign in on that browser.
function storageKey(page: string): string {
  let user = "";
  try { user = localStorage.getItem(`${APP_SLUG}_username`) || ""; } catch { /* storage blocked */ }
  return `${APP_SLUG}_filters_${page}_${user}`;
}

function load(key: string): Saved {
  let saved = cache.get(key);
  if (!saved) {
    saved = NOTHING_SAVED;
    try {
      const parsed = JSON.parse(localStorage.getItem(key) || "null");
      if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) saved = parsed as Saved;
    } catch { /* unreadable: start from the defaults */ }
    cache.set(key, saved);
  }
  return saved;
}

function save(key: string, saved: Saved) {
  cache.set(key, saved);
  try {
    if (Object.keys(saved).length) localStorage.setItem(key, JSON.stringify(saved));
    else localStorage.removeItem(key);
  } catch { /* full or blocked: the filters still hold until a reload */ }
  listeners.forEach(listener => listener());
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => { listeners.delete(listener); };
}

// A saved value is used only when it is the same kind as the default — a text
// filter stays text, a list stays a list — so an entry left by an older build
// cannot put into the page's state something its code does not expect.
function sameKind(value: unknown, fallback: unknown): boolean {
  return value !== undefined && value !== null && typeof value === typeof fallback
    && Array.isArray(value) === Array.isArray(fallback);
}

const same = (a: unknown, b: unknown) => JSON.stringify(a) === JSON.stringify(b);

export interface FilterMemory {
  page: string;
  /** The saved filters have been read. Until then every filter is its default. */
  ready: boolean;
  saved: Saved;
}

/** The filters saved for one page, for the user signed in on this browser. */
export function useFilterMemory(page: string): FilterMemory {
  const saved = useSyncExternalStore(subscribe, () => load(storageKey(page)), () => null);
  return { page, ready: saved !== null, saved: saved ?? NOTHING_SAVED };
}

/** useState for one filter, remembered across reloads until it is changed. */
export function useRemembered<T>(memory: FilterMemory, name: string, initial: T): [T, Dispatch<SetStateAction<T>>] {
  // The default as the page first gave it: a list default is a new [] on
  // every render, and that must not count as a different default each time.
  const [fallback] = useState(initial);
  const stored = memory.saved[name];
  const value = sameKind(stored, fallback) ? (stored as T) : fallback;

  const { page } = memory;
  const set = useCallback((next: SetStateAction<T>) => {
    const key = storageKey(page);
    const saved = load(key);
    const before = sameKind(saved[name], fallback) ? (saved[name] as T) : fallback;
    const after = typeof next === "function" ? (next as (previous: T) => T)(before) : next;
    if (same(after, before)) return;
    const changed: Record<string, unknown> = { ...saved };
    if (same(after, fallback)) delete changed[name];
    else changed[name] = after;
    save(key, changed);
  }, [page, name, fallback]);

  return [value, set];
}
