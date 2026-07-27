"use client";
import React from "react";
import { useStock, StockPage, PartyPage } from "../shared";

const COLUMNS = [
  { key: "name", label: "Customer / Project", required: true },
  { key: "gstin", label: "GSTIN" },
  { key: "contact_person", label: "Contact Person" },
  { key: "phone", label: "Phone" },
  { key: "site_address", label: "Site Address" },
];

export default function StockCustomersPage() {
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
