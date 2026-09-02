import base64
import logging
import mimetypes
import re

from django.conf import settings
from django.core.mail import EmailMessage
from django.db.models import Q
from rest_framework import viewsets, permissions, status, parsers
from rest_framework.decorators import action
from rest_framework.response import Response

from . import b2b_access
from .models import (Vendor, PurchaseOrder, Quote, SalesOrder, SalesOrderItem,
                     ProjectSpec, ProjectSpecLine, Quotation, QuoteItem,
                     QuoteSpecLine, PRICE_VARIANTS, split_tax, round_off_for)

logger = logging.getLogger(__name__)
from .serializers import (
    VendorSerializer, PurchaseOrderSerializer, QuoteSerializer, SalesOrderSerializer,
    ProjectSpecSerializer, QuotationSerializer,
)


def can_access_retail_inventory(user):
    """Who the retail inventory module is for.

    The one definition, mirroring the sidebar exactly — see `canSeeInventory` in
    the CRM layout. Keeping the two in step is the whole point: a module a user
    cannot see should also be one they cannot call.

    The module itself — suppliers, purchases, sales, the stock lists — is for
    the admin tier. The two roles that quote reach the quotation from a lead's
    own page instead; see QUOTING_ROLES below.
    """
    if not user or not user.is_authenticated:
        return False
    # Wholesale staff work some of these same shared lists from their own side;
    # SuppliersAccess does the scoping for them.
    if getattr(user, 'is_b2b_only', False):
        return True
    granted = user.can('inventory')      # a custom role decides for itself
    if granted is not None:
        return granted
    return user.sees_everything


# A BDE and a tele caller do not get the inventory module, but both quote: they
# raise a quotation from a lead's own page, and that needs the quotation itself
# and the projects it is built from. Nothing else — not suppliers, not
# purchases, not the stock lists.
QUOTING_ROLES = ('bde', 'tele_caller')


class RetailInventoryAccess(permissions.BasePermission):
    """Gate for the retail inventory endpoints.

    Until now these were open to any authenticated account, so a module hidden
    from someone's sidebar was still one they could fetch — supplier costs and
    purchase orders included. This closes that, and closes it the same way the
    nav decides, so the two cannot drift.

    Two tiers, because "can raise a quotation" and "can see the module" are
    different questions: the admin tier gets everything, while the roles that
    quote reach only the endpoints a quotation needs. A viewset opts into the
    second by setting ``open_to_quoting_roles``.

    The spectator keeps its bargain: it reads everything and writes nothing.
    """
    def has_permission(self, request, view):
        from leads.access import is_view_only
        user = request.user
        if not (user and user.is_authenticated):
            return False
        if request.method not in permissions.SAFE_METHODS and is_view_only(user):
            return False
        if can_access_retail_inventory(user):
            return True
        return (getattr(view, 'open_to_quoting_roles', False)
                and user.role in QUOTING_ROLES)


class SuppliersAccess(permissions.BasePermission):
    """Suppliers is one list shared by both sides of the business.

    So the wholesale matrix only scopes the B2B-only roles here — a store keeper
    and a store manager have no suppliers module. Everyone on the retail side
    keeps the access they always had.
    """
    def has_permission(self, request, view):
        u = request.user
        if not u or not u.is_authenticated:
            return False
        if not getattr(u, 'is_b2b_only', False):
            return True
        level = b2b_access.level_for(u, 'suppliers')
        if level is None:
            self.message = 'You do not have access to suppliers.'
            return False
        if request.method in permissions.SAFE_METHODS:
            return True
        self.message = 'You have read-only access to suppliers.'
        return level == b2b_access.WRITE


class ProjectViewSet(viewsets.ModelViewSet):
    """Projects — the retail side's bundles of products.

    Named ProjectSpec in the models to stay out of the way of leads.Project (the
    installation stage); it is "Project" everywhere a user can see.

    Retail only. The wholesale stock register is a separate module with its own
    item master, and nothing here reaches into it.
    """
    serializer_class = ProjectSpecSerializer
    permission_classes = [permissions.IsAuthenticated, RetailInventoryAccess]
    # Reachable from a lead page by whoever may quote there, without
    # handing them the rest of the module.
    open_to_quoting_roles = True
    queryset = ProjectSpec.objects.all()

    def get_queryset(self):
        qs = (ProjectSpec.objects.all()
              .prefetch_related('lines')
              .order_by('name'))
        search = self.request.query_params.get('search')
        if search:
            qs = qs.filter(Q(name__icontains=search) | Q(capacity__icontains=search)
                           | Q(system_type__icontains=search))
        # Retired projects stay out of the way unless asked for, so the picker on
        # a new quote offers only what is still sold.
        if self.request.query_params.get('all') not in ('1', 'true', 'yes'):
            qs = qs.filter(is_active=True)
        return qs

    @action(detail=True, methods=['post'])
    def duplicate(self, request, pk=None):
        """Copy a project, lines and all.

        Packages differ by one panel make or one cable length far more often
        than they differ wholly, and retyping thirty lines to change one is how
        a specification picks up mistakes.
        """
        source = self.get_object()
        copy = ProjectSpec.objects.create(
            name=f'{source.name} (copy)', capacity=source.capacity,
            system_type=source.system_type,
            notes=source.notes, created_by=request.user)
        ProjectSpecLine.objects.bulk_create([
            ProjectSpecLine(project=copy, item_name=l.item_name,
                            brand=l.brand, quantity=l.quantity, position=l.position)
            for l in source.lines.all()
        ])
        return Response(ProjectSpecSerializer(copy, context={'request': request}).data,
                        status=status.HTTP_201_CREATED)


