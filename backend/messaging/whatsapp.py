"""WhatsApp Cloud API (Meta Graph) client for the EnergyFox organization."""
import re
import requests

from django.utils import timezone

from organization.utils import get_org_settings

GRAPH_BASE = 'https://graph.facebook.com/v20.0'

# One session for all sends — reuses the TLS connection, which matters when the
# queue flusher pushes hundreds of bulk messages in a row.
_session = requests.Session()


# The wholesale side may message from its own number. `channel='b2b'` picks the
# B2B credentials; blank ones fall back to the shared account, so turning it on
# is opt-in rather than all-or-nothing.
B2B = 'b2b'


def _creds(channel=None):
    org = get_org_settings()
    if channel == B2B:
        pid = (org.b2b_whatsapp_phone_number_id or '').strip()
        token = (org.b2b_whatsapp_access_token or '').strip()
        if pid and token:
            return pid, token
    return org.whatsapp_phone_number_id or '', org.whatsapp_access_token or ''


def is_configured(channel=None) -> bool:
    pid, token = _creds(channel)
    return bool(pid and token)


def normalize_number(number: str) -> str:
    """Cloud API expects digits incl. country code, no '+' or spaces."""
    return re.sub(r'\D', '', number or '')


def _post(payload: dict, channel=None) -> str:
    pid, token = _creds(channel)
    if not (pid and token):
        raise ValueError('WhatsApp is not configured for this workspace')
    resp = _session.post(
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


def send_text(to: str, body: str, channel=None) -> str:
    return _post({
        'messaging_product': 'whatsapp',
        'to': normalize_number(to),
        'type': 'text',
        'text': {'body': body or ''},
    }, channel)


def send_document(to: str, link: str, filename: str = '', caption: str = '',
                  channel=None) -> str:
    """Send a PDF (or other document) by URL.

    The Cloud API fetches the file itself, so `link` must be reachable from
    Meta's servers — a public MEDIA_URL in production. On a localhost dev server
    the send will fail at their end, which is expected.
    """
    document = {'link': link}
    if filename:
        document['filename'] = filename
    if caption:
        document['caption'] = caption
    return _post({
        'messaging_product': 'whatsapp',
        'to': normalize_number(to),
        'type': 'document',
        'document': document,
    }, channel)


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
