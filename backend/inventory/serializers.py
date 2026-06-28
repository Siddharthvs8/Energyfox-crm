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
                    item.product.stock_quantity = (item.product.stock_quantity or 0) + int(item.quantity or 0)
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
                    item.product.stock_quantity = max(0, (item.product.stock_quantity or 0) - int(item.quantity or 0))
                    item.product.save(update_fields=['stock_quantity'])
            instance.stock_committed = True
            instance.save(update_fields=['stock_committed'])
