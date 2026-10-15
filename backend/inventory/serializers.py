from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction
from rest_framework import serializers
from .models import (
    Vendor,
    PurchaseOrder, PurchaseOrderItem,
    Quote, QuoteItem,
    SalesOrder, SalesOrderItem,
    ProjectSpec, ProjectSpecLine, QuoteSpecLine, PRICE_VARIANTS,
    Quotation, QuotationSpecLine, QuotationCost, QuotationTemplate, SYSTEM_TYPES,
)


class VendorSerializer(serializers.ModelSerializer):
    purchase_order_count = serializers.IntegerField(source='purchase_orders.count', read_only=True)

    class Meta:
        model = Vendor
        fields = '__all__'


# ─── Line-item serializers ──────────────────────────────────────────────────
class _ItemSerializer(serializers.ModelSerializer):
    product_name = serializers.SerializerMethodField()
    # Printed against the line on any GST document; default so a line with no
    # catalogue product behind it still serialises.
    product_unit = serializers.CharField(source='product.unit', read_only=True, default='')
    product_hsn = serializers.CharField(source='product.hsn', read_only=True, default='')
    line_total = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)

    def get_product_name(self, obj):
        return obj.product.name if obj.product else (obj.description or '')


class PurchaseOrderItemSerializer(_ItemSerializer):
    class Meta:
        model = PurchaseOrderItem
        fields = ['id', 'product', 'product_name', 'product_unit', 'product_hsn',
                  'description', 'quantity', 'unit_price', 'line_total']


class QuoteItemSerializer(_ItemSerializer):
    class Meta:
        model = QuoteItem
        fields = ['id', 'product', 'product_name', 'product_unit', 'product_hsn',
                  'description', 'quantity', 'unit_price', 'line_total']


