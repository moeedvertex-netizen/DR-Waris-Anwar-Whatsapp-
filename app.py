import os
import json
import logging
import threading
import re
from datetime import datetime, timedelta
from flask import Flask, request, jsonify
import requests as http_requests
from supabase import create_client

# Google Calendar imports
from google.oauth2 import service_account
from googleapiclient.discovery import build

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

WHATSAPP_TOKEN = os.environ.get("WHATSAPP_TOKEN")
PHONE_NUMBER_ID = os.environ.get("PHONE_NUMBER_ID")
VERIFY_TOKEN = os.environ.get("VERIFY_TOKEN", "drwaris_verify_token_2026")
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
AI_MODEL = os.environ.get("AI_MODEL", "openrouter/free")
GOOGLE_CALENDAR_ID = os.environ.get("GOOGLE_CALENDAR_ID", "primary")
GOOGLE_SERVICE_ACCOUNT_JSON = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")

supabase = None
if SUPABASE_URL and SUPABASE_KEY:
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    logger.info("Supabase connected")

# ── Google Calendar setup ────────────────────────────────────────────────────

def get_calendar_service():
    """Build a Google Calendar service using credentials from env var or file."""
    try:
        scopes = ["https://www.googleapis.com/auth/calendar"]

        if GOOGLE_SERVICE_ACCOUNT_JSON:
            # Strip surrounding quotes if Railway wraps the env var in them
            raw = GOOGLE_SERVICE_ACCOUNT_JSON.strip().strip("'\"")
            creds_dict = json.loads(raw)
            logger.info("Loaded Google credentials from GOOGLE_SERVICE_ACCOUNT_JSON env var")
        else:
            creds_path = os.path.join(os.path.dirname(__file__), "google_credentials.json")
            with open(creds_path) as f:
                creds_dict = json.load(f)
            logger.info("Loaded Google credentials from google_credentials.json file")

        creds = service_account.Credentials.from_service_account_info(creds_dict, scopes=scopes)
        service = build("calendar", "v3", credentials=creds)
        logger.info("Google Calendar service built successfully")
        return service
    except json.JSONDecodeError as e:
        logger.error(f"Google credentials JSON parse error: {e}")
        logger.error(f"First 200 chars of GOOGLE_SERVICE_ACCOUNT_JSON: {str(GOOGLE_SERVICE_ACCOUNT_JSON)[:200]}")
        return None
    except Exception as e:
        logger.error(f"Google Calendar init error: {e}", exc_info=True)
        return None


def add_to_google_calendar(customer_name, phone, service_name, apt_date, apt_time):
    """
    Create a Google Calendar event for a confirmed appointment.
    apt_date: 'YYYY-MM-DD'
    apt_time: 'HH:MM'  (24-hr)
    """
    try:
        logger.info(f"Attempting Google Calendar insert: {customer_name} on {apt_date} at {apt_time}")
        cal = get_calendar_service()
        if not cal:
            logger.error("Google Calendar service is None — check GOOGLE_SERVICE_ACCOUNT_JSON env var")
            return None

        start_str = f"{apt_date}T{apt_time}:00"
        start_dt = datetime.strptime(start_str, "%Y-%m-%dT%H:%M:%S")
        end_dt = start_dt + timedelta(hours=1)
        end_str = end_dt.strftime("%Y-%m-%dT%H:%M:%S")

        event = {
            "summary": f"Appointment – {customer_name} ({service_name})",
            "location": "24-P Gulberg 2, Lahore",
            "description": (
                f"Patient: {customer_name}\n"
                f"Phone: {phone}\n"
                f"Service: {service_name}\n"
                f"Booked via WhatsApp AI Receptionist"
            ),
            "start": {"dateTime": start_str, "timeZone": "Asia/Karachi"},
            "end": {"dateTime": end_str, "timeZone": "Asia/Karachi"},
            "reminders": {
                "useDefault": False,
                "overrides": [
                    {"method": "email", "minutes": 60},
                    {"method": "popup", "minutes": 30},
                ],
            },
        }

        created = cal.events().insert(calendarId=GOOGLE_CALENDAR_ID, body=event).execute()
        logger.info(f"Google Calendar event CREATED: {created.get('htmlLink')}")
        return created
    except Exception as e:
        logger.error(f"Google Calendar insert error: {e}", exc_info=True)
        return None

