from rest_framework import serializers
from .models import CallLog
from leads.serializers import LeadSerializer

class CallLogSerializer(serializers.ModelSerializer):
    lead_name = serializers.CharField(source='lead.__str__', read_only=True)
    lead_phone = serializers.CharField(source='lead.phone', read_only=True, default='')
    lead_source = serializers.CharField(source='lead.source', read_only=True, default='')
    user_name = serializers.SerializerMethodField()

    class Meta:
        model = CallLog
        fields = '__all__'

    def get_user_name(self, obj):
        if obj.user:
            return f"{obj.user.first_name} {obj.user.last_name}".strip() or obj.user.username
        return "Unknown"
