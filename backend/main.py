"""
main.py — FastAPI backend for the Healthcare AI Chatbot v3.
Features: streaming chat, multilingual (Sarvam AI), emergency detection,
drug search, document upload + lab analysis, and user profile memory.
"""

import json
import re
import uuid
from collections import defaultdict
from fastapi import FastAPI, Request, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse

from database import init_db, search, search_drugs
from groq_client import get_streaming_response, get_response
from sarvam_client import translate_to_english, translate_from_english, get_supported_languages
from lab_analyzer import analyze_report, format_findings

# ─── App ────────────────────────────────────────────────────────────
app = FastAPI(title="Healthcare AI Chatbot", version="3.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

sessions: dict[str, list[dict]] = defaultdict(list)
session_docs: dict[str, str] = {}
session_lab_findings: dict[str, str] = {}

# ─── User Profile Memory ───────────────────────────────────────────
# Stores extracted profile tags per session: {session_id: {tag: value}}
session_profiles: dict[str, dict[str, str]] = defaultdict(dict)

PROFILE_PATTERNS = {
    "age": [
        r"(?:i am|i'm|my age is|age:?)\s*(\d{1,3})\s*(?:years?\s*old|yrs?|yo)?",
        r"(\d{1,3})\s*(?:years?\s*old|yrs?\s*old|yo)\b",
        r"(?:meri umar|meri age|umar)\s*(\d{1,3})",
        r"(?:mai|main|mein)\s*(\d{1,3})\s*(?:saal|sal|years?)\s*(?:ka|ki|ke|ka hu|ki hu)?",
    ],
    "gender": [
        r"(?:i am|i'm)\s*(?:a\s*)?(male|female|man|woman|boy|girl)\b",
        r"(?:gender|sex)[:\s]*(male|female|other)\b",
        r"\b(ladka|ladki|aurat|mard)\b",
    ],
    "weight": [
        r"(?:i weigh|my weight is|weight:?)\s*(\d{2,3})\s*(?:kg|lbs?|pounds?|kilos?)?",
        r"(?:mera weight|wajan)\s*(\d{2,3})\s*(?:kg|kilo)?",
    ],
    "height": [
        r"(?:my height is|height:?|i am)\s*(\d{1,3}(?:\.\d+)?)\s*(?:cm|ft|feet|inches?|m)\b",
        r"(\d)'(\d{1,2})\"",
        r"(?:meri height|lambai)\s*(\d{1,3})\s*(?:cm|ft)?",
    ],
    "blood_group": [
        r"(?:blood\s*(?:group|type)[:\s]*)([ABO]{1,2}[+-]?\s*(?:positive|negative|ve)?)",
        r"\b(A|B|AB|O)\s*(?:\+|-|positive|negative)\b",
    ],
    "allergies": [
        r"(?:i(?:'m| am) allergic to|allerg(?:y|ies)[:\s]*)\s*(.+?)(?:\.|,|$)",
        r"(?:mujhe|muze|meko)\s*(.+?)\s*(?:se\s*allergy|se\s*problem)\b",
        r"allergy\s*(?:hai|he)\s*(.+?)(?:\.|,|$)",
    ],
    "medications": [
        r"(?:i(?:'m| am) (?:taking|on)|(?:current )?medication[s]?[:\s]*)\s*(.+?)(?:\.|,|$)",
        r"(?:mai|main|mein)\s*(.+?)\s*(?:le\s*raha|le\s*rahi|kha\s*raha|kha\s*rahi)\b",
        r"(?:dawai|medicine|tablet)\s*(?:le\s*raha|le\s*rahi)\s*(.+?)(?:\.|,|$)",
    ],
    "conditions": [
        r"(?:i have|i(?:'ve| have) been diagnosed with|suffering from|condition[s]?[:\s]*)\s*(.+?)(?:\.|,|$)",
        r"(?:mujhe|muze|meko)\s*(.+?)\s*(?:hai|he|tha|thi)\b",
    ],
    "symptoms": [
        r"(?:i(?:'m| am) (?:feeling|experiencing|having)|my symptoms?[:\s]*)\s*(.+?)(?:\.|$)",
        r"(?:mujhe|muze|meko|mere)\s*(.+?)\s*(?:ho\s*raha|ho\s*rahi|hai|he|dard|problem)\b",
        r"(.+?)\s*(?:dard|pain|bukhar|fever|sar dard|pet dard|headache)",
    ],
}


def extract_profile(message: str, session_id: str):
    """Extract profile tags from user message and store them."""
    msg_lower = message.lower()
    profile = session_profiles[session_id]

    for tag, patterns in PROFILE_PATTERNS.items():
        for pattern in patterns:
            match = re.search(pattern, msg_lower, re.IGNORECASE)
            if match:
                value = match.group(1).strip()
                if tag == "gender":
                    # Normalize gender
                    if value in ("man", "boy"):
                        value = "male"
                    elif value in ("woman", "girl"):
                        value = "female"

                # For list-type tags, append rather than overwrite
                if tag in ("allergies", "medications", "conditions", "symptoms"):
                    existing = profile.get(tag, "")
                    if existing and value not in existing:
                        profile[tag] = f"{existing}, {value}"
                    else:
                        profile[tag] = value
                else:
                    profile[tag] = value
                break


def format_profile(session_id: str) -> str:
    """Format profile as a context string for the LLM."""
    profile = session_profiles.get(session_id, {})
    if not profile:
        return ""
    lines = ["--- USER HEALTH PROFILE ---"]
    for tag, value in profile.items():
        lines.append(f"#{tag}: {value}")
    return "\n".join(lines)


# ─── Emergency Detection ───────────────────────────────────────────
EMERGENCY_PATTERNS_RE = [re.compile(p, re.IGNORECASE) for p in [
    # Physical emergencies
    r"\bchest\s*pain\b", r"\bheart\s*attack\b", r"\bstroke\b",
    r"\bcan'?t\s*breathe\b", r"\bdifficulty\s*breathing\b",
    r"\bsevere\s*bleeding\b", r"\bunconscious\b", r"\bseizure\b",
    r"\boverdose\b", r"\bpoisoning\b", r"\banaphyla",
    r"\bchoking\b", r"\bsevere\s*allergic\b",
    # Suicidal / self-harm — English
    r"\bsuicid", r"\bkill\s*myself\b", r"\bwant\s*to\s*die\b",
    r"\bend\s*(it|my\s*life|everything)\b", r"\bdone\s*with\s*(life|everything|it\s*all)\b",
    r"\bit'?s\s*done\s*for\s*me\b", r"\bno\s*reason\s*to\s*live\b",
    r"\bself\s*harm\b", r"\bcut\s*my\s*self\b", r"\bhurt\s*myself\b",
    r"\bnot\s*worth\s*living\b", r"\bwant\s*to\s*disappear\b",
    # Suicidal / self-harm — Hinglish
    r"\bmujhe\s*jeena\s*nahi\b", r"\bnahi\s*rahna\b", r"\bjaan\s*de\s*du\b",
    r"\bmarna\s*chahta\b", r"\bmarna\s*chahti\b", r"\bkhatam\s*kar\s*(lu|lena|du)\b",
    r"\bzindagi\s*nahi\s*chahiye\b", r"\bjeene\s*ka\s*mann\s*nahi\b",
    # Suicidal / self-harm — Marathinglish
    r"\bmala\s*jagaycha\s*nahi\b", r"\bmala\s*maraycha\s*aahe\b",
    r"\bsampavun\s*(takto|takte)\b", r"\bjag\s*nako\s*watata\b",
    r"\bnahi\s*rahaycha\b",
]]

EMERGENCY_MESSAGE = (
    "🚨 **Please reach out for help right now.**\n\n"
    "If you're having thoughts of hurting yourself or feeling like you can't go on, "
    "you don't have to face this alone. There are people who care and want to help.\n\n"
    "**India crisis helplines:**\n"
    "- iCall (TISS): **9152987821**\n"
    "- Vandrevala Foundation: **1860-2662-345** (24/7, free)\n"
    "- AASRA: **9820466627**\n"
    "- Emergency / Ambulance: **112 / 108**\n\n"
    "**International:**\n"
    "- US: 988 Suicide & Crisis Lifeline\n"
    "- UK: Samaritans 116 123\n\n"
    "Use the 🏥 **Nearby Hospitals** button in the header to find emergency care close to you.\n\n"
    "*You matter. Please talk to someone.*"
)


def detect_emergency(msg: str) -> bool:
    return any(p.search(msg) for p in EMERGENCY_PATTERNS_RE)


def is_drug_query(msg: str) -> bool:
    patterns = [r"\bmedicine\b", r"\bmedication\b", r"\bdrug\b", r"\btablet\b",
                r"\bshould\s*i\s*take\b", r"\bwhat\s*(?:can|should)\s*i\s*take\b",
                r"\btreatment\b", r"\bpainkiller\b", r"\bantibiotic\b",
                r"\bdosage\b", r"\bside\s*effect", r"\bdrug\s*interaction"]
    return any(re.search(p, msg, re.IGNORECASE) for p in patterns)


@app.on_event("startup")
def startup():
    init_db()


# ─── Chat Endpoints ────────────────────────────────────────────────

@app.post("/chat")
async def chat_stream(request: Request):
    body = await request.json()
    user_message = body.get("message", "").strip()
    session_id = body.get("session_id", str(uuid.uuid4()))
    lang = body.get("language", "en-IN")

    if not user_message:
        return JSONResponse({"error": "Message cannot be empty."}, status_code=400)

    # 1. Translate to English if needed
    msg_for_llm = user_message
    if lang != "en-IN":
        msg_for_llm = translate_to_english(user_message, lang)

    # 2. Extract profile info from message
    extract_profile(msg_for_llm, session_id)
    user_profile = format_profile(session_id)

    # 3. Emergency check
    emergency = detect_emergency(msg_for_llm)

    # 4. Knowledge + drug search
    context_chunks = search(msg_for_llm, top_k=5)
    drug_results = search_drugs(msg_for_llm, top_k=3) if is_drug_query(msg_for_llm) else []

    # 5. Document context + lab findings
    doc_context = session_docs.get(session_id, "")
    lab_context = session_lab_findings.get(session_id, "")

    # 6. History
    history = sessions[session_id]

    # 7. Stream from Groq
    stream, sources = get_streaming_response(
        msg_for_llm, context_chunks, history,
        drug_results=drug_results, doc_context=doc_context,
        user_profile=user_profile, lab_context=lab_context,
    )

    async def event_generator():
        if emergency:
            yield f"data: {json.dumps({'type': 'emergency', 'content': EMERGENCY_MESSAGE})}\n\n"

        # Send profile update to frontend
        profile = session_profiles.get(session_id, {})
        if profile:
            yield f"data: {json.dumps({'type': 'profile', 'profile': profile})}\n\n"

        full_response = ""
        try:
            for chunk in stream:
                delta = chunk.choices[0].delta
                if delta and delta.content:
                    token = delta.content
                    full_response += token
                    yield f"data: {json.dumps({'type': 'token', 'content': token})}\n\n"

            # Translate response if needed
            if lang != "en-IN" and full_response:
                translated = translate_from_english(full_response, lang)
                yield f"data: {json.dumps({'type': 'translated', 'content': translated})}\n\n"

            yield f"data: {json.dumps({'type': 'sources', 'sources': sources})}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"

            sessions[session_id].append({"role": "user", "content": msg_for_llm})
            sessions[session_id].append({"role": "assistant", "content": full_response})

        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


@app.post("/chat/sync")
async def chat_sync(request: Request):
    body = await request.json()
    user_message = body.get("message", "").strip()
    session_id = body.get("session_id", str(uuid.uuid4()))
    lang = body.get("language", "en-IN")

    if not user_message:
        return JSONResponse({"error": "Message cannot be empty."}, status_code=400)

    msg_for_llm = translate_to_english(user_message, lang) if lang != "en-IN" else user_message
    extract_profile(msg_for_llm, session_id)

    context_chunks = search(msg_for_llm, top_k=5)
    drug_results = search_drugs(msg_for_llm, top_k=3) if is_drug_query(msg_for_llm) else []
    doc_context = session_docs.get(session_id, "")
    lab_context = session_lab_findings.get(session_id, "")
    user_profile = format_profile(session_id)
    history = sessions[session_id]

    response_text, sources = get_response(
        msg_for_llm, context_chunks, history,
        drug_results=drug_results, doc_context=doc_context,
        user_profile=user_profile, lab_context=lab_context,
    )

    if lang != "en-IN":
        response_text = translate_from_english(response_text, lang)

    sessions[session_id].append({"role": "user", "content": msg_for_llm})
    sessions[session_id].append({"role": "assistant", "content": response_text})

    return JSONResponse({
        "response": response_text, "sources": sources,
        "session_id": session_id, "emergency": detect_emergency(msg_for_llm),
        "profile": dict(session_profiles.get(session_id, {})),
    })


# ─── Other Endpoints ───────────────────────────────────────────────

@app.get("/history/{session_id}")
async def get_history(session_id: str):
    return JSONResponse({"session_id": session_id, "history": sessions.get(session_id, [])})


@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "Healthcare AI Chatbot v3"}


