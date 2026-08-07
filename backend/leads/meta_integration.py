import json
import logging
import urllib.parse
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any

from django.conf import settings
from django.db import transaction
from django.db.models import Count, Max, Q
from django.utils import timezone

from campaigns.models import Campaign
from leads.models import ActivityLog, IntegrationSettings, Lead

logger = logging.getLogger(__name__)


META_API_VERSION = getattr(settings, "META_GRAPH_API_VERSION", "v23.0")
META_API_BASE = f"https://graph.facebook.com/{META_API_VERSION}"


@dataclass
class MetaImportResult:
    imported: int = 0
    skipped: int = 0
    campaigns: dict[str, int] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "imported": self.imported,
            "skipped": self.skipped,
            "campaigns": self.campaigns,
            "errors": self.errors,
        }


class MetaAPIError(Exception):
    pass


class MetaGraphClient:
    def __init__(self, access_token: str):
        self.access_token = access_token
        # Campaign id → name, so an import of N leads from one campaign costs
        # one Graph API call instead of N.
        self._campaign_name_cache: dict[str, str] = {}

    def _fetch_url(self, url: str) -> dict[str, Any]:
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=20) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            try:
                meta_error = json.loads(body).get("error", {})
                message = meta_error.get("message") or body
                code = meta_error.get("code")
                subcode = meta_error.get("error_subcode")
                details = f"Meta API Error {exc.code}: {message}"
                if code:
                    details += f" (code {code}"
                    if subcode:
                        details += f", subcode {subcode}"
                    details += ")"
            except json.JSONDecodeError:
                details = f"Meta API Error {exc.code}: {body or exc.reason}"
            raise MetaAPIError(details) from exc
        except Exception as exc:
            raise MetaAPIError(str(exc)) from exc

    def get(self, path: str, params: dict[str, Any] | None = None, token: str | None = None) -> dict[str, Any]:
        clean_path = path.lstrip("/")
        query = {"access_token": token or self.access_token}
        if params:
            query.update({k: v for k, v in params.items() if v not in (None, "")})
        return self._fetch_url(f"{META_API_BASE}/{clean_path}?{urllib.parse.urlencode(query)}")

    def get_all_pages(self, path: str, params: dict[str, Any] | None = None, token: str | None = None) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        data = self.get(path, params=params, token=token)
        results.extend(data.get("data", []))

        next_url = data.get("paging", {}).get("next")
        while next_url:
            data = self._fetch_url(next_url)
            results.extend(data.get("data", []))
            next_url = data.get("paging", {}).get("next")

        return results


def normalize_meta_field_data(field_data: list[dict[str, Any]]) -> dict[str, str]:
    values: dict[str, str] = {}
    for field in field_data or []:
        name = (field.get("name") or "").lower()
        raw_values = field.get("values") or []
        value = str(raw_values[0]).strip() if raw_values else ""
        if value:
            values[name] = value

    full_name = values.get("full_name") or values.get("name") or ""
    first_name = values.get("first_name") or full_name or "Meta Lead"
    last_name = values.get("last_name") or ""

    if full_name and not values.get("first_name") and " " in full_name:
        first_name, last_name = full_name.split(" ", 1)

    # Only a question that actually asks for the district. Meta's built-in `city`
    # is a different thing and is not filed as one.
    district = values.get("district") or values.get("dist") or ""

    return {
        "first_name": first_name[:100],
        "last_name": last_name[:100],
        "email": values.get("email", "")[:254],
        "phone": (values.get("phone_number") or values.get("phone") or values.get("mobile_number") or "")[:20],
        "company": (values.get("company_name") or values.get("company") or "")[:200],
        "district": district[:100],
    }


def _same_name(candidate: str, other: str) -> bool:
    """Whether two names are the same once whitespace and case are ignored.

    Compared at the length the Lead columns hold, so a name that was truncated on
    the way in still matches the label it came from.
    """
    def norm(value: str) -> str:
        return " ".join((value or "").split()).casefold()[:100]

    return bool(norm(candidate)) and norm(candidate) == norm(other)


