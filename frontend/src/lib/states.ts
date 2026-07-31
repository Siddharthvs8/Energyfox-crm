/**
 * States the business raises invoices into.
 *
 * A GST document has to name the place of supply, and getting it wrong changes
 * whether the tax splits into CGST/SGST or is charged as IGST — so this is a
 * fixed list rather than free text. Add a state here and every form that offers
 * it picks the new option up.
 */
export const STATES = ["Kerala", "Tamil Nadu"];

/** Where the business is based; what a new record starts as. */
export const HOME_STATE = STATES[0];
