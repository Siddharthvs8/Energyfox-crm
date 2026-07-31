from django.conf import settings
from django.core.mail import EmailMessage
from django.db.models import Q
from rest_framework import viewsets, permissions, status, parsers
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import Vendor, PurchaseOrder, Quote, SalesOrder, SalesOrderItem
from .serializers import (
    VendorSerializer, PurchaseOrderSerializer, QuoteSerializer, SalesOrderSerializer,
)


class VendorViewSet(viewsets.ModelViewSet):
    serializer_class = VendorSerializer
    permission_classes = [permissions.IsAuthenticated]
    queryset = Vendor.objects.all()

    def get_queryset(self):
        qs = Vendor.objects.all().order_by('name')
        search = self.request.query_params.get('search')
        if search:
            qs = qs.filter(
                Q(name__icontains=search) | Q(contact_person__icontains=search) | Q(email__icontains=search)
            )
        return qs


class PurchaseOrderViewSet(viewsets.ModelViewSet):
    serializer_class = PurchaseOrderSerializer
    permission_classes = [permissions.IsAuthenticated]
    queryset = PurchaseOrder.objects.all()

    def get_queryset(self):
        qs = (PurchaseOrder.objects.all()
              .select_related('vendor', 'created_by')
              .prefetch_related('items', 'items__product')
              .order_by('-created_at'))
        status_f = self.request.query_params.get('status')
        if status_f and status_f != 'all':
            qs = qs.filter(status=status_f)
        return qs

    @action(detail=True, methods=['post'], url_path='email')
    def email(self, request, pk=None):
        """Email this purchase order to the vendor (optionally with a PDF attachment)."""
        po = self.get_object()
        to_raw = request.data.get('to') or (po.vendor.email if po.vendor else '')
        recipients = [a.strip() for a in str(to_raw).split(',') if a.strip()]
        if not recipients:
            return Response(
                {'error': 'No recipient email. Add an email to the vendor, or pass "to".'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        subject = request.data.get('subject') or f"Purchase Order {po.number}"
        vendor_name = po.vendor.name if po.vendor else 'Vendor'
        body = request.data.get('message') or (
            f"Dear {vendor_name},\n\n"
            f"Please find attached our Purchase Order {po.number}"
            f"{' dated ' + str(po.order_date) if po.order_date else ''}.\n\n"
            f"Order total: Rs. {po.total}\n\n"
            f"Regards,\nEnergyFox"
        )

        # Sent through the CRM's configured email account (Settings → Email
        # Integration) and recorded in the email outbox.
        from messaging.email import send_and_log
        attachments = []
        pdf = request.FILES.get('pdf')
        if pdf:
            attachments.append((f"{po.number or 'purchase-order'}.pdf", pdf.read(), 'application/pdf'))

        log = send_and_log(to=recipients, subject=subject, body=body, kind='purchase_order',
                           attachments=attachments,
                           created_by=request.user if request.user.is_authenticated else None)
        if log.status != 'sent':
            return Response({'error': f'Email failed: {log.error}'}, status=status.HTTP_502_BAD_GATEWAY)

        return Response({'status': 'sent', 'to': recipients})


BLANK_PARTY = {'name': '', 'gstin': '', 'contact_person': '', 'contact_number': '',
               'address': '', 'state': '', 'email': ''}


def safe_doc_name(number):
    """Document numbers contain slashes (EF/26-27/PI009); filenames can't."""
    return (number or 'proforma').replace('/', '-')


class ProformaDocumentMixin:
    """Serves a quote's proforma invoice and sends it to the customer.

    Retail and wholesale price off different catalogues and address different
    kinds of customer; those two differences are the hooks below. Everything the
    printed document does with them — the GST split, the totals, the wording,
    storing the PDF and sending it — is shared, so the two modules state the same
    figures and can't drift apart.
    """

    def proforma_party(self, quote):
        """Who the invoice is addressed to: name, gstin, address, state, contacts."""
        raise NotImplementedError

    def proforma_line(self, item):
        """(particulars, hsn, unit) for one line of the printed table."""
        raise NotImplementedError

    @action(detail=True, methods=['get'])
    def proforma(self, request, pk=None):
        """Everything the printed proforma invoice needs, in the order the
        document lays it out: company header, both address blocks, the line
        table, the HSN/GST summary, and the total in words.

        Assembled here rather than in the client so the printed figures and the
        stored ones can never disagree.
        """
        from leads.receipts import amount_in_words
        from organization.utils import get_org_settings
        org = get_org_settings()
        quote = self.get_object()
        party = self.proforma_party(quote)

        def url(f):
            return request.build_absolute_uri(f.url) if f else None

        def money(v):
            return str(Decimal(v or 0).quantize(Decimal('0.01')))

        lines, hsn_rows = [], {}
        for n, li in enumerate(quote.items.all(), start=1):
            taxable = li.line_total or Decimal('0')
            rate = quote.tax_percent or Decimal('0')
            tax = (taxable * rate) / Decimal('100')
            label, hsn, unit = self.proforma_line(li)
            lines.append({
                'sl_no': n,
                'particulars': label,
                'hsn': hsn,
                'qty': str(li.quantity or 0),
                'unit': unit,
                'taxable': money(taxable),
                'gst_rate': str(rate),
                'tax': money(tax),
                'total': money(taxable + tax),
            })
            # The HSN summary groups lines and splits GST evenly into CGST/SGST.
            row = hsn_rows.setdefault(hsn or '-', {
                'hsn': hsn or '-', 'rate': str(rate),
                'taxable': Decimal('0'), 'cgst': Decimal('0'), 'sgst': Decimal('0'),
            })
            row['taxable'] += taxable
            row['cgst'] += tax / 2
            row['sgst'] += tax / 2

        grand = quote.total or Decimal('0')
        rounded = grand.quantize(Decimal('1'))

        return Response({
            'company': {
                'name': org.warranty_company_name,
                'address': org.receipt_address,
                'phone': org.receipt_phone,
                'email': org.receipt_email,
                'gst': org.warranty_gst,
                'cin': org.warranty_cin,
                # The PAN is the middle ten characters of the GSTIN.
                'pan': (org.warranty_gst or '')[2:12],
                'logo': url(org.logo),
                'signature': url(org.warranty_signature),
                'seal': url(org.warranty_seal),
            },
            'bank': {
                'name': org.receipt_bank_name,
                'account_name': org.warranty_company_name,
                'ifsc': org.receipt_bank_ifsc,
                'account_number': org.receipt_bank_account,
                'branch': org.receipt_bank_branch,
            },
            'invoice': {
                'number': quote.number,
                'date': quote.quote_date.isoformat() if quote.quote_date else None,
                'efc_ref_no': quote.efc_ref_no,
                'status': quote.status,
            },
            'customer': party,
            'ship_to': {**party, 'address': quote.site or party['address']},
            'lines': lines,
            'hsn_summary': [{
                'hsn': r['hsn'], 'rate': r['rate'],
                'taxable': money(r['taxable']), 'cgst': money(r['cgst']), 'sgst': money(r['sgst']),
            } for r in hsn_rows.values()],
            'totals': {
                'taxable': money(quote.taxable_amount),
                'discount': money(quote.discount_amount),
                'tax': money(quote.tax_amount),
                'invoice_value': money(grand),
                'round_off': money(rounded - grand),
                'grand_total': money(rounded),
                'in_words': amount_in_words(rounded),
            },
            'terms': ['This Proforma Invoice is valid upto 15 days'],
        })

    @action(detail=True, methods=['post'], parser_classes=[parsers.MultiPartParser, parsers.FormParser])
    def send(self, request, pk=None):
        """Store the generated PDF and send it to the customer.

        The client renders the document (it owns the template) and posts it back;
        the file is kept on the record so email can attach it and WhatsApp can
        link to it — the Cloud API fetches documents by URL rather than upload.
        """
        quote = self.get_object()
        party = self.proforma_party(quote)
        pdf = request.FILES.get('pdf')
        if pdf:
            quote.pdf.save(f"{safe_doc_name(quote.number)}.pdf", pdf, save=True)
        if not quote.pdf:
            return Response({'error': 'No document to send. Generate the PDF first.'},
                            status=status.HTTP_400_BAD_REQUEST)

        channels = [c.strip() for c in str(request.data.get('channels', 'email')).split(',') if c.strip()]
        results, failures = {}, []

        if 'email' in channels:
            raw = request.data.get('email') or party.get('email') or ''
            recipients = [a.strip() for a in str(raw).split(',') if a.strip()]
            if not recipients:
                failures.append('No email address given for this customer.')
            else:
                from messaging.email import send_and_log
                quote.pdf.open('rb')
                data = quote.pdf.read()
                quote.pdf.close()
                who = party['name'] or 'Customer'
                log = send_and_log(
                    to=recipients,
                    subject=f"Proforma Invoice {quote.number}",
                    body=(f"Dear {who},\n\nPlease find attached Proforma Invoice "
                          f"{quote.number} for Rs. {quote.total}.\n\nRegards,\nEnergyFox"),
                    kind='proforma_invoice',
                    attachments=[(f"{safe_doc_name(quote.number)}.pdf", data, 'application/pdf')],
                    created_by=request.user if request.user.is_authenticated else None,
                )
                results['email'] = log.status
                if log.status != 'sent':
                    failures.append(f"Email failed: {log.error}")

        if 'whatsapp' in channels:
            number = request.data.get('phone') or party.get('contact_number') or ''
            if not number:
                failures.append('No WhatsApp number given for this customer.')
            else:
                from messaging import whatsapp
                try:
                    whatsapp.send_document(
                        to=number,
                        link=request.build_absolute_uri(quote.pdf.url),
                        filename=f"{safe_doc_name(quote.number)}.pdf",
                        caption=f"Proforma Invoice {quote.number}",
                    )
                    results['whatsapp'] = 'sent'
                except Exception as exc:                     # surfaced to the user
                    failures.append(f"WhatsApp failed: {exc}")

        # Raising the document to the customer moves it out of draft.
        if quote.status == 'draft' and results:
            quote.status = 'sent'
            quote.save(update_fields=['status', 'updated_at'])

        if failures and not results:
            return Response({'error': ' '.join(failures)}, status=status.HTTP_502_BAD_GATEWAY)
        return Response({'sent': results, 'warnings': failures,
                         'pdf': request.build_absolute_uri(quote.pdf.url)})


class QuoteViewSet(ProformaDocumentMixin, viewsets.ModelViewSet):
    serializer_class = QuoteSerializer
    permission_classes = [permissions.IsAuthenticated]
    queryset = Quote.objects.all()

    def proforma_party(self, quote):
        """A retail invoice is addressed to the lead behind the quote."""
        lead = quote.lead
        if not lead:
            return dict(BLANK_PARTY)
        name = f"{lead.first_name or ''} {lead.last_name or ''}".strip()
        return {
            'name': name or (lead.email or ''),
            'gstin': '',                    # retail customers are usually unregistered
            'contact_person': name,
            'contact_number': lead.phone or '',
            'address': lead.installation_location or lead.company or '',
            'state': '',
            'email': lead.email or '',
        }

    def proforma_line(self, item):
        p = item.product
        return (item.description or (p.name if p else ''),
                p.hsn if p else '', p.unit if p else '')

    def get_queryset(self):
        qs = (Quote.objects.all()
              .select_related('lead', 'created_by')
              .prefetch_related('items', 'items__product')
              .order_by('-created_at'))
        status_f = self.request.query_params.get('status')
        if status_f and status_f != 'all':
            qs = qs.filter(status=status_f)
        return qs

    @action(detail=True, methods=['post'])
    def convert(self, request, pk=None):
        """Convert this quote into a draft Sales Order, copying line items."""
        quote = self.get_object()
        so = SalesOrder.objects.create(
            lead=quote.lead,
            source_quote=quote,
            discount_percent=quote.discount_percent,
            tax_percent=quote.tax_percent,
            notes=quote.notes,
            status='draft',
            created_by=request.user if request.user.is_authenticated else None,
        )
        for it in quote.items.all():
            SalesOrderItem.objects.create(
                sales_order=so, product=it.product, description=it.description,
                quantity=it.quantity, unit_price=it.unit_price,
            )
        quote.status = 'converted'
        quote.save(update_fields=['status'])
        return Response(SalesOrderSerializer(so, context={'request': request}).data, status=201)


class SalesOrderViewSet(viewsets.ModelViewSet):
    serializer_class = SalesOrderSerializer
    permission_classes = [permissions.IsAuthenticated]
    queryset = SalesOrder.objects.all()

    def get_queryset(self):
        qs = (SalesOrder.objects.all()
              .select_related('lead', 'created_by', 'source_quote')
              .prefetch_related('items', 'items__product')
              .order_by('-created_at'))
        status_f = self.request.query_params.get('status')
        if status_f and status_f != 'all':
            qs = qs.filter(status=status_f)
        return qs


# ─── Stock register ─────────────────────────────────────────────────────────
from decimal import Decimal  # noqa: E402
from django.db.models import Sum, OuterRef, Subquery, DecimalField, Value, F  # noqa: E402
from django.db.models.functions import Coalesce  # noqa: E402
from django.utils import timezone  # noqa: E402
from rest_framework.views import APIView  # noqa: E402

from .models import (StockItem, StockCustomer, GoodsReceipt, StockDispatch,  # noqa: E402
                     StockQuote)
from .serializers import (  # noqa: E402
    StockItemSerializer, StockCustomerSerializer,
    GoodsReceiptSerializer, StockDispatchSerializer, StockQuoteSerializer,
)

_MONEY = DecimalField(max_digits=16, decimal_places=2)


class IsStockKeeper(permissions.BasePermission):
    """The warehouse desk: admins, general managers, purchase staff, and the
    B2B roles (store manager / store keeper / accounts B2B) whose whole job is
    this module."""
    message = 'You do not have access to the stock register.'

    def has_permission(self, request, view):
        u = request.user
        if not u or not u.is_authenticated:
            return False
        return bool(u.is_staff or getattr(u, 'is_general_manager', False)
                    or getattr(u, 'role', '') == 'purchase_staff'
                    or getattr(u, 'is_b2b_only', False))


def _movement_total(model, field='quantity'):
    """Per-item Sum as a subquery — two plain annotations across two reverse FKs
    would multiply each other's rows and inflate both totals."""
    return Coalesce(
        Subquery(
            model.objects.filter(item=OuterRef('pk')).values('item')
            .annotate(t=Sum(field)).values('t')[:1],
            output_field=_MONEY,
        ),
        Value(Decimal('0')), output_field=_MONEY,
    )


def stock_items_with_ledger():
    """Item master annotated with its received/dispatched totals."""
    return StockItem.objects.annotate(
        received_qty=_movement_total(GoodsReceipt),
        dispatched_qty=_movement_total(StockDispatch),
    )


class StockItemViewSet(viewsets.ModelViewSet):
    serializer_class = StockItemSerializer
    permission_classes = [permissions.IsAuthenticated, IsStockKeeper]

    def get_queryset(self):
        qs = stock_items_with_ledger()
        search = self.request.query_params.get('search')
        if search:
            qs = qs.filter(
                Q(code__icontains=search) | Q(brand__icontains=search)
                | Q(model_name__icontains=search) | Q(category__icontains=search)
            )
        category = self.request.query_params.get('category')
        if category and category != 'all':
            qs = qs.filter(category=category)
        return qs.order_by('code')

    def destroy(self, request, *args, **kwargs):
        """Items with movement history stay put — deleting one would erase the
        receipts and dispatches that explain the stock on hand."""
        item = self.get_object()
        if item.receipts.exists() or item.dispatches.exists():
            return Response(
                {'error': f'{item.code} has receipts or dispatches logged against it. '
                          'Delete those movements first, or mark the item inactive.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return super().destroy(request, *args, **kwargs)


class StockCustomerViewSet(viewsets.ModelViewSet):
    serializer_class = StockCustomerSerializer
    permission_classes = [permissions.IsAuthenticated, IsStockKeeper]
    queryset = StockCustomer.objects.all()

    def get_queryset(self):
        qs = StockCustomer.objects.all().order_by('name')
        search = self.request.query_params.get('search')
        if search:
            qs = qs.filter(Q(name__icontains=search) | Q(contact_person__icontains=search))
        return qs


class _MovementViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated, IsStockKeeper]

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user if self.request.user.is_authenticated else None)


class GoodsReceiptViewSet(_MovementViewSet):
    serializer_class = GoodsReceiptSerializer
    queryset = GoodsReceipt.objects.all()

    def get_queryset(self):
        return GoodsReceipt.objects.select_related('item', 'supplier', 'created_by')


class StockDispatchViewSet(_MovementViewSet):
    serializer_class = StockDispatchSerializer
    queryset = StockDispatch.objects.all()

    def get_queryset(self):
        return StockDispatch.objects.select_related('item', 'customer', 'created_by')


class StockSummaryView(APIView):
    """Dashboard figures for the stock register: total value, reorder alerts,
    this month's movement, a six-month series and the quote pipeline — the same
    shape the retail inventory dashboard reports, so the two screens match."""
    permission_classes = [permissions.IsAuthenticated, IsStockKeeper]
    MONTHS = 6

    def get(self, request):
        items = list(stock_items_with_ledger())

        total_value = sum((i.stock_value for i in items), Decimal('0'))
        low = [i for i in items if i.needs_reorder]

        by_category = {}
        for i in items:
            by_category[i.category] = by_category.get(i.category, Decimal('0')) + i.stock_value

        today = timezone.localdate()
        month_start = today.replace(day=1)

        def movement_value(model, **filters):
            """Money moved. For dispatches that is the invoiced figure, tax
            included; goods receipts carry no tax field."""
            line = F('quantity') * F('rate')
            if model is StockDispatch:
                line = line * (Value(Decimal('1')) + F('tax_percent') / Value(Decimal('100')))
            return model.objects.filter(**filters).aggregate(
                t=Coalesce(Sum(line, output_field=_MONEY),
                           Value(Decimal('0')), output_field=_MONEY))['t']

        month_in = movement_value(GoodsReceipt, date__gte=month_start)
        month_out = movement_value(StockDispatch, date__gte=month_start)

        # Six-month purchases-vs-sales series, matching the retail dashboard's
        # chart. Walk the months so an empty month still gets a bar.
        start_month = month_start
        for _ in range(self.MONTHS - 1):
            start_month = (start_month - timezone.timedelta(days=1)).replace(day=1)

        monthly = []
        cursor = start_month
        while cursor <= today:
            nxt = (cursor.replace(day=28) + timezone.timedelta(days=4)).replace(day=1)
            monthly.append({
                'name': cursor.strftime('%b'),
                'purchases': movement_value(GoodsReceipt, date__gte=cursor, date__lt=nxt),
                'sales': movement_value(StockDispatch, date__gte=cursor, date__lt=nxt),
            })
            cursor = nxt

        # Quote pipeline. Totals come from the model's own `total` property, since
        # discount and tax live on the header — see InventoryDashboardView.
        quotes = list(StockQuote.objects.prefetch_related('items'))
        quote_status = {}
        for q in quotes:
            quote_status[q.status] = quote_status.get(q.status, 0) + 1
        open_quote_value = sum((q.total or Decimal('0')) for q in quotes
                               if q.status in {'draft', 'sent', 'accepted'})

        return Response({
            'sku_count': len(items),
            'total_value': total_value,
            'reorder_count': len(low),
            'month_purchases': month_in,
            'month_sales': month_out,
            'monthly': monthly,
            'receipt_count': GoodsReceipt.objects.count(),
            'dispatch_count': StockDispatch.objects.count(),
            'supplier_count': Vendor.objects.count(),
            'customer_count': StockCustomer.objects.count(),
            'quote_count': len(quotes),
            'quote_status': quote_status,
            'open_quote_value': open_quote_value,
            'by_category': [{'name': name, 'value': value} for name, value in sorted(by_category.items())],
            'reorder_alerts': [{
                'id': i.id, 'code': i.code, 'brand': i.brand, 'model_name': i.model_name,
                'unit': i.unit, 'closing_stock': i.closing_stock, 'reorder_level': i.reorder_level,
            } for i in low],
            'stock_levels': [{
                'id': i.id, 'code': i.code, 'unit': i.unit,
                'closing_stock': i.closing_stock, 'reorder_level': i.reorder_level,
                'status': 'REORDER' if i.needs_reorder else 'OK',
            } for i in items],
        })


# ─── Inventory dashboard (retail side: products + sales documents) ───────────
class IsInventoryViewer(permissions.BasePermission):
    """Same audience as the Inventory module in the sidebar."""
    message = 'You do not have access to the inventory dashboard.'

    def has_permission(self, request, view):
        u = request.user
        if not u or not u.is_authenticated:
            return False
        granted = u.can('inventory') if hasattr(u, 'can') else None
        if granted is not None:
            return granted
        return bool(u.is_staff or getattr(u, 'is_general_manager', False))


class InventoryDashboardView(APIView):
    """Overview of the retail inventory module: product stock plus the quote,
    sales-order and purchase-order pipelines.

    Document totals come from each model's own `total` property rather than a SQL
    sum, because discount and tax live on the header while the line values live on
    the items — reimplementing that in SQL would be a second source of truth. The
    query set is bounded to the reporting window to keep that affordable.
    """
    permission_classes = [permissions.IsAuthenticated, IsInventoryViewer]
    MONTHS = 6

    def get(self, request):
        from leads.models import Product

        today = timezone.localdate()
        # First day of the month, MONTHS-1 months back.
        start_month = today.replace(day=1)
        for _ in range(self.MONTHS - 1):
            start_month = (start_month - timezone.timedelta(days=1)).replace(day=1)

        # ── Products / stock ──
        products = list(Product.objects.all())
        stock_value = sum((Decimal(p.stock_quantity or 0) * (p.cost_price or Decimal('0'))
                           for p in products), Decimal('0'))
        low = [p for p in products if p.low_stock]

        def doc_date(doc, field):
            return getattr(doc, field, None) or timezone.localtime(doc.created_at).date()

        def load(model, date_field):
            return list(model.objects.prefetch_related('items').all()), date_field

        quotes, q_field = load(Quote, 'quote_date')
        orders, so_field = load(SalesOrder, 'order_date')
        pos, po_field = load(PurchaseOrder, 'order_date')

        def status_counts(rows):
            out = {}
            for r in rows:
                out[r.status] = out.get(r.status, 0) + 1
            return out

        def month_key(d):
            return f"{d.year}-{d.month:02d}"

        # Six-month value series, purchases vs sales.
        series = {}
        cursor = start_month
        while cursor <= today:
            series[month_key(cursor)] = {
                'name': cursor.strftime('%b'), 'purchases': Decimal('0'), 'sales': Decimal('0'),
            }
            cursor = (cursor.replace(day=28) + timezone.timedelta(days=4)).replace(day=1)

        for rows, field, bucket in ((pos, po_field, 'purchases'), (orders, so_field, 'sales')):
            for r in rows:
                d = doc_date(r, field)
                key = month_key(d)
                if key in series:
                    series[key][bucket] += (r.total or Decimal('0'))

        def open_value(rows, open_statuses):
            return sum((r.total or Decimal('0')) for r in rows if r.status in open_statuses)

        return Response({
            'product_count': len(products),
            'stock_value': stock_value,
            'low_stock_count': len(low),
            'vendor_count': Vendor.objects.count(),

            'quote_count': len(quotes),
            'quote_status': status_counts(quotes),
            'open_quote_value': open_value(quotes, {'draft', 'sent'}),

            'sales_order_count': len(orders),
            'sales_order_status': status_counts(orders),
            'open_sales_value': open_value(orders, {'draft', 'confirmed', 'shipped'}),

            'purchase_order_count': len(pos),
            'purchase_order_status': status_counts(pos),
            'open_purchase_value': open_value(pos, {'draft', 'ordered'}),

            'monthly': list(series.values()),
            'low_stock': [{
                'id': p.id, 'name': p.name, 'sku': p.sku, 'unit': p.unit,
                'stock_quantity': p.stock_quantity, 'reorder_level': p.reorder_level,
            } for p in sorted(low, key=lambda x: x.stock_quantity)[:10]],
        })



class StockQuoteViewSet(ProformaDocumentMixin, viewsets.ModelViewSet):
    """Wholesale quotations. Accepting one is recorded by converting it, which
    writes the dispatch rows that take the goods out of stock."""
    serializer_class = StockQuoteSerializer
    permission_classes = [permissions.IsAuthenticated, IsStockKeeper]
    queryset = StockQuote.objects.all()

    def get_queryset(self):
        qs = (StockQuote.objects
              .select_related('customer', 'created_by')
              .prefetch_related('items', 'items__item'))
        status_f = self.request.query_params.get('status')
        if status_f and status_f != 'all':
            qs = qs.filter(status=status_f)
        return qs

    def destroy(self, request, *args, **kwargs):
        quote = self.get_object()
        if quote.status == 'converted':
            return Response(
                {'error': f'{quote.number} has been dispatched. Delete those dispatch '
                          f'rows first if this was a mistake.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return super().destroy(request, *args, **kwargs)

    def proforma_party(self, quote):
        """A wholesale invoice is addressed to the trade customer."""
        c = quote.customer
        if not c:
            return dict(BLANK_PARTY)
        return {
            'name': c.name, 'gstin': c.gstin, 'contact_person': c.contact_person,
            'contact_number': c.contact_number or c.phone, 'address': c.site_address,
            'state': c.state, 'email': getattr(c, 'email', '') or '',
        }

    def proforma_line(self, item):
        it = item.item
        label = item.description or f"{it.brand} {it.model_name}".strip() or it.code
        return label, it.hsn, it.unit

    @action(detail=True, methods=['post'])
    def convert(self, request, pk=None):
        """Turn an accepted quote into stock dispatches — one row per line, all
        sharing the quote's number as the invoice reference.

        Guarded so it can only happen once: a second call would take the same
        goods out of stock twice.
        """
        quote = self.get_object()
        if quote.status == 'converted':
            return Response({'error': f'{quote.number} has already been dispatched.'},
                            status=status.HTTP_400_BAD_REQUEST)
        lines = list(quote.items.all())
        if not lines:
            return Response({'error': 'Add at least one line before dispatching.'},
                            status=status.HTTP_400_BAD_REQUEST)

        dispatch_date = quote.quote_date or timezone.localdate()
        created = [
            StockDispatch.objects.create(
                invoice_no=quote.number or '', date=dispatch_date, customer=quote.customer,
                item=line.item, quantity=line.quantity, rate=line.unit_price,
                tax_percent=quote.tax_percent or Decimal('0'),
                site=quote.site, notes=f"From quote {quote.number}",
                created_by=request.user if request.user.is_authenticated else None,
            )
            for line in lines
        ]
        quote.status = 'converted'
        quote.converted_at = timezone.now()
        quote.save(update_fields=['status', 'converted_at', 'updated_at'])

        data = self.get_serializer(quote).data
        data['dispatched_lines'] = len(created)
        return Response(data)
