"use client";
import React from "react";
import { useStock, MovementScreen } from "../shared";

export default function StockPurchasesPage() {
  const { receipts, items, suppliers, loading, denied, save, remove } =
    useStock(["receipts", "items", "suppliers"]);

  return (
    <MovementScreen
      kind="receipt" rows={receipts} items={items} parties={suppliers}
      loading={loading} denied={denied}
      onSave={(body, id) => save("receipts", body, id)}
      onDelete={(id) => remove("receipts", id, "receipt")} />
  );
}