class SalesOrderItemSerializer(_ItemSerializer):
    class Meta:
        model = SalesOrderItem
        fields = ['id', 'product', 'product_name', 'product_unit', 'product_hsn',
                  'description', 'quantity', 'unit_price', 'line_total']


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
    # `total` is the exact arithmetic of the lines; `grand_total` is what the
    # customer is billed, with `round_off` the adjustment between them.
    grand_total = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    round_off = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)

    class Meta:
        model = PurchaseOrder
        fields = [
            'id', 'number', 'vendor', 'vendor_name', 'status', 'order_date', 'expected_date',
            'notes', 'stock_received', 'created_by', 'created_by_name', 'created_at',
            'items', 'subtotal', 'total', 'grand_total', 'round_off',
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
    # `total` is the exact arithmetic of the lines; `grand_total` is what the
    # customer is billed, with `round_off` the adjustment between them.
    grand_total = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    round_off = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    lead_name = serializers.SerializerMethodField()

    def get_lead_name(self, obj):
        if obj.lead:
            return f"{obj.lead.first_name} {obj.lead.last_name or ''}".strip()
        return None


# ─── Projects (B2C product bundles) ─────────────────────────────────────────
class _SpecLineSerializer(serializers.ModelSerializer):
    """A specification line — the same three columns wherever it appears."""

    class Meta:
        fields = ['id', 'item_name', 'brand', 'quantity', 'position']
        read_only_fields = ['id']


class ProjectSpecLineSerializer(_SpecLineSerializer):
    class Meta(_SpecLineSerializer.Meta):
        model = ProjectSpecLine


class QuoteSpecLineSerializer(_SpecLineSerializer):
    class Meta(_SpecLineSerializer.Meta):
        model = QuoteSpecLine


class ProjectSpecSerializer(serializers.ModelSerializer):
    lines = ProjectSpecLineSerializer(many=True, required=False)
    line_count = serializers.SerializerMethodField()
    # So the list can show "5kVA Single Phase · 12 items" without fetching each.
    quoted_count = serializers.SerializerMethodField()

    # Derived on the server so the screen and the invoice cannot disagree about
    # what a package costs. One block per price, keyed by variant.
    system_type_display = serializers.CharField(source='get_system_type_display', read_only=True)
    pricing = serializers.SerializerMethodField()

    def get_pricing(self, obj):
        return {variant: {k: str(v) for k, v in obj.figures_for(variant).items()}
                for variant, _ in PRICE_VARIANTS}

    class Meta:
        model = ProjectSpec
        fields = ['id', 'name', 'system_type', 'system_type_display', 'capacity', 'subsidy_amount',
                  'price_dcr', 'price_non_dcr', 'tax_percent', 'price_includes_tax',
                  'pricing',
                  'notes', 'is_active', 'lines',
                  'line_count', 'quoted_count', 'created_at', 'updated_at']
        read_only_fields = ['created_at', 'updated_at']

    def get_line_count(self, obj):
        return obj.lines.count()

    def get_quoted_count(self, obj):
        """How many documents name this bundle — quotations and proformas both.

        It used to count only `quotes` (proformas). That was right when they
        were the only document a project could be named on, but the retail side
        now sells through quotations, so a bundle used on five quotations and no
        proformas reported zero. Two things read this: the QUOTED ON column,
        which then showed a dash for a bundle in daily use, and the delete
        confirmation, which told the user nothing depended on it.
        """
        return obj.quotations.count() + obj.quotes.count()

    def _replace_lines(self, project, lines):
        """The whole sheet is sent each time, so it is written the same way.

        Rewriting rather than reconciling keeps the order the user arranged: a
        line moved to the top is simply a sheet whose lines now read in that
        order, and there is no id to chase.
        """
        project.lines.all().delete()
        ProjectSpecLine.objects.bulk_create(
            [ProjectSpecLine(project=project, **line) for line in lines])

    def create(self, validated_data):
        lines = validated_data.pop('lines', [])
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            validated_data['created_by'] = request.user
        project = ProjectSpec.objects.create(**validated_data)
        self._replace_lines(project, lines)
        return project

    def update(self, instance, validated_data):
        lines = validated_data.pop('lines', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        if lines is not None:
            self._replace_lines(instance, lines)
        return instance


class QuotationTemplateSerializer(serializers.ModelSerializer):
    """The uploaded artwork a system type's proposal is built on."""
    system_type_display = serializers.CharField(source='get_system_type_display',
                                                read_only=True)
    uploaded_by_name = serializers.SerializerMethodField()
    file_name = serializers.SerializerMethodField()

    class Meta:
        model = QuotationTemplate
        fields = ['id', 'system_type', 'system_type_display', 'pdf', 'file_name',
                  'uploaded_at', 'uploaded_by', 'uploaded_by_name']
        read_only_fields = ['uploaded_at', 'uploaded_by']

    def get_uploaded_by_name(self, obj):
        u = obj.uploaded_by
        return (f'{u.first_name} {u.last_name}'.strip() or u.username) if u else None

    def get_file_name(self, obj):
        return obj.pdf.name.rsplit('/', 1)[-1] if obj.pdf else ''

    def validate_pdf(self, value):
        # A template that is not a PDF fails much later, inside the renderer,
        # with a message about page counts. Better to say so at the door.
        if not (value.name or '').lower().endswith('.pdf'):
            return self.fail_pdf()
        return value

    def fail_pdf(self):
        raise serializers.ValidationError('The template must be a PDF.')


# ─── Quotations ─────────────────────────────────────────────────────────────
class QuotationSpecLineSerializer(_SpecLineSerializer):
    class Meta(_SpecLineSerializer.Meta):
        model = QuotationSpecLine


class QuotationCostSerializer(serializers.ModelSerializer):
    # Spelled out rather than left to the model's blank=False, whose message is
    # "This field may not be blank" — true, but it does not say what the field
    # is for or why anyone should care.
    remark = serializers.CharField(max_length=255, error_messages={
        'blank': 'Say what this cost is for.',
        'required': 'Say what this cost is for.',
    })

    class Meta:
        model = QuotationCost
        fields = ['id', 'remark', 'amount', 'position']
        read_only_fields = ['id']


class QuotationSerializer(serializers.ModelSerializer):
    spec_lines = QuotationSpecLineSerializer(many=True, required=False)
    costs = QuotationCostSerializer(many=True, required=False)
    lead_name = serializers.SerializerMethodField()
    project_name = serializers.CharField(source='project.name', read_only=True)
    # Every figure derived on the server, so the screen and the document cannot
    # disagree about what was offered.
    extras_total = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    subtotal = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    net_amount = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    is_order = serializers.BooleanField(read_only=True)
    subsidy_shown = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    net_effective = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    base_amount = serializers.SerializerMethodField()
    tax_amount = serializers.SerializerMethodField()
    total = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    grand_total = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    round_off = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)

    class Meta:
        model = Quotation
        fields = [
            'id', 'number', 'lead', 'lead_name', 'project', 'project_name',
            'price_variant', 'status', 'quotation_date', 'expiry_date', 'site',
            'package_amount', 'tax_percent', 'price_includes_tax',
            'discount_amount', 'discount_remark', 'subsidy_amount',
            'spec_lines', 'costs',
            'extras_total', 'subtotal', 'net_amount', 'subsidy_shown', 'net_effective',
            'base_amount', 'tax_amount',
            'total', 'grand_total', 'round_off',
            'converted_quote', 'order_converted_at', 'is_order',
            'pdf', 'notes', 'created_by', 'created_at',
        ]
        read_only_fields = ['number', 'created_by', 'converted_quote', 'pdf',
                            'order_converted_at']

    def get_lead_name(self, obj):
        if obj.lead:
            return f"{obj.lead.first_name} {obj.lead.last_name or ''}".strip()
        return None

    def validate(self, attrs):
        """Anything that moves the price has to say why.

        A discount and an extra charge are the two figures on this document that
        were not read off a price list — someone decided them — and the person
        who has to answer for them months later is rarely the person who set
        them. An unexplained ₹15,000 off is exactly the number that becomes an
        argument, so the reason is part of the figure rather than a note beside
        it.

        Written as a validator rather than a required field because it is
        conditional: a quotation with no discount needs no reason for one.
        """
        def settled(field):
            """The value after this write — sent, or what is already stored."""
            if field in attrs:
                return attrs[field]
            return getattr(self.instance, field, None)

        if Decimal(settled('discount_amount') or 0) and not str(settled('discount_remark') or '').strip():
            raise serializers.ValidationError(
                {'discount_remark': 'Say why this discount was given.'})

        # Costs arrive whole, so they are checked whole. The per-line blank rule
        # is on QuotationCostSerializer; this catches a line that carries an
        # amount with only whitespace for a reason.
        for cost in (attrs.get('costs') or []):
            if Decimal(cost.get('amount') or 0) and not str(cost.get('remark') or '').strip():
                raise serializers.ValidationError(
                    {'costs': 'Say what each additional cost is for.'})
        return attrs

    def get_base_amount(self, obj):
        return str(obj.figures['base_amount'])

    def get_tax_amount(self, obj):
        return str(obj.figures['tax_amount'])

    # ── Writing ──
    def _write_children(self, quotation, spec_lines, costs):
        """The whole of each list is sent, so it is written whole.

        Rewriting rather than reconciling keeps the order the user arranged and
        spares the client from tracking ids for rows it may have just deleted.
        """
        if spec_lines is not None:
            quotation.spec_lines.all().delete()
            QuotationSpecLine.objects.bulk_create(
                [QuotationSpecLine(quotation=quotation, **l) for l in spec_lines])
        if costs is not None:
            quotation.costs.all().delete()
            QuotationCost.objects.bulk_create(
                [QuotationCost(quotation=quotation, **c) for c in costs])

    def create(self, validated_data):
        spec_lines = validated_data.pop('spec_lines', None)
        costs = validated_data.pop('costs', None)
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            validated_data['created_by'] = request.user
        quotation = Quotation.objects.create(**validated_data)
        # A project fills the specification and the price; anything the client
        # sent explicitly then overwrites that, because it is what the user has
        # just typed on screen.
        if quotation.project_id:
            quotation.fill_from_project()
        self._write_children(quotation, spec_lines, costs)
        return quotation

    def update(self, instance, validated_data):
        if instance.is_order:
            # A converted order is the record of what the customer paid against.
            # Editing it would change the agreement after the money arrived,
            # and the document has already been sent.
            raise serializers.ValidationError(
                {'detail': f'{instance.number} became an order when payment was '
                           f'received and can no longer be edited.'})
        spec_lines = validated_data.pop('spec_lines', None)
        costs = validated_data.pop('costs', None)
        # Only a *change* re-fills from the project. Re-saving with the same
        # project and the same variant must not throw away a negotiated price or
        # an edited specification.
        refill = (
            ('project' in validated_data and validated_data['project'] != instance.project)
            or ('price_variant' in validated_data
                and validated_data['price_variant'] != instance.price_variant)
        )
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        if refill and instance.project_id:
            instance.fill_from_project()
        self._write_children(instance, spec_lines, costs)
        return instance


class QuoteSerializer(_TaxedDocSerializer):
    item_model = QuoteItem
    parent_fk = 'quote'
    items = QuoteItemSerializer(many=True, required=False)
    spec_lines = QuoteSpecLineSerializer(many=True, required=False)
    project_name = serializers.CharField(source='project.name', read_only=True)

    class Meta:
        model = Quote
        fields = [
            'id', 'number', 'lead', 'lead_name', 'status', 'quote_date', 'expiry_date',
            'site', 'ship_to_state', 'ship_to_gstin',
            'efc_ref_no', 'discount_percent', 'tax_percent', 'notes', 'pdf',
            'created_by', 'created_at',
            'project', 'project_name', 'price_variant', 'spec_lines',
            'items', 'subtotal', 'discount_amount', 'taxable_amount', 'tax_amount', 'total', 'grand_total', 'round_off',
        ]
        read_only_fields = ['number', 'created_by', 'pdf']

    def _write_spec(self, quote, spec_lines, project_sent, variant_sent=False):
        """Settle the specification and the price on this proforma.

        Lines sent by the client win: they are what the user has just edited on
        screen. Otherwise, naming a project copies that project's sheet and
        price across — which is what picking one from the dropdown is meant to
        do. A quote whose project is unchanged keeps whatever sheet it already
        had, edits included.

        Switching between DCR and non-DCR on the same project reprices only:
        the specification is the same system either way, so re-copying the sheet
        would throw away edits for no reason.
        """
        if spec_lines is not None:
            quote.spec_lines.all().delete()
            QuoteSpecLine.objects.bulk_create(
                [QuoteSpecLine(quote=quote, **line) for line in spec_lines])
        elif project_sent and quote.project_id:
            quote.project.copy_onto(quote)
            return
        if variant_sent and not project_sent and quote.project_id:
            quote.project.price_onto(quote)

    def create(self, validated_data):
        spec_lines = validated_data.pop('spec_lines', None)
        project_sent = 'project' in validated_data
        quote = super().create(validated_data)
        self._write_spec(quote, spec_lines, project_sent)
        return quote

    def update(self, instance, validated_data):
        spec_lines = validated_data.pop('spec_lines', None)
        # Only a *changed* project re-copies the sheet, and only a *changed*
        # variant reprices. Re-saving a quote with the same values must not
        # throw away edits made to its copy or a price agreed by hand.
        project_sent = ('project' in validated_data
                        and validated_data['project'] != instance.project)
        variant_sent = ('price_variant' in validated_data
                        and validated_data['price_variant'] != instance.price_variant)
        quote = super().update(instance, validated_data)
        self._write_spec(quote, spec_lines, project_sent, variant_sent)
        return quote


class SalesOrderSerializer(_TaxedDocSerializer):
    item_model = SalesOrderItem
    parent_fk = 'sales_order'
    items = SalesOrderItemSerializer(many=True, required=False)

    class Meta:
        model = SalesOrder
        fields = [
            'id', 'number', 'lead', 'lead_name', 'source_quote', 'status', 'order_date',
            'discount_percent', 'tax_percent', 'notes', 'stock_committed', 'created_by', 'created_at',
            'items', 'subtotal', 'discount_amount', 'taxable_amount', 'tax_amount', 'total', 'grand_total', 'round_off',
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
                     StockQuote, StockQuoteItem,
                     StockPurchaseOrder, StockPurchaseOrderItem)


class StockItemSerializer(serializers.ModelSerializer):
    """The item master row plus its derived ledger (never stored, always summed
    from the movements — see StockItem.closing_stock)."""
    received = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    dispatched = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    # Promised on live proforma invoices, and the shelf figure before that
    # promise is taken off it. `closing_stock` is what is left to sell.
    reserved = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    physical_stock = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    closing_stock = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    stock_value = serializers.DecimalField(max_digits=16, decimal_places=2, read_only=True)
    status = serializers.SerializerMethodField()

    class Meta:
        model = StockItem
        fields = ['id', 'code', 'category', 'brand', 'model_name', 'unit', 'hsn',
                  'opening_stock', 'unit_cost', 'reorder_level', 'location', 'is_active',
                  'received', 'dispatched', 'reserved', 'physical_stock',
                  'closing_stock', 'stock_value', 'status',
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
    item_hsn = serializers.CharField(source='item.hsn', read_only=True, default='')
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
                  'item_label', 'item_hsn', 'quantity', 'rate', 'amount', 'notes',
                  'created_by', 'created_by_name', 'created_at']
        read_only_fields = ['created_by', 'created_at']


class StockDispatchSerializer(_MovementSerializer):
    customer_name = serializers.CharField(source='customer.name', read_only=True, default=None)
    discount_amount = serializers.DecimalField(max_digits=16, decimal_places=2, read_only=True)
    taxable_amount = serializers.DecimalField(max_digits=16, decimal_places=2, read_only=True)
    tax_amount = serializers.DecimalField(max_digits=16, decimal_places=2, read_only=True)
    total = serializers.DecimalField(max_digits=16, decimal_places=2, read_only=True)
    # The payment that released this delivery, joined on by invoice number in
    # StockDispatchViewSet.get_queryset. Absent on a row written through the
    # plain row endpoint rather than the gated dispatch action, which is what
    # `payment_verified` is for.
    payment_verified = serializers.BooleanField(read_only=True, default=False)
    payment_amount = serializers.DecimalField(max_digits=16, decimal_places=2,
                                              read_only=True, default=None)
    payment_mode = serializers.CharField(read_only=True, default=None)
    payment_reference = serializers.CharField(read_only=True, default=None)
    payment_paid_on = serializers.DateField(read_only=True, default=None)
    # Where the delivery stands: pending until the invoice is settled and the
    # goods released. A pending row holds its stock rather than having moved it.
    status_label = serializers.CharField(source='get_status_display', read_only=True)
    amount_received = serializers.SerializerMethodField()
    balance = serializers.SerializerMethodField()
    fully_paid = serializers.SerializerMethodField()
    # What the delivery is billed at once rounded, and the adjustment that got
    # it there — the invoice prints both.
    invoice_total = serializers.SerializerMethodField()
    round_off = serializers.SerializerMethodField()

    def _received(self, obj):
        from .models import DispatchPayment
        if not obj.invoice_no:
            return Decimal('0')
        if not hasattr(self, '_received_cache'):
            self._received_cache = {}
        if obj.invoice_no not in self._received_cache:
            self._received_cache[obj.invoice_no] = DispatchPayment.received_for(
                invoice_no=obj.invoice_no)
        return self._received_cache[obj.invoice_no]

    def _exact_total(self, obj):
        """The whole delivery's worth, not this row's — the customer pays for
        the delivery, and every row of it reports the same position."""
        if not obj.invoice_no:
            return obj.total or Decimal('0')
        if not hasattr(self, '_total_cache'):
            self._total_cache = {}
        if obj.invoice_no not in self._total_cache:
            rows = StockDispatch.objects.filter(invoice_no=obj.invoice_no)
            # To paise, as `settlement` takes it, so this list and the payment
            # screen are rounding the same figure.
            self._total_cache[obj.invoice_no] = sum(
                (r.total or Decimal('0') for r in rows), Decimal('0')
            ).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        return self._total_cache[obj.invoice_no]

    def _invoice_total(self, obj):
        """What the customer owes: the delivery total, rounded to the rupee.

        Rounded on the sum of the whole delivery rather than line by line —
        rounding each row and adding them up lands somewhere else. The same
        figure `payment_state` reconciles against, so this list and the
        verification dialog cannot disagree about whether an invoice is settled.
        """
        from .models import round_off_for
        return round_off_for(self._exact_total(obj))[0]

    def get_invoice_total(self, obj):
        return str(self._invoice_total(obj).quantize(Decimal('0.01')))

    def get_round_off(self, obj):
        from .models import round_off_for
        return str(round_off_for(self._exact_total(obj))[1].quantize(Decimal('0.01')))

    def _settles_at(self, obj):
        """What clears this delivery: the rounded bill or the exact arithmetic,
        whichever is lower. The same rule `payment_state` applies, so this list
        and the verification dialog cannot disagree about whether it is paid."""
        return min(self._invoice_total(obj), self._exact_total(obj))

    def get_amount_received(self, obj):
        return str(self._received(obj).quantize(Decimal('0.01')))

    def get_balance(self, obj):
        if self.get_fully_paid(obj):
            return '0.00'
        left = self._invoice_total(obj) - self._received(obj)
        return str((left if left > 0 else Decimal('0')).quantize(Decimal('0.01')))

    def get_fully_paid(self, obj):
        total = self._invoice_total(obj)
        return bool(total > 0 and self._received(obj) >= self._settles_at(obj))

    # Fields that describe the invoice rather than the line. A delivery is
    # several rows under one number, and the printed invoice reads its header
    # off whichever row was opened — so editing one row's customer, date, site
    # or tax has to edit all of them, or the invoice depends on which line you
    # clicked and its rows are taxed at different rates.
    INVOICE_FIELDS = ('date', 'customer', 'site', 'tax_percent', 'discount_percent')

    def validate_invoice_no(self, value):
        value = (value or '').strip()
        current = (self.instance.invoice_no or '') if self.instance is not None else None
        if current is None or value == current:
            return value
        # Payments are filed under the number, and the rows of a delivery are
        # found by it: blanking it orphaned both.
        if not value:
            raise serializers.ValidationError(
                'An invoice needs its number — its payments are filed under it.')
        from .models import document_number_in_use
        if document_number_in_use('IN', value):
            raise serializers.ValidationError(
                f'{value} is already in use. Renaming onto another invoice would merge '
                f'two deliveries.')
        return value

    def update(self, instance, validated_data):
        old_no = instance.invoice_no
        with transaction.atomic():
            target = validated_data.get('invoice_no', old_no)
            if old_no and target and target != old_no:
                # Payments left under the new number by an earlier delivery step
                # aside first — once this row carries the number they would be
                # swept in below with this delivery's own.
                from .models import park_stranded_payments
                park_stranded_payments(target)
            instance = super().update(instance, validated_data)
            if not old_no:
                return instance
            siblings = StockDispatch.objects.filter(invoice_no=old_no).exclude(pk=instance.pk)
            shared = {f: validated_data[f] for f in self.INVOICE_FIELDS if f in validated_data}
            new_no = instance.invoice_no
            if new_no != old_no:
                # The whole delivery is renamed, payments with it — a rename of
                # one row would split the invoice in two.
                from .models import DispatchPayment, absorb_document_number
                shared['invoice_no'] = new_no
                DispatchPayment.objects.filter(invoice_no=old_no).update(invoice_no=new_no)
                absorb_document_number('IN', new_no, on=instance.date)
            if shared:
                siblings.update(**shared)
        return instance

    class Meta:
        model = StockDispatch
        fields = ['id', 'invoice_no', 'date', 'customer', 'customer_name', 'item', 'item_code',
                  'item_label', 'item_hsn', 'quantity', 'rate', 'amount',
                  'discount_percent', 'discount_amount', 'taxable_amount',
                  'tax_percent', 'tax_amount', 'total',
                  'serial_numbers', 'site', 'notes', 'pdf',
                  'payment_verified', 'payment_amount', 'payment_mode',
                  'payment_reference', 'payment_paid_on',
                  'status', 'status_label', 'released_at', 'invoice_total', 'round_off',
                  'amount_received', 'balance', 'fully_paid',
                  'created_by', 'created_by_name', 'created_at']
        # Releasing is its own action, with the invoice settled first — it must
        # not be reachable by PATCHing a row's status.
        read_only_fields = ['created_by', 'created_at', 'pdf', 'status', 'released_at']


class StockQuoteItemSerializer(serializers.ModelSerializer):
    item_code = serializers.CharField(source='item.code', read_only=True)
    item_label = serializers.SerializerMethodField()
    line_total = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)

    item_unit = serializers.CharField(source='item.unit', read_only=True)
    item_hsn = serializers.CharField(source='item.hsn', read_only=True)

    class Meta:
        model = StockQuoteItem
        fields = ['id', 'item', 'item_code', 'item_label', 'item_unit', 'item_hsn',
                  'description', 'quantity', 'unit_price', 'line_total']

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
            'site', 'ship_to_state', 'ship_to_gstin',
            'efc_ref_no', 'discount_percent', 'tax_percent', 'notes', 'pdf',
            'created_by', 'created_by_name', 'created_at', 'converted_at',
            'items', 'subtotal', 'discount_amount', 'taxable_amount', 'tax_amount', 'total', 'grand_total', 'round_off',
        ]
        # Status reaches 'converted' only through the convert action, which is what
        # writes the dispatch rows — setting it by hand would skip the stock move.
        read_only_fields = ['number', 'created_by', 'converted_at', 'pdf']

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


