"""
AI Meeting Engine — Powered by Google Gemini
Runs individual 1-on-1 meetings between the AI Sales Manager and each agent.
"""
import logging
import time
import google.generativeai as genai
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)
genai.configure(api_key=settings.GEMINI_API_KEY)

# ── Language map ───────────────────────────────────────────────────────────────
LANGUAGE_MAP = {
    "en-US": "English",
    "en-GB": "English",
    "en-IN": "English",
    "es-ES": "Spanish",
    "fr-FR": "French",
    "de-DE": "German",
    "it-IT": "Italian",
    "pt-BR": "Portuguese (Brazil)",
    "hi-IN": "Hindi",
    "ml-IN": "Malayalam",
    "zh-CN": "Chinese (Simplified)",
    "ja-JP": "Japanese",
    "ko-KR": "Korean",
    "ru-RU": "Russian",
    "ar-SA": "Arabic",
    "nl-NL": "Dutch",
}

# Native-script "reply only in X" commands embedded into prompts
# This makes Gemini obey the language instruction far more reliably.
NATIVE_COMMAND = {
    "Malayalam": "മലയാള ലിപിയിൽ (Malayalam script) മാത്രം മറുപടി നൽകുക. Manglish (English letters) ഉപയോഗിക്കരുത്. ഇംഗ്ലീഷ് അക്ഷരങ്ങൾ തീർത്തും ഒഴിവാക്കുക.",
    "Hindi": "केवल देवनागरी लिपि (Devanagari script) में जवाब दें। Hinglish या अंग्रेजी अक्षरों का प्रयोग बिल्कुल न करें।",
    "Spanish": "Responde SOLO en español. No uses otro idioma.",
    "French": "Réponds UNIQUEMENT en français.",
    "German": "Antworte NUR auf Deutsch.",
    "Italian": "Rispondi SOLO in italiano.",
    "Portuguese (Brazil)": "Responda SOMENTE em português.",
    "Chinese (Simplified)": "只用简体中文回复。不要使用拼音或英语。",
    "Japanese": "日本語の文字（漢字、ひらがな、カタカナ）のみで返答してください。ローマ字や英語を使わないでください。",
    "Korean": "한글로만 대답하세요. 영어나 로마자를 사용하지 마세요.",
    "Russian": "Отвечай ТОЛЬКО на кириллице. Не используй латиницу.",
    "Arabic": "أجب باللروف العربية فقط. لا تستخدم الأحرف الإنجليزية.",
    "Dutch": "Antwoord ALLEEN in het Nederlands.",
    "English": "",  # No constraint needed for English
}

# Hard-coded opening fallbacks for Gemini outages
OPENING_FALLBACKS = {
    "Malayalam": "ഹലോ {name}! ഞാൻ ആലക്സ്, നിങ്ങളുടെ AI സെയിൽസ് മാനേജർ ആണ്. ഇന്നത്തെ നിങ്ങളുടെ പ്രകടനം വിലയിരുത്താൻ നമുക്ക് ഒരു ചെറു ചർച്ച നടത്താം. ഇന്ന് നിങ്ങൾ എന്ത് ലക്ഷ്യം നേടി?",
    "Hindi": "नमस्ते {name}! मैं एलेक्स हूं, आपका AI सेल्स मैनेजर। आज के आपके प्रदर्शन के बारे में बात करते हैं। आज आपने क्या हासिल किया?",
    "Spanish": "¡Hola {name}! Soy Alex, tu gerente de ventas IA. Hablemos de tu desempeño hoy. ¿Qué lograste hoy?",
    "French": "Bonjour {name}! Je suis Alex, votre directeur commercial IA. Parlons de vos performances aujourd'hui. Qu'avez-vous accompli aujourd'hui?",
    "English": "Hello {name}! I'm Alex, your AI Sales Manager. Let's do a quick performance check-in. How are your leads going today?",
}

RESPONSE_FALLBACKS = {
    "Malayalam": "നന്ദി. നിങ്ങൾ ഈ ദിശയിൽ കൂടുതൽ ശ്രദ്ധ കേന്ദ്രീകരിക്കണം. മറ്റ് വെല്ലുവിളികൾ എന്തെങ്കിലും ഉണ്ടോ?",
    "Hindi": "धन्यवाद। आपको इस दिशा में अधिक ध्यान देना चाहिए। कोई अन्य चुनौतियां हैं?",
    "Spanish": "Gracias. Deberías enfocarte más en esa área. ¿Hay otros desafíos?",
    "French": "Merci. Vous devriez vous concentrer davantage sur cette direction. Y a-t-il d'autres défis?",
    "English": "Thank you for sharing that. What other challenges are you facing with your current leads?",
}


