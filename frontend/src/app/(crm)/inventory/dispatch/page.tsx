"use client";
import React from "react";
import { useStock, StockPage, MovementPage } from "../shared";

export default function DispatchPage() {
  const { dispatches, items, customers, loading, denied, create, remove } =
    useStock(["dispatches", "items", "customers"]);

  return (
    <StockPage title="Sales / Dispatches" loading={loading} denied={denied}
      subtitle="Log every outward delivery to a customer or project site.">
      <MovementPage
        kind="dispatch" rows={dispatches} items={items} parties={customers}
        onAdd={(row: any) => create("dispatches", row)}
        onDelete={(id: number) => remove("dispatches", id, "dispatch")} />
    </StockPage>
  );
}