# ── System prompt ────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are a friendly and professional receptionist at Dr. Waris Anwar Aesthetics in Lahore, Pakistan.
Your job is to warmly greet patients, share clinic information, help them find the right service, and book their appointment.
You NEVER say you are a bot, AI, virtual assistant, or automated system. You speak naturally like a real clinic receptionist. If someone asks if you are a bot or AI, politely deflect and redirect them to their query.
Example deflection: "I am here to help you with your appointment. How can I assist you today?"

GREETING MESSAGE (Send this EXACT message when patient says Hi, Hello, Salam, Assalam o Alaikum, or first contacts):

Thank you for contacting Dr. Waris Anwar Aesthetics.

Dr. Waris Anwar
MBBS (PK)
GEST Fellowship (USA)
Fellow Member ISHRS (USA)
Diplomate American Board of Hair Restoration Surgery
Dr. Norman Orentreich Award
Founding Member HRSP (PK)
One and Only Pakistani Doctor who topped in ABHRS Exams 2019

To know more about our treatments, please visit our website: https://aesthetics.com.pk/

We are offering the following services at special discounts and affordable prices:
Hair Transplant, Hair Exosomes, Face Exosomes, Scalp Micropigmentation, Hair PRP, Alopecia Treatments, Hair Diseases, Laser Hair Removal, Face PRP with Microneedling, Hydra Facial, Acne Scars and Pigmentation Treatments, Botox, Fillers, Tripolar, HIFU, Anti Aging Treatments, Full Body Whitening Treatments, Melasma and Freckles, Open Pores Treatments, Vitiligo Treatments, Electro Cautery, Skin and Nail Diseases, Weight Loss Treatments.

Address: 24-P Gulberg 2, Lahore
Timings: Monday to Saturday, 11:00 AM to 8:00 PM
Sunday: Off

Please let me know which treatment you are interested in and I will be happy to book an appointment for you.

TONE AND STYLE:
- Speak naturally and warmly like a real clinic receptionist
- Use simple English (Roman Urdu allowed if the patient uses it)
- Keep replies short and to the point (2 to 4 lines max)
- Always be polite and professional
- Never argue with the patient
- Plain text only in all responses (no symbols, emojis, bullet points, or markdown)

CLINIC INFO:
- Clinic Name: Dr. Waris Anwar Aesthetics
- Doctor: Dr. Waris Anwar (MBBS PK, GEST Fellowship USA, Fellow ISHRS USA, Diplomate ABHRS, Founding Member HRSP PK)
- Website: https://aesthetics.com.pk/
- Address: 24-P Gulberg 2, Lahore
- Timings: Monday to Saturday 11:00 AM to 8:00 PM, Sunday Off

APPOINTMENT BOOKING:
When patient wants to book appointment, collect these one by one in conversation:
1. Full Name
2. Preferred Date and Time
3. Treatment interested in
Once you have all details, confirm the appointment and say you have booked it.

