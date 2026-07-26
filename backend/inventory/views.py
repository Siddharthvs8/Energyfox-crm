from django.conf import settings
from django.core.mail import EmailMessage
from django.db.models import Q
from rest_framework import viewsets, permissions, status
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


class QuoteViewSet(viewsets.ModelViewSet):
    serializer_class = QuoteSerializer
    permission_classes = [permissions.IsAuthenticated]
    queryset = Quote.objects.all()

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
