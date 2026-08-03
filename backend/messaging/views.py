import json
import re

from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from organization.utils import get_org_settings

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import permissions

from .models import WhatsAppMessage


def _digits(s):
    return re.sub(r'\D', '', s or '')


def _find_lead_by_number(number):
    """Match an inbound number to a lead without scanning the whole table.

    Fast path: the stored phone literally ends with the same 10 digits.
    Fallback: narrow to a small candidate set sharing the last 4 digits, then
    verify digit-by-digit (handles stored formatting like '+91 99888-77665').
    Newest lead wins when several match.
    """
    from leads.models import Lead
    d = _digits(number)
    if not d:
        return None
    tail = d[-10:]
    base = (Lead.objects.exclude(phone__isnull=True).exclude(phone='')
            .only('id', 'phone', 'first_name', 'last_name')
            .order_by('-created_at'))
    lead = base.filter(phone__endswith=tail).first()
    if lead:
        return lead
    for lead in base.filter(phone__contains=tail[-4:])[:200]:
        if _digits(lead.phone).endswith(tail):
            return lead
    return None


# Cloud API delivery receipts, in progression order — never downgrade a message
# (a late 'delivered' receipt arriving after 'read' is ignored).
_STATUS_RANK = {'pending': 0, 'sent': 1, 'delivered': 2, 'read': 3, 'failed': 4}


def _apply_status_receipt(st):
    """Update an outbound message from a webhook `statuses` entry (sent →
    delivered / read / failed, with the failure reason captured)."""
    mid = st.get('id') or ''
    new = (st.get('status') or '').lower()
    if not mid or new not in ('delivered', 'read', 'failed'):
        return
    m = WhatsAppMessage.objects.filter(provider_message_id=mid, direction='out').first()
    if m is None:
        return
    if new != 'failed' and _STATUS_RANK.get(new, 0) <= _STATUS_RANK.get(m.status, 0):
        return
    m.status = new
    if new == 'failed':
        errs = st.get('errors') or []
        if errs:
            e0 = errs[0] or {}
            m.error = str(e0.get('title') or e0.get('message') or e0)[:500]
    m.save(update_fields=['status', 'error'])


def _handle_inbound_message(msg):
    """Log one inbound message on its lead and fire the automation trigger.
    Idempotent: Meta retries webhook deliveries, so a message id we have
    already logged is skipped (no duplicate rows, no double-fired rules)."""
    mid = msg.get('id', '')
    if mid and WhatsAppMessage.objects.filter(provider_message_id=mid, direction='in').exists():
        return
    from_number = msg.get('from', '')
    mtype = msg.get('type', 'text')
    text = ''
    if mtype == 'text':
        text = (msg.get('text') or {}).get('body', '')
    elif mtype == 'button':
        text = (msg.get('button') or {}).get('text', '')
    elif mtype == 'interactive':
        inter = msg.get('interactive') or {}
        text = ((inter.get('button_reply') or inter.get('list_reply') or {}).get('title', '')) or f'[{mtype}]'
    else:
        text = f'[{mtype} message]'

    lead = _find_lead_by_number(from_number)
    WhatsAppMessage.objects.create(
        lead=lead, to_number=from_number, direction='in',
        kind='text', text=text, status='received',
        provider_message_id=mid,
    )
    if lead is not None:
        try:
            from leads.models import ActivityLog
            ActivityLog.objects.create(
                activity_type='note_added',
                description=f"WhatsApp from {lead.first_name}: {text[:200]}",
                lead=lead,
                extra={'channel': 'whatsapp', 'from': from_number},
            )
        except Exception:
            pass
        try:
            from automations.engine import fire_trigger
            fire_trigger('whatsapp_received', lead, context={'text': text, 'from': from_number})
        except Exception:
            pass


