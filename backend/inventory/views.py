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


# ─── Stock register ─────────────────────────────────────────────────────────
from decimal import Decimal  # noqa: E402
from django.db.models import Sum, OuterRef, Subquery, DecimalField, Value, F  # noqa: E402
from django.db.models.functions import Coalesce  # noqa: E402
from django.utils import timezone  # noqa: E402
from rest_framework.views import APIView  # noqa: E402

from .models import StockItem, StockCustomer, GoodsReceipt, StockDispatch  # noqa: E402
from .serializers import (  # noqa: E402
    StockItemSerializer, StockCustomerSerializer,
    GoodsReceiptSerializer, StockDispatchSerializer,
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
    """Dashboard figures for the stock register: total value, reorder alerts and
    this month's inward/outward movement."""
    permission_classes = [permissions.IsAuthenticated, IsStockKeeper]

    def get(self, request):
        items = list(stock_items_with_ledger())

        total_value = sum((i.stock_value for i in items), Decimal('0'))
        low = [i for i in items if i.needs_reorder]

        by_category = {}
        for i in items:
            by_category[i.category] = by_category.get(i.category, Decimal('0')) + i.stock_value

        month_start = timezone.localdate().replace(day=1)
        month_in = GoodsReceipt.objects.filter(date__gte=month_start).aggregate(
            t=Coalesce(Sum(F('quantity') * F('rate'), output_field=_MONEY),
                       Value(Decimal('0')), output_field=_MONEY))['t']
        month_out = StockDispatch.objects.filter(date__gte=month_start).aggregate(
            t=Coalesce(Sum(F('quantity') * F('rate'), output_field=_MONEY),
                       Value(Decimal('0')), output_field=_MONEY))['t']

        return Response({
            'sku_count': len(items),
            'total_value': total_value,
            'reorder_count': len(low),
            'month_purchases': month_in,
            'month_sales': month_out,
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
