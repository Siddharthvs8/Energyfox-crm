from decimal import Decimal
from django.db import models


class Vendor(models.Model):
    """A supplier the workspace buys stock from."""
    name = models.CharField(max_length=200)
    contact_person = models.CharField(max_length=150, blank=True, default='')
    email = models.EmailField(blank=True, null=True)
    phone = models.CharField(max_length=20, blank=True, default='')
    gst_number = models.CharField(max_length=30, blank=True, default='')
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
