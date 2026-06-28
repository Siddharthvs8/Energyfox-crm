import json
import logging
import traceback
import os
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from .models import CallLog, WebhookLog
from django.utils import timezone
from datetime import timedelta
from organization.utils import get_org_settings
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

def get_last_10_digits(num):
    if not num:
        return ''
    digits = ''.join(c for c in str(num) if c.isdigit())
    return digits[-10:] if len(digits) >= 10 else digits

def get_or_create_lead_by_phone(phone_number):
    if not phone_number:
        return None
    last_10 = get_last_10_digits(phone_number)
    if not last_10:
        return None
    from leads.models import Lead
    lead = Lead.objects.filter(phone__endswith=last_10).first()
    if not lead:
        lead = Lead.objects.create(
            first_name="Inbound",
            last_name=f"Call {phone_number}",
            phone=phone_number,
            source="inbound_call",
            status="new"
        )
    return lead

def get_user_by_phone_or_extension(agent_number):
    if not agent_number:
        return None
    last_10 = get_last_10_digits(agent_number)
    from users.models import User
    user = User.objects.filter(voxbay_extension=str(agent_number)).first()
    if not user and last_10:
        user = User.objects.filter(phone__endswith=last_10).first()
    return user


@csrf_exempt
def airtel_status_callback(request):
    """Keep the old callback for backwards compatibility."""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
        except Exception:
            data = request.POST

        session_id = data.get('sessionId')
        status = data.get('status')
        duration = data.get('duration_seconds', 0)
        recording_url = data.get('recordingUrl')
        
        try:
            call = CallLog.objects.get(airtel_session_id=session_id)
            call.outcome = status
            call.duration_seconds = int(duration) if duration else 0
            if recording_url:
                call.recording_url = recording_url
            call.save()
        except CallLog.DoesNotExist:
            pass
            
    return HttpResponse(status=200)

@csrf_exempt
def airtel_bridge_callback(request):
    return JsonResponse({"status": "success", "action": "bridge"})


def log_webhook_to_file(method, host, raw_payload, raw_headers, matched_id, notes):
    """Saves a diagnostic copy of the webhook callback to a text log file."""
    try:
        from django.conf import settings
        log_file_path = os.path.join(settings.BASE_DIR, 'voxbay_webhooks.log')
        import datetime
        timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        with open(log_file_path, 'a', encoding='utf-8') as f:
            f.write(f"=== WEBHOOK RECEIVED AT {timestamp} ===\n")
            f.write(f"Method: {method}\n")
            f.write(f"Host: {host}\n")
            f.write(f"Matched Call ID: {matched_id}\n")
            f.write(f"Notes:\n{notes}\n")
            f.write(f"Headers: {raw_headers}\n")
            f.write(f"Payload: {raw_payload}\n")
            f.write("="*60 + "\n\n")
    except Exception as e:
        logger.error(f"Failed to write to voxbay_webhooks.log: {e}")


