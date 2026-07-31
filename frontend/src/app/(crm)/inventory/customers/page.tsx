"use client";
import React from "react";
import { useStock, PartyScreen, PartyCol } from "../shared";
import { STATES, HOME_STATE } from "@/lib/states";

export const CUSTOMER_COLUMNS: PartyCol[] = [
  { key: "name", label: "Customer / Project", required: true, placeholder: "e.g. Green Fields Resort" },
  { key: "gstin", label: "GSTIN", mono: true },
  { key: "contact_person", label: "Contact Person" },
  { key: "phone", label: "Phone", mono: true },
  { key: "site_address", label: "Address" },
  // Printed on the proforma invoice, and it decides how GST splits, so it is
  // picked from a list rather than typed.
  { key: "state", label: "State", defaultValue: HOME_STATE, options: STATES },
];

export default function StockCustomersPage() {
  const { customers, loading, denied, save, remove } = useStock(["customers"]);

  return (
    <PartyScreen
      title="Customers" subtitle="Buyers and project sites you dispatch to." noun="Customer"
      columns={CUSTOMER_COLUMNS} rows={customers} loading={loading} denied={denied}
      onSave={(body, id) => save("customers", body, id)}
      onDelete={(id) => remove("customers", id, "customer")} />
  );
}
