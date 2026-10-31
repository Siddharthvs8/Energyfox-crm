"use client";
/**
 * Pick a member of staff by typing their name: the "Referred by" field on a
 * lead whose source is Referral.
 *
 * Every active person in the company is on the list (/api/users/referrers/),
 * which is long enough that a plain dropdown becomes a scroll hunt; typing any
 * part of a name narrows it, words in any order.
 *
 * Built like the project picker on the quotation form: closed, it reads as the
 * choice; open, it is the search box. Arrow keys move, Enter picks without
 * submitting the form around it, and Escape or a click elsewhere closes it
 * with the choice unchanged.
 */
import { APP_SLUG } from "@/lib/config";
import { getApiBase } from "@/lib/mock-data";
import React, { KeyboardEvent as ReactKeyboardEvent, useEffect, useId, useMemo, useRef, useState } from "react";

type Person = { id: number; name: string; role_label: string };

export default function StaffPicker({ value, onChange, currentName, inputClassName }: {
  /** The chosen person's id as a string; "" for nobody. */
  value: string;
  onChange: (id: string) => void;
  /** The name the record carries now, shown even if they have since left. */
  currentName?: string | null;
  inputClassName: string;
}) {
  const [people, setPeople] = useState<Person[]>([]);
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const box = useRef<HTMLDivElement>(null);
  const list = useRef<HTMLUListElement>(null);
  const listId = useId();

  useEffect(() => {
    const tk = localStorage.getItem(`${APP_SLUG}_access`);
    if (!tk) return;
    fetch(`${getApiBase(APP_SLUG)}/api/users/referrers/`, { headers: { Authorization: `Bearer ${tk}` } })
      .then(r => (r.ok ? r.json() : []))
      .then(d => setPeople(Array.isArray(d) ? d : []))
      .catch(() => {});
  }, []);

  const chosen = people.find(p => String(p.id) === value) || null;
  const shown = chosen ? chosen.name : value ? (currentName || "") : "";

  const matches = useMemo(() => {
    const words = query.trim().toLowerCase().split(/\s+/).filter(Boolean);
    if (!words.length) return people;
    return people.filter(p => words.every(w => p.name.toLowerCase().includes(w)));
  }, [people, query]);

  // A new search starts the highlight at the top of what it found.
  const search = (text: string) => {
    setQuery(text);
    setActive(0);
    setOpen(true);
  };

  useEffect(() => {
    if (!open) return;
    const away = (e: MouseEvent) => {
      if (box.current && !box.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", away);
    return () => document.removeEventListener("mousedown", away);
  }, [open]);

  // Keep the keyboard selection in sight when arrowing past the fold.
  useEffect(() => {
    if (!open || !list.current) return;
    const el = list.current.querySelectorAll("[data-option]")[active] as HTMLElement | undefined;
    el?.scrollIntoView({ block: "nearest" });
  }, [active, open]);

  const pick = (p: Person | null) => {
    onChange(p ? String(p.id) : "");
    setQuery("");
    setOpen(false);
  };

  const onKey = (e: ReactKeyboardEvent<HTMLInputElement>) => {
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      if (!open) { setOpen(true); return; }
      const n = matches.length;
      if (n) setActive(i => e.key === "ArrowDown" ? (i + 1) % n : (i - 1 + n) % n);
    } else if (e.key === "Enter" && open) {
      e.preventDefault();
      if (matches[active]) pick(matches[active]);
    } else if (e.key === "Escape" && open) {
      e.preventDefault();
      setOpen(false);
    }
  };

  return (
    <div className="relative" ref={box}>
      <input
        value={open ? query : shown}
        onChange={e => search(e.target.value)}
        onFocus={() => search("")}
        onKeyDown={onKey}
        placeholder="Search staff by name…"
        role="combobox" aria-expanded={open} aria-controls={listId} aria-autocomplete="list"
        className={`${inputClassName} ${shown && !open ? "pr-9" : ""}`} />

      {shown && !open && (
        <button type="button" onClick={() => pick(null)} title="Clear" aria-label="Clear referred by"
          className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-700 transition">
          <svg width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2"
            strokeLinecap="round" viewBox="0 0 24 24"><path d="M18 6L6 18M6 6l12 12" /></svg>
        </button>
      )}

      {open && (
        <ul ref={list} id={listId} role="listbox"
          className="absolute z-30 mt-1 w-full max-h-60 overflow-y-auto bg-white border border-slate-200 rounded-xl shadow-lg py-1">
          {matches.length === 0 ? (
            <li className="px-4 py-3 text-sm text-slate-400">
              {people.length ? <>No staff named &ldquo;{query}&rdquo;.</> : "Loading staff…"}
            </li>
          ) : matches.map((p, i) => (
            <li key={p.id} role="option" aria-selected={String(p.id) === value}>
              <button type="button" data-option onClick={() => pick(p)} onMouseEnter={() => setActive(i)}
                className={`w-full text-left px-4 py-2 flex items-center justify-between gap-3 transition ${
                  i === active ? "bg-indigo-50" : "hover:bg-slate-50"}`}>
                <span className="text-sm font-medium text-slate-800 truncate">{p.name}</span>
                <span className="text-[11px] text-slate-400 flex-shrink-0">{p.role_label}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
