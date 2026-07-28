from decimal import Decimal
from django.db import models


class Vendor(models.Model):
    """A supplier the workspace buys stock from."""
    name = models.CharField(max_length=200)
    contact_person = models.CharField(max_length=150, blank=True, default='')
    email = models.EmailField(blank=True, null=True)
    phone = models.CharField(max_length=20, blank=True, default='')
    gst_number = models.CharField(max_length=30, blank=True, default='')
    payment_terms = models.CharField(max_length=100, blank=True, default='')
    address = models.TextField(blank=True, default='')
    notes = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class _NumberedDoc(models.Model):
    """Shared header behaviour: auto document number + money math."""
    NUMBER_PREFIX = 'DOC'

    number = models.CharField(max_length=30, blank=True, db_index=True)
    notes = models.TextField(blank=True, default='')
    created_by = models.ForeignKey('users.User', on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
        creating = self._state.adding
        super().save(*args, **kwargs)
        if creating and not self.number:
            self.number = f"{self.NUMBER_PREFIX}-{self.pk:04d}"
            super().save(update_fields=['number'])

    @property
    def subtotal(self):
        return sum((item.line_total for item in self.items.all()), Decimal('0'))

    def __str__(self):
        return self.number or f"{self.NUMBER_PREFIX} #{self.pk}"


class _TaxedDoc(_NumberedDoc):
    """Header with discount + tax (Quotes & Sales Orders)."""
    discount_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    tax_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)

    class Meta(_NumberedDoc.Meta):
        abstract = True

    @property
    def discount_amount(self):
        return (self.subtotal * (self.discount_percent or 0)) / Decimal('100')

    @property
    def taxable_amount(self):
        return self.subtotal - self.discount_amount

    @property
    def tax_amount(self):
        return (self.taxable_amount * (self.tax_percent or 0)) / Decimal('100')

    @property
    def total(self):
        return self.taxable_amount + self.tax_amount


# ─── Purchase Orders ────────────────────────────────────────────────────────
class PurchaseOrder(_NumberedDoc):
    NUMBER_PREFIX = 'PO'
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('ordered', 'Ordered'),
        ('received', 'Received'),
        ('cancelled', 'Cancelled'),
    ]
    vendor = models.ForeignKey(Vendor, on_delete=models.SET_NULL, null=True, blank=True, related_name='purchase_orders')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft', db_index=True)
    order_date = models.DateField(null=True, blank=True)
    expected_date = models.DateField(null=True, blank=True)
    stock_received = models.BooleanField(default=False)  # guard: stock-in applied once

    @property
    def total(self):
        return self.subtotal


