from decimal import Decimal

from rest_framework import serializers
from .models import (
    Vendor,
    PurchaseOrder, PurchaseOrderItem,
    Quote, QuoteItem,
    SalesOrder, SalesOrderItem,
)


class VendorSerializer(serializers.ModelSerializer):
    purchase_order_count = serializers.IntegerField(source='purchase_orders.count', read_only=True)

    class Meta:
        model = Vendor
        fields = '__all__'


# ─── Line-item serializers ──────────────────────────────────────────────────
class _ItemSerializer(serializers.ModelSerializer):
    product_name = serializers.SerializerMethodField()
    line_total = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)

    def get_product_name(self, obj):
        return obj.product.name if obj.product else (obj.description or '')


class PurchaseOrderItemSerializer(_ItemSerializer):
    class Meta:
        model = PurchaseOrderItem
        fields = ['id', 'product', 'product_name', 'description', 'quantity', 'unit_price', 'line_total']


class QuoteItemSerializer(_ItemSerializer):
    class Meta:
        model = QuoteItem
        fields = ['id', 'product', 'product_name', 'description', 'quantity', 'unit_price', 'line_total']


class SalesOrderItemSerializer(_ItemSerializer):
    class Meta:
        model = SalesOrderItem
        fields = ['id', 'product', 'product_name', 'description', 'quantity', 'unit_price', 'line_total']


# ─── Shared nested-items handling ───────────────────────────────────────────
class _DocSerializer(serializers.ModelSerializer):
    item_model = None
    parent_fk = None

    def _replace_items(self, instance, items_data):
        instance.items.all().delete()
        objs = [self.item_model(**{self.parent_fk: instance}, **item) for item in items_data]
        self.item_model.objects.bulk_create(objs)

    def _current_user(self):
        request = self.context.get('request')
        return request.user if request and request.user.is_authenticated else None

    def create(self, validated_data):
        items_data = validated_data.pop('items', [])
        validated_data['created_by'] = self._current_user()
        instance = self.Meta.model.objects.create(**validated_data)
        self._replace_items(instance, items_data)
        self._post_save(instance)
        return instance

    def update(self, instance, validated_data):
        items_data = validated_data.pop('items', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        if items_data is not None:
            self._replace_items(instance, items_data)
        self._post_save(instance)
        return instance

    def _post_save(self, instance):
        """Hook for stock side-effects."""
        pass


# ─── Purchase Orders ────────────────────────────────────────────────────────
class PurchaseOrderSerializer(_DocSerializer):
    item_model = PurchaseOrderItem
    parent_fk = 'purchase_order'

    items = PurchaseOrderItemSerializer(many=True, required=False)
    vendor_name = serializers.CharField(source='vendor.name', read_only=True, default=None)
    created_by_name = serializers.SerializerMethodField()
    subtotal = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    total = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)

    class Meta:
        model = PurchaseOrder
        fields = [
            'id', 'number', 'vendor', 'vendor_name', 'status', 'order_date', 'expected_date',
            'notes', 'stock_received', 'created_by', 'created_by_name', 'created_at',
            'items', 'subtotal', 'total',
        ]
        read_only_fields = ['number', 'created_by', 'stock_received']

    def get_created_by_name(self, obj):
        if obj.created_by:
            return f"{obj.created_by.first_name} {obj.created_by.last_name}".strip() or obj.created_by.username
        return None

    def _post_save(self, instance):
        # Receiving a PO adds the ordered quantities into product stock (once).
        if instance.status == 'received' and not instance.stock_received:
            for item in instance.items.all():
                if item.product:
                    # No int(): receiving 4.5 must add 4.5, not 4.
                    item.product.stock_quantity = ((item.product.stock_quantity or Decimal('0'))
                                                   + (item.quantity or Decimal('0')))
                    item.product.save(update_fields=['stock_quantity'])
            instance.stock_received = True
            instance.save(update_fields=['stock_received'])


# ─── Quotes ─────────────────────────────────────────────────────────────────
class _TaxedDocSerializer(_DocSerializer):
    discount_amount = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    taxable_amount = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    tax_amount = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    subtotal = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    total = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    lead_name = serializers.SerializerMethodField()

    def get_lead_name(self, obj):
        if obj.lead:
            return f"{obj.lead.first_name} {obj.lead.last_name or ''}".strip()
        return None


class QuoteSerializer(_TaxedDocSerializer):
    item_model = QuoteItem
    parent_fk = 'quote'
    items = QuoteItemSerializer(many=True, required=False)

    class Meta:
        model = Quote
        fields = [
            'id', 'number', 'lead', 'lead_name', 'status', 'quote_date', 'expiry_date',
            'discount_percent', 'tax_percent', 'notes', 'created_by', 'created_at',
            'items', 'subtotal', 'discount_amount', 'taxable_amount', 'tax_amount', 'total',
        ]
        read_only_fields = ['number', 'created_by']


class SalesOrderSerializer(_TaxedDocSerializer):
    item_model = SalesOrderItem
    parent_fk = 'sales_order'
    items = SalesOrderItemSerializer(many=True, required=False)

    class Meta:
        model = SalesOrder
        fields = [
            'id', 'number', 'lead', 'lead_name', 'source_quote', 'status', 'order_date',
            'discount_percent', 'tax_percent', 'notes', 'stock_committed', 'created_by', 'created_at',
            'items', 'subtotal', 'discount_amount', 'taxable_amount', 'tax_amount', 'total',
        ]
        read_only_fields = ['number', 'created_by', 'stock_committed']

    def _post_save(self, instance):
        # Confirming/shipping/delivering a sales order removes stock (once).
        if instance.status in ('confirmed', 'shipped', 'delivered') and not instance.stock_committed:
            for item in instance.items.all():
                if item.product:
                    item.product.stock_quantity = max(Decimal('0'),
                                                      (item.product.stock_quantity or Decimal('0'))
                                                      - (item.quantity or Decimal('0')))
                    item.product.save(update_fields=['stock_quantity'])
            instance.stock_committed = True
            instance.save(update_fields=['stock_committed'])


