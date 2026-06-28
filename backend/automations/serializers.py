from rest_framework import serializers
from .models import AutomationRule, AutomationLog


class AutomationRuleSerializer(serializers.ModelSerializer):
    created_by_name = serializers.SerializerMethodField()
    trigger_event_display = serializers.SerializerMethodField()
    logs_count = serializers.SerializerMethodField()

    class Meta:
        model = AutomationRule
        fields = [
            'id', 'name', 'description', 'is_active', 'priority',
            'trigger_event', 'trigger_event_display', 'trigger_config',
            'condition_logic', 'conditions', 'actions',
            'max_executions_per_hour', 'cooldown_seconds',
            'execution_count', 'success_count', 'failure_count',
            'last_executed_at', 'created_by', 'created_by_name',
            'logs_count', 'created_at', 'updated_at',
        ]
        read_only_fields = [
            'execution_count', 'success_count', 'failure_count',
            'last_executed_at', 'created_by', 'created_by_name',
            'trigger_event_display', 'logs_count', 'created_at', 'updated_at',
        ]

    def get_created_by_name(self, obj):
        if obj.created_by:
            name = f"{obj.created_by.first_name} {obj.created_by.last_name}".strip()
            return name or obj.created_by.username
        return None

    def get_trigger_event_display(self, obj):
        return obj.get_trigger_event_display()

    def get_logs_count(self, obj):
        return obj.logs.count()


class AutomationLogSerializer(serializers.ModelSerializer):
    rule_name = serializers.CharField(source='rule.name', read_only=True)

    class Meta:
        model = AutomationLog
        fields = [
            'id', 'rule', 'rule_name', 'trigger_event',
            'trigger_object_type', 'trigger_object_id', 'trigger_data',
            'conditions_matched', 'actions_executed',
            'status', 'error_message', 'execution_time_ms',
            'created_at',
        ]
        read_only_fields = fields
