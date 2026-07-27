"use client";
/**
 * Inventory → Customers.
 *
 * The buyers and project sites stock is dispatched to. Same customer book the
 * wholesale side uses (`/api/stock-customers/`), so a customer added here is the
 * one offered when logging a dispatch — hence the shared components rather than
 * a second copy of the same screen.
 */
import React from "react";
import { useStock, StockPage, PartyPage } from "../inventory/shared";

const COLUMNS = [
  { key: "name", label: "Customer / Project", required: true },
  { key: "gstin", label: "GSTIN" },
  { key: "contact_person", label: "Contact Person" },
  { key: "phone", label: "Phone" },
  { key: "site_address", label: "Site Address" },
];

export default function InventoryCustomersPage() {
  const { customers, loading, denied, create, remove } = useStock(["customers"]);

  return (
    <StockPage title="Customers" loading={loading} denied={denied}
      subtitle="Buyers and project sites you dispatch to.">
      <PartyPage
        noun="customer" columns={COLUMNS} rows={customers}
        onAdd={(row: any) => create("customers", row)}
        onDelete={(id: number) => remove("customers", id, "customer")} />
    </StockPage>
  );
}