@csrf_exempt
def voxbay_webhook(request):
    """
    Unified Voxbay webhook supporting all events.
    Logs every raw payload to WebhookLog for debugging.
    """
    notes_log = []  # Accumulate processing notes for the logs

    # ── 1. Parse the incoming payload ──
    raw_body = ''
    data = {}
    if request.method == 'POST':
        try:
            raw_body = request.body.decode('utf-8', errors='replace')
            if raw_body.strip():
                data = json.loads(raw_body)
            else:
                data = request.POST.dict()
        except Exception:
            data = request.POST.dict()
            raw_body = json.dumps(data, default=str)
    elif request.method == 'GET':
        data = request.GET.dict()
        raw_body = json.dumps(data, default=str)
    else:
        return HttpResponse("success")

    # Combine query parameters into data if they are not already set from the body
    for k, v in request.GET.items():
        if k not in data or not data[k]:
            data[k] = v

    # Capture request headers for debugging
    raw_headers = {}
    for key, value in request.META.items():
        if key.startswith('HTTP_') or key in ('CONTENT_TYPE', 'CONTENT_LENGTH', 'SERVER_NAME'):
            raw_headers[key] = value

    notes_log.append(f"Method: {request.method}")
    notes_log.append(f"Full Path: {request.get_full_path()}")
    notes_log.append(f"Host: {request.get_host()}")
    notes_log.append(f"Payload keys: {list(data.keys())}")

    logger.info(f"[VOXBAY-WEBHOOK] method={request.method} host={request.get_host()} raw_payload={raw_body[:2000]}")

    # ── 2. Helper functions ──
    def get_val(key):
        for k, v in data.items():
            if k.lower() == key.lower():
                return v
        return None

    def get_last_10_digits(num):
        if not num:
            return ''
        digits = ''.join(c for c in str(num) if c.isdigit())
        return digits[-10:] if len(digits) >= 10 else digits

    # ── 3. Extract fields (try EVERY possible field name Voxbay might use) ──
    uuid = get_val('CallUUID') or get_val('callUUID') or get_val('calluuid') or get_val('call_uuid') or get_val('uniqueid') or get_val('Uniqueid')
    agent_number = get_val('AgentNumber') or get_val('extension') or get_val('agent_number') or get_val('agent') or get_val('src') or get_val('Extension') or get_val('user_no')
    customer_number = (
        get_val('callerNumber') or get_val('destination') or get_val('caller_number')
        or get_val('dst') or get_val('did') or get_val('callerid') or get_val('CallerNumber')
        or get_val('Destination') or get_val('caller_id') or get_val('customer_number')
        or get_val('from') or get_val('source')
    )
    duration = (
        get_val('totalCallDuration') or get_val('duration') or get_val('conversationDuration')
        or get_val('billsec') or get_val('duration_seconds') or get_val('call_duration')
        or get_val('billseconds') or get_val('total_duration') or get_val('Duration')
        or get_val('TotalCallDuration') or get_val('Billsec')
    )
    status = get_val('callStatus') or get_val('status') or get_val('disposition') or get_val('call_status') or get_val('Status') or get_val('Disposition') or get_val('CallStatus')
    recording_url = (
        get_val('recording_URL') or get_val('recording_url') or get_val('recording')
        or get_val('recordingurl') or get_val('RecordingUrl') or get_val('recordfile')
        or get_val('record_file') or get_val('recordingFile') or get_val('Recording')
        or get_val('RecordingURL') or get_val('recording_file') or get_val('RecordFile')
    )
    event_type = get_val('Event') or get_val('event') or get_val('event_type') or get_val('EventType')
    virtual_number = get_val('did') or get_val('Destination') or get_val('destination') or get_val('dst') or get_val('to') or get_val('To')

    notes_log.append(f"Extracted: uuid={uuid}, agent={agent_number}, customer={customer_number}, virtual={virtual_number}")
    notes_log.append(f"Extracted: duration={duration}, status={status}, recording={recording_url}, event={event_type}")

    logger.info(
        f"[VOXBAY-WEBHOOK] Extracted: uuid={uuid}, agent={agent_number}, "
        f"customer={customer_number}, duration={duration}, status={status}, "
        f"recording={recording_url}, event={event_type}"
    )

    # ── 4. Matching logic ──
    def find_call_in_schema(agent_num, cust_num, call_uuid=None):
        """Find the most recent matching CallLog in the current tenant schema."""
        # A. Direct UUID match
        if call_uuid:
            call_obj = CallLog.objects.filter(voxbay_uuid=call_uuid).first()
            if call_obj:
                notes_log.append(f"UUID match: CallLog id={call_obj.id}")
                return call_obj

        # B. Time-window + phone matching
        time_threshold = timezone.now() - timedelta(hours=48)  # Expanded to 48h for safety
        recent_logs = list(CallLog.objects.filter(
            created_at__gte=time_threshold
        ).select_related('lead', 'user'))

        notes_log.append(f"Recent logs in 48h: {len(recent_logs)}")

        if not recent_logs:
            return None

        # Debug: Log all recent logs' details
        for rl in recent_logs[:10]:
            user_ext = getattr(rl.user, 'voxbay_extension', None) if rl.user else None
            user_phone = getattr(rl.user, 'phone', None) if rl.user else None
            lead_phone = getattr(rl.lead, 'phone', None) if rl.lead else None
            notes_log.append(
                f"  Log id={rl.id}: outcome={rl.outcome}, "
                f"user_ext={user_ext}, user_phone={user_phone}, "
                f"lead_phone={lead_phone}, created={rl.created_at}"
            )

        # Filter by customer first (Lead phone) - this is highly specific and robust!
        if cust_num:
            clean_cust = get_last_10_digits(cust_num)
            if clean_cust:
                filtered = []
                for log in recent_logs:
                    if not log.lead:
                        continue
                    lead_phone = get_last_10_digits(getattr(log.lead, 'phone', '') or '')
                    if lead_phone == clean_cust:
                        filtered.append(log)
                notes_log.append(f"Customer filter '{cust_num}' (clean={clean_cust}): {len(filtered)} matches")
                recent_logs = filtered

        # Filter by agent as a tie-breaker if multiple matches exist and agent_num is provided
        if len(recent_logs) > 1 and agent_num:
            clean_agent = get_last_10_digits(agent_num)
            if clean_agent and clean_agent != '0':
                filtered = []
                for log in recent_logs:
                    if not log.user:
                        continue
                    user_ext = str(getattr(log.user, 'voxbay_extension', '') or '')
                    user_phone = get_last_10_digits(getattr(log.user, 'phone', '') or '')
                    user_name = str(getattr(log.user, 'username', '') or '')
                    if (user_ext == str(agent_num) or 
                        user_phone == clean_agent or 
                        user_name == str(agent_num) or
                        user_ext == clean_agent):
                        filtered.append(log)
                notes_log.append(f"Agent tie-breaker filter '{agent_num}' (clean={clean_agent}): {len(filtered)} matches")
                if filtered:
                    recent_logs = filtered

        # Prioritize 'initiated', then most recent
        recent_logs.sort(key=lambda x: x.created_at, reverse=True)
        initiated = [log for log in recent_logs if log.outcome == 'initiated']
        matched = initiated[0] if initiated else (recent_logs[0] if recent_logs else None)

        if matched:
            notes_log.append(f"MATCHED: CallLog id={matched.id} outcome={matched.outcome}")
            if call_uuid and not matched.voxbay_uuid:
                matched.voxbay_uuid = call_uuid
                matched.save()
        else:
            notes_log.append("NO MATCH in this schema")

        return matched

    # ── 5. Update call fields ──
    def update_call_fields(call_obj, call_status, call_duration, rec_url):
        update_kwargs = {}

        if call_status:
            s = str(call_status).upper().strip()
            # Voxbay CDR statuses → CRM outcomes
            if s in ['ANSWERED', 'CONNECTED', 'ANSWER', 'COMPLETED', 'SUCCESS']:
                update_kwargs['outcome'] = 'connected'
            elif s in ['NOT ANSWERED', 'NOANSWER', 'NO ANSWER', 'NO-ANSWER',
                        'NOT REACHED TO USER', 'RINGING', 'RING']:
                update_kwargs['outcome'] = 'rnr'
            elif s in ['CANCEL', 'CANCELLED', 'CANCELED']:
                update_kwargs['outcome'] = 'cancelled'
            elif s in ['BUSY', 'CONGESTION', 'CHANNEL UNAVAILABLE', 'CHANUNAVAIL', 'FAILED', 'FAILURE', 'ERROR']:
                update_kwargs['outcome'] = 'busy'
            else:
                update_kwargs['outcome'] = 'busy'

        if call_duration:
            try:
                dur = int(float(call_duration))
                if dur >= 0:
                    update_kwargs['duration_seconds'] = dur
            except (ValueError, TypeError):
                notes_log.append(f"Could not parse duration: {call_duration}")

        if rec_url:
            rec_str = str(rec_url).strip()
            if rec_str:
                if '://' in rec_str:
                    update_kwargs['recording_url'] = rec_str
                else:
                    try:
                        base = get_org_settings().voxbay_api_url or 'https://x.voxbay.com'
                        parsed = urlparse(base)
                        host = parsed.netloc.split(':')[0]
                        update_kwargs['recording_url'] = f"{parsed.scheme}://{host}:81/callcenter/{rec_str}"
                    except Exception:
                        update_kwargs['recording_url'] = f"https://x.voxbay.com:81/callcenter/{rec_str}"

        if update_kwargs:
            for k, v in update_kwargs.items():
                setattr(call_obj, k, v)
            call_obj.save()
            notes_log.append(f"UPDATED CallLog id={call_obj.id}: {update_kwargs}")
            logger.info(f"[VOXBAY-WEBHOOK] Updated CallLog id={call_obj.id}: {update_kwargs}")
        else:
            notes_log.append(f"Nothing to update for CallLog id={call_obj.id}")


    # ── 6. Execute matching (single database) ──
    matched_id = None
    try:
        call = find_call_in_schema(agent_number, customer_number, uuid)
        if call:
            matched_id = call.id
            update_call_fields(call, status, duration, recording_url)
        else:
            # No existing outbound log matched — treat this as an inbound call.
            notes_log.append("No match found. Processing as Inbound Call...")
            inbound_lead = None
            if customer_number:
                clean_cust = get_last_10_digits(customer_number)
                if clean_cust:
                    from leads.models import Lead
                    inbound_lead = Lead.objects.filter(phone__endswith=clean_cust).first()
                if not inbound_lead:
                    inbound_lead = get_or_create_lead_by_phone(customer_number)

            inbound_user = get_user_by_phone_or_extension(agent_number) if agent_number else None

            # Determine outcome
            outcome = 'connected'
            if status:
                s = str(status).upper().strip()
                if s in ['ANSWERED', 'CONNECTED', 'ANSWER', 'COMPLETED', 'SUCCESS']:
                    outcome = 'connected'
                elif s in ['NOT ANSWERED', 'NOANSWER', 'NO ANSWER', 'NO-ANSWER', 'NOT REACHED TO USER', 'RINGING', 'RING']:
                    outcome = 'rnr'
                elif s in ['CANCEL', 'CANCELLED', 'CANCELED']:
                    outcome = 'cancelled'
                else:
                    outcome = 'busy'

            # Parse duration
            duration_sec = 0
            if duration:
                try:
                    duration_sec = int(float(duration))
                except (ValueError, TypeError):
                    pass

            # Format recording url if it's relative
            rec_url_formatted = None
            if recording_url:
                rec_str = str(recording_url).strip()
                if rec_str:
                    if '://' in rec_str:
                        rec_url_formatted = rec_str
                    else:
                        try:
                            base = get_org_settings().voxbay_api_url or 'https://x.voxbay.com'
                            parsed = urlparse(base)
                            host_part = parsed.netloc.split(':')[0]
                            rec_url_formatted = f"{parsed.scheme}://{host_part}:81/callcenter/{rec_str}"
                        except Exception:
                            rec_url_formatted = f"https://x.voxbay.com:81/callcenter/{rec_str}"

            if inbound_lead:
                existing = CallLog.objects.filter(voxbay_uuid=uuid).first() if uuid else None
                if not existing:
                    new_log = CallLog.objects.create(
                        lead=inbound_lead,
                        user=inbound_user,
                        voxbay_uuid=uuid,
                        outcome=outcome,
                        duration_seconds=duration_sec,
                        recording_url=rec_url_formatted,
                        direction='inbound',
                        notes=f"Inbound call via Voxbay. Status: {outcome}."
                    )
                    matched_id = new_log.id
                    notes_log.append(f"CREATED Inbound CallLog id={new_log.id}")
                else:
                    matched_id = existing.id
                    notes_log.append(f"Inbound call already exists: CallLog id={existing.id}")
    except Exception as e:
        notes_log.append(f"ERROR: {str(e)}\n{traceback.format_exc()}")
        logger.error(f"[VOXBAY-WEBHOOK] Error: {str(e)}", exc_info=True)


    # ── 7. Save the webhook logs ──
    # Save a diagnostic copy to global text log file for absolute safety
    log_webhook_to_file(
        method=request.method,
        host=request.get_host(),
        raw_payload=raw_body,
        raw_headers=json.dumps(raw_headers, default=str),
        matched_id=matched_id,
        notes='\n'.join(notes_log)
    )

    # Save to the WebhookLog DB model.
    try:
        WebhookLog.objects.create(
            source='voxbay',
            method=request.method,
            host=request.get_host(),
            raw_payload=raw_body[:5000],
            raw_headers=json.dumps(raw_headers, default=str)[:3000],
            matched_call_id=matched_id,
            processing_notes='\n'.join(notes_log)
        )
    except Exception as e:
        logger.error(f"[VOXBAY-WEBHOOK] Failed to save WebhookLog: {e}")

    return HttpResponse("success")


