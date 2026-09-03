"use client";
/**
 * Converted Orders — accepted quotations the customer has paid against.
 *
 * The same list as the Quotation module, the other side of payment: one page
 * told which side it is showing, because two copies would drift the moment
 * either grew a column.
 */
import QuotationsPage from "../quotations/page";

export default function ConvertedOrdersPage() {
  return <QuotationsPage scope="orders" />;
}
