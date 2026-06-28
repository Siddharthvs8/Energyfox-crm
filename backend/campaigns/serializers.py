from rest_framework import serializers
from .models import Campaign

class CampaignSerializer(serializers.ModelSerializer):
    leads_count = serializers.SerializerMethodField()

    class Meta:
        model = Campaign
        fields = [
            'id', 'name', 'campaign_type', 'status', 'start_date', 'end_date',
            'expected_revenue', 'budgeted_cost', 'actual_cost', 'expected_response',
            'number_sent', 'description', 'leads', 'leads_count', 
            'created_at', 'updated_at'
        ]
        read_only_fields = ['leads_count', 'created_at', 'updated_at']

    def get_leads_count(self, obj):
        return obj.leads.count()
