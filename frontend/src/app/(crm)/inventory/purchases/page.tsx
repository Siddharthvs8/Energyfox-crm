"use client";
import React from "react";
import { useStock, StockPage, MovementPage } from "../shared";

export default function PurchasesPage() {
  const { receipts, items, suppliers, loading, denied, create, remove } =
    useStock(["receipts", "items", "suppliers"]);

  return (
    <StockPage title="Purchases (GRN)" loading={loading} denied={denied}
      subtitle="Log every stock receipt from a supplier.">
      <MovementPage
        kind="receipt" rows={receipts} items={items} parties={suppliers}
        onAdd={(row: any) => create("receipts", row)}
        onDelete={(id: number) => remove("receipts", id, "receipt")} />
    </StockPage>
  );
}
