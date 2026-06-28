from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import AutomationRuleViewSet

router = DefaultRouter()
router.register(r'', AutomationRuleViewSet, basename='automations')

urlpatterns = [
    path('', include(router.urls)),
]
