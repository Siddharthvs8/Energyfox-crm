/**
 * The spectator: an account that reads the whole company and writes nothing.
 *
 * Every module page guards itself by role, and those guards were written before
 * the spectator existed. So the sidebar offered the module — its own rule does
 * include the spectator — and the page then sent the reader straight back to
 * the dashboard. Eighteen modules behaved that way, which looked like eighteen
 * bugs and was really one missing clause repeated.
 *
 * The API already lets a spectator read these modules (`leads.access`'s gates
 * end with `or is_view_only(user)`, and the write side is refused by
 * `SpectatorReadOnlyMiddleware` regardless), so admitting them here opens
 * nothing the server would not already answer.
 *
 * `read_only` is what /api/users/me/ calls the flag, and it is the same one the
 * sidebar reads to decide what to show.
 */
export const isSpectator = (u?: { read_only?: boolean } | null) => !!u?.read_only;