@csrf_exempt
def voxbay_webhook_debug(request):
    """
    Debug endpoint: Shows the tail of voxbay_webhooks.log,
    plus recent WebhookLogs and CallLogs from the database.
    """
    logs = []
    log_file_content = ""
    try:
        from django.conf import settings
        log_file_path = os.path.join(settings.BASE_DIR, 'voxbay_webhooks.log')
        if os.path.exists(log_file_path):
            with open(log_file_path, 'r', encoding='utf-8') as f:
                # Read the last 20,000 characters
                f.seek(0, os.SEEK_END)
                size = f.tell()
                f.seek(max(0, size - 20000))
                log_file_content = f.read()
        else:
            log_file_content = "Log file voxbay_webhooks.log does not exist yet."
    except Exception as e:
        log_file_content = f"Error reading log file: {str(e)}"

    # Fetch recent webhook logs
    try:
        for wl in WebhookLog.objects.all()[:15]:
            logs.append({
                'id': wl.id,
                'source': wl.source,
                'method': wl.method,
                'host': wl.host,
                'raw_payload': wl.raw_payload,
                'matched_call_id': wl.matched_call_id,
                'processing_notes': wl.processing_notes,
                'created_at': str(wl.created_at),
            })
    except Exception as e:
        logs.append({'error': f'WebhookLog read error: {str(e)}'})

    # Show recent CallLogs
    call_logs = []
    try:
        for cl in CallLog.objects.all()[:10]:
            user_ext = getattr(cl.user, 'voxbay_extension', None) if cl.user else None
            user_phone = getattr(cl.user, 'phone', None) if cl.user else None
            lead_phone = getattr(cl.lead, 'phone', None) if cl.lead else None
            call_logs.append({
                'id': cl.id,
                'outcome': cl.outcome,
                'duration': cl.duration_seconds,
                'recording_url': cl.recording_url,
                'voxbay_uuid': cl.voxbay_uuid,
                'user_ext': user_ext,
                'user_phone': user_phone,
                'lead_phone': lead_phone,
                'created_at': str(cl.created_at),
            })
    except Exception as e:
        call_logs.append({'error': str(e)})

    return JsonResponse({
        'raw_log_file_tail': log_file_content,
        'webhook_db_logs': logs,
        'recent_call_logs': call_logs,
        'current_time': str(timezone.now()),
    }, json_dumps_params={'indent': 2})


