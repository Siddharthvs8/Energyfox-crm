"""Email sending for the CRM.

SMTP credentials come from Settings (``OrgSettings.email_*``) so an admin can
configure email in the UI like the WhatsApp integration. If no host is set there
we fall back to the ``EMAIL_*`` env settings, and finally to whatever backend
Django is configured with (the console backend in dev) — so email never hard-fails
a request.

Every send is recorded in the ``EmailMessage`` outbox with its status.
"""
import re

from django.conf import settings
from django.core.mail import EmailMultiAlternatives, get_connection
from django.utils import timezone

from organization.utils import get_org_settings


# The wholesale side may trade under its own identity. `channel='b2b'` picks the
# B2B account; any B2B field left blank falls back to the shared one, so turning
# it on is opt-in per credential rather than all-or-nothing.
B2B = 'b2b'


def _org_field(org, channel, name):
    """Read `name` for this channel, falling back to the shared setting."""
    if channel == B2B:
        value = getattr(org, f'b2b_{name}', '')
        if str(value).strip():
            return value
    return getattr(org, name, '')


def _config(channel=None):
    """Resolved SMTP config: Settings first, then env. Returns (dict, source)."""
    org = get_org_settings()
    host = _org_field(org, channel, 'email_host')
    if (host or '').strip():
        prefix = 'b2b_' if (channel == B2B and (getattr(org, 'b2b_email_host', '') or '').strip()) else ''
        return {
            'host': host.strip(),
            'port': getattr(org, f'{prefix}email_port') or 587,
            'username': getattr(org, f'{prefix}email_host_user') or '',
            'password': getattr(org, f'{prefix}email_host_password') or '',
            'use_tls': bool(getattr(org, f'{prefix}email_use_tls')),
            'use_ssl': bool(getattr(org, f'{prefix}email_use_ssl')),
        }, 'settings'
    if getattr(settings, 'EMAIL_HOST', ''):
        return {
            'host': settings.EMAIL_HOST,
            'port': getattr(settings, 'EMAIL_PORT', 587),
            'username': getattr(settings, 'EMAIL_HOST_USER', ''),
            'password': getattr(settings, 'EMAIL_HOST_PASSWORD', ''),
            'use_tls': getattr(settings, 'EMAIL_USE_TLS', True),
            'use_ssl': getattr(settings, 'EMAIL_USE_SSL', False),
        }, 'env'
    return None, 'none'


def is_configured(channel=None) -> bool:
    cfg, _ = _config(channel)
    return cfg is not None


def config_status(channel=None) -> dict:
    """What the UI shows: whether email is configured and where from."""
    cfg, source = _config(channel)
    org = get_org_settings()
    return {
        'configured': cfg is not None,
        'source': source,                       # 'settings' | 'env' | 'none'
        'host': (cfg or {}).get('host', ''),
        'from_address': from_address(channel),
        'from_name': _org_field(org, channel, 'email_from_name') or '',
    }


def from_address(channel=None) -> str:
    """The address outgoing mail is sent from."""
    org = get_org_settings()
    return (_org_field(org, channel, 'email_from_address')
            or _org_field(org, channel, 'email_host_user')
            or getattr(settings, 'DEFAULT_FROM_EMAIL', '')
            or getattr(settings, 'EMAIL_HOST_USER', '')
            or 'no-reply@energyfox.in')


def _from_header(channel=None) -> str:
    org = get_org_settings()
    addr = from_address(channel)
    name = (_org_field(org, channel, 'email_from_name') or '').strip()
    return f'{name} <{addr}>' if name else addr


def _connection(channel=None):
    """An SMTP connection from the resolved config, or None to use the default
    backend (console in dev) so a missing config doesn't raise."""
    cfg, _ = _config(channel)
    if not cfg:
        return None
    return get_connection(
        backend='django.core.mail.backends.smtp.EmailBackend',
        host=cfg['host'], port=cfg['port'],
        username=cfg['username'] or None, password=cfg['password'] or None,
        use_tls=cfg['use_tls'], use_ssl=cfg['use_ssl'],
        fail_silently=False,
    )


