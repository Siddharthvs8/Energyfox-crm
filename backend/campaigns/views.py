from rest_framework import viewsets, status, permissions
from core.permissions import IsAdminOrManager
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import Campaign
from .serializers import CampaignSerializer
from leads.models import Lead

class CampaignViewSet(viewsets.ModelViewSet):
    queryset = Campaign.objects.all()
    serializer_class = CampaignSerializer
    permission_classes = [IsAdminOrManager]

    @action(detail=True, methods=['post'])
    def add_leads(self, request, pk=None):
        campaign = self.get_object()
        lead_ids = request.data.get('lead_ids', [])
        
        if not isinstance(lead_ids, list):
            return Response({'error': 'lead_ids must be a list'}, status=status.HTTP_400_BAD_REQUEST)
            
        leads_to_add = Lead.objects.filter(id__in=lead_ids)
        campaign.leads.add(*leads_to_add)
        
        return Response({'status': 'leads added', 'count': leads_to_add.count()}, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'])
    def remove_leads(self, request, pk=None):
        campaign = self.get_object()
        lead_ids = request.data.get('lead_ids', [])
        
        if not isinstance(lead_ids, list):
            return Response({'error': 'lead_ids must be a list'}, status=status.HTTP_400_BAD_REQUEST)
            
        leads_to_remove = Lead.objects.filter(id__in=lead_ids)
        campaign.leads.remove(*leads_to_remove)
        
        return Response({'status': 'leads removed', 'count': leads_to_remove.count()}, status=status.HTTP_200_OK)
