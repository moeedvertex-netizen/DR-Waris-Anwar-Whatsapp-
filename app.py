import os
import json
import re
import logging
from datetime import datetime, timedelta
from flask import Flask, request, jsonify
import requests
from supabase import create_client
from google.oauth2 import service_account
from googleapiclient.discovery import build
import google.generativeai as genai

# ============================================================
# CONFIGURATION
# ============================================================
app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Environment Variables
WHATSAPP_TOKEN = os.environ.get("WHATSAPP_TOKEN")
PHONE_NUMBER_ID = os.environ.get("PHONE_NUMBER_ID")
VERIFY_TOKEN = os.environ.get("VERIFY_TOKEN", "drwaris_verify_token_2026")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
GOOGLE_CALENDAR_ID = os.environ.get("GOOGLE_CALENDAR_ID")
GOOGLE_SERVICE_ACCOUNT_JSON = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")

# Initialize Supabase
supabase = None
if SUPABASE_URL and SUPABASE_KEY:
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    logger.info("Supabase connected")

# Initialize Gemini
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-2.0-flash")

# ============================================================
# SYSTEM PROMPT - DR. WARIS ANWAR AESTHETICS
# ============================================================
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

# ============================================================
# CONVERSATION MEMORY (In-memory + Supabase)
# ============================================================
conversations = {}  # {phone_number: [{"role": "user/model", "parts": ["text"]}]}

def get_conversation_history(phone):
    """Get conversation history from memory or Supabase"""
    if phone in conversations:
        return conversations[phone]
    
    # Try loading from Supabase
    if supabase:
        try:
            conv = supabase.table("conversations").select("id").eq("customer_phone", phone).execute()
            if conv.data:
                conv_id = conv.data[0]["id"]
                msgs = supabase.table("messages").select("*").eq("conversation_id", conv_id).order("created_at").limit(30).execute()
                history = []
                for m in msgs.data:
                    role = "user" if m["sender_type"] == "customer" else "model"
                    history.append({"role": role, "parts": [m["message_text"]]})
                conversations[phone] = history
                return history
        except Exception as e:
            logger.error(f"Supabase read error: {e}")
    
    conversations[phone] = []
    return conversations[phone]

def save_message_to_db(phone, name, text, sender_type):
    """Save message to Supabase"""
    if not supabase:
        return None
    
    try:
        # Get or create conversation
        conv = supabase.table("conversations").select("id").eq("customer_phone", phone).execute()
        
        if conv.data:
            conv_id = conv.data[0]["id"]
            supabase.table("conversations").update({
                "last_message_at": datetime.utcnow().isoformat(),
                "customer_name": name if name else None
            }).eq("id", conv_id).execute()
        else:
            result = supabase.table("conversations").insert({
                "customer_phone": phone,
                "customer_name": name,
                "status": "active",
                "last_message_at": datetime.utcnow().isoformat(),
                "unread_count": 0
            }).execute()
            conv_id = result.data[0]["id"]
        
        # Save message
        supabase.table("messages").insert({
            "conversation_id": conv_id,
            "sender_type": sender_type,
            "message_text": text,
            "message_type": "text"
        }).execute()
        
        # Increment unread if customer
        if sender_type == "customer":
            supabase.rpc("increment_unread", {"conv_id": conv_id}).execute()
        
        return conv_id
    except Exception as e:
        logger.error(f"Supabase save error: {e}")
        return None

# ============================================================
# GOOGLE CALENDAR INTEGRATION
# ============================================================
def get_calendar_service():
    """Initialize Google Calendar service"""
    if not GOOGLE_SERVICE_ACCOUNT_JSON:
        return None
    try:
        creds_dict = json.loads(GOOGLE_SERVICE_ACCOUNT_JSON)
        creds = service_account.Credentials.from_service_account_info(
            creds_dict,
            scopes=["https://www.googleapis.com/auth/calendar"]
        )
        service = build("calendar", "v3", credentials=creds)
        return service
    except Exception as e:
        logger.error(f"Calendar service error: {e}")
        return None