class PurchaseOrderItem(models.Model):
    purchase_order = models.ForeignKey(PurchaseOrder, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey('leads.Product', on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    description = models.CharField(max_length=255, blank=True, default='')
    quantity = models.DecimalField(max_digits=12, decimal_places=2, default=1)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    @property
    def line_total(self):
        return (self.quantity or Decimal('0')) * (self.unit_price or Decimal('0'))


# ─── Quotes ─────────────────────────────────────────────────────────────────
class Quote(_TaxedDoc):
    NUMBER_PREFIX = 'QT'
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('sent', 'Sent'),
        ('accepted', 'Accepted'),
        ('declined', 'Declined'),
        ('converted', 'Converted'),
    ]
    lead = models.ForeignKey('leads.Lead', on_delete=models.SET_NULL, null=True, blank=True, related_name='quotes')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft', db_index=True)
    quote_date = models.DateField(null=True, blank=True)
    expiry_date = models.DateField(null=True, blank=True)


class QuoteItem(models.Model):
    quote = models.ForeignKey(Quote, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey('leads.Product', on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    description = models.CharField(max_length=255, blank=True, default='')
    quantity = models.DecimalField(max_digits=12, decimal_places=2, default=1)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    @property
    def line_total(self):
        return (self.quantity or Decimal('0')) * (self.unit_price or Decimal('0'))


# ─── Sales Orders ───────────────────────────────────────────────────────────
class SalesOrder(_TaxedDoc):
    NUMBER_PREFIX = 'SO'
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('confirmed', 'Confirmed'),
        ('shipped', 'Shipped'),
        ('delivered', 'Delivered'),
        ('cancelled', 'Cancelled'),
    ]
    lead = models.ForeignKey('leads.Lead', on_delete=models.SET_NULL, null=True, blank=True, related_name='sales_orders')
    source_quote = models.ForeignKey(Quote, on_delete=models.SET_NULL, null=True, blank=True, related_name='sales_orders')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft', db_index=True)
    order_date = models.DateField(null=True, blank=True)
    stock_committed = models.BooleanField(default=False)  # guard: stock-out applied once


class SalesOrderItem(models.Model):
    sales_order = models.ForeignKey(SalesOrder, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey('leads.Product', on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    description = models.CharField(max_length=255, blank=True, default='')
    quantity = models.DecimalField(max_digits=12, decimal_places=2, default=1)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    @property
    def line_total(self):
        return (self.quantity or Decimal('0')) * (self.unit_price or Decimal('0'))


# ─── Stock register ─────────────────────────────────────────────────────────
# A warehouse-side stock ledger, separate from the sales documents above:
# closing stock is always derived (opening + goods received − dispatched) rather
# than stored, so the books can never drift from the movements that made them.

class StockItem(models.Model):
    """One SKU in the warehouse — a panel, inverter, battery, structure, cable."""
    CATEGORY_CHOICES = [
        ('Solar Panel', 'Solar Panel'),
        ('Inverter', 'Inverter'),
        ('Battery', 'Battery'),
        ('Mounting Structure', 'Mounting Structure'),
        ('Cable', 'Cable'),
        ('BOS Accessory', 'BOS Accessory'),
        ('Other', 'Other'),
    ]

    code = models.CharField(max_length=40, unique=True)
    category = models.CharField(max_length=40, choices=CATEGORY_CHOICES, default='Other', db_index=True)
    brand = models.CharField(max_length=120, blank=True, default='')
    model_name = models.CharField(max_length=150, blank=True, default='', verbose_name='Model / spec')
    unit = models.CharField(max_length=20, default='Nos')

    opening_stock = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    unit_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    reorder_level = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    location = models.CharField(max_length=150, blank=True, default='')

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['code']

    def __str__(self):
        return self.code

    # Fall back to per-row queries when the row wasn't annotated by the viewset.
    @property
    def received(self):
        cached = getattr(self, 'received_qty', None)
        if cached is not None:
            return cached
        return self.receipts.aggregate(t=models.Sum('quantity'))['t'] or Decimal('0')

    @property
    def dispatched(self):
        cached = getattr(self, 'dispatched_qty', None)
        if cached is not None:
            return cached
        return self.dispatches.aggregate(t=models.Sum('quantity'))['t'] or Decimal('0')

    @property
    def closing_stock(self):
        return (self.opening_stock or Decimal('0')) + self.received - self.dispatched

    @property
    def stock_value(self):
        return self.closing_stock * (self.unit_cost or Decimal('0'))

    @property
    def needs_reorder(self):
        return self.closing_stock <= (self.reorder_level or Decimal('0'))


class StockCustomer(models.Model):
    """A buyer / project site the warehouse dispatches to."""
    name = models.CharField(max_length=200)
    gstin = models.CharField(max_length=30, blank=True, default='')
    contact_person = models.CharField(max_length=150, blank=True, default='')
    phone = models.CharField(max_length=20, blank=True, default='')
    site_address = models.CharField(max_length=255, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class _StockMovement(models.Model):
    """Shared shape of an inward/outward line: which item, how many, at what rate."""
    date = models.DateField(db_index=True)
    quantity = models.DecimalField(max_digits=12, decimal_places=2)
    rate = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    notes = models.TextField(blank=True, default='')
    created_by = models.ForeignKey('users.User', on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        abstract = True
        ordering = ['-date', '-id']

    @property
    def amount(self):
        return (self.quantity or Decimal('0')) * (self.rate or Decimal('0'))


class GoodsReceipt(_StockMovement):
    """Stock in — a GRN against a supplier."""
    grn_no = models.CharField(max_length=30, blank=True, default='', db_index=True)
    supplier = models.ForeignKey(Vendor, on_delete=models.SET_NULL, null=True, blank=True, related_name='goods_receipts')
    # PROTECT: an item with movement history can't be deleted out from under it.
    item = models.ForeignKey(StockItem, on_delete=models.PROTECT, related_name='receipts')

    def __str__(self):
        return self.grn_no or f"GRN #{self.pk}"


class StockDispatch(_StockMovement):
    """Stock out — a delivery to a customer / project site."""
    invoice_no = models.CharField(max_length=30, blank=True, default='', db_index=True)
    customer = models.ForeignKey(StockCustomer, on_delete=models.SET_NULL, null=True, blank=True, related_name='dispatches')
    item = models.ForeignKey(StockItem, on_delete=models.PROTECT, related_name='dispatches')
    site = models.CharField(max_length=255, blank=True, default='')

    class Meta(_StockMovement.Meta):
        verbose_name_plural = 'Stock dispatches'

    def __str__(self):
        return self.invoice_no or f"Dispatch #{self.pk}"


class StockQuote(_TaxedDoc):
    """A wholesale quotation over stock items.

    Reuses the same header maths as the retail Quote (subtotal → discount → tax),
    but priced off StockItem rather than the product catalogue. Accepting one is
    recorded by converting it, which writes the dispatch rows that take the goods
    out of stock — see StockQuoteViewSet.convert.
    """
    NUMBER_PREFIX = 'SQ'
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('sent', 'Sent'),
        ('accepted', 'Accepted'),
        ('declined', 'Declined'),
        ('converted', 'Converted'),
    ]
    customer = models.ForeignKey(StockCustomer, on_delete=models.SET_NULL, null=True, blank=True,
                                related_name='quotes')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft', db_index=True)
    quote_date = models.DateField(null=True, blank=True)
    expiry_date = models.DateField(null=True, blank=True)
    site = models.CharField(max_length=255, blank=True, default='')
    # Guard: a quote's stock may only be dispatched once.
    converted_at = models.DateTimeField(null=True, blank=True)


class StockQuoteItem(models.Model):
    quote = models.ForeignKey(StockQuote, on_delete=models.CASCADE, related_name='items')
    # PROTECT for the same reason movements use it: an item with paperwork against
    # it can't be deleted out from under it.
    item = models.ForeignKey(StockItem, on_delete=models.PROTECT, related_name='quote_lines')
    description = models.CharField(max_length=255, blank=True, default='')
    quantity = models.DecimalField(max_digits=12, decimal_places=2, default=1)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    @property
    def line_total(self):
        return (self.quantity or Decimal('0')) * (self.unit_price or Decimal('0'))
