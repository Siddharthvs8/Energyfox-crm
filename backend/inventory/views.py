import base64
import mimetypes

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


def inline_image(f):
    """Read an image file into a data: URI.

    The PDF is drawn in the browser, so any artwork it needs has to be readable
    from there. Handing out a media URL only works while that URL is same-origin
    — once the app is hosted with media on another host or a CDN, fetching it
    from the page is a cross-origin request that fails and the logo silently
    disappears from the document. Inlining the bytes here removes that fetch.
    """
    if not f:
        return None
    try:
        f.open('rb')
        raw = f.read()
        f.close()
    except Exception:                       # missing file: draw without artwork
        return None
    mime = mimetypes.guess_type(f.name)[0] or 'image/png'
    return f"data:{mime};base64,{base64.b64encode(raw).decode()}"


def money(v):
    return str(Decimal(v or 0).quantize(Decimal('0.01')))


def document_chrome(request):
    """Company header and bank block — identical on every document printed."""
    from organization.utils import get_org_settings
    org = get_org_settings()

    def url(f):
        return request.build_absolute_uri(f.url) if f else None

    return {
        'company': {
            'name': org.warranty_company_name,
            'address': org.receipt_address,
            'phone': org.receipt_phone,
            'email': org.receipt_email,
            'gst': org.warranty_gst,
            'cin': org.warranty_cin,
            # The PAN is the middle ten characters of the GSTIN.
            'pan': (org.warranty_gst or '')[2:12],
            # Inlined rather than linked — see inline_image().
            'logo': inline_image(org.logo) or url(org.logo),
            'signature': inline_image(org.warranty_signature) or url(org.warranty_signature),
            'seal': inline_image(org.warranty_seal) or url(org.warranty_seal),
        },
        'bank': {
            'name': org.receipt_bank_name,
            'account_name': org.warranty_company_name,
            'ifsc': org.receipt_bank_ifsc,
            'account_number': org.receipt_bank_account,
            'branch': org.receipt_bank_branch,
        },
    }


def summarise_lines(rows):
    """Number the printed lines and group them into the HSN/GST summary.

    `rows` are dicts of particulars / serials / hsn / qty / unit / taxable /
    gst_rate. Returns (lines, hsn_summary); GST splits evenly into CGST and SGST,
    which is what an intra-state supply shows.
    """
    lines, hsn_rows = [], {}
    for n, r in enumerate(rows, start=1):
        taxable = r['taxable'] or Decimal('0')
        rate = r['gst_rate'] or Decimal('0')
        tax = (taxable * rate) / Decimal('100')
        hsn = r.get('hsn') or ''
        lines.append({
            'sl_no': n,
            'particulars': r.get('particulars') or '',
            'serials': r.get('serials') or '',
            'hsn': hsn,
            'qty': str(r.get('qty') or 0),
            'unit': r.get('unit') or '',
            'taxable': money(taxable),
            'gst_rate': str(rate),
            'tax': money(tax),
            'total': money(taxable + tax),
        })
        row = hsn_rows.setdefault(hsn or '-', {
            'hsn': hsn or '-', 'rate': str(rate),
            'taxable': Decimal('0'), 'cgst': Decimal('0'), 'sgst': Decimal('0'),
        })
        row['taxable'] += taxable
        row['cgst'] += tax / 2
        row['sgst'] += tax / 2

    summary = [{
        'hsn': r['hsn'], 'rate': r['rate'],
        'taxable': money(r['taxable']), 'cgst': money(r['cgst']), 'sgst': money(r['sgst']),
    } for r in hsn_rows.values()]
    return lines, summary


def totals_block(taxable, discount, tax, grand):
    """The figures under the table, with the rounding the document prints."""
    from leads.receipts import amount_in_words
    grand = grand or Decimal('0')
    rounded = grand.quantize(Decimal('1'))
    return {
        'taxable': money(taxable),
        'discount': money(discount),
        'tax': money(tax),
        'invoice_value': money(grand),
        'round_off': money(rounded - grand),
        'grand_total': money(rounded),
        'in_words': amount_in_words(rounded),
    }