def _get_gemini_model(system_instruction: str = None, model_name: str = 'models/gemini-2.5-flash'):
    """Create and return a configured Gemini GenerativeModel."""
    kwargs = {
        'model_name': model_name,
        'generation_config': {
            'temperature': 0.7,
            'max_output_tokens': 500,
        }
    }
    if system_instruction:
        kwargs['system_instruction'] = system_instruction
    return genai.GenerativeModel(**kwargs)


def _call_gemini(prompt: str, system_instruction: str, history: list = None) -> str:
    """
    Call Gemini with retry on rate-limit (429) errors.
    Uses gemini-1.5-flash which has better rate limits on free tier.
    Returns the text response or raises an exception.
    """
    MAX_RETRIES = 3
    RETRY_DELAYS = [5, 15, 30]  # seconds between retries

    last_error = None
    for attempt in range(MAX_RETRIES):
        try:
            model = _get_gemini_model(system_instruction=system_instruction)
            if history:
                chat = model.start_chat(history=history)
                response = chat.send_message(prompt)
            else:
                response = model.generate_content(prompt)
            return response.text.strip()
        except Exception as e:
            last_error = e
            err_str = str(e).lower()
            # Check for rate limit / quota errors
            is_rate_limit = '429' in str(e) or 'quota' in err_str or 'rate' in err_str or 'resource_exhausted' in err_str
            if is_rate_limit and attempt < MAX_RETRIES - 1:
                wait = RETRY_DELAYS[attempt]
                logger.warning(f"[AI Meeting] Rate limit hit (attempt {attempt+1}), retrying in {wait}s...")
                time.sleep(wait)
            else:
                logger.error(f"[AI Meeting] Gemini call failed (attempt {attempt+1}): {e}")
                break

    raise last_error


def _get_meeting_language(config) -> str:
    """Resolve the full language name from the config language code."""
    raw = getattr(config, 'meeting_language', 'en-US') or 'en-US'
    return LANGUAGE_MAP.get(raw, 'English')


def _build_agent_context(agent) -> str:
    """Build performance context string for a specific agent."""
    from .engine import check_daily_progress, check_monthly_progress
    today = timezone.localdate()
    now = timezone.now()
    dp = check_daily_progress(agent, today)
    mp = check_monthly_progress(agent, now.month, now.year)
    name = agent.first_name or agent.username

    ctx = f"Agent Name: {name}\n"
    if dp.get('has_target'):
        ctx += (
            f"Today's Target: {dp['target_leads']} leads | "
            f"Achieved: {dp['actual_leads']} leads ({dp['leads_pct']}%)\n"
            f"Today's Revenue Target: ₹{dp['target_amount']:,.0f} | "
            f"Achieved: ₹{dp['actual_amount']:,.0f} ({dp['amount_pct']}%)\n"
        )
    else:
        ctx += "Today's Target: Not set\n"

    if mp.get('has_target'):
        ctx += (
            f"Monthly Target ({now.strftime('%B')}): {mp['target_leads']} leads | "
            f"Achieved: {mp['actual_leads']} leads ({mp['leads_pct']}%)\n"
            f"Monthly Revenue Target: ₹{mp['target_amount']:,.0f} | "
            f"Achieved: ₹{mp['actual_amount']:,.0f} ({mp['amount_pct']}%)\n"
        )
    else:
        ctx += "Monthly Target: Not set\n"

    return ctx


def _build_system_instruction(meeting_language: str) -> str:
    """Build a rock-solid model-level language constraint."""
    native = NATIVE_COMMAND.get(meeting_language, "")
    native_part = f" {native}" if native else ""
    return (
        f"You are Alex, an AI Sales Manager. "
        f"ABSOLUTE RULE: You MUST write every single word of every response in {meeting_language} ONLY. "
        f"Never write in English, not even a single word. "
        f"You MUST use the native script of {meeting_language}. Do NOT use English letters or transliteration (like Manglish or Hinglish). "
        f"If you use Latin/English letters, you have failed your task.{native_part}"
    )


