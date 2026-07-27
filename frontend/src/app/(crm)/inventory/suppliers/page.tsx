"use client";
import React from "react";
import { useStock, StockPage, PartyPage } from "../shared";

const COLUMNS = [
  { key: "name", label: "Supplier Name", required: true },
  { key: "gst_number", label: "GSTIN" },
  { key: "contact_person", label: "Contact Person" },
  { key: "phone", label: "Phone" },
  { key: "payment_terms", label: "Payment Terms" },
];

export default function SuppliersPage() {
  const { suppliers, loading, denied, create, remove } = useStock(["suppliers"]);

  return (
    <StockPage title="Suppliers" loading={loading} denied={denied}
      subtitle="Vendors you purchase solar equipment from.">
      <PartyPage
        noun="supplier" columns={COLUMNS} rows={suppliers}
        onAdd={(row: any) => create("suppliers", row)}
        onDelete={(id: number) => remove("suppliers", id, "supplier")} />
    </StockPage>
  );
}