# ─── Stock register ─────────────────────────────────────────────────────────
from .models import (StockItem, StockCustomer, GoodsReceipt, StockDispatch,  # noqa: E402
                     StockQuote, StockQuoteItem)


class StockItemSerializer(serializers.ModelSerializer):
    """The item master row plus its derived ledger (never stored, always summed
    from the movements — see StockItem.closing_stock)."""
    received = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    dispatched = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    closing_stock = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    stock_value = serializers.DecimalField(max_digits=16, decimal_places=2, read_only=True)
    status = serializers.SerializerMethodField()

    class Meta:
        model = StockItem
        fields = ['id', 'code', 'category', 'brand', 'model_name', 'unit',
                  'opening_stock', 'unit_cost', 'reorder_level', 'location', 'is_active',
                  'received', 'dispatched', 'closing_stock', 'stock_value', 'status',
                  'created_at']
        read_only_fields = ['created_at']

    def get_status(self, obj):
        return 'REORDER' if obj.needs_reorder else 'OK'


class StockCustomerSerializer(serializers.ModelSerializer):
    class Meta:
        model = StockCustomer
        fields = '__all__'
        read_only_fields = ['created_at']


class _MovementSerializer(serializers.ModelSerializer):
    item_code = serializers.CharField(source='item.code', read_only=True)
    item_label = serializers.SerializerMethodField()
    amount = serializers.DecimalField(max_digits=16, decimal_places=2, read_only=True)
    created_by_name = serializers.SerializerMethodField()

    def get_item_label(self, obj):
        it = obj.item
        return f"{it.brand} {it.model_name}".strip() or it.code

    def get_created_by_name(self, obj):
        u = obj.created_by
        if not u:
            return None
        return f"{u.first_name} {u.last_name}".strip() or u.username


class GoodsReceiptSerializer(_MovementSerializer):
    supplier_name = serializers.CharField(source='supplier.name', read_only=True, default=None)

    class Meta:
        model = GoodsReceipt
        fields = ['id', 'grn_no', 'date', 'supplier', 'supplier_name', 'item', 'item_code',
                  'item_label', 'quantity', 'rate', 'amount', 'notes',
                  'created_by', 'created_by_name', 'created_at']
        read_only_fields = ['created_by', 'created_at']


class StockDispatchSerializer(_MovementSerializer):
    customer_name = serializers.CharField(source='customer.name', read_only=True, default=None)

    class Meta:
        model = StockDispatch
        fields = ['id', 'invoice_no', 'date', 'customer', 'customer_name', 'item', 'item_code',
                  'item_label', 'quantity', 'rate', 'amount', 'site', 'notes',
                  'created_by', 'created_by_name', 'created_at']
        read_only_fields = ['created_by', 'created_at']


class StockQuoteItemSerializer(serializers.ModelSerializer):
    item_code = serializers.CharField(source='item.code', read_only=True)
    item_label = serializers.SerializerMethodField()
    line_total = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)

    class Meta:
        model = StockQuoteItem
        fields = ['id', 'item', 'item_code', 'item_label', 'description',
                  'quantity', 'unit_price', 'line_total']

    def get_item_label(self, obj):
        it = obj.item
        return f"{it.brand} {it.model_name}".strip() or it.code


class StockQuoteSerializer(_DocSerializer):
    item_model = StockQuoteItem
    parent_fk = 'quote'

    items = StockQuoteItemSerializer(many=True, required=False)
    customer_name = serializers.CharField(source='customer.name', read_only=True, default=None)
    created_by_name = serializers.SerializerMethodField()
    subtotal = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    discount_amount = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    taxable_amount = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    tax_amount = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    total = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)

    class Meta:
        model = StockQuote
        fields = [
            'id', 'number', 'customer', 'customer_name', 'status', 'quote_date', 'expiry_date',
            'site', 'discount_percent', 'tax_percent', 'notes',
            'created_by', 'created_by_name', 'created_at', 'converted_at',
            'items', 'subtotal', 'discount_amount', 'taxable_amount', 'tax_amount', 'total',
        ]
        # Status reaches 'converted' only through the convert action, which is what
        # writes the dispatch rows — setting it by hand would skip the stock move.
        read_only_fields = ['number', 'created_by', 'converted_at']

    def get_created_by_name(self, obj):
        u = obj.created_by
        if not u:
            return None
        return f"{u.first_name} {u.last_name}".strip() or u.username

    def validate_status(self, value):
        if value == 'converted':
            raise serializers.ValidationError(
                'Use the convert action so the dispatch is recorded with it.')
        if self.instance and self.instance.status == 'converted':
            raise serializers.ValidationError('A converted quote can no longer be changed.')
        return value

    def validate(self, data):
        # Editing anything on a converted quote would silently diverge from the
        # dispatches already written from it.
        if self.instance and self.instance.status == 'converted':
            raise serializers.ValidationError('A converted quote can no longer be edited.')
        return data