def is_ad_metadata_name(person_name: str, *labels: str) -> bool:
    """True when a lead's "name" is really the ad's, the form's or the campaign's.

    Meta hands the campaign, ad and form names back on the same payload as the
    lead. When one of those ends up in the name field, every lead in the batch
    arrives called the same thing — which is a label, not a customer, and no use
    to whoever has to ring them.
    """
    return any(_same_name(person_name, label) for label in labels)


def get_or_create_meta_campaign(meta_campaign_id: str, meta_campaign_name: str) -> Campaign | None:
    if not meta_campaign_id and not meta_campaign_name:
        return None

    campaign_name = meta_campaign_name or f"Meta Campaign {meta_campaign_id}"
    query = Q(name=campaign_name)
    if meta_campaign_id:
        query |= Q(description__icontains=f"Meta Campaign ID: {meta_campaign_id}")

    campaign = Campaign.objects.filter(query).first()
    if campaign:
        return campaign

    return Campaign.objects.create(
        name=campaign_name,
        campaign_type="advertisement",
        status="active",
        description=f"Auto-created from Meta Ads. Meta Campaign ID: {meta_campaign_id or 'unknown'}",
    )


def find_meta_campaign(meta_campaign_id: str, meta_campaign_name: str) -> Campaign | None:
    if not meta_campaign_id and not meta_campaign_name:
        return None

    query = Q()
    if meta_campaign_name:
        query |= Q(name=meta_campaign_name)
    if meta_campaign_id:
        query |= Q(description__icontains=f"Meta Campaign ID: {meta_campaign_id}")

    return Campaign.objects.filter(query).first()


def fetch_campaign_name(client: MetaGraphClient, campaign_id: str) -> str:
    if not campaign_id:
        return ""
    cache = getattr(client, "_campaign_name_cache", None)
    if cache is not None and campaign_id in cache:
        return cache[campaign_id]
    try:
        campaign_data = client.get(campaign_id, params={"fields": "name"})
        name = campaign_data.get("name", "")
    except MetaAPIError:
        logger.exception("Failed to fetch Meta campaign %s", campaign_id)
        # Cache the miss too — one failing campaign must not cost a Graph call per lead.
        name = ""
    if cache is not None:
        cache[campaign_id] = name
    return name