def _build_meeting_prompt(agent, session_type: str, meeting_language: str) -> str:
    """Build the full contextual prompt for the meeting."""
    agent_ctx = _build_agent_context(agent)
    name = agent.first_name or agent.username
    time_label = {'morning': 'morning', 'evening': 'evening'}.get(session_type, 'ad-hoc')
    now_str = timezone.now().strftime('%A, %d %B %Y, %I:%M %p')
    native = NATIVE_COMMAND.get(meeting_language, "")

    return (
        f"[DATA — for context only, do NOT quote in English]\n"
        f"Date: {now_str}\n"
        f"{agent_ctx}\n"
        f"[TASK]\n"
        f"You are Alex, AI Sales Manager. Start a {time_label} standup meeting with {name}.\n"
        f"- Greet them warmly\n"
        f"- Mention their current progress numbers\n"
        f"- Ask ONE focused question about leads or challenges\n"
        f"- Keep your response extremely brief (MAX 1-2 short sentences)\n\n"
        f"CRITICAL LANGUAGE RULE: Your ENTIRE response MUST be written in {meeting_language}. "
        f"Do NOT write a single word in English.\n"
        + (f"{native}\n" if native else "") +
        f"\nBegin the {time_label} meeting now in {meeting_language}:"
    )


def start_meeting(agent, session_type):
    """
    Create a new AIMeetingSession and generate the opening AI message.
    Returns the session object.
    """
    from .models import AIMeetingSession, AIMeetingMessage
    from .engine import get_or_create_config

    config = get_or_create_config()
    meeting_language = _get_meeting_language(config)
    name = agent.first_name or agent.username

    # Create the session
    session = AIMeetingSession.objects.create(
        agent=agent,
        session_type=session_type,
    )

    system_instruction = _build_system_instruction(meeting_language)
    opening_prompt = _build_meeting_prompt(agent, session_type, meeting_language)
    opening_message = None

    try:
        opening_message = _call_gemini(opening_prompt, system_instruction)
        logger.info(f"[AI Meeting] Session {session.id} opened for {name} in {meeting_language}")
    except Exception as e:
        logger.error(f"[AI Meeting] Gemini completely failed for start_meeting: {e}")

    # Hard-coded language fallback if Gemini is unavailable
    if not opening_message:
        template = OPENING_FALLBACKS.get(meeting_language, OPENING_FALLBACKS["English"])
        opening_message = template.format(name=name)
        logger.warning(f"[AI Meeting] Used hard-coded fallback for {meeting_language}")

    AIMeetingMessage.objects.create(
        session=session,
        sender_type='ai',
        content=opening_message,
    )

    return session


def ai_respond(session, user_message_text, user):
    """
    Generate the next AI response for a user message.
    Saves both the user message and AI reply to the session.
    Returns the AI reply text.
    """
    from .models import AIMeetingMessage
    from .engine import get_or_create_config

    # Save user message first
    AIMeetingMessage.objects.create(
        session=session,
        sender_type='user',
        sender=user,
        content=user_message_text,
    )

    config = get_or_create_config()
    meeting_language = _get_meeting_language(config)
    system_instruction = _build_system_instruction(meeting_language)

    # Build conversation history
    all_messages = list(session.messages.all())
    # Exclude the last user message we just saved
    history = []
    for msg in all_messages[:-1]:
        role = 'model' if msg.sender_type == 'ai' else 'user'
        history.append({'role': role, 'parts': [msg.content]})

    agent_ctx = _build_agent_context(session.agent)
    name = session.agent.first_name or session.agent.username
    native = NATIVE_COMMAND.get(meeting_language, "")

    context_prefix = (
        f"[CONTEXT — use this data but do NOT respond in English]\n"
        f"Agent name: {name}\n"
        f"{agent_ctx}\n"
        f"The agent just said: \"{user_message_text}\"\n\n"
        f"ABSOLUTE RULE: Your reply MUST be written entirely in {meeting_language} using native script. "
        f"Not a single English word or English letter is allowed. Extremely brief conversational responses only. Max 1-2 short sentences. Ask at most 1 follow-up question.\n"
        + (f"{native}\n" if native else "") +
        f"\nYour response in {meeting_language}:"
    )

    ai_reply = None
    try:
        ai_reply = _call_gemini(context_prefix, system_instruction, history=history)
    except Exception as e:
        logger.error(f"[AI Meeting] ai_respond Gemini error: {e}")

    # Language-aware fallback
    if not ai_reply:
        ai_reply = RESPONSE_FALLBACKS.get(meeting_language, RESPONSE_FALLBACKS["English"])

    AIMeetingMessage.objects.create(
        session=session,
        sender_type='ai',
        content=ai_reply,
    )

    return ai_reply