class QuotationViewSet(viewsets.ModelViewSet):
    """Quotations — what the customer is offered, before an invoice is raised."""
    serializer_class = QuotationSerializer
    permission_classes = [permissions.IsAuthenticated, RetailInventoryAccess]
    # Reachable from a lead page by whoever may quote there, without
    # handing them the rest of the module.
    open_to_quoting_roles = True
    queryset = Quotation.objects.all()

    def get_queryset(self):
        qs = (Quotation.objects.all()
              .select_related('lead', 'project')
              .prefetch_related('spec_lines', 'costs')
              .order_by('-created_at'))
        status_filter = self.request.query_params.get('status')
        if status_filter:
            qs = qs.filter(status=status_filter)
        # The panel on a lead's own page asks for just that lead's quotations.
        lead = self.request.query_params.get('lead')
        if lead:
            qs = qs.filter(lead_id=lead)
        search = self.request.query_params.get('search')
        if search:
            qs = qs.filter(Q(number__icontains=search)
                           | Q(lead__first_name__icontains=search)
                           | Q(lead__last_name__icontains=search)
                           | Q(project__name__icontains=search))
        return qs

    def quotation_party(self, quotation):
        """Who the quotation is addressed to — the lead behind it."""
        lead = quotation.lead
        if not lead:
            return dict(BLANK_PARTY)
        name = f"{lead.first_name or ''} {lead.last_name or ''}".strip()
        return {
            'name': name or (lead.email or ''),
            'gstin': '',
            'contact_person': name,
            'contact_number': lead.phone or '',
            'address': lead.installation_location or lead.company or '',
            'state': '',
            'email': lead.email or '',
        }

    @action(detail=True, methods=['get'])
    def document(self, request, pk=None):
        """Everything the printed quotation needs.

        Emitted in the same shape the proforma invoice uses, so the two print
        through one template and carry the same letterhead, signature and seal.
        A quotation that looked like a different company's document would be the
        one thing a customer noticed about it.

        The negotiation is the document's whole job, so it becomes the lines:
        the package, then each thing added to it under its own remark, with the
        discount and its reason in the totals block. Assembled here rather than
        in the client so the printed figures and the stored ones cannot disagree.
        """
        q = self.get_object()
        rate = q.tax_percent or Decimal('0')
        inclusive = q.price_includes_tax

        def base_of(amount):
            return split_tax(amount, rate, inclusive)['base_amount']

        # The same name the invoice line carries — see ProjectSpec.full_name.
        package_label = q.project.full_name if q.project else 'Solar installation'
        package_label += f' ({dict(PRICE_VARIANTS).get(q.price_variant, "")})'

        components = [(package_label, base_of(q.package_amount))]
        components += [(c.remark, base_of(c.amount)) for c in q.costs.all()]

        lines, hsn_summary = summarise_lines([
            {'particulars': label, 'hsn': '', 'unit': '', 'qty': 1,
             'taxable': amount, 'gst_rate': rate}
            for label, amount in components
        ])

        taxable = sum((amount for _, amount in components), Decimal('0'))
        discount = base_of(q.discount_amount)
        # Derived by subtraction so the printed block reconciles exactly: the
        # component bases are each rounded, and recomputing tax from the rate
        # would leave the document a paisa short of its own total.
        tax = q.total - (taxable - discount)

        return Response({
            **document_chrome(request, 'b2c'),
            'title': 'QUOTATION',
            'label': 'Quotation',
            'invoice': {
                'number': q.number,
                'date': q.quotation_date.isoformat() if q.quotation_date else None,
                'efc_ref_no': '',
                'status': q.status,
            },
            'customer': self.quotation_party(q),
            'ship_to': {**self.quotation_party(q), 'address': q.site or ''},
            'lines': lines,
            'hsn_summary': hsn_summary,
            'totals': totals_block(taxable, discount, tax, q.total),
            'terms': ([f'Discount: {q.discount_remark}'] if q.discount_remark else [])
                     + ['This quotation is valid for 15 days from the date above.'],
            # Extra, for the screen: the specification and the statement as
            # entered. Ignored by the PDF template, which takes the lines above.
            'spec': [{'item_name': l.item_name, 'brand': l.brand, 'quantity': l.quantity}
                     for l in q.spec_lines.all()],
        })

    @action(detail=True, methods=['get'])
    def proposal(self, request, pk=None):
        """The branded proposal for this quotation, as a PDF.

        Rendered on the server rather than in the browser because it is built on
        the company's own approved artwork — the template is a file, and the
        file lives here.
        """
        from django.http import HttpResponse
        try:
            from .proposal import build_proposal
        except ImportError:
            # PyMuPDF builds this document; without it the endpoint should say
            # so rather than answering 500 and leaving someone guessing at a
            # missing dependency from the outside.
            logger.exception('PyMuPDF is not installed; the proposal cannot be built')
            return Response(
                {'error': 'The document builder is not installed on this server '
                          '(PyMuPDF). Deploy the current requirements.txt.'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE)

        q = self.get_object()
        template = self._template_for(q)
        if template is None:
            return Response(
                {'error': 'No proposal template has been uploaded for '
                          f'{q.project.get_system_type_display() if q.project and q.project.system_type else "this system type"}.'},
                status=status.HTTP_400_BAD_REQUEST)

        with template.pdf.open('rb') as handle:
            pdf = build_proposal(q, handle)
        response = HttpResponse(pdf, content_type='application/pdf')
        response['Content-Disposition'] = (
            f'inline; filename="{safe_doc_name(q.number, self.quotation_party(q).get("name"))}.pdf"')
        return response

    @staticmethod
    def _template_for(quotation):
        """The artwork for this quotation's system type.

        A quotation whose project has no system type set has no template to
        use — the three documents differ, and guessing which one a customer
        should receive is worse than saying nothing has been uploaded.
        """
        from .models import QuotationTemplate
        system_type = quotation.project.system_type if quotation.project else ''
        if not system_type:
            return None
        return QuotationTemplate.objects.filter(system_type=system_type).first()

    @action(detail=True, methods=['post'], parser_classes=[parsers.MultiPartParser, parsers.FormParser])
    def send(self, request, pk=None):
        """Store the rendered PDF against this quotation and send it out.

        The same delivery path the proforma uses, so a quotation reaches the
        customer the same way an invoice does and lands on the lead's timeline.
        """
        q = self.get_object()
        payload, code = deliver_document(
            request, holder=q, number=q.number, amount=q.total,
            party=self.quotation_party(q), noun='Quotation', lead=q.lead)
        if code == status.HTTP_200_OK and q.status == 'draft' and payload.get('sent'):
            q.status = 'sent'
            q.save(update_fields=['status', 'updated_at'])
        return Response(payload, status=code)

    @action(detail=True, methods=['post'])
    def convert(self, request, pk=None):
        """Raise the proforma invoice this quotation was accepted as.

        The invoice is billed from the quotation's *net* figure — the package
        plus its extras, less the discount — so what was agreed is what is
        invoiced. The line is priced pre-tax with the rate on the document, so
        the proforma's own arithmetic reaches the same total rather than taxing
        an already-taxed figure a second time.

        Converting twice returns the invoice already raised instead of minting a
        second one: a customer must never receive two invoices for one job.
        """
        quotation = self.get_object()
        if quotation.converted_quote_id:
            return Response(
                {'error': 'This quotation has already been invoiced.',
                 'quote': QuoteSerializer(quotation.converted_quote,
                                          context={'request': request}).data},
                status=status.HTTP_400_BAD_REQUEST)

        figures = quotation.figures
        quote = Quote.objects.create(
            lead=quotation.lead, project=quotation.project,
            price_variant=quotation.price_variant,
            quote_date=timezone.localdate(), site=quotation.site,
            tax_percent=quotation.tax_percent, notes=quotation.notes,
            status='draft',
            created_by=request.user if request.user.is_authenticated else None)

        QuoteItem.objects.create(
            quote=quote,
            description=quotation.project.name if quotation.project else 'Solar installation',
            quantity=Decimal('1'), unit_price=figures['base_amount'])

        # The specification travels with it: the invoice should say what the
        # customer was offered, not send them back to the quotation for it.
        for line in quotation.spec_lines.all():
            QuoteSpecLine.objects.create(
                quote=quote, item_name=line.item_name,
                brand=line.brand, quantity=line.quantity, position=line.position)

        quotation.converted_quote = quote
        quotation.status = 'converted'
        quotation.save(update_fields=['converted_quote', 'status', 'updated_at'])
        return Response(QuoteSerializer(quote, context={'request': request}).data,
                        status=status.HTTP_201_CREATED)


class VendorViewSet(viewsets.ModelViewSet):
    serializer_class = VendorSerializer
    # Suppliers keeps SuppliersAccess as its only gate, deliberately. The list
    # is shared with the wholesale side and is read by people who never see the
    # retail inventory group — purchase staff order from these vendors — so
    # putting the group's gate on it would take away access that is theirs by
    # the job they do rather than by the menu they are shown.
    permission_classes = [permissions.IsAuthenticated, SuppliersAccess]
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
    permission_classes = [permissions.IsAuthenticated, RetailInventoryAccess]
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


def safe_doc_name(number, party=None):
    """The name a generated document is saved and attached under.

    "<Customer> - <NUMBER>", because a folder — or an inbox — of files named only
    by their serial tells you nothing about whose they are. The number stays on
    the end so two documents for one customer cannot collide, and so the files
    still sort by series.

    Kept in step with `proformaFileName` in the frontend, which names the copy the
    browser downloads; the customer should not receive a differently-named file
    from the one the office keeps.
    """
    illegal = re.compile(r'[\\/:*?"<>|]+')
    tidy = lambda value: re.sub(r'\s+', ' ', illegal.sub('-', str(value or ''))).strip()

    serial = tidy(number) or 'proforma'
    # Long trade names would push the stored path past what some filesystems
    # accept; the number is the part that has to survive intact.
    customer = tidy(party)[:60].strip()
    return f'{customer} - {serial}' if customer else serial


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


def document_chrome(request, side='b2c'):
    """Company header and bank block for a printed document.

    Retail and wholesale each have their own profile (Settings → Inventory
    Documents), so the two sides can trade under different identities; a field
    left blank there falls back to the organisation's own settings.
    """
    from organization.models import InventoryDocumentProfile
    from organization.utils import get_org_settings

    org = get_org_settings()
    printed = InventoryDocumentProfile.load(side).resolved(org)

    def url(f):
        return request.build_absolute_uri(f.url) if f else None

    def art(f):
        # Inlined rather than linked — see inline_image().
        return inline_image(f) or url(f)

    return {
        'company': {
            'name': printed['name'], 'address': printed['address'],
            'phone': printed['phone'], 'email': printed['email'],
            'gst': printed['gst'], 'cin': printed['cin'], 'pan': printed['pan'],
            'logo': art(printed['logo']),
            'signature': art(printed['signature']),
            'seal': art(printed['seal']),
        },
        'bank': printed['bank'],
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
    """The figures under the table, with the rounding the document prints.

    Rounds through the shared helper rather than a bare quantize: Decimal's
    default is banker's rounding, so a total landing on exactly .50 printed one
    figure while payment verification expected another, and the invoice would
    never settle. One rule, one place.
    """
    from leads.receipts import amount_in_words
    grand = grand or Decimal('0')
    rounded, _adjustment = round_off_for(grand)
    return {
        'taxable': money(taxable),
        'discount': money(discount),
        'tax': money(tax),
        'invoice_value': money(grand),
        'round_off': money(rounded - grand),
        'grand_total': money(rounded),
        'in_words': amount_in_words(rounded),
    }


def deliver_document(request, *, holder, number, amount, party, noun, channel=None, lead=None):
    """Store the posted PDF against `holder` and send it out.

    Shared by the proforma invoice and the dispatch invoice: the client renders
    the document (it owns the template) and posts it back, the file is kept so
    email can attach it and WhatsApp can link to it — the Cloud API fetches
    documents by URL rather than by upload.

    `lead` records the send on that customer's Activity Timeline. Only the retail
    proforma has one — the wholesale documents are raised against a stock
    customer or a supplier, who have no lead history to write to.

    Returns (payload, http_status).
    """
    # Named for the customer as well as the number, matching the copy the
    # browser downloads — see safe_doc_name.
    doc_name = safe_doc_name(number, (party or {}).get('name'))
    pdf = request.FILES.get('pdf')
    if pdf:
        holder.pdf.save(f"{doc_name}.pdf", pdf, save=True)
    if not holder.pdf:
        return {'error': 'No document to send. Generate the PDF first.'}, status.HTTP_400_BAD_REQUEST

    channels = [c.strip() for c in str(request.data.get('channels', 'email')).split(',') if c.strip()]
    results, failures, delivered = {}, [], []

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
                attachments=[(f"{doc_name}.pdf", data, 'application/pdf')],
                created_by=request.user if request.user.is_authenticated else None,
                channel=channel,
            )
            results['email'] = log.status
            if log.status == 'sent':
                delivered.append(f"email to {', '.join(recipients)}")
            else:
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
                    filename=f"{doc_name}.pdf",
                    caption=f"{noun} {number}",
                    channel=channel,
                )
                results['whatsapp'] = 'sent'
                delivered.append(f'WhatsApp to {to}')
            except Exception as exc:                         # surfaced to the user
                failures.append(f"WhatsApp failed: {exc}")

    if failures and not results:
        return {'error': ' '.join(failures)}, status.HTTP_502_BAD_GATEWAY
    # Only actual deliveries reach the timeline — a refusal is not an event.
    if lead is not None and delivered:
        from leads.models import ActivityLog
        ActivityLog.objects.create(
            activity_type='note_added', lead=lead,
            actor=request.user if request.user.is_authenticated else None,
            description=f"{noun} {number} sent by {' and '.join(delivered)}.",
            extra={'auto_generated': True, 'document': number, 'channels': sorted(results)},
        )
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
    # Which Settings → Inventory Documents profile the printed form uses.
    DOC_SIDE = 'b2c'

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
            **document_chrome(request, self.DOC_SIDE),
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
            channel=self.SEND_CHANNEL,
            # Retail quotes hang off a lead; wholesale ones do not.
            lead=getattr(quote, 'lead', None))
        # Raising the document to the customer moves it out of draft.
        if code == status.HTTP_200_OK and quote.status == 'draft' and payload.get('sent'):
            quote.status = 'sent'
            quote.save(update_fields=['status', 'updated_at'])
        return Response(payload, status=code)