@csrf_exempt
def whatsapp_webhook(request):
    """Meta WhatsApp webhook for the active tenant (resolved by subdomain).

    GET  → verification handshake (hub.challenge).
    POST → inbound messages: log on the lead + fire `whatsapp_received`.
    """
    org = get_org_settings()

    if request.method == 'GET':
        mode = request.GET.get('hub.mode')
        token = request.GET.get('hub.verify_token')
        challenge = request.GET.get('hub.challenge', '')
        expected = org.whatsapp_verify_token or ''
        if mode == 'subscribe' and expected and token == expected:
            return HttpResponse(challenge, content_type='text/plain')
        return HttpResponse('verification failed', status=403)

    if request.method == 'POST':
        try:
            body = json.loads(request.body.decode('utf-8') or '{}')
        except Exception:
            return JsonResponse({'status': 'bad json'}, status=400)

        # One bad message must never 500 the whole webhook — Meta would retry the
        # batch (duplicating work) and eventually disable the subscription.
        for entry in body.get('entry', []) or []:
            for change in entry.get('changes', []) or []:
                value = change.get('value', {}) or {}
                for st in value.get('statuses', []) or []:
                    try:
                        _apply_status_receipt(st)
                    except Exception:
                        pass
                for msg in value.get('messages', []) or []:
                    try:
                        _handle_inbound_message(msg)
                    except Exception:
                        pass
        return JsonResponse({'status': 'ok'})

    return HttpResponse(status=405)


class WhatsAppBulkView(APIView):
    """Queue a WhatsApp message to many leads (by status / campaign / explicit ids).

    Rows are created as 'pending' and flushed (rate-limited) by
    `process_automation_queue`.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        from leads.models import Lead
        from .whatsapp import is_configured

        if not is_configured():
            return Response({'detail': 'WhatsApp is not configured for this workspace.'}, status=400)

        data = request.data or {}
        kind = data.get('kind', 'template')
        template_name = data.get('template_name', '')
        language = data.get('language', 'en_US')
        var_fields = data.get('variables', []) or []   # list of lead field names
        text_tpl = data.get('text', '')

        if kind == 'template' and not template_name:
            return Response({'detail': 'template_name is required for template messages.'}, status=400)

        qs = Lead.objects.exclude(phone__isnull=True).exclude(phone='')
        status_f = data.get('status')
        if status_f and status_f != 'all':
            qs = qs.filter(status=status_f)
        campaign_id = data.get('campaign_id')
        if campaign_id:
            qs = qs.filter(campaigns__id=campaign_id)
        lead_ids = data.get('lead_ids')
        if lead_ids:
            qs = qs.filter(id__in=lead_ids)

        qs = qs.distinct()[:1000]  # safety cap

        def render(tpl, lead):
            return re.sub(r'\{\{\s*(\w+)\s*\}\}', lambda m: str(getattr(lead, m.group(1), '') or ''), tpl or '')

        rows = []
        for lead in qs:
            rows.append(WhatsAppMessage(
                lead=lead, to_number=lead.phone, direction='out', kind=kind,
                template_name=template_name, language=language,
                text=render(text_tpl, lead) if kind == 'text' else '',
                variables=[str(getattr(lead, f, '') or '') for f in var_fields] if kind == 'template' else [],
                status='pending', created_by=request.user if request.user.is_authenticated else None,
            ))
        WhatsAppMessage.objects.bulk_create(rows)
        return Response({'queued': len(rows)})


class WhatsAppSendView(APIView):
    """Send a single WhatsApp message to a lead right now (interactive use)."""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        from leads.models import Lead
        from .whatsapp import is_configured, send_and_log
        if not is_configured():
            return Response({'detail': 'WhatsApp is not configured for this workspace.'}, status=400)
        data = request.data or {}
        lead = None
        to = data.get('to')
        lead_id = data.get('lead_id')
        if lead_id:
            lead = Lead.objects.filter(id=lead_id).first()
            if lead and not to:
                to = lead.phone
        if not to:
            return Response({'detail': 'No destination number.'}, status=400)
        kind = data.get('kind', 'text')
        msg = send_and_log(
            to=to, lead=lead, kind=kind, text=data.get('text', ''),
            template_name=data.get('template_name', ''), language=data.get('language', 'en_US'),
            variables=data.get('variables') or [],
            created_by=request.user if request.user.is_authenticated else None,
        )
        ok = msg.status == 'sent'
        return Response({'id': msg.id, 'status': msg.status, 'error': msg.error}, status=200 if ok else 400)


class WhatsAppMessagesView(APIView):
    """Recent WhatsApp messages (for a lead, or the latest across the workspace)."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        qs = WhatsAppMessage.objects.all()
        lead_id = request.query_params.get('lead')
        if lead_id:
            qs = qs.filter(lead_id=lead_id)
        rows = qs[:100]
        return Response([{
            'id': m.id, 'lead': m.lead_id, 'direction': m.direction, 'kind': m.kind,
            'text': m.text, 'template_name': m.template_name, 'to_number': m.to_number,
            'status': m.status, 'error': m.error,
            'created_at': timezone.localtime(m.created_at).isoformat(),
        } for m in rows])


