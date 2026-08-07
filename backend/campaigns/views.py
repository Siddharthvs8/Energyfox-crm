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

    def get_permissions(self):
        """`options` is open to anyone who can work leads.

        A tele caller filters their list by campaign, which needs the names — but
        the campaign record itself carries budget, spend and expected revenue, so
        the full endpoint stays with admins and managers and `options` returns
        nothing but the id and the name.
        """
        if self.action == 'options':
            return [permissions.IsAuthenticated()]
        return super().get_permissions()

    @action(detail=False, methods=['get'])
    def options(self, request):
        """Campaign id + name, for the campaign filter on the leads list."""
        rows = Campaign.objects.order_by('name').values('id', 'name')
        return Response(list(rows))

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