class QuoteViewSet(ProformaDocumentMixin, viewsets.ModelViewSet):
    serializer_class = QuoteSerializer
    permission_classes = [permissions.IsAuthenticated, RetailInventoryAccess]
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
    permission_classes = [permissions.IsAuthenticated, RetailInventoryAccess]
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
from django.db import transaction  # noqa: E402
from django.db.models import Sum, OuterRef, Subquery, DecimalField, Value, F, Exists  # noqa: E402
from django.db.models.functions import Coalesce  # noqa: E402
from django.utils import timezone  # noqa: E402
from rest_framework.views import APIView  # noqa: E402

from .models import (StockItem, StockCustomer, GoodsReceipt, StockDispatch,  # noqa: E402
                     StockQuote, StockQuoteItem, StockPurchaseOrder, DispatchPayment,
                     LIVE_QUOTE_STATUSES,
                     next_stock_po_number, next_document_number, financial_year)
from .serializers import (  # noqa: E402
    StockItemSerializer, StockCustomerSerializer,
    GoodsReceiptSerializer, StockDispatchSerializer, StockQuoteSerializer,
    StockPurchaseOrderSerializer,
)

_MONEY = DecimalField(max_digits=16, decimal_places=2)


class IsStockKeeper(permissions.BasePermission):
    """Anywhere on the wholesale side.

    The wholesale side is a separate business rather than another admin screen,
    so crossing into it is limited to the super admin and the COO — an admin
    runs the retail CRM and does not see the stock register. Purchase staff keep
    it because they buy against it, and the B2B roles because it is their whole
    job. Which *modules* each of those B2B roles reaches, and whether they may
    write, is the matrix in b2b_access — see StockModule.
    """
    message = 'You do not have access to the stock register.'

    def has_permission(self, request, view):
        u = request.user
        if not u or not u.is_authenticated:
            return False
        return bool(getattr(u, 'is_superuser', False)
                    or getattr(u, 'is_spectator', False)
                    or getattr(u, 'role', '') in b2b_access.UNRESTRICTED_ROLES
                    or getattr(u, 'is_b2b_only', False))


def StockModule(module):
    """Permission for one wholesale module, read/write per role.

    Built per module rather than one blanket check, because the B2B roles do
    different jobs: a store keeper looks stock up, a store manager keeps the item
    master and watches the rest, Accounts B2B runs the lot.
    """
    class _Permission(permissions.BasePermission):
        def has_permission(self, request, view):
            u = request.user
            if not u or not u.is_authenticated:
                return False
            level = b2b_access.level_for(u, module)
            if level is None:
                self.message = 'You do not have access to this part of the stock register.'
                return False
            if request.method in permissions.SAFE_METHODS:
                return True
            self.message = 'You have read-only access here.'
            return level == b2b_access.WRITE

    _Permission.__name__ = f'StockModule_{module}'
    return _Permission


def _movement_total(model, field='quantity', **extra):
    """Per-item Sum as a subquery — two plain annotations across two reverse FKs
    would multiply each other's rows and inflate both totals."""
    return Coalesce(
        Subquery(
            model.objects.filter(item=OuterRef('pk'), **extra).values('item')
            .annotate(t=Sum(field)).values('t')[:1],
            output_field=_MONEY,
        ),
        Value(Decimal('0')), output_field=_MONEY,
    )


