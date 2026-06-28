from django.conf import settings
from organization.utils import get_org_settings
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import CallLog
from .serializers import CallLogSerializer
from leads.models import Lead
import requests
import logging

logger = logging.getLogger(__name__)

from rest_framework_simplejwt.authentication import JWTAuthentication

class QueryParamJWTAuthentication(JWTAuthentication):
    """
    Custom authentication class that allows JWT token to be passed in query params.
    Useful for HTML5 audio tags that cannot set custom headers.
    """
    def authenticate(self, request):
        # Try default header authentication first
        header_auth = super().authenticate(request)
        if header_auth:
            return header_auth

        # Try query parameter token
        token = request.query_params.get('token')
        if not token:
            return None

        try:
            validated_token = self.get_validated_token(token)
            return self.get_user(validated_token), validated_token
        except Exception:
            return None


class CallLogViewSet(viewsets.ModelViewSet):
    serializer_class = CallLogSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user

        # ── Role-based visibility ──
        # sees_all_leads roles (admin/superadmin/coo/sales & doc managers/doc staff): all calls
        # branch manager: calls of users in their branch (+ their own)
        # BDE / tele caller: only their own calls
        if user.sees_all_leads:
            queryset = CallLog.objects.all()
        elif user.branch_scoped:
            from users.models import User
            branch_user_ids = list(
                User.objects.filter(branch=user.branch, is_active=True).values_list('id', flat=True)
            )
            if user.id not in branch_user_ids:
                branch_user_ids.append(user.id)
            queryset = CallLog.objects.filter(user_id__in=branch_user_ids)
        else:
            # BDE / tele caller — own calls only
            queryset = CallLog.objects.filter(user=user)

        # ── Filters ──
        lead_id = self.request.query_params.get('lead')
        user_id = self.request.query_params.get('user')
        outcome = self.request.query_params.get('outcome')
        date_from = self.request.query_params.get('date_from')
        date_to = self.request.query_params.get('date_to')

        if lead_id:
            queryset = queryset.filter(lead_id=lead_id)
        if user_id:
            # Only allow filtering by user_id if the requester can see that user's calls
            queryset = queryset.filter(user_id=user_id)
        if outcome:
            queryset = queryset.filter(outcome=outcome)
        if date_from:
            queryset = queryset.filter(created_at__date__gte=date_from)
        if date_to:
            queryset = queryset.filter(created_at__date__lte=date_to)
        direction = self.request.query_params.get('direction')
        if direction:
            queryset = queryset.filter(direction=direction)

        return queryset


    def perform_create(self, serializer):
        """Auto-assign the current user when creating a call log manually."""
        serializer.save(user=self.request.user)

    @action(detail=False, methods=['post'])
    def initiate(self, request):
        lead_id = request.data.get('lead_id')
        try:
            lead = Lead.objects.get(id=lead_id)
        except Lead.DoesNotExist:
            return Response({'error': 'Lead not found'}, status=status.HTTP_404_NOT_FOUND)
        
        tenant = get_org_settings()
        provider = getattr(tenant, 'telephony_provider', 'voxbay')

        if provider == 'exotel':
            if not tenant.exotel_sid or not tenant.exotel_api_key or not tenant.exotel_api_token or not tenant.exotel_callerid:
                return Response({'error': 'Telephony is not configured for this workspace. Please configure Exotel settings in Workspace Settings.'}, status=status.HTTP_400_BAD_REQUEST)
        else:
            if not tenant.voxbay_callerid or (not tenant.voxbay_access_token and (not tenant.voxbay_uid or not tenant.voxbay_upin)):
                return Response({'error': 'Telephony is not configured for this workspace. Please configure Voxbay settings in Workspace Settings.'}, status=status.HTTP_400_BAD_REQUEST)

        # Get agent details and clean country code + prefix to match telephony formats
        agent_ext = request.user.voxbay_extension
        agent_phone = request.user.phone
        lead_number = lead.phone

        if lead_number:
            lead_number = lead_number.lstrip('+')

        if not lead_number:
            return Response({'error': 'Lead must have a phone number.'}, status=status.HTTP_400_BAD_REQUEST)

        if provider == 'exotel':
            if not agent_phone:
                return Response({'error': 'You must configure a Phone Number in your Team profile to start calls via Exotel.'}, status=status.HTTP_400_BAD_REQUEST)
        else:
            if not agent_ext and not agent_phone:
                return Response({'error': 'You must configure either a Phone Number or Voxbay Extension in your Team profile to start calls.'}, status=status.HTTP_400_BAD_REQUEST)

        # Construct the Click to Call API URL or initiate server-side request
        try:
            import urllib.parse
            import time

            if provider == 'exotel':
                def format_e164(phone):
                    if not phone:
                        return ''
                    phone_str = str(phone).strip()
                    if not phone_str.startswith('+'):
                        phone_str = '+' + phone_str
                    return phone_str

                agent_phone_e164 = format_e164(agent_phone)
                lead_phone_e164 = format_e164(lead.phone)
                callerid_e164 = format_e164(tenant.exotel_callerid)

                exotel_uuid = f"EXOTEL_REQ_{lead.id}_{request.user.id}_{int(time.time())}"
                subdomain = tenant.exotel_subdomain or 'api.exotel.com'
                endpoint_url = f"https://{subdomain}/v1/Accounts/{tenant.exotel_sid}/Calls/connect.json"
                auth = (tenant.exotel_api_key, tenant.exotel_api_token)

                host = request.get_host()
                # Force https — behind reverse proxy, is_secure() may return False
                status_callback_url = f"https://{host}/api/calls/webhook/exotel/"

                params = {
                    'From': agent_phone_e164,
                    'To': lead_phone_e164,
                    'CallerId': callerid_e164,
                    'CallType': 'trans',
                    'CustomField': exotel_uuid,
                    'StatusCallback': status_callback_url,
                    'StatusCallbackContentType': 'application/json',
                    'StatusCallbackEvents[0]': 'terminal',
                    'Record': 'true',
                }

                logger.info(f"[EXOTEL] Initiating call from {agent_phone_e164} to {lead_phone_e164} via ExoPhone {callerid_e164}")
                logger.info(f"[EXOTEL] StatusCallback URL: {status_callback_url}")
                response = requests.post(endpoint_url, data=params, auth=auth, timeout=15)

                if response.status_code == 200:
                    try:
                        res_data = response.json()
                        call_sid = res_data.get('Call', {}).get('Sid') or exotel_uuid
                        exotel_status = res_data.get('Call', {}).get('Status') or 'Call initiated'
                    except ValueError:
                        call_sid = exotel_uuid
                        exotel_status = response.text or 'Call initiated'
                else:
                    return Response({'error': f'Exotel API returned status code {response.status_code}: {response.text}'}, status=status.HTTP_400_BAD_REQUEST)

                # Create the initial log
                log = CallLog.objects.create(
                    lead=lead,
                    user=request.user,
                    exotel_sid=call_sid,
                    outcome='initiated',
                    notes=f'Automated click-to-call initiated server-side via Exotel. Status: {exotel_status}'
                )

                return Response({
                    'status': f'Call initiated successfully! {exotel_status}',
                    'sid': log.exotel_sid
                }, status=status.HTTP_200_OK)

            else:
                base_api_url = tenant.voxbay_api_url.rstrip('/') if tenant.voxbay_api_url else 'https://x.voxbay.com'
                
                # If using mobile phone without extension, format it as mobile-to-mobile (Format 2) and clean '+'
                source_phone = agent_phone.lstrip('+') if (agent_phone and not agent_ext) else None
                callerid = tenant.voxbay_callerid.lstrip('+') if tenant.voxbay_callerid else ''

                # Generate a temporary unique tracking ID for Voxbay
                voxbay_uuid = f"VOXBAY_REQ_{lead.id}_{request.user.id}_{int(time.time())}"

                if tenant.voxbay_access_token:
                    # If access token is present, we make a server-side API request using Bearer auth
                    headers = {
                        'token': tenant.voxbay_access_token,
                        'Authorization': f'Bearer {tenant.voxbay_access_token}'
                    }
                    params = {
                        'id_dept': '0',
                        'user_no': agent_ext or '0',
                        'destination': lead_number,
                        'callerid': callerid
                    }
                    if source_phone:
                        params['source'] = source_phone
                    if tenant.voxbay_uid:
                        params['uid'] = tenant.voxbay_uid
                    if tenant.voxbay_upin:
                        params['upin'] = tenant.voxbay_upin

                    endpoint_url = f"{base_api_url}/api/click_to_call"
                    
                    # Make the GET request with query params as shown in the successful Voxbay X Click-To-Call logs,
                    # falling back to POST if needed.
                    try:
                        response = requests.get(endpoint_url, params=params, headers=headers, timeout=10)
                        if response.status_code not in [200, 201]:
                            response = requests.post(endpoint_url, json=params, headers=headers, timeout=10)
                    except Exception:
                        response = requests.post(endpoint_url, json=params, headers=headers, timeout=10)
                    
                    if response.status_code == 200:
                        try:
                            res_data = response.json()
                            voxbay_status = res_data.get('status') or res_data.get('message') or 'Call initiated'
                        except ValueError:
                            voxbay_status = response.text or 'Call initiated'
                    else:
                        return Response({'error': f'Voxbay API returned status code {response.status_code}: {response.text}'}, status=status.HTTP_400_BAD_REQUEST)

                    # Create the initial log
                    log = CallLog.objects.create(
                        lead=lead,
                        user=request.user,
                        voxbay_uuid=voxbay_uuid,
                        outcome='initiated',
                        notes=f'Automated click-to-call initiated server-side via Voxbay. Status: {voxbay_status}'
                    )

                    return Response({
                        'status': f'Call initiated successfully! {voxbay_status}',
                        'sid': log.voxbay_uuid
                    }, status=status.HTTP_200_OK)

                else:
                    # Format legacy click to call parameters
                    params = {
                        'id_dept': '0',
                        'uid': tenant.voxbay_uid,
                        'upin': tenant.voxbay_upin,
                        'user_no': agent_ext or '0',
                        'destination': lead_number,
                        'callerid': callerid
                    }
                    if source_phone:
                        params['source'] = source_phone

                    url_params = urllib.parse.urlencode(params)
                    click_to_call_url = f"{base_api_url}/api/click_to_call?{url_params}"
                    
                    # Create the initial log
                    log = CallLog.objects.create(
                        lead=lead,
                        user=request.user,
                        voxbay_uuid=voxbay_uuid,
                        outcome='initiated',
                        notes='Automated click-to-call initiated via Voxbay.'
                    )

                    return Response({
                        'status': 'Opening Voxbay dialer...',
                        'voxbay_click_to_call_url': click_to_call_url,
                        'sid': log.voxbay_uuid
                    }, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(f"Telephony Error: {str(e)}")
            return Response({'error': f'Telephony provider error: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=False, methods=['post'])
    def sync_exotel(self, request):
        """
        Fallback: poll Exotel Call Details API for calls still stuck in 'initiated'.
        This handles cases where the webhook was missed.
        """
        tenant = get_org_settings()
        provider = getattr(tenant, 'telephony_provider', 'voxbay')

        if provider != 'exotel':
            return Response({'message': 'Not using Exotel provider.'}, status=status.HTTP_200_OK)

        if not tenant.exotel_sid or not tenant.exotel_api_key or not tenant.exotel_api_token:
            return Response({'error': 'Exotel credentials not configured.'}, status=status.HTTP_400_BAD_REQUEST)

        # Find all calls with exotel_sid that are still 'initiated'
        pending_calls = CallLog.objects.filter(
            outcome='initiated',
            exotel_sid__isnull=False,
        ).exclude(exotel_sid='').order_by('-created_at')[:20]

        synced = 0
        errors = []
        subdomain = tenant.exotel_subdomain or 'api.exotel.com'
        auth = (tenant.exotel_api_key, tenant.exotel_api_token)

        for call_log in pending_calls:
            try:
                detail_url = f"https://{subdomain}/v1/Accounts/{tenant.exotel_sid}/Calls/{call_log.exotel_sid}.json"
                resp = requests.get(detail_url, auth=auth, timeout=10)

                if resp.status_code == 200:
                    try:
                        call_data = resp.json().get('Call', {})
                    except (ValueError, AttributeError):
                        continue

                    update_kwargs = {}
                    ex_status = (call_data.get('Status') or '').lower()
                    if ex_status in ['completed', 'answered']:
                        update_kwargs['outcome'] = 'connected'
                    elif ex_status in ['no-answer', 'noanswer']:
                        update_kwargs['outcome'] = 'rnr'
                    elif ex_status in ['failed', 'busy']:
                        update_kwargs['outcome'] = 'busy'
                    elif ex_status in ['canceled', 'cancelled']:
                        update_kwargs['outcome'] = 'cancelled'
                    elif ex_status in ['in-progress', 'ringing', 'queued']:
                        # Still ongoing, skip
                        continue
                    else:
                        update_kwargs['outcome'] = 'busy'

                    # ConversationDuration is nested inside Details
                    details = call_data.get('Details') or {}
                    duration = details.get('ConversationDuration') or call_data.get('Duration') or 0
                    try:
                        update_kwargs['duration_seconds'] = int(float(duration))
                    except (ValueError, TypeError):
                        pass

                    rec_url = call_data.get('RecordingUrl') or ''
                    if rec_url:
                        update_kwargs['recording_url'] = rec_url

                    if update_kwargs:
                        for k, v in update_kwargs.items():
                            setattr(call_log, k, v)
                        call_log.save()
                        synced += 1
                        logger.info(f"[EXOTEL-SYNC] Updated CallLog id={call_log.id}: {update_kwargs}")
                else:
                    errors.append(f"CallSid {call_log.exotel_sid}: HTTP {resp.status_code}")
            except Exception as e:
                errors.append(f"CallSid {call_log.exotel_sid}: {str(e)}")

        return Response({
            'synced': synced,
            'pending_checked': len(pending_calls),
            'errors': errors[:5] if errors else [],
        }, status=status.HTTP_200_OK)

    @action(detail=True, methods=['get'], authentication_classes=[QueryParamJWTAuthentication])
    def recording_proxy(self, request, pk=None):
        """
        Proxy endpoint to stream Exotel call recordings.
        Exotel recording URLs require API key/token auth, so the browser
        can't play them directly. This endpoint fetches with auth and streams back.
        """
        try:
            call_log = CallLog.objects.get(pk=pk)
        except CallLog.DoesNotExist:
            return Response({'error': 'Call not found'}, status=status.HTTP_404_NOT_FOUND)

        if not call_log.recording_url:
            return Response({'error': 'No recording available'}, status=status.HTTP_404_NOT_FOUND)

        recording_url = call_log.recording_url

        # Check if this is an Exotel recording that needs auth
        needs_auth = 'exotel' in recording_url.lower() or 'recordings.exotel' in recording_url.lower()

        try:
            if needs_auth:
                tenant = get_org_settings()
                auth = (tenant.exotel_api_key, tenant.exotel_api_token)
                resp = requests.get(recording_url, auth=auth, stream=True, timeout=30)
            else:
                resp = requests.get(recording_url, stream=True, timeout=30)

            if resp.status_code != 200:
                return Response({'error': f'Recording fetch failed: HTTP {resp.status_code}'}, status=status.HTTP_502_BAD_GATEWAY)

            from django.http import StreamingHttpResponse
            content_type = resp.headers.get('Content-Type', 'audio/mpeg')
            response = StreamingHttpResponse(
                resp.iter_content(chunk_size=8192),
                content_type=content_type,
            )
            response['Content-Disposition'] = f'inline; filename="recording_{pk}.mp3"'
            if 'Content-Length' in resp.headers:
                response['Content-Length'] = resp.headers['Content-Length']
            return response
        except Exception as e:
            logger.error(f"Recording proxy error for call {pk}: {str(e)}")
            return Response({'error': f'Failed to fetch recording: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