def deliver_document(request, *, holder, number, amount, party, noun, channel=None):
    """Store the posted PDF against `holder` and send it out.

    Shared by the proforma invoice and the dispatch invoice: the client renders
    the document (it owns the template) and posts it back, the file is kept so
    email can attach it and WhatsApp can link to it — the Cloud API fetches
    documents by URL rather than by upload.

    Returns (payload, http_status).
    """
    pdf = request.FILES.get('pdf')
    if pdf:
        holder.pdf.save(f"{safe_doc_name(number)}.pdf", pdf, save=True)
    if not holder.pdf:
        return {'error': 'No document to send. Generate the PDF first.'}, status.HTTP_400_BAD_REQUEST

    channels = [c.strip() for c in str(request.data.get('channels', 'email')).split(',') if c.strip()]
    results, failures = {}, []

    if 'email' in channels:
        raw = request.data.get('email') or party.get('email') or ''
        recipients = [a.strip() for a in str(raw).split(',') if a.strip()]
        if not recipients:
            failures.append('No email address given for this customer.')
        else:
            from messaging.email import send_and_log
            holder.pdf.open('rb')
            data = holder.pdf.read()
            holder.pdf.close()
            log = send_and_log(
                to=recipients,
                subject=f"{noun} {number}",
                body=(f"Dear {party.get('name') or 'Customer'},\n\nPlease find attached "
                      f"{noun} {number} for Rs. {amount}.\n\nRegards,\nEnergyFox"),
                kind=noun.lower().replace(' ', '_'),
                attachments=[(f"{safe_doc_name(number)}.pdf", data, 'application/pdf')],
                created_by=request.user if request.user.is_authenticated else None,
                channel=channel,
            )
            results['email'] = log.status
            if log.status != 'sent':
                failures.append(f"Email failed: {log.error}")

    if 'whatsapp' in channels:
        to = request.data.get('phone') or party.get('contact_number') or ''
        if not to:
            failures.append('No WhatsApp number given for this customer.')
        else:
            from messaging import whatsapp
            try:
                whatsapp.send_document(
                    to=to,
                    link=request.build_absolute_uri(holder.pdf.url),
                    filename=f"{safe_doc_name(number)}.pdf",
                    caption=f"{noun} {number}",
                    channel=channel,
                )
                results['whatsapp'] = 'sent'
            except Exception as exc:                         # surfaced to the user
                failures.append(f"WhatsApp failed: {exc}")

    if failures and not results:
        return {'error': ' '.join(failures)}, status.HTTP_502_BAD_GATEWAY
    return ({'sent': results, 'warnings': failures,
             'pdf': request.build_absolute_uri(holder.pdf.url)}, status.HTTP_200_OK)


class ProformaDocumentMixin:
    """Serves a quote's proforma invoice and sends it to the customer.

    Retail and wholesale price off different catalogues and address different
    kinds of customer; those two differences are the hooks below. Everything the
    printed document does with them — the GST split, the totals, the wording,
    storing the PDF and sending it — is shared, so the two modules state the same
    figures and can't drift apart.
    """

    # Which messaging account these documents go out on. Retail keeps the shared
    # one; the wholesale viewsets override this to 'b2b'.
    SEND_CHANNEL = None

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
        quote = self.get_object()
        party = self.proforma_party(quote)
        lines, hsn_summary = summarise_lines([
            dict(zip(('particulars', 'hsn', 'unit'), self.proforma_line(li)),
                 qty=li.quantity or 0, taxable=li.line_total or Decimal('0'),
                 gst_rate=quote.tax_percent or Decimal('0'))
            for li in quote.items.all()
        ])

        return Response({
            **document_chrome(request),
            'title': 'PROFORMA INVOICE',
            'label': 'Proforma Invoice',
            'invoice': {
                'number': quote.number,
                'date': quote.quote_date.isoformat() if quote.quote_date else None,
                'efc_ref_no': quote.efc_ref_no,
                'status': quote.status,
            },
            'customer': party,
            # The delivery block prefers what was entered on the invoice and
            # falls back to the customer's own details.
            'ship_to': {
                **party,
                'address': quote.site or party['address'],
                'state': quote.ship_to_state or party['state'],
                'gstin': quote.ship_to_gstin or party['gstin'],
            },
            'lines': lines,
            'hsn_summary': hsn_summary,
            'totals': totals_block(quote.taxable_amount, quote.discount_amount,
                                   quote.tax_amount, quote.total),
            'terms': ['This Proforma Invoice is valid upto 15 days'],
        })

    @action(detail=True, methods=['post'], parser_classes=[parsers.MultiPartParser, parsers.FormParser])
    def send(self, request, pk=None):
        """Store the generated PDF and send it to the customer."""
        quote = self.get_object()
        payload, code = deliver_document(
            request, holder=quote, number=quote.number, amount=quote.total,
            party=self.proforma_party(quote), noun='Proforma Invoice',
            channel=self.SEND_CHANNEL)
        # Raising the document to the customer moves it out of draft.
        if code == status.HTTP_200_OK and quote.status == 'draft' and payload.get('sent'):
            quote.status = 'sent'
            quote.save(update_fields=['status', 'updated_at'])
        return Response(payload, status=code)


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
                     StockQuote, StockPurchaseOrder,
                     next_stock_po_number, next_document_number, financial_year)
