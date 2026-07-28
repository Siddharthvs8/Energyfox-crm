"use client";
import React from "react";
import { useStock, PartyScreen, PartyCol } from "../shared";

const COLUMNS: PartyCol[] = [
  { key: "name", label: "Supplier", required: true, placeholder: "e.g. Waaree Energies Ltd" },
  { key: "gst_number", label: "GSTIN", mono: true },
  { key: "contact_person", label: "Contact Person" },
  { key: "phone", label: "Phone", mono: true },
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