def _split_recipients(value):
    """Accept a list, or a comma/semicolon separated string."""
    if not value:
        return []
    if isinstance(value, (list, tuple, set)):
        items = list(value)
    else:
        items = re.split(r'[,;]+', str(value))
    return [x.strip() for x in items if str(x).strip()]


def _with_signature(body: str, channel=None) -> str:
    org = get_org_settings()
    sig = (_org_field(org, channel, 'email_signature') or '').strip()
    if not sig:
        return body or ''
    return f"{(body or '').rstrip()}\n\n{sig}"


def _as_html(text: str) -> str:
    """Plain text as an HTML fragment — escaped, with the line breaks kept."""
    from django.utils.html import escape
    return escape(text or '').replace('\n', '<br>')


def _signature_html(channel=None) -> str:
    """The signature for the HTML part.

    The HTML signature if one is set, otherwise the plain one turned into HTML so
    the two parts of the message say the same thing.
    """
    org = get_org_settings()
    html = (_org_field(org, channel, 'email_signature_html') or '').strip()
    if html:
        return html
    plain = (_org_field(org, channel, 'email_signature') or '').strip()
    return _as_html(plain) if plain else ''


def _html_alternative(body: str, html_body: str | None, channel=None) -> str:
    """The text/html part to send, or '' for none.

    A caller that built its own HTML gets the signature appended to it. A caller
    that only wrote plain text still gets an HTML part when an HTML signature is
    configured — otherwise that signature would be set up and never seen.
    """
    sig = _signature_html(channel)
    if html_body:
        return f'{html_body}<br><br>{sig}' if sig else html_body
    org = get_org_settings()
    if not (_org_field(org, channel, 'email_signature_html') or '').strip():
        # Nothing richer than the plain text to show, so stay a plain-text mail.
        return ''
    return f'<div>{_as_html((body or "").rstrip())}<br><br>{sig}</div>'


def send_and_log(*, to, subject, body, lead=None, cc=None, kind='manual',
                 created_by=None, attachments=None, html_body=None, channel=None):
    """Send an email and record it in the outbox. Never raises — a failed send is
    stored with its error so the caller can report it and staff can see it."""
    from .models import EmailMessage as EmailLog

    recipients = _split_recipients(to)
    cc_list = _split_recipients(cc)
    final_body = _with_signature(body, channel)
    final_html = _html_alternative(body, html_body, channel)

    log = EmailLog(
        lead=lead, to_email=', '.join(recipients)[:254], cc=', '.join(cc_list)[:500],
        subject=(subject or '')[:255], body=final_body, kind=kind,
        created_by=created_by, status='pending',
    )
    try:
        if not recipients:
            raise ValueError('No recipient address')
        msg = EmailMultiAlternatives(
            subject=subject or '', body=final_body,
            from_email=_from_header(channel), to=recipients, cc=cc_list or None,
            connection=_connection(channel),
        )
        if final_html:
            msg.attach_alternative(final_html, 'text/html')
        for att in (attachments or []):
            # (filename, content, mimetype)
            msg.attach(*att)
        msg.send(fail_silently=False)
        log.status = 'sent'
        log.sent_at = timezone.now()
    except Exception as e:
        log.status = 'failed'
        log.error = str(e)[:1000]
    log.save()
    return log


def send_test(to, created_by=None, channel=None):
    """Send a "does my config work?" email from the Settings screen."""
    org = get_org_settings()
    side = ' (B2B)' if channel == B2B else ''
    return send_and_log(
        to=to, channel=channel,
        subject=f'{org.name or "EnergyFox"} CRM{side} — test email',
        body=('This is a test email from your CRM.\n\n'
              'If you received it, outgoing email is configured correctly.'),
        kind='test', created_by=created_by,
    )
