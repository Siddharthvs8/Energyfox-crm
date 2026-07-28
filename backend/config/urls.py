from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.http import JsonResponse
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
)
from leads.views import LeadViewSet
from leads.webhooks import meta_leads_webhook
from tasks.views import TaskViewSet
from users.views import (UserViewSet, SubscriptionStatusView, WorkspaceTeamViewSet,
                         TenantSettingsView, BranchViewSet, CustomRoleViewSet)
from leads.views import LeadViewSet, IntegrationSettingsViewSet, DashboardStatsView, LeaderboardView, ConvertedAnalyticsView, ProductViewSet, ServiceEntryViewSet, EmergencyServiceViewSet
from inventory.views import (VendorViewSet, PurchaseOrderViewSet, QuoteViewSet, SalesOrderViewSet,
                            StockItemViewSet, StockCustomerViewSet, GoodsReceiptViewSet,
                            StockDispatchViewSet, StockSummaryView,
                            InventoryDashboardView, StockQuoteViewSet)

router = DefaultRouter()
router.register(r'leads', LeadViewSet)
router.register(r'tasks', TaskViewSet)
router.register(r'users', UserViewSet, basename='users')
router.register(r'teams', WorkspaceTeamViewSet, basename='teams')
router.register(r'branches', BranchViewSet, basename='branches')
router.register(r'custom-roles', CustomRoleViewSet, basename='custom-roles')
router.register(r'integration-settings', IntegrationSettingsViewSet, basename='integration-settings')
router.register(r'products', ProductViewSet, basename='products')
router.register(r'service-entries', ServiceEntryViewSet, basename='service-entries')
router.register(r'emergency-services', EmergencyServiceViewSet, basename='emergency-services')
router.register(r'vendors', VendorViewSet, basename='vendors')
router.register(r'purchase-orders', PurchaseOrderViewSet, basename='purchase-orders')
router.register(r'quotes', QuoteViewSet, basename='quotes')
router.register(r'sales-orders', SalesOrderViewSet, basename='sales-orders')
router.register(r'stock-items', StockItemViewSet, basename='stock-items')
router.register(r'stock-customers', StockCustomerViewSet, basename='stock-customers')
router.register(r'goods-receipts', GoodsReceiptViewSet, basename='goods-receipts')
router.register(r'stock-dispatches', StockDispatchViewSet, basename='stock-dispatches')
router.register(r'stock-quotes', StockQuoteViewSet, basename='stock-quotes')


urlpatterns = [
    path('api/health/', lambda request: JsonResponse({"status": "ok"}), name='health-check'),
    # Django admin behind a hard-to-guess path.
    path('sys-admin/', admin.site.urls),
    path('api/token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('api/subscription/', SubscriptionStatusView.as_view(), name='subscription-status'),
    path('api/org-settings/', TenantSettingsView.as_view(), name='org-settings'),
    path('api/ai-manager/', include('ai_manager.urls')),
    path('api/calls/', include('calls.urls')),
    path('api/dashboard-stats/', DashboardStatsView.as_view(), name='dashboard-stats'),
    path('api/leaderboard/', LeaderboardView.as_view(), name='leaderboard'),
    path('api/converted-analytics/', ConvertedAnalyticsView.as_view(), name='converted-analytics'),
    path('api/campaigns/', include('campaigns.urls')),
    path('api/automations/', include('automations.urls')),
    path('api/whatsapp/', include('messaging.urls')),
    path('api/email/', include('messaging.email_urls')),
    path('api/stock-summary/', StockSummaryView.as_view(), name='stock-summary'),
    path('api/inventory-dashboard/', InventoryDashboardView.as_view(), name='inventory-dashboard'),
    path('api/', include(router.urls)),
    path('api/webhooks/meta-leads/', meta_leads_webhook, name='meta-leads-webhook'),
    path('api/webhooks/meta-leads', meta_leads_webhook, name='meta-leads-webhook-no-slash'),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