def create_lead_from_meta_payload(
    lead_payload: dict[str, Any],
    client: MetaGraphClient | None = None,
    actor=None,
    integration: "IntegrationSettings | None" = None,
    skip_duplicate_check: bool = False,
) -> tuple[Lead | None, bool]:
    meta_lead_id = str(lead_payload.get("id") or lead_payload.get("leadgen_id") or "").strip()
    if not meta_lead_id:
        return None, False

    # Bulk imports pre-check duplicates in one query and pass skip_duplicate_check.
    if not skip_duplicate_check and Lead.objects.filter(meta_lead_id=meta_lead_id).exists():
        return None, True

    graph_data = lead_payload
    if client and "field_data" not in graph_data:
        graph_data = client.get(
            meta_lead_id,
            params={"fields": "id,created_time,field_data,campaign_id,campaign_name,ad_id,ad_name,form_id"},
    )

    names = normalize_meta_field_data(graph_data.get("field_data", []))
    if not graph_data.get("field_data"):
        # Only `full_name`: a Meta *lead* has no `name` of its own, so a `name` on
        # this payload belongs to the form, the ad or the campaign that came back
        # with it. Reading it named every lead in the batch after the ad.
        full_name = graph_data.get("full_name") or ""
        fallback_first = graph_data.get("first_name") or full_name
        fallback_last = graph_data.get("last_name") or ""
        if full_name and not graph_data.get("first_name") and " " in full_name:
            fallback_first, fallback_last = full_name.split(" ", 1)
        names.update(
            {
                "first_name": (fallback_first or names["first_name"])[:100],
                "last_name": (fallback_last or names["last_name"])[:100],
                "email": (graph_data.get("email") or names["email"])[:254],
                "phone": (graph_data.get("phone_number") or graph_data.get("phone") or names["phone"])[:20],
                "company": (graph_data.get("company_name") or graph_data.get("company") or names["company"])[:200],
                "district": (graph_data.get("district") or names["district"])[:100],
            }
        )
    meta_campaign_id = str(graph_data.get("campaign_id") or lead_payload.get("campaign_id") or "").strip()
    meta_campaign_name = str(graph_data.get("campaign_name") or lead_payload.get("campaign_name") or "").strip()

    if client and meta_campaign_id and not meta_campaign_name:
        meta_campaign_name = fetch_campaign_name(client, meta_campaign_id)

    # A name that is really the ad's, the form's or the campaign's is worse than
    # no name: it is the same for every lead in the batch, and it looks like a
    # customer. The campaign is still recorded on the lead either way, so nothing
    # is lost by refusing it here.
    ad_name = str(graph_data.get("ad_name") or lead_payload.get("ad_name") or "").strip()
    form_name = str(graph_data.get("form_name") or lead_payload.get("form_name") or "").strip()
    person_name = f"{names['first_name']} {names['last_name']}".strip()
    if is_ad_metadata_name(person_name, meta_campaign_name, ad_name, form_name):
        logger.warning(
            "Meta lead %s arrived named after its own campaign/ad (%r) — filed without a name.",
            meta_lead_id, person_name,
        )
        names["first_name"], names["last_name"] = "Meta Lead", ""

    with transaction.atomic():
        lead = Lead.objects.create(
            first_name=names["first_name"],
            last_name=names["last_name"],
            email=names["email"],
            phone=names["phone"],
            company=names["company"],
            district=names["district"],
            source="meta_ads",
            status="new",
            meta_lead_id=meta_lead_id,
            meta_campaign_id=meta_campaign_id,
            meta_campaign_name=meta_campaign_name,
            meta_integration=integration,
        )

        campaign = get_or_create_meta_campaign(meta_campaign_id, meta_campaign_name)
        if campaign:
            campaign.leads.add(lead)

        ActivityLog.objects.create(
            activity_type="meta_import",
            description=f"Imported Meta lead: {lead.first_name} {lead.last_name}".strip(),
            actor=actor,
            lead=lead,
            extra={
                "meta_lead_id": meta_lead_id,
                "meta_campaign_id": meta_campaign_id,
                "meta_campaign_name": meta_campaign_name,
            },
        )

    try:
        from automations.engine import fire_trigger

        fire_trigger("lead_created", lead)
    except Exception:
        logger.exception("Automation fire_trigger failed on Meta lead #%s", lead.pk)

    return lead, False


def import_meta_leads(settings_obj: IntegrationSettings, actor=None, page_id: str = "", form_id: str = "", limit: int = 100) -> MetaImportResult:
    result = MetaImportResult()
    if not settings_obj.meta_access_token:
        result.errors.append("Meta access token is not configured.")
        return result

    client = MetaGraphClient(settings_obj.meta_access_token)
    lead_fields = "id,created_time,field_data,campaign_id,campaign_name,ad_id,ad_name,form_id"
    limit = max(1, min(int(limit or 100), 500))

    try:
        leads: list[dict[str, Any]] = []

        form_id = form_id or settings_obj.meta_form_id or ""
        page_id = page_id or settings_obj.meta_page_id or ""

        if form_id:
            leads.extend(client.get_all_pages(f"{form_id}/leads", params={"fields": lead_fields, "limit": limit}))
        elif page_id:
            try:
                forms = client.get_all_pages(
                    f"{page_id}/leadgen_forms",
                    params={"fields": f"id,name,leads.limit({limit}){{{lead_fields}}}", "limit": 100},
                )
                for form in forms:
                    leads.extend(form.get("leads", {}).get("data", []))
            except MetaAPIError as exc:
                logger.warning(
                    "Failed to fetch leadgen_forms for page %s: %s. "
                    "Falling back to token-based discovery. "
                    "Ensure the token has 'leads_retrieval' and 'pages_manage_ads' permissions.",
                    page_id, exc,
                )
                leads = _discover_leads_from_token(client, lead_fields, limit)
        else:
            leads = _discover_leads_from_token(client, lead_fields, limit)

        # One query for the whole batch instead of an exists() per payload —
        # re-imports are almost entirely duplicates, so this is the hot path.
        payload_ids = {str(p.get("id") or p.get("leadgen_id") or "").strip() for p in leads}
        payload_ids.discard("")
        existing_ids = set(
            Lead.objects.filter(meta_lead_id__in=payload_ids).values_list("meta_lead_id", flat=True)
        )

        for lead_payload in leads:
            meta_lead_id = str(lead_payload.get("id") or lead_payload.get("leadgen_id") or "").strip()
            if meta_lead_id and meta_lead_id in existing_ids:
                result.skipped += 1
                continue
            try:
                lead, duplicate = create_lead_from_meta_payload(
                    lead_payload, client=client, actor=actor, integration=settings_obj,
                    skip_duplicate_check=True)
                if duplicate:
                    result.skipped += 1
                    continue
                if lead:
                    result.imported += 1
                    if meta_lead_id:
                        existing_ids.add(meta_lead_id)  # same lead twice in one batch
                    campaign_key = lead.meta_campaign_name or lead.meta_campaign_id or "Uncategorized"
                    result.campaigns[campaign_key] = result.campaigns.get(campaign_key, 0) + 1
            except Exception as exc:
                logger.exception("Failed to import Meta lead payload")
                result.errors.append(str(exc))

    except MetaAPIError as exc:
        result.errors.append(str(exc))

    return result


