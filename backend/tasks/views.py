from rest_framework import viewsets, permissions
from .models import Task
from .serializers import TaskSerializer

TASK_STATUS_LABELS = {
    'todo': 'To Do',
    'in_progress': 'In Progress',
    'review': 'In Review',
    'done': 'Done',
}

class TaskViewSet(viewsets.ModelViewSet):
    queryset = Task.objects.all()
    serializer_class = TaskSerializer
    permission_classes = [permissions.IsAuthenticated]

    def paginate_queryset(self, queryset):
        # `?all=true` returns every task unpaginated (the Kanban board needs all).
        if self.request.query_params.get('all') == 'true':
            return None
        return super().paginate_queryset(queryset)

    def get_queryset(self):
        user = self.request.user
        if user.sees_everything:
            queryset = Task.objects.all().order_by('-created_at')
        elif user.is_manager:
            from django.db.models import Q
            # Teams they head + (branch managers) everyone in their branch.
            queryset = Task.objects.filter(
                Q(assignee__id__in=user.managed_user_ids()) | Q(assignee__isnull=True)
            ).distinct().order_by('-created_at')
        else:
            queryset = Task.objects.filter(assignee=user).order_by('-created_at')
        
        # Filter by "Assigned to Me"
        assigned_to_me = self.request.query_params.get('assigned_to_me')
        if assigned_to_me == 'true' or assigned_to_me == '1':
            queryset = queryset.filter(assignee=self.request.user)

        # Filter by status
        status = self.request.query_params.get('status')
        if status:
            queryset = queryset.filter(status=status)
        
        # Filter by priority
        priority = self.request.query_params.get('priority')
        if priority:
            queryset = queryset.filter(priority=priority)
        
        # Filter by assignee (by ID now)
        assignee_id = self.request.query_params.get('assignee_id')
        if assignee_id:
            queryset = queryset.filter(assignee_id=assignee_id)
        
        # Filter by linked lead
        lead_id = self.request.query_params.get('lead')
        if lead_id:
            queryset = queryset.filter(lead_id=lead_id)

        # Search
        search = self.request.query_params.get('search')
        if search:
            from django.db.models import Q
            queryset = queryset.filter(
                Q(title__icontains=search) |
                Q(description__icontains=search)
            )
        
        return queryset

    def perform_create(self, serializer):
        from leads.models import ActivityLog
        from ai_manager.models import Notification
        instance = serializer.save()
        ActivityLog.objects.create(
            activity_type='task_created',
            description=f"New task created: \"{instance.title}\"",
            actor=self.request.user,
            extra={'task_id': instance.id, 'task_title': instance.title},
        )
        # Notify the assignee via popup
        if instance.assignee and instance.assignee != self.request.user:
            Notification.objects.create(
                user=instance.assignee,
                title="📋 New Task Assigned to You",
                message=f"You have been assigned the task: \"{instance.title}\". Check your task list for details.",
                notification_type='general',
                is_popup=True,
                extra_data={'task_id': instance.id, 'task_title': instance.title},
            )

    def perform_update(self, serializer):
        from leads.models import ActivityLog
        from ai_manager.models import Notification
        old_status = serializer.instance.status
        old_assignee = serializer.instance.assignee
        instance = serializer.save()
        if 'status' in serializer.validated_data and old_status != instance.status:
            old_label = TASK_STATUS_LABELS.get(old_status, old_status)
            new_label = TASK_STATUS_LABELS.get(instance.status, instance.status)
            activity_type = 'task_completed' if instance.status == 'done' else 'task_stage_change'
            ActivityLog.objects.create(
                activity_type=activity_type,
                description=f"Task \"{instance.title}\": {old_label} → {new_label}",
                actor=self.request.user,
                extra={'task_id': instance.id, 'task_title': instance.title,
                       'old_status': old_status, 'new_status': instance.status},
            )
        # Notify the new assignee via popup if assignee changed
        new_assignee = instance.assignee
        if new_assignee and new_assignee != old_assignee and new_assignee != self.request.user:
            Notification.objects.create(
                user=new_assignee,
                title="📋 Task Assigned to You",
                message=f"You have been assigned the task: \"{instance.title}\". Check your task list for details.",
                notification_type='general',
                is_popup=True,
                extra_data={'task_id': instance.id, 'task_title': instance.title},
            )

