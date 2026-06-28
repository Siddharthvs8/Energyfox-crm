from rest_framework import serializers
from .models import ManagerConfig, MonthlyTarget, DailyTarget, Holiday, Meeting, Notification, DailyTargetProof
class ManagerConfigSerializer(serializers.ModelSerializer):
    class Meta:
        model = ManagerConfig
        fields = [
            'id', 'assignment_strategy', 'auto_assign_enabled', 'reminder_hour',
            'morning_meeting_time', 'evening_meeting_time', 'meeting_enabled',
            'meeting_language', 'updated_at'
        ]
        read_only_fields = ['updated_at']


class MonthlyTargetSerializer(serializers.ModelSerializer):
    agent_name = serializers.SerializerMethodField()

    class Meta:
        model = MonthlyTarget
        fields = [
            'id', 'agent', 'agent_name', 'month', 'year',
            'target_leads', 'target_amount', 'target_dialed_calls', 'target_call_time', 'created_by',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['created_by', 'created_at', 'updated_at']

    def get_agent_name(self, obj):
        if obj.agent:
            name = f"{obj.agent.first_name} {obj.agent.last_name}".strip()
            return name or obj.agent.username
        return None


class DailyTargetProofSerializer(serializers.ModelSerializer):
    class Meta:
        model = DailyTargetProof
        fields = ['id', 'daily_target', 'file', 'uploaded_at']
        read_only_fields = ['uploaded_at']


class DailyTargetSerializer(serializers.ModelSerializer):
    agent_name = serializers.SerializerMethodField()
    proofs = DailyTargetProofSerializer(many=True, read_only=True)

    class Meta:
        model = DailyTarget
        fields = [
            'id', 'monthly_target', 'agent', 'agent_name',
            'date', 'target_leads', 'target_amount', 
            'target_dialed_calls', 'target_call_time',
            'achieved_dialed_calls', 'achieved_call_time',
            'status', 'is_manual', 'proofs', 'created_at'
        ]

    def get_agent_name(self, obj):
        if obj.agent:
            name = f"{obj.agent.first_name} {obj.agent.last_name}".strip()
            return name or obj.agent.username
        return None


class HolidaySerializer(serializers.ModelSerializer):
    class Meta:
        model = Holiday
        fields = ['id', 'date', 'name', 'created_by', 'created_at']
        read_only_fields = ['created_by', 'created_at']


class MeetingSerializer(serializers.ModelSerializer):
    attendee_names = serializers.SerializerMethodField()
    created_by_name = serializers.SerializerMethodField()

    class Meta:
        model = Meeting
        fields = [
            'id', 'title', 'description', 'scheduled_at',
            'duration_minutes', 'attendees', 'attendee_names',
            'created_by', 'created_by_name', 'created_at', 'updated_at'
        ]
        read_only_fields = ['created_by', 'created_at', 'updated_at']

    def get_attendee_names(self, obj):
        names = []
        for u in obj.attendees.all():
            name = f"{u.first_name} {u.last_name}".strip()
            names.append({'id': u.id, 'name': name or u.username})
        return names

    def get_created_by_name(self, obj):
        if obj.created_by:
            name = f"{obj.created_by.first_name} {obj.created_by.last_name}".strip()
            return name or obj.created_by.username
        return None


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ['id', 'title', 'message', 'notification_type', 'is_read', 'is_popup', 'popup_shown', 'extra_data', 'created_at']
        read_only_fields = ['title', 'message', 'notification_type', 'is_popup', 'extra_data', 'created_at']