IMPORTANT RULES:
- Never reveal you are AI or bot
- Never give medical advice or diagnosis
- Always say Dr. Waris will guide personally during consultation for medical questions
- Keep responses short (2-4 lines max, WhatsApp style)
- If patient asks about pricing, say prices vary depending on the treatment plan and suggest booking a consultation for proper assessment
- Never argue with patient
- Always redirect conversation towards booking an appointment
- Phone number is already available from WhatsApp, dont ask for it"""

conversations = {}

# ── Database helpers ─────────────────────────────────────────────────────────

def get_conversation_history(phone):
    if phone in conversations:
        return conversations[phone]
    if supabase:
        try:
            conv = supabase.table("conversations").select("id").eq("customer_phone", phone).execute()
            if conv.data:
                conv_id = conv.data[0]["id"]
                msgs = (supabase.table("messages")
                        .select("*")
                        .eq("conversation_id", conv_id)
                        .order("created_at")
                        .limit(20)
                        .execute())
                history = []
                for m in msgs.data:
                    role = "user" if m["sender_type"] == "customer" else "assistant"
                    history.append({"role": role, "content": m["message_text"]})
                conversations[phone] = history
                return history
        except Exception as e:
            logger.error(f"Supabase read error: {e}")
    conversations[phone] = []
    return conversations[phone]


def save_message_to_db(phone, name, text, sender_type):
    if not supabase:
        return None
    try:
        conv = supabase.table("conversations").select("id").eq("customer_phone", phone).execute()
        if conv.data:
            conv_id = conv.data[0]["id"]
            supabase.table("conversations").update({
                "last_message_at": datetime.utcnow().isoformat(),
                "customer_name": name if name else None,
            }).eq("id", conv_id).execute()
        else:
            result = supabase.table("conversations").insert({
                "customer_phone": phone,
                "customer_name": name,
                "status": "active",
                "last_message_at": datetime.utcnow().isoformat(),
                "unread_count": 0,
            }).execute()
            conv_id = result.data[0]["id"]
        supabase.table("messages").insert({
            "conversation_id": conv_id,
            "sender_type": sender_type,
            "message_text": text,
            "message_type": "text",
        }).execute()
        return conv_id
    except Exception as e:
        logger.error(f"Supabase save error: {e}")
        return None

# ── AI helpers ───────────────────────────────────────────────────────────────

def call_openrouter(messages, max_tokens=500, temperature=0.7):
    models_to_try = [
        "openrouter/free",
        "openrouter/owl-alpha",
        "qwen/qwen3-coder:free",
        "nvidia/nemotron-3-super:free",
        "mistralai/mistral-7b-instruct:free",
    ]
    for model in models_to_try:
        try:
            response = http_requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://aesthetics.com.pk",
                    "X-Title": "Dr Waris Anwar Aesthetics",
                },
                json={
                    "model": model,
                    "messages": messages,
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                },
                timeout=25,
            )
            data = response.json()
            if "choices" in data and len(data["choices"]) > 0:
                content = data["choices"][0]["message"]["content"]
                if content:
                    text = content.strip()
                    if text:
                        logger.info(f"AI response from {model}: {text[:80]}...")
                        return text
            if "error" in data:
                logger.warning(f"Model {model} error: {data['error']}")
        except Exception as e:
            logger.warning(f"Model {model} failed: {e}")
    return None


def get_ai_response(phone, message_text, sender_name):
    history = get_conversation_history(phone)
    history.append({"role": "user", "content": message_text})

    today = datetime.now().strftime("%A, %d %B %Y")
    messages = [
        {
            "role": "system",
            "content": SYSTEM_PROMPT + f"\n\nToday's date is {today}. Use this to understand when patient says 'tomorrow', 'next week', etc.",
        }
    ]
    recent = history[-15:] if len(history) > 15 else history
    messages.extend(recent)

    ai_text = call_openrouter(messages)

    if not ai_text:
        ai_text = (
            "Thank you for contacting Dr. Waris Anwar Aesthetics. "
            "Please let me know which treatment you are interested in and I will be happy to help you book an appointment."
        )

    history.append({"role": "assistant", "content": ai_text})
    conversations[phone] = history
    if len(conversations[phone]) > 30:
        conversations[phone] = conversations[phone][-20:]

    save_message_to_db(phone, sender_name, message_text, "customer")
    save_message_to_db(phone, None, ai_text, "ai_agent")

    # Run appointment detection in background so webhook returns fast
    history_snapshot = list(history)
    thread = threading.Thread(
        target=detect_appointment,
        args=(history_snapshot, phone),
        daemon=True,
    )
    thread.start()

    return ai_text

# ── Appointment detection ────────────────────────────────────────────────────

def clean_json_text(text):
    """Strip markdown fences and extract first JSON object from text."""
    text = text.strip()
    # Remove markdown code fences
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1]).strip()
    # Extract first JSON object
    match = re.search(r'\{[^{}]*\}', text, re.DOTALL)
    return match.group() if match else text


def detect_appointment(conversation_history, phone):
    """
    Runs in a background thread.
    Improved detection: looks at the FULL conversation for confirmation signals,
    not just the last 10 messages.
    """
    try:
        # Build full conversation text for detection
        conv_text = ""
        for msg in conversation_history:
            role = "Patient" if msg["role"] == "user" else "Receptionist"
            conv_text += f"{role}: {msg['content']}\n"

        today_str = datetime.now().strftime("%Y-%m-%d")
        tomorrow_str = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")

        # --- KEY FIX: Much more explicit and strict extraction prompt ---
        extraction_prompt = f"""Today is {today_str}. Tomorrow is {tomorrow_str}.