def _reserved_total():
    """Units held by live proforma invoices, per item — see StockItem.reserved.

    Same subquery shape as the movement totals for the same reason: a plain
    annotation across a third reverse FK would multiply the other two.
    """
    return Coalesce(
        Subquery(
            StockQuoteItem.objects
            .filter(item=OuterRef('pk'), quote__status__in=LIVE_QUOTE_STATUSES)
            .values('item').annotate(t=Sum('quantity')).values('t')[:1],
            output_field=_MONEY,
        ),
        Value(Decimal('0')), output_field=_MONEY,
    )


def stock_items_with_ledger():
    """Item master annotated with its received/dispatched/reserved totals.

    Only a *released* dispatch has moved stock; one still waiting on payment
    holds it instead, alongside the proformas — see StockItem.reserved.
    """
    return StockItem.objects.annotate(
        received_qty=_movement_total(GoodsReceipt),
        dispatched_qty=_movement_total(StockDispatch, status=StockDispatch.RELEASED),
        reserved_qty=_reserved_total() + _movement_total(StockDispatch,
                                                         status=StockDispatch.PENDING),
    )


class StockItemViewSet(viewsets.ModelViewSet):
    serializer_class = StockItemSerializer
    permission_classes = [permissions.IsAuthenticated, StockModule('items')]

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

    @action(detail=True, methods=['get'])
    def history(self, request, pk=None):
        """Where this item's stock came from — every quantity ever added.

        Goods receipts have no screen of their own anywhere in the CRM, so a
        line of stock that appeared last March is otherwise unaccountable: the
        Item Master shows a running total and nothing behind it. This is that
        behind.

        Additions only, which is what the button offers. The opening stock leads
        the list as its own entry, because it is a quantity the item started
        with rather than one that arrived, and leaving it out would make the
        entries fail to add up to the total. `running_total` is the stock added
        so far — deliberately not a stock balance, which would have to net off
        dispatches and would be wrong on every line.
        """
        item = self.get_object()

        # Multiplying two 2-dp figures gives a 4-dp one, so amounts are brought
        # back to paise here rather than reaching the screen as 750.0000.
        money = lambda v: str(Decimal(v or 0).quantize(PAISE))

        rows = []
        opening = item.opening_stock or Decimal('0')
        if opening:
            rows.append({
                'id': None,
                'kind': 'opening',
                'label': 'Opening stock',
                'date': None,
                'quantity': str(opening),
                'rate': money(item.unit_cost),
                'amount': money(opening * (item.unit_cost or Decimal('0'))),
                'reference': '',
                'supplier': '',
                'notes': 'The quantity this item was set up with.',
                'added_by': None,
                'created_at': None,
            })

        receipts = (item.receipts.select_related('supplier', 'created_by')
                    .order_by('date', 'created_at', 'pk'))
        for receipt in receipts:
            who = receipt.created_by
            rows.append({
                'id': receipt.pk,
                'kind': 'receipt',
                'label': 'Stock added',
                'date': receipt.date.isoformat() if receipt.date else None,
                'quantity': str(receipt.quantity or Decimal('0')),
                'rate': money(receipt.rate),
                'amount': money(receipt.amount),
                'reference': receipt.grn_no or '',
                'supplier': receipt.supplier.name if receipt.supplier else '',
                'notes': receipt.notes or '',
                'added_by': ((f'{who.first_name} {who.last_name}'.strip() or who.username)
                             if who else None),
                'created_at': receipt.created_at.isoformat() if receipt.created_at else None,
            })

        running = Decimal('0')
        for row in rows:
            running += Decimal(row['quantity'])
            row['running_total'] = str(running)

        # Newest first for reading; the running total above was accumulated in
        # the order the stock actually arrived.
        rows.reverse()

        received = sum((Decimal(r['quantity']) for r in rows if r['kind'] == 'receipt'),
                       Decimal('0'))
        return Response({
            'item': {
                'id': item.pk,
                'code': item.code,
                'name': f'{item.brand} {item.model_name}'.strip() or item.code,
                'unit': item.unit,
            },
            'entries': rows,
            'summary': {
                'opening_stock': str(opening),
                'total_added': str(received),
                'total_in': str(opening + received),
                # The rest of the item's position, so the modal agrees with the
                # row it was opened from.
                'dispatched': str(item.dispatched),
                'reserved': str(item.reserved),
                'physical_stock': str(item.physical_stock),
                'closing_stock': str(item.closing_stock),
            },
        })

    def destroy(self, request, *args, **kwargs):
        """Items with movement history stay put — deleting one would erase the
        receipts and dispatches that explain the stock on hand.

        The refusal names what is actually holding the item, because goods
        receipts have no screen of their own: told only "receipts or dispatches",
        someone can empty the dispatch list and still be blocked by a GRN they
        cannot see anywhere.

        `?force=1` deletes the movements along with the item. That erases ledger
        history, so it is limited to admins and super admins however wide a
        storekeeper's write access to the item master is.
        """
        item = self.get_object()
        receipts = item.receipts.count()
        dispatches = item.dispatches.count()
        if receipts or dispatches:
            forcing = str(request.query_params.get('force', '')).lower() in ('1', 'true', 'yes')
            user = request.user
            may_force = bool(user.is_superuser or user.is_staff)
            if not forcing or not may_force:
                parts = []
                if receipts:
                    parts.append(f'{receipts} goods receipt' + ('s' if receipts != 1 else ''))
                if dispatches:
                    parts.append(f'{dispatches} dispatch' + ('es' if dispatches != 1 else ''))
                detail = f'{item.code} has {" and ".join(parts)} logged against it.'
                if may_force:
                    detail += (' Deleting the item would erase that stock history —'
                               ' confirm again to delete the movements with it.')
                else:
                    detail += (' Those movements have to go first, or an admin can'
                               ' delete the item along with them.')
                return Response(
                    {'error': detail, 'receipts': receipts, 'dispatches': dispatches,
                     'can_force': may_force},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            # The FKs are PROTECT, so the movements go before the item does.
            item.receipts.all().delete()
            item.dispatches.all().delete()
        return super().destroy(request, *args, **kwargs)


class StockCustomerViewSet(viewsets.ModelViewSet):
    serializer_class = StockCustomerSerializer
    permission_classes = [permissions.IsAuthenticated, StockModule('customers')]
    queryset = StockCustomer.objects.all()

    def get_queryset(self):
        qs = StockCustomer.objects.all().order_by('name')
        search = self.request.query_params.get('search')
        if search:
            qs = qs.filter(Q(name__icontains=search) | Q(contact_person__icontains=search))
        return qs


PAISE = Decimal('0.01')


def to_money(value, default=Decimal('0')):
    """A figure off the wire as rupees and paise, or `default` if it isn't one."""
    from decimal import ROUND_HALF_UP, InvalidOperation
    if value in (None, ''):
        return default
    try:
        return Decimal(str(value)).quantize(PAISE, rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError, TypeError):
        return None


def to_date(value):
    """An ISO date off the wire as a real date, or None."""
    from datetime import date, datetime
    if isinstance(value, date):
        return value
    try:
        return datetime.strptime(str(value)[:10], '%Y-%m-%d').date()
    except (ValueError, TypeError):
        return None


def check_payment(raw, invoice_total, already_received=Decimal('0'), paid_on_default=None):
    """Validate one payment against what is still owed on a document.

    Verifying and dispatching are separate acts: a payment may be part of the
    total — instalments are normal — and it is *releasing* the goods that needs
    the invoice settled in full. So the only rules here are that the payment is a
    real amount, in a real mode, and does not exceed what is left owing.

    Returns ``(kwargs, error)`` — kwargs ready for a DispatchPayment, or a
    response body explaining what is wrong. The error carries the figures as well
    as the sentence, so the screen can show the position rather than only
    complain about it.
    """
    raw = raw if isinstance(raw, dict) else {}
    # Billed on the rounded figure, cleared by either it or the exact one — the
    # same rule `payment_state` reports, so this dialog cannot refuse a payment
    # as unnecessary while the screen behind it still shows money owing.
    invoice_total, exact_total, settles_at = settlement(invoice_total)
    already = to_money(already_received) or Decimal('0')
    outstanding = max(invoice_total - already, Decimal('0'))
    if already >= settles_at:
        outstanding = Decimal('0')

    if invoice_total <= 0:
        return None, {'error': 'This document has no value to collect against. '
                               'Check the quantities and rates first.'}
    if outstanding <= 0:
        return None, {'error': 'This invoice has already been settled in full.',
                      'invoice_total': str(invoice_total),
                      'amount_received': str(already), 'balance': '0'}

    received = to_money(raw.get('amount_received'), default=None)
    if received is None:
        return None, {'error': 'Enter the amount received.',
                      'invoice_total': str(invoice_total), 'balance': str(outstanding)}
    if received <= 0:
        return None, {'error': 'Enter an amount greater than zero.',
                      'invoice_total': str(invoice_total), 'balance': str(outstanding)}

    mode = str(raw.get('mode') or '').strip().lower()
    if mode not in {m for m, _label in DispatchPayment.MODE_CHOICES}:
        return None, {'error': 'Choose how the payment was received.',
                      'invoice_total': str(invoice_total), 'balance': str(outstanding)}

    # Capped on the higher figure, not the billed one: see `payment_ceiling`.
    ceiling = max(payment_ceiling(exact_total) - already, Decimal('0'))
    if received > ceiling:
        return None, {
            'error': (f'That is more than the ₹{outstanding} still owing on this '
                      f'invoice. Record what was actually received.'),
            'invoice_total': str(invoice_total),
            'amount_received': str(already), 'balance': str(outstanding)}

    paid_on = to_date(raw.get('paid_on')) or paid_on_default or timezone.localdate()
    return {
        'invoice_total': invoice_total,
        'amount_received': received,
        'mode': mode,
        'reference': str(raw.get('reference') or '')[:100],
        'paid_on': paid_on,
        'notes': str(raw.get('notes') or ''),
    }, None


def settlement(total):
    """What an invoice is billed at, and what clears it.

    Three figures, because rounding makes them differ: `exact` is the arithmetic
    of the lines, `grand` is the rounded figure printed on the invoice, and
    `settles_at` is the lower of the two.

    Either payment clears the invoice, and it has to. A customer sent the exact
    95,794.65 their copy of the invoice showed; the rounded bill says 95,795, so
    the balance sat at 35 paise and the goods would never release — nobody is
    going to transfer 35 paise. The reverse case is just as real: an invoice
    rounded *down* is settled by the rounded figure even though the arithmetic
    is a few paise higher. Anything below a rupee here is an artefact of
    rounding, not a debt.
    """
    exact = to_money(total) or Decimal('0')
    grand, _adjustment = round_off_for(exact)
    return grand, exact, min(grand, exact)


def payment_ceiling(total):
    """The most that can still be taken against an invoice.

    The higher of the two figures, for the same reason `settles_at` is the
    lower: a customer paying the exact 2,252.25 on a bill rounded down to 2,252
    is not overpaying, they are paying what the arithmetic said. Refusing that
    as an overpayment strands the invoice exactly as demanding 35 paise did.
    """
    grand, exact, _settles_at = settlement(total)
    return max(grand, exact)


def payment_state(total, received):
    """The money position on a document, as every screen reports it.

    The figure the customer owes is the rounded one. Nobody pays 65 paise, so
    settling an invoice of 95,794.65 with 95,795 has to read as paid in full —
    against the exact total it would sit 35 paise short for ever and the goods
    would never release. Rounding here rather than at each caller is deliberate:
    this is the one function every payment screen reconciles through, so the
    invoice, the verification dialog and the Payments module cannot disagree.

    For a delivery of several lines the total handed in is already the sum of
    the group, so the rounding lands on the invoice, not on each line.
    """
    grand, exact, settles_at = settlement(total)
    round_off = grand - exact
    received = to_money(received) or Decimal('0')
    paid_up = grand > 0 and received >= settles_at
    balance = Decimal('0') if paid_up else max(grand - received, Decimal('0'))
    # Every figure to paise, whole rupees included: a payload that mixed "95795"
    # with "45795.00" made the screens format the same money two ways.
    money2 = lambda v: str(v.quantize(PAISE))
    return {
        'invoice_total': money2(grand),
        'exact_total': money2(exact),
        'round_off': money2(round_off),
        'amount_received': money2(received),
        'balance': money2(balance),
        'fully_paid': bool(paid_up),
    }


def payment_rows(payments):
    """The verified payments on a document, oldest first, for the history list."""
    return [{
        'id': p.id,
        'amount_received': str(p.amount_received),
        'mode': p.mode,
        'mode_label': p.get_mode_display(),
        'reference': p.reference,
        'paid_on': p.paid_on.isoformat() if p.paid_on else None,
        'notes': p.notes,
        'verified_by': (f"{p.verified_by.first_name} {p.verified_by.last_name}".strip()
                        or p.verified_by.username) if p.verified_by else None,
        'verified_at': p.verified_at.isoformat() if p.verified_at else None,
    } for p in payments]

class _MovementViewSet(viewsets.ModelViewSet):
    # Subclasses set their own module: receipts belong to purchases, dispatches
    # to the sales module.
    permission_classes = [permissions.IsAuthenticated, IsStockKeeper]

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user if self.request.user.is_authenticated else None)