def _discover_leads_from_token(client: MetaGraphClient, lead_fields: str, limit: int) -> list[dict[str, Any]]:
    leads: list[dict[str, Any]] = []

    try:
        forms = client.get_all_pages(
            "me/leadgen_forms",
            params={"fields": f"id,name,leads.limit({limit}){{{lead_fields}}}", "limit": 100},
        )
        for form in forms:
            leads.extend(form.get("leads", {}).get("data", []))
        if leads:
            return leads
    except MetaAPIError:
        logger.info("Token does not expose /me/leadgen_forms; trying page discovery.")

    try:
        accounts = client.get_all_pages("me/accounts", params={"fields": "id,name,access_token", "limit": 100})
        for account in accounts:
            page_token = account.get("access_token") or client.access_token
            forms = client.get_all_pages(
                f"{account['id']}/leadgen_forms",
                params={"fields": f"id,name,leads.limit({limit}){{{lead_fields}}}", "limit": 100},
                token=page_token,
            )
            for form in forms:
                leads.extend(form.get("leads", {}).get("data", []))
    except MetaAPIError:
        logger.info("Token does not expose /me/accounts; page-level discovery unavailable.")

    if not leads:
        raise MetaAPIError(
            "Could not discover lead forms. Your Page Access Token may lack the "
            "'leads_retrieval' or 'pages_show_list' permissions. "
            "Please enter a specific Lead Form ID, or regenerate your token with "
            "the required permissions in Meta Business Suite."
        )

    return leads


def meta_summary() -> dict[str, Any]:
    connected = IntegrationSettings.objects.exclude(meta_access_token__isnull=True).exclude(meta_access_token="").exists()
    meta_leads = Lead.objects.filter(source="meta_ads")

    campaign_rows = (
        meta_leads.values("meta_campaign_id", "meta_campaign_name")
        .annotate(leads_count=Count("id"), last_import=Max("created_at"))
        .order_by("-last_import")
    )

    campaigns = []
    for row in campaign_rows:
        name = row["meta_campaign_name"] or (
            f"Meta Campaign {row['meta_campaign_id']}" if row["meta_campaign_id"] else "Uncategorized"
        )
        linked_campaign = find_meta_campaign(row["meta_campaign_id"] or "", row["meta_campaign_name"] or "")
        campaigns.append(
            {
                "id": linked_campaign.id if linked_campaign else None,
                "name": name,
                "meta_campaign_id": row["meta_campaign_id"],
                "status": linked_campaign.status if linked_campaign else "active",
                "leads_count": row["leads_count"],
                "last_import": row["last_import"],
            }
        )

    import_history = []
    for log in ActivityLog.objects.filter(activity_type="meta_import").order_by("-created_at")[:10]:
        import_history.append(
            {
                "id": log.id,
                "timestamp": timezone.localtime(log.created_at).strftime("%Y-%m-%d %H:%M:%S"),
                "campaign": log.extra.get("meta_campaign_name") or log.extra.get("meta_campaign_id") or "Uncategorized",
                "imported": 1,
                "skipped": 0,
                "status": "success",
            }
        )

    return {
        "connected": connected,
        "total_meta_leads": meta_leads.count(),
        "campaigns": campaigns,
        "import_history": import_history,
    }
