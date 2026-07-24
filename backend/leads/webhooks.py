"""
Meta Lead Ads Webhook Endpoint

This endpoint receives webhook notifications from Meta (Facebook/Instagram)
when a new lead form is submitted through Lead Ads.

Setup in Meta Business Suite:
1. Go to Business Settings > Integrations > Lead Access
2. Set webhook URL to: https://yourdomain.com/api/webhooks/meta-leads/
3. Subscribe to 'leadgen' events
"""
import json
import logging

from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from leads.meta_integration import MetaGraphClient, create_lead_from_meta_payload
from leads.models import IntegrationSettings

logger = logging.getLogger(__name__)

def _resolve_integration(page_id):
    """Find the Meta integration for an incoming webhook entry, by Facebook Page ID.

    Falls back to the only integration if there is exactly one, so single-account
    setups keep working without a page id configured.
    """
    if page_id:
        match = IntegrationSettings.objects.filter(meta_page_id=str(page_id)).first()
        if match:
            return match
    if IntegrationSettings.objects.count() == 1:
        return IntegrationSettings.objects.first()
    return None


@csrf_exempt
@require_http_methods(["GET", "POST"])
def meta_leads_webhook(request):
    """Handle Meta Lead Ads webhook events for any configured integration."""

    # GET request: Meta verification challenge
    if request.method == "GET":
        verify_token = request.GET.get("hub.verify_token", "")
        challenge = request.GET.get("hub.challenge", "")
        mode = request.GET.get("hub.mode", "")

        # Accept the token if it matches ANY integration's verify token.
        tokens = set(
            IntegrationSettings.objects
            .exclude(meta_verify_token__isnull=True).exclude(meta_verify_token="")
            .values_list("meta_verify_token", flat=True)
        )
        if not tokens:
            tokens = {"leadplatform_meta_webhook"}  # default until one is configured

        if mode == "subscribe" and verify_token in tokens:
            return HttpResponse(challenge, content_type="text/plain")

        return JsonResponse({"error": "Verification failed"}, status=403)

    # POST request: Incoming lead data
    if request.method == "POST":
        try:
            payload = json.loads(request.body)
            entries = payload.get("entry", [])
            leads_created = 0
            leads_skipped = 0
            errors = []

            for entry in entries:
                # `entry.id` is the Facebook Page ID — route to the right integration.
                integration = _resolve_integration(entry.get("id"))
                client = MetaGraphClient(integration.meta_access_token) if (integration and integration.meta_access_token) else None

                for change in entry.get("changes", []):
                    if change.get("field") == "leadgen":
                        lead_data = change.get("value", {})
                        try:
                            lead, duplicate = create_lead_from_meta_payload(
                                lead_data, client=client, integration=integration
                            )
                            if duplicate:
                                leads_skipped += 1
                            elif lead:
                                leads_created += 1
                        except Exception as exc:
                            errors.append(str(exc))

            return JsonResponse({
                "status": "ok",
                "leads_created": leads_created,
                "leads_skipped": leads_skipped,
                "errors": errors,
            })

        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid JSON"}, status=400)
        except Exception as e:
            # Always acknowledge with 200 — repeated non-2xx responses make Meta
            # retry the same events (duplicating work) and eventually disable
            # the webhook subscription. The failure is logged for us instead.
            logger.exception("Meta leads webhook processing failed")
            return JsonResponse({"status": "error", "error": str(e)})