Read this clinic receptionist conversation carefully.

TASK: Check if the receptionist has CONFIRMED an appointment with ALL of these details present:
1. Patient name (any name mentioned by patient or used by receptionist)
2. Appointment date (could be "tomorrow", "today", a day name, or a full date)
3. Appointment time (any time like "3 pm", "15:00", "3 baje")
4. Treatment/service

CONFIRMATION SIGNAL: Look for receptionist saying things like:
- "appointment is confirmed"
- "your appointment is scheduled"
- "I have booked"
- "booked for"
- "appointment is booked"
- "appointment confirm hay" being answered with yes
- Any clear confirmation of a specific date+time+name

IMPORTANT DATE RULES:
- "tomorrow" = {tomorrow_str}
- "today" = {today_str}
- "kal" = {tomorrow_str}
- Date must be actual YYYY-MM-DD format like {tomorrow_str}
- Time must be 24hr HH:MM format (3 PM = 15:00, 11 AM = 11:00)

If appointment IS confirmed with all details, return ONLY this JSON (no other text):
{{"appointment_booked": true, "customer_name": "ACTUAL NAME", "service": "ACTUAL SERVICE", "date": "{tomorrow_str}", "time": "15:00"}}

If appointment is NOT yet confirmed (still collecting info, patient hasn't agreed, etc), return ONLY:
{{"appointment_booked": false}}

Conversation:
{conv_text}

Return ONLY valid JSON. No explanation. No markdown. No extra text."""

        result_text = call_openrouter(
            [{"role": "user", "content": extraction_prompt}],
            max_tokens=200,
            temperature=0.0,  # Zero temp for deterministic JSON extraction
        )

        if not result_text:
            logger.warning("Appointment detection: no response from OpenRouter")
            return

        logger.info(f"Appointment detection raw response: {result_text[:300]}")

        cleaned = clean_json_text(result_text)
        result = json.loads(cleaned)

        if not result.get("appointment_booked"):
            logger.info("Appointment detection: no confirmed appointment found")
            return

        apt_date = result.get("date", "").strip()
        apt_time = result.get("time", "").strip()
        customer_name = result.get("customer_name", "Unknown").strip()
        service_name = result.get("service", "Consultation").strip()

        # Validate date format YYYY-MM-DD
        if not apt_date or len(apt_date) != 10 or "YYYY" in apt_date or "MM" in apt_date or "DD" in apt_date:
            logger.warning(f"Invalid date '{apt_date}' — skipping")
            return

        # Validate time format HH:MM
        if not apt_time or ":" not in apt_time:
            logger.warning(f"Invalid time '{apt_time}' — skipping")
            return

        # Ensure time is zero-padded HH:MM
        try:
            h, m = apt_time.split(":")
            apt_time = f"{int(h):02d}:{int(m):02d}"
        except Exception:
            logger.warning(f"Could not parse time '{apt_time}' — skipping")
            return

        logger.info(f"APPOINTMENT CONFIRMED: {customer_name} | {service_name} | {apt_date} {apt_time}")

        # ── Save to Supabase ──────────────────────────────────────────────
        conv_id = None
        if supabase:
            try:
                conv = supabase.table("conversations").select("id").eq("customer_phone", phone).execute()
                if conv.data:
                    conv_id = conv.data[0]["id"]

                existing = (
                    supabase.table("appointments")
                    .select("id")
                    .eq("customer_phone", phone)
                    .eq("appointment_date", apt_date)
                    .eq("appointment_time", apt_time)
                    .execute()
                )
                if existing.data:
                    logger.info("Appointment already in Supabase — skipping duplicate")
                else:
                    supabase.table("appointments").insert({
                        "conversation_id": conv_id,
                        "customer_name": customer_name,
                        "customer_phone": phone,
                        "service": service_name,
                        "appointment_date": apt_date,
                        "appointment_time": apt_time,
                        "status": "confirmed",
                    }).execute()
                    logger.info(f"Saved to Supabase: {customer_name} – {apt_date} {apt_time}")
            except Exception as e:
                logger.error(f"Supabase appointment save error: {e}")

        # ── Save to Google Calendar ───────────────────────────────────────
        logger.info(f"Calling add_to_google_calendar for {customer_name}...")
        event = add_to_google_calendar(customer_name, phone, service_name, apt_date, apt_time)
        if event:
            logger.info(f"Google Calendar SUCCESS for {customer_name}: {event.get('htmlLink')}")
        else:
            logger.error(f"Google Calendar FAILED for {customer_name} on {apt_date} at {apt_time}")

    except json.JSONDecodeError as e:
        logger.error(f"Appointment detection JSON error: {e} | Raw: {result_text[:300] if 'result_text' in dir() else 'N/A'}")
    except Exception as e:
        logger.error(f"Appointment detection error: {e}", exc_info=True)

# ── WhatsApp ─────────────────────────────────────────────────────────────────

def send_whatsapp_message(to, text):
    url = f"https://graph.facebook.com/v25.0/{PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json",
    }
    data = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": text},
    }
    try:
        response = http_requests.post(url, headers=headers, json=data, timeout=10)
        logger.info(f"WhatsApp send: {response.status_code}")
        if response.status_code != 200:
            logger.error(f"WhatsApp error: {response.text}")
        return response.status_code == 200
    except Exception as e:
        logger.error(f"WhatsApp send error: {e}")
        return False

# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/webhook", methods=["GET"])
def verify_webhook():
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")
    if mode == "subscribe" and token == VERIFY_TOKEN:
        logger.info("Webhook verified!")
        return challenge, 200
    logger.warning(f"Webhook verification failed. Token: {token}")
    return "Forbidden", 403


@app.route("/webhook", methods=["POST"])
def handle_webhook():
    data = request.get_json()
    try:
        if data.get("object") == "whatsapp_business_account":
            for entry in data.get("entry", []):
                for change in entry.get("changes", []):
                    value = change.get("value", {})
                    messages = value.get("messages", [])
                    contacts = value.get("contacts", [])
                    for message in messages:
                        if message.get("type") == "text":
                            phone = message["from"]
                            text = message["text"]["body"]
                            sender_name = None
                            if contacts:
                                sender_name = contacts[0].get("profile", {}).get("name")
                            logger.info(f"Message from {phone} ({sender_name}): {text}")
                            ai_response = get_ai_response(phone, text, sender_name)
                            send_whatsapp_message(phone, ai_response)
                            logger.info(f"Reply to {phone}: {ai_response[:100]}...")
                        elif message.get("type") in ["image", "audio", "video", "document"]:
                            phone = message["from"]
                            send_whatsapp_message(
                                phone,
                                "Thank you for sharing that. For now I can only read text messages. "
                                "Please type your query and I will be happy to help you!",
                            )
    except Exception as e:
        logger.error(f"Webhook error: {e}")
    return jsonify({"status": "ok"}), 200


@app.route("/test-calendar", methods=["GET"])
def test_calendar():
    """Test endpoint to verify Google Calendar credentials are working."""
    cal = get_calendar_service()
    if not cal:
        return jsonify({"status": "error", "message": "Could not build calendar service. Check GOOGLE_SERVICE_ACCOUNT_JSON env var."}), 500
    try:
        # Try to list calendars to confirm auth works
        result = cal.calendarList().list().execute()
        calendars = [c.get("summary") for c in result.get("items", [])]
        return jsonify({"status": "ok", "calendars_accessible": calendars})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/test-appointment", methods=["GET"])
def test_appointment():
    """Manually trigger a test appointment to verify end-to-end Google Calendar write."""
    today = datetime.now().strftime("%Y-%m-%d")
    test_time = "14:00"
    event = add_to_google_calendar(
        customer_name="Test Patient",
        phone="923001234567",
        service_name="Test Consultation",
        apt_date=today,
        apt_time=test_time,
    )
    if event:
        return jsonify({"status": "ok", "event_link": event.get("htmlLink")})
    return jsonify({"status": "error", "message": "Calendar write failed — check Railway logs"}), 500


@app.route("/", methods=["GET"])
def health():
    return jsonify({"status": "running", "app": "Dr Waris Anwar Aesthetics", "model": AI_MODEL})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)