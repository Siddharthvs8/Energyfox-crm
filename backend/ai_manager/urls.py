from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r'monthly-targets', views.MonthlyTargetViewSet, basename='monthly-targets')
router.register(r'daily-targets', views.DailyTargetViewSet, basename='daily-targets')
router.register(r'holidays', views.HolidayViewSet, basename='holidays')
router.register(r'meetings', views.MeetingViewSet, basename='meetings')
router.register(r'notifications', views.NotificationViewSet, basename='notifications')

urlpatterns = [
    path('config/', views.ConfigView.as_view(), name='ai-config'),
    path('dashboard/', views.AIDashboardView.as_view(), name='ai-dashboard'),
    path('auto-assign/', views.AutoAssignView.as_view(), name='ai-auto-assign'),
    path('generate-reminders/', views.GenerateRemindersView.as_view(), name='ai-generate-reminders'),
    path('my-performance/', views.MyPerformanceView.as_view(), name='my-performance'),
    path('submit-performance/', views.SubmitDailyPerformanceView.as_view(), name='submit-performance'),
    path('proofs/<int:proof_id>/', views.DeleteDailyProofView.as_view(), name='delete-proof'),
    path('team-performance/', views.TeamPerformanceView.as_view(), name='team-performance'),
    path('popups/', views.PopupRemindersView.as_view(), name='ai-popups'),
    path('custom-reminders/', views.SendCustomReminderView.as_view(), name='ai-custom-reminders'),
    # AI Meeting Room
    path('meeting-check/', views.AIMeetingCheckView.as_view(), name='ai-meeting-check'),
    path('meeting-start/', views.AIMeetingStartView.as_view(), name='ai-meeting-start'),
    path('meeting-sessions/', views.AIMeetingSessionListView.as_view(), name='ai-meeting-sessions'),
    path('meeting-sessions/<int:session_id>/chat/', views.AIMeetingChatView.as_view(), name='ai-meeting-chat'),
    path('meeting-sessions/<int:session_id>/end/', views.AIMeetingEndView.as_view(), name='ai-meeting-end'),
    path('meeting-config/', views.AIMeetingConfigView.as_view(), name='ai-meeting-config'),
    path('force-ai-meeting/', views.ForceAIMeetingView.as_view(), name='ai-force-meeting'),
    path('', include(router.urls)),
]
