"use client";
import React from "react";
import { useStock, MovementScreen } from "../shared";

export default function StockDispatchPage() {
  const { dispatches, items, customers, loading, denied, save, remove } =
    useStock(["dispatches", "items", "customers"]);

  return (
    <MovementScreen
      kind="dispatch" rows={dispatches} items={items} parties={customers}
      loading={loading} denied={denied}
      onSave={(body, id) => save("dispatches", body, id)}
      onDelete={(id) => remove("dispatches", id, "dispatch")} />
  );
}
