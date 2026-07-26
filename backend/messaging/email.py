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


def _config():
    """Resolved SMTP config: Settings first, then env. Returns (dict, source)."""
    org = get_org_settings()
    if (org.email_host or '').strip():
        return {
            'host': org.email_host.strip(),
            'port': org.email_port or 587,
            'username': org.email_host_user or '',
            'password': org.email_host_password or '',
            'use_tls': bool(org.email_use_tls),
            'use_ssl': bool(org.email_use_ssl),
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


def is_configured() -> bool:
    cfg, _ = _config()
    return cfg is not None


def config_status() -> dict:
    """What the UI shows: whether email is configured and where from."""
    cfg, source = _config()
    org = get_org_settings()
    return {
        'configured': cfg is not None,
        'source': source,                       # 'settings' | 'env' | 'none'
        'host': (cfg or {}).get('host', ''),
        'from_address': from_address(),
        'from_name': org.email_from_name or '',
    }


def from_address() -> str:
    """The address outgoing mail is sent from."""
    org = get_org_settings()
    return (org.email_from_address or org.email_host_user
            or getattr(settings, 'DEFAULT_FROM_EMAIL', '')
            or getattr(settings, 'EMAIL_HOST_USER', '')
            or 'no-reply@energyfox.in')


def _from_header() -> str:
    org = get_org_settings()
    addr = from_address()
    name = (org.email_from_name or '').strip()
    return f'{name} <{addr}>' if name else addr


def _connection():
    """An SMTP connection from the resolved config, or None to use the default
    backend (console in dev) so a missing config doesn't raise."""
    cfg, _ = _config()
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


def _with_signature(body: str) -> str:
    org = get_org_settings()
    sig = (org.email_signature or '').strip()
    if not sig:
        return body or ''
    return f"{(body or '').rstrip()}\n\n{sig}"


def send_and_log(*, to, subject, body, lead=None, cc=None, kind='manual',
                 created_by=None, attachments=None, html_body=None):
    """Send an email and record it in the outbox. Never raises — a failed send is
    stored with its error so the caller can report it and staff can see it."""
    from .models import EmailMessage as EmailLog

    recipients = _split_recipients(to)
    cc_list = _split_recipients(cc)
    final_body = _with_signature(body)

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
            from_email=_from_header(), to=recipients, cc=cc_list or None,
            connection=_connection(),
        )
        if html_body:
            msg.attach_alternative(html_body, 'text/html')
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


def send_test(to, created_by=None):
    """Send a "does my config work?" email from the Settings screen."""
    org = get_org_settings()
    return send_and_log(
        to=to,
        subject=f'{org.name or "EnergyFox"} CRM — test email',
        body=('This is a test email from your CRM.\n\n'
              'If you received it, outgoing email is configured correctly.'),
        kind='test', created_by=created_by,
    )