@csrf_exempt
def exotel_webhook(request):
    """
    StatusCallback webhook for Exotel calls.
    Supports both application/json and application/x-www-form-urlencoded formats.
    """
    notes_log = []
    
    # ── 1. Parse the incoming payload ──
    raw_body = ''
    data = {}
    if request.method == 'POST':
        try:
            raw_body = request.body.decode('utf-8', errors='replace')
            if raw_body.strip():
                content_type = getattr(request, 'content_type', '') or ''
                if content_type.startswith('application/json'):
                    data = json.loads(raw_body)
                else:
                    # Try JSON first, fall back to form data
                    try:
                        data = json.loads(raw_body)
                    except (json.JSONDecodeError, ValueError):
                        data = request.POST.dict()
            else:
                data = request.POST.dict()
        except Exception:
            data = request.POST.dict()
            raw_body = json.dumps(data, default=str)
    elif request.method == 'GET':
        data = request.GET.dict()
        raw_body = json.dumps(data, default=str)
    else:
        return HttpResponse("success")

    # Combine query parameters into data if they are not already set from the body
    for k, v in request.GET.items():
        if k not in data or not data[k]:
            data[k] = v

    # Capture request headers for debugging
    raw_headers = {}
    for key, value in request.META.items():
        if key.startswith('HTTP_') or key in ('CONTENT_TYPE', 'CONTENT_LENGTH', 'SERVER_NAME'):
            raw_headers[key] = value

    notes_log.append(f"Method: {request.method}")
    notes_log.append(f"Full Path: {request.get_full_path()}")
    notes_log.append(f"Host: {request.get_host()}")
    notes_log.append(f"Payload keys: {list(data.keys())}")

    # Helper function to get values case-insensitively
    def get_val(key):
        for k, v in data.items():
            if k.lower() == key.lower():
                return v
        return None

    call_sid = get_val('CallSid') or get_val('Sid') or get_val('call_sid') or get_val('sid')
    status = get_val('Status') or get_val('status')
    duration = get_val('ConversationDuration') or get_val('duration') or get_val('ConversationDurationSeconds') or get_val('Duration')
    recording_url = get_val('RecordingUrl') or get_val('recording_url')
    custom_field = get_val('CustomField') or get_val('custom_field')
    direction_raw = (get_val('Direction') or get_val('direction') or 'inbound').lower().strip()
    direction = 'outbound' if 'outbound' in direction_raw else 'inbound'

    cust_phone = get_val('From') or get_val('from') or get_val('CallFrom')
    agent_phone_val = get_val('DialWhomNumber') or get_val('AgentPhoneNumber') or get_val('AgentNumber')
    virtual_phone_val = get_val('To') or get_val('to') or get_val('CallTo')

    logger.info(f"[EXOTEL-WEBHOOK] CallSid={call_sid} Status={status} Duration={duration} CustomField={custom_field}")
    notes_log.append(f"Extracted: CallSid={call_sid}, Status={status}, Duration={duration}, Recording={recording_url}, CustomField={custom_field}, direction={direction}")

    # ── Helper to find the call ──
    def find_call_in_schema(sid, custom_f=None):
        if sid:
            call_obj = CallLog.objects.filter(exotel_sid=sid).first()
            if call_obj:
                return call_obj
        if custom_f:
            # Fallback check if sid matches custom field or was stored in voxbay_uuid
            call_obj = CallLog.objects.filter(exotel_sid=custom_f).first() or CallLog.objects.filter(voxbay_uuid=custom_f).first()
            if call_obj:
                return call_obj
        return None

    # ── Update CallLog ──
    def update_call_fields(call_obj, call_status, call_duration, rec_url):
        update_kwargs = {}
        if call_status:
            s = str(call_status).lower().strip()
            if s in ['completed', 'answered', 'connected', 'success']:
                update_kwargs['outcome'] = 'connected'
            elif s in ['no-answer', 'noanswer', 'rnr']:
                update_kwargs['outcome'] = 'rnr'
            elif s in ['failed', 'busy', 'rejected']:
                update_kwargs['outcome'] = 'busy'
            elif s in ['canceled', 'cancelled']:
                update_kwargs['outcome'] = 'cancelled'
            else:
                update_kwargs['outcome'] = 'busy'
        
        if call_duration:
            try:
                update_kwargs['duration_seconds'] = int(float(call_duration))
            except (ValueError, TypeError):
                pass
        
        if rec_url:
            update_kwargs['recording_url'] = str(rec_url).strip()

        if update_kwargs:
            for k, v in update_kwargs.items():
                setattr(call_obj, k, v)
            call_obj.save()
            notes_log.append(f"UPDATED CallLog id={call_obj.id}: {update_kwargs}")
            logger.info(f"[EXOTEL-WEBHOOK] Updated CallLog id={call_obj.id}: {update_kwargs}")

    # ── Match (single database) ──
    matched_id = None

    call = find_call_in_schema(call_sid, custom_field)
    if call:
        matched_id = call.id
        update_call_fields(call, status, duration, recording_url)
    else:
        notes_log.append("No matched CallLog found. Attempting Inbound Call processing...")
        try:
            inbound_lead = None
            if cust_phone:
                clean_cust = get_last_10_digits(cust_phone)
                if clean_cust:
                    from leads.models import Lead
                    inbound_lead = Lead.objects.filter(phone__endswith=clean_cust).first()
                if not inbound_lead:
                    inbound_lead = get_or_create_lead_by_phone(cust_phone)

            inbound_user = get_user_by_phone_or_extension(agent_phone_val) if agent_phone_val else None

            # Determine outcome
            outcome = 'connected'
            if status:
                s = str(status).lower().strip()
                if s in ['completed', 'answered', 'connected', 'success']:
                    outcome = 'connected'
                elif s in ['no-answer', 'noanswer', 'rnr']:
                    outcome = 'rnr'
                elif s in ['failed', 'busy', 'rejected']:
                    outcome = 'busy'
                elif s in ['canceled', 'cancelled']:
                    outcome = 'cancelled'
                else:
                    outcome = 'busy'

            # Determine duration
            duration_sec = 0
            if duration:
                try:
                    duration_sec = int(float(duration))
                except (ValueError, TypeError):
                    pass

            if inbound_lead:
                existing = CallLog.objects.filter(exotel_sid=call_sid).first() if call_sid else None
                if not existing:
                    new_log = CallLog.objects.create(
                        lead=inbound_lead,
                        user=inbound_user,
                        exotel_sid=call_sid,
                        outcome=outcome,
                        duration_seconds=duration_sec,
                        recording_url=recording_url,
                        direction='inbound',
                        notes=f"Inbound call via Exotel. Status: {outcome}."
                    )
                    matched_id = new_log.id
                    notes_log.append(f"CREATED Inbound Exotel CallLog id={new_log.id}")
                else:
                    matched_id = existing.id
                    notes_log.append(f"Inbound call already exists: CallLog id={existing.id}")

        except Exception as e:
            notes_log.append(f"Error resolving inbound call: {str(e)}")
            logger.error(f"[EXOTEL-WEBHOOK] Inbound resolution error: {e}", exc_info=True)


    # Log to file
    try:
        from django.conf import settings
        log_file_path = os.path.join(settings.BASE_DIR, 'exotel_webhooks.log')
        import datetime
        timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        with open(log_file_path, 'a', encoding='utf-8') as f:
            f.write(f"=== EXOTEL WEBHOOK RECEIVED AT {timestamp} ===\n")
            f.write(f"Matched Call ID: {matched_id}\n")
            f.write(f"Notes:\n" + "\n".join(notes_log) + "\n")
            f.write(f"Payload: {raw_body}\n")
            f.write("="*60 + "\n\n")
    except Exception as e:
        logger.error(f"Failed to write to exotel_webhooks.log: {e}")

    # Log to DB
    try:
        WebhookLog.objects.create(
            source='exotel',
            method=request.method,
            host=request.get_host(),
            raw_payload=raw_body[:5000],
            raw_headers=json.dumps(raw_headers, default=str)[:3000],
            matched_call_id=matched_id,
            processing_notes='\n'.join(notes_log)
        )
    except Exception as e:
        logger.error(f"[EXOTEL-WEBHOOK] Failed to save WebhookLog: {e}")

    return HttpResponse("success")
