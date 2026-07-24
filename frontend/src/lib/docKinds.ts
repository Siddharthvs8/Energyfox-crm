// Slot doc_type -> canonical shared "kind". Mirrors backend leads/document_kinds.py.
//
// A customer document (Aadhaar, PAN, …) is entered once and inherited by every
// slot of the same kind across the BDE site visit and Documentation Stage 1.
// Slots absent from this map are stage-local (site photos, generated PDFs, the
// loan passbook copy) and keep their own per-stage storage.
export const SLOT_TO_KIND: Record<string, string> = {
  // BDE site visit
  aadhaar_card: "aadhaar",
  pan_card: "pan",
  passbook: "passbook",
  kseb_bill_file: "kseb_bill",
  land_tax: "land_tax",
  ownership_certificate: "ownership_certificate",
  building_certificate: "building_certificate",
  customer_passport_photo: "customer_photo",
  itr_report: "itr",
  loan_document: "loan_document",
  // Documentation Stage 1
  nc_aadhaar: "aadhaar",
  nc_kseb_bill: "kseb_bill",
  nc_landtax: "land_tax",
  nc_ownership: "ownership_certificate",
  nc_building_certificate: "building_certificate",
  nc_customer_photo: "customer_photo",
  le_aadhaar: "aadhaar",
  mnre_aadhaar: "aadhaar",
  mnre_pan: "pan",
  mnre_passbook: "passbook",
  mnre_kseb_bill: "kseb_bill",
  loan_aadhaar: "aadhaar",
  loan_pan: "pan",
  loan_passbook: "passbook",
  loan_land_tax: "land_tax",
  loan_itr: "itr",
  // Purchase order — uploaded once on the BDE site visit, inherited by the
  // Documentation Stage 1 MNRE and Loan slots.
  purchase_order: "purchase_order",
  mnre_purchase_order: "purchase_order",
  loan_agreement_purchase_order: "purchase_order",
};

/** Canonical shared kind for a slot doc_type, or undefined if it's stage-local. */
export const kindForSlot = (slot: string): string | undefined => SLOT_TO_KIND[slot];