def close_meeting_and_generate_mom(session):
    """
    End the meeting, generate a MOM summary using Gemini, save it,
    and send it as a notification to all Admins and General Managers.
    """
    from .models import AIMeetingMessage, Notification
    from users.models import User

    session.status = 'completed'
    session.ended_at = timezone.now()
    session.save(update_fields=['status', 'ended_at'])

    messages = session.messages.all()
    transcript_lines = []
    for msg in messages:
        if msg.sender_type == 'ai':
            role = "AI Manager (Alex)"
        else:
            role = msg.sender.first_name or msg.sender.username if msg.sender else "Agent"
        transcript_lines.append(f"{role}: {msg.content}")
    transcript = "\n".join(transcript_lines)

    agent_name = session.agent.first_name or session.agent.username
    session_date = session.started_at.strftime('%d %B %Y, %I:%M %p')
    session_label = session.get_session_type_display()

    mom_prompt = (
        f"Generate a concise, professional Minutes of Meeting (MOM) from this AI Sales Manager meeting.\n\n"
        f"Meeting: {session_label} with {agent_name} on {session_date}\n\n"
        f"TRANSCRIPT:\n{transcript}\n\n"
        f"Create a structured MOM with:\n"
        f"1. MEETING SUMMARY (2-3 sentences)\n"
        f"2. KEY DISCUSSION POINTS (bullet points)\n"
        f"3. PERFORMANCE SNAPSHOT (their actual numbers)\n"
        f"4. ACTION ITEMS (specific next steps)\n"
        f"5. AI RECOMMENDATIONS\n\n"
        f"Write the MOM in English regardless of the meeting language."
    )

    try:
        mom_text = _call_gemini(mom_prompt, "You are a professional meeting secretary. Generate clear, structured meeting minutes in English.")
    except Exception as e:
        logger.error(f"[AI Meeting] MOM generation failed: {e}")
        mom_text = f"Meeting with {agent_name} on {session_date}.\n\nTranscript:\n{transcript}"

    session.mom = mom_text
    session.mom_sent = True
    session.save(update_fields=['mom', 'mom_sent'])

    # Notify admins and GMs
    recipients = (User.objects.filter(is_staff=True) | User.objects.filter(is_general_manager=True))
    for recipient in recipients.distinct():
        Notification.objects.create(
            user=recipient,
            title=f"📋 MOM: {session_label} with {agent_name}",
            message=(
                f"The AI-led {session_label.lower()} with {agent_name} has concluded. "
                f"View the full MOM in the AI Meetings section."
            ),
            notification_type='meeting',
            is_popup=False,
            extra_data={'session_id': session.id, 'agent_name': agent_name},
        )

    return mom_text


def check_and_auto_start_meeting(agent):
    """
    Check if it's currently meeting time for this agent and auto-start if needed.
    Returns (session, is_new) or (None, False) if no meeting should start.
    """
    from .models import AIMeetingSession
    from .engine import get_or_create_config

    config = get_or_create_config()
    if not config.meeting_enabled:
        return None, False

    now = timezone.now()
    today = timezone.localdate(now)
    current_time = now.time()

    # Check if there's already an active session today
    existing_active = AIMeetingSession.objects.filter(
        agent=agent,
        status='active',
        started_at__date=today,
    ).first()
    if existing_active:
        return existing_active, False

    from datetime import datetime
    morning_time = config.morning_meeting_time
    evening_time = config.evening_meeting_time

    morning_dt = datetime.combine(today, morning_time)
    evening_dt = datetime.combine(today, evening_time)
    now_dt = datetime.combine(today, current_time)

    WINDOW_MINUTES = 30

    already_had_morning = AIMeetingSession.objects.filter(
        agent=agent, session_type='morning', started_at__date=today
    ).exists()
    already_had_evening = AIMeetingSession.objects.filter(
        agent=agent, session_type='evening', started_at__date=today
    ).exists()

    session_type = None
    if not already_had_morning and 0 <= (now_dt - morning_dt).total_seconds() <= WINDOW_MINUTES * 60:
        session_type = 'morning'
    elif not already_had_evening and 0 <= (now_dt - evening_dt).total_seconds() <= WINDOW_MINUTES * 60:
        session_type = 'evening'

    if session_type:
        session = start_meeting(agent, session_type)
        return session, True

    return None, False
