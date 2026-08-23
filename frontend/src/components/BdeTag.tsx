/**
 * Who did the site visit, as a tag on the customer's row.
 *
 * Every stage after the BDE's shows it — feasibility, documentation, accounts,
 * purchase, project, liasoning, maintenance — because by then the customer has
 * passed through several desks and the person who actually stood on the roof is
 * the one worth asking about them. It is shown to everyone who can open the
 * module, not only to admins: the documentation clerk needs it as much as the
 * manager does.
 *
 * Renders nothing when no BDE is recorded, rather than an empty chip or a
 * placeholder dash — a lead that never had a site visit has no one to name, and
 * a row of "—" tags reads as missing data rather than as absent by nature.
 */
export default function BdeTag({ name, className = "" }: {
  name?: string | null;
  className?: string;
}) {
  const who = (name || "").trim();
  if (!who) return null;
  return (
    <span
      title={`Site visit by ${who}`}
      className={`inline-flex items-center gap-1 text-[10px] font-bold uppercase tracking-wide
                  px-2 py-0.5 rounded-full bg-violet-50 text-violet-700
                  whitespace-nowrap ${className}`}
    >
      {/* A person outline, so the tag reads as a name at a glance rather than
          as one more status pill. */}
      <svg width="9" height="9" viewBox="0 0 24 24" fill="none" stroke="currentColor"
        strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
        <circle cx="12" cy="7" r="4" />
      </svg>
      {who}
    </span>
  );
}