# ─── Purchase orders (wholesale) ────────────────────────────────────────────
class StockPurchaseOrderItemSerializer(serializers.ModelSerializer):
    item_code = serializers.CharField(source='item.code', read_only=True, default=None)
    item_label = serializers.SerializerMethodField()
    base_amount = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)

    class Meta:
        model = StockPurchaseOrderItem
        fields = ['id', 'item', 'item_code', 'item_label', 'type_of_spare', 'description',
                  'part_code', 'unit_price', 'quantity', 'base_amount']

    def get_item_label(self, obj):
        it = obj.item
        if not it:
            return None
        return f"{it.brand} {it.model_name}".strip() or it.code


class StockPurchaseOrderSerializer(_DocSerializer):
    item_model = StockPurchaseOrderItem
    parent_fk = 'purchase_order'

    items = StockPurchaseOrderItemSerializer(many=True, required=False)
    supplier_name = serializers.CharField(source='supplier.name', read_only=True, default=None)
    created_by_name = serializers.SerializerMethodField()
    goods_amount = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    taxable_amount = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    tax_amount = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    total = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)

    class Meta:
        model = StockPurchaseOrder
        fields = [
            'id', 'number', 'fy', 'po_date', 'supplier', 'supplier_name', 'status',
            'ship_to_address', 'ship_to_phone', 'transportation', 'tax_percent', 'tax_label',
            'terms_taxes', 'terms_delivery', 'notes', 'pdf',
            'created_by', 'created_by_name', 'created_at',
            'items', 'goods_amount', 'taxable_amount', 'tax_amount', 'total',
        ]
        # The number is issued by the series, not chosen by the caller.
        read_only_fields = ['number', 'fy', 'created_by', 'created_at', 'pdf']

    def get_created_by_name(self, obj):
        u = obj.created_by
        if not u:
            return None
        return f"{u.first_name} {u.last_name}".strip() or u.username
