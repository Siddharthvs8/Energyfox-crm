"use client";
/**
 * Inventory → Customers (retail menu).
 *
 * The buyers and project sites stock is dispatched to. Same customer book the
 * wholesale side uses (`/api/stock-customers/`) and the same screen component, so
 * a customer added here is the one offered when logging a dispatch.
 */
import React from "react";
import { useStock, PartyScreen, PartyCol } from "../inventory/shared";

const COLUMNS: PartyCol[] = [
  { key: "name", label: "Customer / Project", required: true, placeholder: "e.g. Green Fields Resort" },
  { key: "gstin", label: "GSTIN", mono: true },
  { key: "contact_person", label: "Contact Person" },
  { key: "phone", label: "Phone", mono: true },
  { key: "site_address", label: "Site Address" },
];

export default function InventoryCustomersPage() {
  const { customers, loading, denied, save, remove } = useStock(["customers"]);

  return (
    <PartyScreen
      title="Customers" subtitle="Buyers and project sites you dispatch to." noun="Customer"
      columns={COLUMNS} rows={customers} loading={loading} denied={denied}
      onSave={(body, id) => save("customers", body, id)}
      onDelete={(id) => remove("customers", id, "customer")} />
  );
}
