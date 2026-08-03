"use client";
import React from "react";
import { useStock, PartyScreen, PartyCol } from "../shared";

// Address, PAN and IEC are here because a purchase order prints them in the
// supplier block — the order takes the supplier's details from this record.
const COLUMNS: PartyCol[] = [
  { key: "name", label: "Supplier", required: true, placeholder: "e.g. Waaree Energies Ltd" },
  { key: "gst_number", label: "GSTIN", mono: true },
  { key: "pan_number", label: "PAN No", mono: true },
  { key: "iec_code", label: "IEC Code", mono: true },
  { key: "address", label: "Address", placeholder: "Printed on the purchase order" },
  { key: "contact_person", label: "Contact Person" },
  { key: "phone", label: "Phone", mono: true },
  { key: "email", label: "Email" },
  { key: "payment_terms", label: "Payment Terms", placeholder: "e.g. 30 days credit" },
];

export default function StockSuppliersPage() {
  const { suppliers, loading, denied, save, remove } = useStock(["suppliers"]);

  return (
    <PartyScreen
      title="Suppliers" subtitle="The suppliers you purchase stock from." noun="Supplier"
      columns={COLUMNS} rows={suppliers} loading={loading} denied={denied}
      onSave={(body, id) => save("suppliers", body, id)}
      onDelete={(id) => remove("suppliers", id, "supplier")} />
  );
}
