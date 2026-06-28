"""WhatsApp Cloud API (Meta Graph) client for the EnergyFox organization."""
import re
import requests

from django.utils import timezone

from organization.utils import get_org_settings

GRAPH_BASE = 'https://graph.facebook.com/v20.0'


def _creds():
    org = get_org_settings()
    return org.whatsapp_phone_number_id or '', org.whatsapp_access_token or ''


def is_configured() -> bool:
    pid, token = _creds()
    return bool(pid and token)


def normalize_number(number: str) -> str:
    """Cloud API expects digits incl. country code, no '+' or spaces."""
    return re.sub(r'\D', '', number or '')


def _post(payload: dict) -> str:
    pid, token = _creds()
    if not (pid and token):
        raise ValueError('WhatsApp is not configured for this workspace')
    resp = requests.post(
        f'{GRAPH_BASE}/{pid}/messages',
        json=payload,
        headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'},
        timeout=15,
    )
    data = {}
    try:
        data = resp.json()
    except Exception:
        pass
    if resp.status_code >= 400:
        err = (data.get('error') or {}).get('message') or resp.text
        raise ValueError(f'WhatsApp API error ({resp.status_code}): {err}')
    return ((data.get('messages') or [{}])[0] or {}).get('id', '')


def send_text(to: str, body: str) -> str:
    return _post({
        'messaging_product': 'whatsapp',
        'to': normalize_number(to),
        'type': 'text',
        'text': {'body': body or ''},
    })


def send_template(to: str, template_name: str, language: str = 'en_US', variables=None) -> str:
    components = []
    if variables:
        components = [{
            'type': 'body',
            'parameters': [{'type': 'text', 'text': str(v)} for v in variables],
        }]
    return _post({
        'messaging_product': 'whatsapp',
        'to': normalize_number(to),
        'type': 'template',
        'template': {
            'name': template_name,
            'language': {'code': language or 'en_US'},
            'components': components,
        },
    })


def send_and_log(*, to, lead=None, kind='text', text='', template_name='',
                 language='en_US', variables=None, created_by=None):
    """Send a WhatsApp message and record it in the outbox (status sent/failed)."""
    from .models import WhatsAppMessage
    msg = WhatsAppMessage(
        lead=lead, to_number=to or '', direction='out', kind=kind,
        text=text or '', template_name=template_name or '', language=language or 'en_US',
        variables=variables or [], created_by=created_by, status='pending',
    )
    try:
        if not (to and normalize_number(to)):
            raise ValueError('No destination number')
        if kind == 'template':
            mid = send_template(to, template_name, language, variables)
        else:
            mid = send_text(to, text)
        msg.status = 'sent'
        msg.provider_message_id = mid
        msg.sent_at = timezone.now()
    except Exception as e:
        msg.status = 'failed'
        msg.error = str(e)[:500]
    msg.save()
    return msg