class GoodsReceiptViewSet(_MovementViewSet):
    permission_classes = [permissions.IsAuthenticated, StockModule('purchases')]
    serializer_class = GoodsReceiptSerializer
    queryset = GoodsReceipt.objects.all()

    def get_queryset(self):
        return GoodsReceipt.objects.select_related('item', 'supplier', 'created_by')


class StockDispatchViewSet(_MovementViewSet):
    permission_classes = [permissions.IsAuthenticated, StockModule('dispatch')]
    serializer_class = StockDispatchSerializer
    queryset = StockDispatch.objects.all()

    def get_queryset(self):
        # The payment is held once per invoice number, so it is joined on rather
        # than looked up per row — a list of dispatches would otherwise be a
        # query each.
        paid = DispatchPayment.objects.filter(invoice_no=OuterRef('invoice_no'))
        return (StockDispatch.objects
                .select_related('item', 'customer', 'created_by')
                .annotate(
                    payment_verified=Exists(paid),
                    payment_amount=Subquery(paid.values('amount_received')[:1]),
                    payment_mode=Subquery(paid.values('mode')[:1]),
                    payment_reference=Subquery(paid.values('reference')[:1]),
                    payment_paid_on=Subquery(paid.values('paid_on')[:1]),
                ))

    @action(detail=False, methods=['post'], url_path='dispatch')
    def dispatch_document(self, request):
        """Raise a whole delivery, pending payment.

        This is what Save Dispatch calls. The rows are written together in one
        transaction — a half-written delivery must not be a state the database
        can reach — but they are *pending*: the goods stay on the shelf, held
        rather than moved, until the invoice is settled and the delivery
        released. Payments go to `verify-payment`, releasing to `release`.

        The plain ``POST /api/stock-dispatches/`` is still the row primitive
        (editing a line, the quote conversion's own rows); the payment gate
        belongs to this document-level action, which is the one the warehouse
        actually uses.
        """
        data = request.data
        raw_lines = data.get('lines') or []
        if not isinstance(raw_lines, list) or not raw_lines:
            return Response({'error': 'Add at least one product before dispatching.'},
                            status=status.HTTP_400_BAD_REQUEST)

        tax_percent = to_money(data.get('tax_percent')) or Decimal('0')
        lines, goods = [], Decimal('0')
        for raw in raw_lines:
            item_id = (raw or {}).get('item')
            quantity = to_money((raw or {}).get('quantity'))
            rate = to_money((raw or {}).get('rate')) or Decimal('0')
            if not item_id or not quantity or quantity <= 0:
                continue
            lines.append((item_id, quantity, rate, str((raw or {}).get('serial_numbers') or '')))
            goods += quantity * rate
        if not lines:
            return Response({'error': 'Add at least one product with a quantity.'},
                            status=status.HTTP_400_BAD_REQUEST)

        # The same arithmetic the modal shows: goods value, then tax on top,
        # rounded once at the end. Rounding per row instead would leave the
        # popup demanding a total a paisa away from the one on screen.
        invoice_total = to_money(goods + (goods * tax_percent / Decimal('100')))

        dispatch_date = to_date(data.get('date')) or timezone.localdate()
        customer_id = data.get('customer') or None
        invoice_no = (str(data.get('invoice_no') or '').strip()
                      or next_document_number('IN', on=dispatch_date))
        if StockDispatch.objects.filter(invoice_no=invoice_no).exists():
            return Response({'error': f'{invoice_no} already exists.'},
                            status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            rows = [
                StockDispatch.objects.create(
                    invoice_no=invoice_no, date=dispatch_date, customer_id=customer_id,
                    item_id=item_id, quantity=quantity, rate=rate,
                    status=StockDispatch.PENDING,
                    tax_percent=tax_percent, serial_numbers=serials,
                    site=str(data.get('site') or ''), notes=str(data.get('notes') or ''),
                    created_by=request.user if request.user.is_authenticated else None,
                )
                for item_id, quantity, rate, serials in lines
            ]
            # An opening payment can come with the delivery; it is optional, and
            # partial is fine — releasing is the step that needs the full amount.
            if data.get('payment'):
                payment, error = check_payment(data.get('payment'), invoice_total,
                                               paid_on_default=dispatch_date)
                if error:
                    transaction.set_rollback(True)
                    return Response(error, status=status.HTTP_400_BAD_REQUEST)
                DispatchPayment.objects.create(
                    invoice_no=invoice_no,
                    verified_by=request.user if request.user.is_authenticated else None,
                    **payment)

        return Response({
            'invoice_no': invoice_no,
            'dispatched_lines': len(rows),
            'invoice_total': str(invoice_total),
            'rows': StockDispatchSerializer(
                self.get_queryset().filter(id__in=[r.id for r in rows]),
                many=True, context={'request': request}).data,
        }, status=status.HTTP_201_CREATED)

    # ── Money, then goods ──
    @staticmethod
    def invoice_total_for(rows):
        """What a delivery's rows come to, tax included — one rounding, at the
        end, so the figure matches the one the screen adds up."""
        goods = sum((r.amount or Decimal('0') for r in rows), Decimal('0'))
        tax = sum((r.tax_amount or Decimal('0') for r in rows), Decimal('0'))
        return to_money(goods + tax) or Decimal('0')

    def _invoice_rows(self, invoice_no):
        return list(StockDispatch.objects.filter(invoice_no=invoice_no)
                    .select_related('item', 'customer').order_by('id'))

    @action(detail=False, methods=['get', 'post'], url_path='verify-payment')
    def verify_payment(self, request):
        """Record a payment against a pending delivery, or read its position.

        Verifying is not dispatching: a payment may be part of the total, and
        several of them may arrive before the invoice is settled. Releasing the
        goods is a separate act — see `release`.
        """
        invoice_no = str(request.data.get('invoice_no')
                         or request.query_params.get('invoice_no') or '').strip()
        rows = self._invoice_rows(invoice_no) if invoice_no else []
        if not rows:
            return Response({'error': 'No delivery found under that invoice number.'},
                            status=status.HTTP_404_NOT_FOUND)

        total = self.invoice_total_for(rows)

        def position():
            payments = DispatchPayment.objects.filter(invoice_no=invoice_no)
            received = DispatchPayment.received_for(invoice_no=invoice_no)
            return {
                'invoice_no': invoice_no,
                'status': rows[0].status,
                **payment_state(total, received),
                'payments': payment_rows(payments),
            }

        if request.method == 'GET':
            return Response(position())

        if rows[0].status == StockDispatch.RELEASED:
            return Response({'error': f'{invoice_no} has already been dispatched.'},
                            status=status.HTTP_400_BAD_REQUEST)

        payment, error = check_payment(
            request.data.get('payment') or request.data, total,
            already_received=DispatchPayment.received_for(invoice_no=invoice_no),
            paid_on_default=rows[0].date)
        if error:
            return Response(error, status=status.HTTP_400_BAD_REQUEST)

        DispatchPayment.objects.create(
            invoice_no=invoice_no,
            verified_by=request.user if request.user.is_authenticated else None,
            **payment)
        return Response(position(), status=status.HTTP_201_CREATED)

    @action(detail=False, methods=['post'], url_path='release')
    def release(self, request):
        """Send a settled delivery out: pending → released.

        This is the step the stock ledger has been waiting for. Until now the
        goods were reserved — on the shelf but spoken for; releasing is what
        moves them, and it needs the invoice paid in full.
        """
        invoice_no = str(request.data.get('invoice_no') or '').strip()
        rows = self._invoice_rows(invoice_no) if invoice_no else []
        if not rows:
            return Response({'error': 'No delivery found under that invoice number.'},
                            status=status.HTTP_404_NOT_FOUND)
        if rows[0].status == StockDispatch.RELEASED:
            return Response({'error': f'{invoice_no} has already been dispatched.'},
                            status=status.HTTP_400_BAD_REQUEST)

        total = self.invoice_total_for(rows)
        received = DispatchPayment.received_for(invoice_no=invoice_no)
        state = payment_state(total, received)
        if not state['fully_paid']:
            return Response({
                'error': (f"₹{state['balance']} of ₹{state['invoice_total']} is still "
                          f"owing. The invoice must be settled in full before the "
                          f"goods can leave."),
                **state,
            }, status=status.HTTP_400_BAD_REQUEST)

        now = timezone.now()
        StockDispatch.objects.filter(invoice_no=invoice_no).update(
            status=StockDispatch.RELEASED, released_at=now)
        return Response({'invoice_no': invoice_no, 'status': StockDispatch.RELEASED,
                         'released_at': now.isoformat(), **state})

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
            **document_chrome(request, 'b2b'),
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


class StockPaymentView(APIView):
    """One recorded payment — for undoing one that should never have been there.

    Super admin only, and deliberately not grantable through a custom role. A
    verified payment is the CRM's record that money arrived: it decides whether
    an invoice is settled, whether goods may leave, and what the revenue figures
    say. Correcting a mis-keyed one is a real need, but it sits above the admin
    tier rather than beside it.

    What this does *not* do is pull a delivery back. A dispatch released on the
    strength of this payment stays released, because the goods physically went
    out — reverting it would put stock back on the shelf that is not there. The
    reply says so, and the caller is expected to show it.
    """
    permission_classes = [permissions.IsAuthenticated, StockModule('dispatch')]

    def delete(self, request, pk):
        if not getattr(request.user, 'is_superuser', False):
            return Response({'error': 'Only a super admin can delete a verified payment.'},
                            status=status.HTTP_403_FORBIDDEN)

        payment = DispatchPayment.objects.filter(pk=pk).select_related('quote').first()
        if payment is None:
            return Response({'error': 'That payment is no longer there.'},
                            status=status.HTTP_404_NOT_FOUND)

        quote, invoice_no = payment.quote, payment.invoice_no
        amount, mode = payment.amount_received, payment.mode
        number = quote.number if quote else invoice_no

        # Read the delivery's state before the row goes, so the reply can say
        # what the deletion did and did not change.
        released = bool(invoice_no) and StockDispatch.objects.filter(
            invoice_no=invoice_no, status=StockDispatch.RELEASED).exists()

        payment.delete()

        # No ActivityLog here: it hangs off a lead, and a wholesale payment has
        # no lead behind it. The log line is the trail.
        logger.warning(
            'Payment of %s (%s) on %s deleted by %s', amount, mode, number,
            getattr(request.user, 'username', 'unknown'))

        if quote is not None:
            total, received = quote.total, DispatchPayment.received_for(quote=quote)
        else:
            rows = StockDispatch.objects.filter(invoice_no=invoice_no)
            total = sum((r.total or Decimal('0') for r in rows), Decimal('0'))
            received = DispatchPayment.received_for(invoice_no=invoice_no)

        return Response({
            'deleted': pk,
            'document': number,
            'amount_removed': str(amount),
            **payment_state(total, received),
            # The goods are already gone; the money record is what was wrong.
            'still_released': released,
            'note': (f'{number} was already released, so the delivery stands — only the '
                     f'payment record has gone.') if released else None,
        })


class StockPaymentsView(APIView):
    """Inventory → Payments: every document money has been verified against.

    Three sections, and they are exclusive so a document appears once and the
    counts add up:

      * credit         — anything released on terms. Credit settles an invoice, so
                         these would otherwise sit under "fully paid" and hide the
                         fact that no money came in.
      * fully paid     — settled, in real money.
      * partially paid — some received, a balance still owing.

    Both kinds of document are here. A delivery is the usual one, but a proforma
    takes its instalments before it becomes one — leaving those out would hide
    part-paid business precisely while it is part-paid, which is when someone
    wants to see it.
    """
    permission_classes = [permissions.IsAuthenticated, StockModule('dispatch')]

    def get(self, request):
        rows = [*self._invoice_rows(), *self._proforma_rows()]

        sections = {'credit': [], 'fully_paid': [], 'partially_paid': []}
        for row in rows:
            sections[row.pop('_section')].append(row)

        # Newest first within each section — the money that just moved is the
        # money being looked for.
        for group in sections.values():
            group.sort(key=lambda r: (r['last_paid_on'] or '', r['number']), reverse=True)

        return Response({
            'sections': {name: self._summarise(group) for name, group in sections.items()},
            'totals': self._summarise(rows[:])['totals'] if rows else self._summarise([])['totals'],
        })

    @staticmethod
    def _summarise(rows):
        received = sum((Decimal(r['received']) for r in rows), Decimal('0'))
        billed = sum((Decimal(r['invoice_total']) for r in rows), Decimal('0'))
        owing = sum((Decimal(r['balance']) for r in rows), Decimal('0'))
        return {
            'rows': rows,
            'totals': {'count': len(rows), 'invoice_total': str(billed),
                       'received': str(received), 'balance': str(owing)},
        }

    @staticmethod
    def _classify(received, total, has_credit):
        if has_credit:
            return 'credit'
        return 'fully_paid' if total > 0 and received >= total else 'partially_paid'

    def _row(self, *, number, kind, customer, date, total, payments, status, status_label):
        received = sum((p.amount_received or Decimal('0') for p in payments), Decimal('0'))
        total = to_money(total) or Decimal('0')
        balance = total - received
        modes = []
        for p in payments:                       # ordered oldest first, kept that way
            if p.mode not in modes:
                modes.append(p.mode)
        paid_dates = [p.paid_on.isoformat() for p in payments if p.paid_on]
        return {
            '_section': self._classify(received, total, any(p.mode == 'credit' for p in payments)),
            'number': number,
            'kind': kind,                        # 'invoice' | 'proforma'
            'customer': customer,
            'date': date.isoformat() if date else None,
            'invoice_total': str(total),
            'received': str(received),
            'balance': str(balance if balance > 0 else Decimal('0')),
            'modes': modes,
            'payment_count': len(payments),
            'last_paid_on': max(paid_dates) if paid_dates else None,
            'status': status,
            'status_label': status_label,
            'payments': payment_rows(payments),
        }

    def _invoice_rows(self):
        """One row per dispatch invoice that has taken a payment."""
        payments = (DispatchPayment.objects.exclude(invoice_no='')
                    .select_related('verified_by'))
        by_invoice = {}
        for p in payments:
            by_invoice.setdefault(p.invoice_no, []).append(p)
        if not by_invoice:
            return []

        lines = (StockDispatch.objects.filter(invoice_no__in=by_invoice)
                 .select_related('customer'))
        grouped = {}
        for line in lines:
            grouped.setdefault(line.invoice_no, []).append(line)

        out = []
        for invoice_no, paid in by_invoice.items():
            dispatch_lines = grouped.get(invoice_no, [])
            head = dispatch_lines[0] if dispatch_lines else None
            total = (StockDispatchViewSet.invoice_total_for(dispatch_lines)
                     if dispatch_lines
                     # The delivery was deleted out from under its payments; the
                     # money still happened, so report it against what was owed.
                     else max((p.invoice_total for p in paid), default=Decimal('0')))
            out.append(self._row(
                number=invoice_no, kind='invoice',
                customer=head.customer.name if head and head.customer else None,
                date=head.date if head else None,
                total=total, payments=paid,
                status=head.status if head else StockDispatch.RELEASED,
                status_label=head.get_status_display() if head else 'Released',
            ))
        return out

    def _proforma_rows(self):
        """Proformas still collecting — their payments have not moved onto an
        invoice yet, because there is no delivery until they are settled."""
        quotes = (StockQuote.objects.filter(payments__isnull=False)
                  .select_related('customer').prefetch_related('items', 'payments')
                  .distinct())
        return [self._row(
            number=q.number, kind='proforma',
            customer=q.customer.name if q.customer else None,
            date=q.quote_date, total=q.total, payments=list(q.payments.all()),
            status=q.status, status_label=q.get_status_display(),
        ) for q in quotes]

class StockSummaryView(APIView):
    """Dashboard figures for the stock register: total value, reorder alerts,
    this month's movement, a six-month series and the quote pipeline — the same
    shape the retail inventory dashboard reports, so the two screens match."""
    permission_classes = [permissions.IsAuthenticated, StockModule('dashboard')]
    MONTHS = 6
    # A month per bar; more than a year of them is unreadable, so a long period
    # (or all time) shows the most recent twelve. Short windows get a bar a day
    # instead — "this month" as one bar tells nobody anything.
    MAX_BUCKETS = 12
    DAILY_UP_TO_DAYS = 62
    MAX_DAILY_BUCKETS = 62

    @staticmethod
    def resolve_period(request):
        """The window the movement figures cover: (start, end, key, label).

        `start` of None means all time. Defaults to this month, which is what the
        dashboard reported before it could be asked for anything else.

        Stock on hand is deliberately *not* part of this — items, stock value and
        the reorder list describe the warehouse as it is now, and a date range
        cannot change what is on the shelf today.
        """
        today = timezone.localdate()
        key = (request.query_params.get('period') or 'this_month').strip().lower()

        if key == 'all':
            return None, None, 'all', 'All time'
        if key == 'this_year':
            return today.replace(month=1, day=1), today, 'this_year', f'This year ({today.year})'
        if key == 'custom':
            start = to_date(request.query_params.get('from'))
            end = to_date(request.query_params.get('to')) or today
            if start and end < start:
                start, end = end, start
            if not start:
                # A "to" on its own reads as everything up to that date.
                return None, end, 'custom', f'Up to {end.strftime("%d %b %Y")}'
            return start, end, 'custom', (f'{start.strftime("%d %b %Y")} – '
                                          f'{end.strftime("%d %b %Y")}')
        start = today.replace(day=1)
        return start, today, 'this_month', f'This month ({today.strftime("%B %Y")})'

    def get(self, request):
        start, end, period_key, period_label = self.resolve_period(request)

        def within(field='date'):
            """Date filter for the chosen window, as kwargs."""
            out = {}
            if start:
                out[f'{field}__gte'] = start
            if end:
                out[f'{field}__lte'] = end
            return out

        items = list(stock_items_with_ledger())

        total_value = sum((i.stock_value for i in items), Decimal('0'))
        low = [i for i in items if i.needs_reorder]

        by_category = {}
        for i in items:
            by_category[i.category] = by_category.get(i.category, Decimal('0')) + i.stock_value

        today = timezone.localdate()

        def movement_value(model, **filters):
            """Money moved. For dispatches that is the invoiced figure, tax
            included; goods receipts carry no tax field."""
            line = F('quantity') * F('rate')
            if model is StockDispatch:
                line = line * (Value(Decimal('1')) + F('tax_percent') / Value(Decimal('100')))
            return model.objects.filter(**filters).aggregate(
                t=Coalesce(Sum(line, output_field=_MONEY),
                           Value(Decimal('0')), output_field=_MONEY))['t']

        period_in = movement_value(GoodsReceipt, **within())
        period_out = movement_value(StockDispatch, **within())

        # Purchases-vs-sales across the chosen window. The bucket follows the
        # span rather than being fixed: a month asked for as a single bar is not
        # a chart, and five years of days is not one either. Empty buckets are
        # still drawn, so a quiet week reads as quiet rather than disappearing.
        first_movement = min(
            (d for d in (GoodsReceipt.objects.order_by('date').values_list('date', flat=True).first(),
                         StockDispatch.objects.order_by('date').values_list('date', flat=True).first())
             if d), default=today)
        chart_end = end or today
        chart_start = start or first_movement
        if chart_start > chart_end:
            chart_start = chart_end
        daily = (chart_end - chart_start).days <= self.DAILY_UP_TO_DAYS

        monthly = []
        cursor = chart_start if daily else chart_start.replace(day=1)
        while cursor <= chart_end:
            if daily:
                nxt = cursor + timezone.timedelta(days=1)
                name = cursor.strftime('%d %b')
            else:
                nxt = (cursor.replace(day=28) + timezone.timedelta(days=4)).replace(day=1)
                name = cursor.strftime('%b %y')
            stop = min(nxt, chart_end + timezone.timedelta(days=1))
            monthly.append({
                'name': name,
                'purchases': movement_value(GoodsReceipt, date__gte=cursor, date__lt=stop),
                'sales': movement_value(StockDispatch, date__gte=cursor, date__lt=stop),
            })
            cursor = nxt
        monthly = monthly[-(self.MAX_DAILY_BUCKETS if daily else self.MAX_BUCKETS):]

        # Quote pipeline. Totals come from the model's own `total` property, since
        # discount and tax live on the header — see InventoryDashboardView.
        quotes = list(StockQuote.objects.filter(**within('quote_date')).prefetch_related('items'))
        quote_status = {}
        for q in quotes:
            quote_status[q.status] = quote_status.get(q.status, 0) + 1
        open_quote_value = sum((q.total or Decimal('0')) for q in quotes
                               if q.status in {'draft', 'sent', 'accepted'})

        return Response({
            # What the window is, so the screen can label its own figures rather
            # than guessing at them.
            'period': period_key,
            'period_label': period_label,
            'period_from': start.isoformat() if start else None,
            'period_to': end.isoformat() if end else None,
            # Stock on hand — the warehouse as it stands, whatever the period.
            'sku_count': len(items),
            'total_value': total_value,
            'reorder_count': len(low),
            # Everything below is within the window.
            'period_purchases': period_in,
            'period_sales': period_out,
            'monthly': monthly,
            'receipt_count': GoodsReceipt.objects.filter(**within()).count(),
            'dispatch_count': StockDispatch.objects.filter(**within()).count(),
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
        return bool(getattr(u, 'sees_everything', False))


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
    permission_classes = [permissions.IsAuthenticated, StockModule('proforma')]
    # Wholesale trades under its own identity — see OrgSettings.b2b_email_*.
    SEND_CHANNEL = 'b2b'
    DOC_SIDE = 'b2b'
    """Wholesale quotations. Accepting one is recorded by converting it, which
    writes the dispatch rows that take the goods out of stock."""
    serializer_class = StockQuoteSerializer
    queryset = StockQuote.objects.all()

    def get_queryset(self):
        qs = (StockQuote.objects
              .select_related('customer', 'created_by')
              .prefetch_related('items', 'items__item'))
        status_f = self.request.query_params.get('status')
        if status_f and status_f != 'all':
            qs = qs.filter(status=status_f)
        return qs

    # Deleting a dispatched proforma is allowed: the dispatch rows it produced
    # do not reference it — they carry their own invoice number and their own
    # stock movement — so removing the proforma takes the offer off the books
    # without unwinding the sale. See StockQuoteDeletionTests.

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

    def payment_position(self, quote):
        """What has been verified against this proforma, and what is left."""
        received = DispatchPayment.received_for(quote=quote)
        return {
            'number': quote.number,
            'status': quote.status,
            **payment_state(quote.total, received),
            'payments': payment_rows(quote.payments.all()),
        }

    @action(detail=True, methods=['get', 'post'], url_path='verify-payment')
    def verify_payment(self, request, pk=None):
        """Record a payment against this proforma, or read its position.

        Verifying is not dispatching. Money can arrive in instalments and each
        one is checked here; the goods move only once the whole invoice is
        settled, which is `convert`.
        """
        quote = self.get_object()
        if request.method == 'GET':
            return Response(self.payment_position(quote))

        if quote.status == 'converted':
            return Response({'error': f'{quote.number} has already been dispatched.'},
                            status=status.HTTP_400_BAD_REQUEST)

        payment, error = check_payment(
            request.data.get('payment') or request.data, quote.total,
            already_received=DispatchPayment.received_for(quote=quote),
            paid_on_default=quote.quote_date or timezone.localdate())
        if error:
            return Response(error, status=status.HTTP_400_BAD_REQUEST)

        DispatchPayment.objects.create(
            quote=quote,
            verified_by=request.user if request.user.is_authenticated else None,
            **payment)
        return Response(self.payment_position(quote), status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'])
    def convert(self, request, pk=None):
        """Turn a settled proforma into stock dispatches — one row per line, all
        sharing one invoice number.

        This is the step that puts the goods out of the door, so it needs the
        invoice paid in full; the payments themselves were verified one at a time
        against the proforma (see `verify-payment`). Guarded so it can only
        happen once, too — a second call would take the same goods out twice.
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
        # A final payment may come with the request, so the last instalment and
        # the dispatch can be one action from the screen.
        if request.data.get('payment'):
            payment, error = check_payment(
                request.data.get('payment'), quote.total,
                already_received=DispatchPayment.received_for(quote=quote),
                paid_on_default=dispatch_date)
            if error:
                return Response(error, status=status.HTTP_400_BAD_REQUEST)
            DispatchPayment.objects.create(
                quote=quote,
                verified_by=request.user if request.user.is_authenticated else None,
                **payment)

        state = payment_state(quote.total, DispatchPayment.received_for(quote=quote))
        if not state['fully_paid']:
            return Response({
                'error': (f"₹{state['balance']} of ₹{state['invoice_total']} is still "
                          f"owing on {quote.number}. The invoice must be settled in "
                          f"full before the goods can leave."),
                **state,
            }, status=status.HTTP_400_BAD_REQUEST)

        # The dispatch is a sale, so it takes its own number from the invoice
        # series rather than carrying the proforma's. One number for the whole
        # set — the rows of a delivery share it — with the proforma recorded in
        # the note so the two stay traceable.
        invoice_no = next_document_number('IN', on=dispatch_date)
        with transaction.atomic():
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
            # The payments followed the proforma; move them onto the invoice
            # they actually paid for, so the delivery carries its own history.
            quote.payments.update(invoice_no=invoice_no, quote=None)
            quote.status = 'converted'
            quote.converted_at = timezone.now()
            quote.save(update_fields=['status', 'converted_at', 'updated_at'])

        data = self.get_serializer(quote).data
        data['dispatched_lines'] = len(created)
        data['invoice_no'] = invoice_no
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
    permission_classes = [permissions.IsAuthenticated, StockModule('purchases')]
    """Purchase orders raised on a supplier for stock (wholesale).

    The outbound counterpart of the GRN: this is the order that goes out, the
    goods receipt is what comes back against it.
    """
    serializer_class = StockPurchaseOrderSerializer
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
        chrome = document_chrome(request, 'b2b')
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