def create_calendar_event(name, phone, service_name, date_str, time_str):
    """Create Google Calendar event for appointment"""
    cal_service = get_calendar_service()
    if not cal_service or not GOOGLE_CALENDAR_ID:
        logger.warning("Google Calendar not configured, saving to DB only")
        return None
    
    try:
        start_dt = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
        end_dt = start_dt + timedelta(hours=1)
        
        event = {
            "summary": f"{service_name} - {name}",
            "description": f"Patient: {name}\nPhone: {phone}\nService: {service_name}\nBooked via WhatsApp AI Agent",
            "start": {
                "dateTime": start_dt.strftime("%Y-%m-%dT%H:%M:%S"),
                "timeZone": "Asia/Karachi"
            },
            "end": {
                "dateTime": end_dt.strftime("%Y-%m-%dT%H:%M:%S"),
                "timeZone": "Asia/Karachi"
            },
            "location": "24-P Gulberg 2, Lahore",
            "reminders": {
                "useDefault": False,
                "overrides": [
                    {"method": "popup", "minutes": 60},
                    {"method": "popup", "minutes": 15}
                ]
            }
        }
        
        created = cal_service.events().insert(calendarId=GOOGLE_CALENDAR_ID, body=event).execute()
        logger.info(f"Calendar event created: {created.get('id')}")
        return created.get("id")
    except Exception as e:
        logger.error(f"Calendar create error: {e}")
        return None

def save_appointment_to_db(phone, name, service_name, date_str, time_str, google_event_id=None, conv_id=None):
    """Save appointment to Supabase"""
    if not supabase:
        return
    try:
        supabase.table("appointments").insert({
            "conversation_id": conv_id,
            "customer_name": name,
            "customer_phone": phone,
            "service": service_name,
            "appointment_date": date_str,
            "appointment_time": time_str,
            "status": "confirmed",
            "google_event_id": google_event_id
        }).execute()
        logger.info(f"Appointment saved: {name} - {service_name} - {date_str} {time_str}")
    except Exception as e:
        logger.error(f"Appointment save error: {e}")

# ============================================================
# APPOINTMENT DETECTION
# ============================================================
def detect_appointment(conversation_history, phone):
    """Use Gemini to detect if appointment was booked"""
    try:
        last_messages = conversation_history[-15:] if len(conversation_history) > 15 else conversation_history
        
        conv_text = ""
        for msg in last_messages:
            role = "Patient" if msg["role"] == "user" else "Receptionist"
            conv_text += f"{role}: {msg['parts'][0]}\n"
        
        extraction_prompt = f"""Analyze this WhatsApp conversation between a clinic receptionist and a patient. 
Determine if an appointment has been CONFIRMED (meaning the receptionist confirmed a specific date, time, service and patient name).

Conversation:
{conv_text}

If an appointment was CONFIRMED, extract details in this EXACT JSON format:
{{"appointment_booked": true, "customer_name": "...", "service": "...", "date": "YYYY-MM-DD", "time": "HH:MM"}}

If NO appointment was confirmed yet, return:
{{"appointment_booked": false}}

IMPORTANT: 
- Date must be in YYYY-MM-DD format
- Time must be in HH:MM 24-hour format  
- Only return true if ALL details (name, service, date, time) are clearly mentioned and confirmed
- Return ONLY valid JSON, nothing else"""

        response = model.generate_content(extraction_prompt)
        result_text = response.text.strip()
        
        # Clean JSON
        result_text = result_text.replace("```json", "").replace("```", "").strip()
        
        result = json.loads(result_text)
        
        if result.get("appointment_booked"):
            logger.info(f"Appointment detected: {result}")
            
            # Create Google Calendar event
            google_event_id = create_calendar_event(
                result["customer_name"],
                phone,
                result["service"],
                result["date"],
                result["time"]
            )
            
            # Save to database
            conv_id = None
            if supabase:
                conv = supabase.table("conversations").select("id").eq("customer_phone", phone).execute()
                if conv.data:
                    conv_id = conv.data[0]["id"]
            
            save_appointment_to_db(
                phone,
                result["customer_name"],
                result["service"],
                result["date"],
                result["time"],
                google_event_id,
                conv_id
            )
            
            return result
    except json.JSONDecodeError as e:
        logger.error(f"JSON parse error in appointment detection: {e}")
    except Exception as e:
        logger.error(f"Appointment detection error: {e}")
    
    return None