# ── Email ────────────────────────────────────────────────────────────────────
class EmailStatusView(APIView):
    """Whether outgoing email is configured, and from where (Settings vs env)."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        from .email import config_status
        # ?channel=b2b reports the wholesale account rather than the shared one.
        return Response(config_status(request.query_params.get('channel') or None))


class EmailSendView(APIView):
    """Send an email now — to a lead, or to an explicit address."""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        from leads.models import Lead
        from .email import send_and_log

        data = request.data or {}
        lead = None
        to = data.get('to')
        lead_id = data.get('lead_id')
        if lead_id:
            lead = Lead.objects.filter(id=lead_id).first()
            if lead and not to:
                to = lead.email
        if not to:
            return Response({'detail': 'No recipient address.'}, status=400)
        subject = (data.get('subject') or '').strip()
        if not subject:
            return Response({'detail': 'A subject is required.'}, status=400)

        log = send_and_log(
            to=to, subject=subject, body=data.get('body', ''), lead=lead,
            cc=data.get('cc'), kind=data.get('kind') or 'manual',
            created_by=request.user if request.user.is_authenticated else None,
        )
        ok = log.status == 'sent'
        # Emails to a customer belong in that customer's history.
        if ok and lead is not None:
            try:
                from leads.models import ActivityLog
                ActivityLog.objects.create(
                    activity_type='note_added',
                    description=f"Email sent to {log.to_email}: {log.subject}",
                    actor=request.user if request.user.is_authenticated else None,
                    lead=lead, extra={'channel': 'email'})
            except Exception:
                pass
        return Response({'id': log.id, 'status': log.status, 'error': log.error},
                        status=200 if ok else 400)


class EmailTestView(APIView):
    """Send a test email to verify the SMTP settings. Admins only."""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        if not request.user.is_staff:
            return Response({'detail': 'Only admins can send a test email.'}, status=403)
        from .email import send_test, from_address
        to = (request.data or {}).get('to') or request.user.email
        if not to:
            return Response({'detail': 'No address to send the test to — add one to your profile.'},
                            status=400)
        channel = (request.data or {}).get('channel') or None
        log = send_test(to, created_by=request.user, channel=channel)
        ok = log.status == 'sent'
        return Response({'status': log.status, 'to': log.to_email,
                         'from': from_address(channel), 'error': log.error},
                        status=200 if ok else 400)


class EmailMessagesView(APIView):
    """Recent emails (for a lead, or the latest across the workspace)."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        from .models import EmailMessage as EmailLog
        qs = EmailLog.objects.all()
        lead_id = request.query_params.get('lead')
        if lead_id:
            qs = qs.filter(lead_id=lead_id)
        return Response([{
            'id': m.id, 'lead': m.lead_id, 'to_email': m.to_email, 'cc': m.cc,
            'subject': m.subject, 'body': m.body, 'kind': m.kind,
            'status': m.status, 'error': m.error,
            'created_by': m.created_by_id,
            'created_at': timezone.localtime(m.created_at).isoformat(),
        } for m in qs[:100]])