from .serializers import (  # noqa: E402
    StockItemSerializer, StockCustomerSerializer,
    GoodsReceiptSerializer, StockDispatchSerializer, StockQuoteSerializer,
    StockPurchaseOrderSerializer,
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

    # ── The invoice for a dispatch ──
    def _document_rows(self, dispatch):
        """Every row that belongs to this dispatch's invoice.

        A dispatch is one row per item, so a delivery of four products is four
        rows sharing one invoice number — that grouping is what the printed
        invoice covers. Without a number the row stands alone.
        """
        if not dispatch.invoice_no:
            return [dispatch]
        return list(StockDispatch.objects
                    .filter(invoice_no=dispatch.invoice_no)
                    .select_related('item', 'customer')
                    .order_by('id'))

    @staticmethod
    def _party(customer):
        if not customer:
            return dict(BLANK_PARTY)
        return {
            'name': customer.name, 'gstin': customer.gstin,
            'contact_person': customer.contact_person,
            'contact_number': customer.contact_number or customer.phone,
            'address': customer.site_address, 'state': customer.state,
            'email': getattr(customer, 'email', '') or '',
        }

    @action(detail=True, methods=['get'])
    def invoice(self, request, pk=None):
        """The tax invoice for this dispatch, in the proforma's layout.

        Same blocks and the same figures — it is the same printed form with the
        wording changed, because this document is the sale rather than the offer.
        """
        dispatch = self.get_object()
        rows = self._document_rows(dispatch)
        party = self._party(dispatch.customer)

        lines, hsn_summary = summarise_lines([{
            'particulars': (f"{r.item.brand} {r.item.model_name}".strip() or r.item.code),
            'serials': r.serial_numbers,
            'hsn': r.item.hsn,
            'qty': r.quantity or 0,
            'unit': r.item.unit,
            'taxable': r.amount or Decimal('0'),
            'gst_rate': r.tax_percent or Decimal('0'),
        } for r in rows])

        taxable = sum((r.amount or Decimal('0') for r in rows), Decimal('0'))
        tax = sum((r.tax_amount or Decimal('0') for r in rows), Decimal('0'))

        return Response({
            **document_chrome(request),
            'title': 'INVOICE',
            'label': 'Invoice',
            'invoice': {
                'number': dispatch.invoice_no or f'DSP-{dispatch.pk}',
                'date': dispatch.date.isoformat() if dispatch.date else None,
                'efc_ref_no': '',
                'status': 'dispatched',
            },
            'customer': party,
            'ship_to': {**party, 'address': dispatch.site or party['address']},
            'lines': lines,
            'hsn_summary': hsn_summary,
            'totals': totals_block(taxable, Decimal('0'), tax, taxable + tax),
            'terms': ['Goods once dispatched will not be taken back.'],
        })

    @action(detail=True, methods=['post'], parser_classes=[parsers.MultiPartParser, parsers.FormParser])
    def send(self, request, pk=None):
        """Store the generated invoice and send it to the customer."""
        dispatch = self.get_object()
        rows = self._document_rows(dispatch)
        amount = sum((r.total or Decimal('0') for r in rows), Decimal('0'))
        # The file lives on the first row of the group, so re-sending any row of
        # a multi-item delivery finds the same document.
        payload, code = deliver_document(
            request, holder=rows[0], number=dispatch.invoice_no or f'DSP-{dispatch.pk}',
            amount=amount, party=self._party(dispatch.customer), noun='Invoice',
            channel='b2b')
        return Response(payload, status=code)


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
    # Wholesale trades under its own identity — see OrgSettings.b2b_email_*.
    SEND_CHANNEL = 'b2b'
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
        # The dispatch is a sale, so it takes its own number from the invoice
        # series rather than carrying the proforma's. One number for the whole
        # set — the rows of a delivery share it — with the proforma recorded in
        # the note so the two stay traceable.
        invoice_no = next_document_number('IN', StockDispatch, 'invoice_no', on=dispatch_date)
        created = [
            StockDispatch.objects.create(
                invoice_no=invoice_no, date=dispatch_date, customer=quote.customer,
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


def purchase_order_words(amount):
    """The total in words, in the purchase order form's own style.

    The shared receipt helper prints "Rupees Thirty Four Thousand Eight Hundred
    Sixty Nine Only"; this form's In Words cell drops the prefix and reads
    "... Eight Hundred and Sixty Nine Only". Kept here rather than in the shared
    helper so money receipts keep reading the way they always have.
    """
    from leads.receipts import amount_in_words

    words = amount_in_words(amount)
    prefix = 'Rupees '
    if words.startswith(prefix):
        words = words[len(prefix):]
    tail = ' Hundred '
    at = words.rfind(tail)
    if at != -1:
        rest = words[at + len(tail):]
        if not rest.startswith('and ') and not rest.startswith('Only'):
            words = words[:at + len(tail)] + 'and ' + rest
    return words


class StockPurchaseOrderViewSet(viewsets.ModelViewSet):
    """Purchase orders raised on a supplier for stock (wholesale).

    The outbound counterpart of the GRN: this is the order that goes out, the
    goods receipt is what comes back against it.
    """
    serializer_class = StockPurchaseOrderSerializer
    permission_classes = [permissions.IsAuthenticated, IsStockKeeper]
    queryset = StockPurchaseOrder.objects.all()

    def get_queryset(self):
        qs = (StockPurchaseOrder.objects.all()
              .select_related('supplier', 'created_by')
              .prefetch_related('items', 'items__item')
              .order_by('-created_at'))
        status_f = self.request.query_params.get('status')
        if status_f and status_f != 'all':
            qs = qs.filter(status=status_f)
        return qs

    @staticmethod
    def _supplier_block(vendor):
        if not vendor:
            return {'name': '', 'address': '', 'gstin': '', 'pan': '', 'iec': '',
                    'contact_person': '', 'contact_number': '', 'email': ''}
        return {
            'name': vendor.name,
            'address': vendor.address,
            'gstin': vendor.gst_number,
            'pan': vendor.pan_number,
            'iec': vendor.iec_code,
            'contact_person': vendor.contact_person,
            'contact_number': vendor.phone,
            'email': vendor.email or '',
        }

    @action(detail=True, methods=['get'], url_path='document')
    def document(self, request, pk=None):
        """Everything the printed purchase order needs, in the order the form
        lays it out.

        Assembled here rather than in the client so the printed figures and the
        stored ones can never disagree.
        """
        po = self.get_object()
        chrome = document_chrome(request)
        company = chrome['company']
        lines = [{
            'sl': n,
            'type_of_spare': li.type_of_spare or '',
            'description': li.description or (
                f"{li.item.brand} {li.item.model_name}".strip() or li.item.code if li.item else ''),
            'part_code': li.part_code or (li.item.code if li.item else ''),
            'unit_price': money(li.unit_price),
            'quantity': str(li.quantity or 0),
            'base_amount': money(li.base_amount),
        } for n, li in enumerate(po.items.all(), start=1)]

        return Response({
            **chrome,
            'title': 'PURCHASE ORDER',
            'label': 'Purchase Order',
            'order': {
                'number': po.number,
                'fy': po.fy,
                'date': po.po_date.isoformat() if po.po_date else None,
                'status': po.status,
            },
            'supplier': self._supplier_block(po.supplier),
            # Bill-to is always the company; ship-to falls back to it.
            'bill_to': {
                'name': company['name'],
                'address': company['address'],
                'gstin': company['gst'],
            },
            'ship_to': {
                'address': po.ship_to_address or company['address'],
                'phone': po.ship_to_phone or company['phone'],
            },
            'lines': lines,
            # money() quantizes to paise — the form prints two decimals, and the
            # raw Decimal carries the multiplication's full scale.
            'totals': {
                'goods': money(po.goods_amount),
                'transportation': money(po.transportation),
                'taxable': money(po.taxable_amount),
                'tax_label': po.tax_label or 'IGST',
                'tax_percent': str(po.tax_percent or 0),
                'tax_amount': money(po.tax_amount),
                'total': money(po.total),
                'in_words': purchase_order_words(po.total),
            },
            'terms': {
                'taxes': po.terms_taxes,
                'delivery': po.terms_delivery,
            },
        })

    @action(detail=True, methods=['post'], parser_classes=[parsers.MultiPartParser, parsers.FormParser])
    def send(self, request, pk=None):
        """Store the generated PDF and send it to the supplier."""
        po = self.get_object()
        payload, code = deliver_document(
            request, holder=po, number=f"PO-{po.fy}-{po.number}", amount=po.total,
            party=self._supplier_block(po.supplier), noun='Purchase Order',
            channel='b2b')
        # Raising the order to the supplier moves it out of draft.
        if code == status.HTTP_200_OK and po.status == 'draft' and payload.get('sent'):
            po.status = 'sent'
            po.save(update_fields=['status', 'updated_at'])
        return Response(payload, status=code)

    @action(detail=False, methods=['get'], url_path='next-number')
    def next_number(self, request):
        """The number the next order will take, so the form can show it."""
        return Response({'number': next_stock_po_number(), 'fy': financial_year()})