@app.get("/languages")
async def list_languages():
    return JSONResponse(get_supported_languages())


@app.get("/profile/{session_id}")
async def get_profile(session_id: str):
    return JSONResponse(dict(session_profiles.get(session_id, {})))


@app.post("/upload")
async def upload_document(file: UploadFile = File(...)):
    import io

    content = await file.read()
    extracted_text = ""

    if file.filename.endswith(".pdf"):
        try:
            from PyPDF2 import PdfReader
            reader = PdfReader(io.BytesIO(content))
            pages_text = [page.extract_text() or "" for page in reader.pages]
            extracted_text = "\n".join(pages_text)
        except Exception as e:
            return JSONResponse({"error": f"Failed to parse PDF: {str(e)}"}, status_code=400)
    else:
        extracted_text = content.decode("utf-8", errors="ignore")

    if len(extracted_text) > 5000:
        extracted_text = extracted_text[:5000] + "\n...(truncated)"

    # Run lab analysis
    findings = analyze_report(extracted_text)
    findings_text = format_findings(findings)

    # Store for session use
    session_docs["default"] = extracted_text
    if findings_text:
        session_lab_findings["default"] = findings_text

    return JSONResponse({
        "text": extracted_text,
        "filename": file.filename,
        "chars": len(extracted_text),
        "lab_findings": [f for f in findings],
        "lab_summary": findings_text,
    })