# ============================================================
# GEMINI AI RESPONSE
# ============================================================
def get_ai_response(phone, message_text, sender_name):
    """Get AI response from Gemini"""
    history = get_conversation_history(phone)
    
    # Add user message to history
    history.append({"role": "user", "parts": [message_text]})
    
    try:
        chat = model.start_chat(history=history[:-1])
        
        # Build context with system prompt
        full_prompt = message_text
        if len(history) <= 1:
            full_prompt = f"[System: {SYSTEM_PROMPT}]\n\nPatient says: {message_text}"
        
        response = chat.send_message(
            full_prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=0.7,
                max_output_tokens=500
            )
        )
        
        ai_text = response.text.strip()
        
        # Add AI response to history
        history.append({"role": "model", "parts": [ai_text]})
        conversations[phone] = history
        
        # Keep history manageable
        if len(conversations[phone]) > 40:
            conversations[phone] = conversations[phone][-30:]
        
        # Save to database
        save_message_to_db(phone, sender_name, message_text, "customer")
        save_message_to_db(phone, None, ai_text, "ai_agent")
        
        # Check for appointment
        detect_appointment(history, phone)
        
        return ai_text
    except Exception as e:
        logger.error(f"Gemini error: {e}")
        
        # Fallback with fresh chat
        try:
            response = model.generate_content(
                f"{SYSTEM_PROMPT}\n\nPatient says: {message_text}\n\nReply as the receptionist:"
            )
            ai_text = response.text.strip()
            history.append({"role": "model", "parts": [ai_text]})
            conversations[phone] = history
            
            save_message_to_db(phone, sender_name, message_text, "customer")
            save_message_to_db(phone, None, ai_text, "ai_agent")
            
            return ai_text
        except Exception as e2:
            logger.error(f"Gemini fallback error: {e2}")
            return "Thank you for reaching out. Our team will get back to you shortly. You can also call us at our clinic number."

# ============================================================
# WHATSAPP API
# ============================================================
def send_whatsapp_message(to, text):
    """Send message via WhatsApp Cloud API"""
    url = f"https://graph.facebook.com/v25.0/{PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json"
    }
    data = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": text}
    }
    
    try:
        response = requests.post(url, headers=headers, json=data)
        logger.info(f"WhatsApp send response: {response.status_code}")
        if response.status_code != 200:
            logger.error(f"WhatsApp error: {response.text}")
        return response.status_code == 200
    except Exception as e:
        logger.error(f"WhatsApp send error: {e}")
        return False

# ============================================================
# WEBHOOK ROUTES
# ============================================================
@app.route("/webhook", methods=["GET"])
def verify_webhook():
    """Webhook verification for Meta"""
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
    """Handle incoming WhatsApp messages"""
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
                            
                            # Get sender name
                            sender_name = None
                            if contacts:
                                sender_name = contacts[0].get("profile", {}).get("name")
                            
                            logger.info(f"Message from {phone} ({sender_name}): {text}")
                            
                            # Get AI response
                            ai_response = get_ai_response(phone, text, sender_name)
                            
                            # Send reply
                            send_whatsapp_message(phone, ai_response)
                            
                            logger.info(f"Reply to {phone}: {ai_response[:100]}...")
                        
                        elif message.get("type") in ["image", "audio", "video", "document"]:
                            phone = message["from"]
                            send_whatsapp_message(
                                phone, 
                                "Thank you for sharing that. For now I can only read text messages. Please type your query and I will be happy to help you."
                            )
    except Exception as e:
        logger.error(f"Webhook processing error: {e}")
    
    return jsonify({"status": "ok"}), 200

# ============================================================
# HEALTH CHECK
# ============================================================
@app.route("/", methods=["GET"])
def health():
    return jsonify({
        "status": "running",
        "app": "Dr. Waris Anwar Aesthetics - WhatsApp AI Agent",
        "whatsapp": "connected" if WHATSAPP_TOKEN else "not configured",
        "gemini": "connected" if GEMINI_API_KEY else "not configured",
        "supabase": "connected" if supabase else "not configured",
        "calendar": "connected" if GOOGLE_SERVICE_ACCOUNT_JSON else "not configured"
    })

# ============================================================
# RUN
# ============================================================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
