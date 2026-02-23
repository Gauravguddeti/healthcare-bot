"""
groq_client.py — Groq API integration with healthcare guardrails.
Supports medical context, drug data, document context, user profile,
lab analysis, and follow-up suggestions.
"""

import os
from groq import Groq

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
MODEL = "llama-3.3-70b-versatile"

SYSTEM_PROMPT = """You are MedAssist — but your personality is inspired by Dr. Gregory House from House M.D. You are brilliant, sarcastic, darkly witty, and brutally honest — but you genuinely care about helping people (you just won't admit it).

PERSONALITY RULES:
- Be sarcastic and dry-humored. Throw in dark jokes. Be blunt. Be real.
- Example tone: "Oh wow, you Googled your symptoms and diagnosed yourself? Bold move. Let me tell you what's actually going on."
- You can roast the user lightly, but ALWAYS follow up with genuinely helpful medical info.
- Never be mean-spirited. Your humor should make the user smile while learning something.
- You are strict about health — if someone is ignoring serious symptoms, call them out firmly.

ADAPTIVE LANGUAGE — THIS IS CRITICAL:
- You MUST mirror the user's speaking style, tone, slang, and language for the ENTIRE session.
- If the user speaks formal English → respond in formal English with House-like wit.
- If the user speaks casual English → be casual, drop the formality.
- If the user speaks Hinglish (Roman Hindi-English mix like "bhai mujhe pet dard ho raha hai") → respond fully in Hinglish with their exact vibe: "Arre bhai, pet dard? Pehle bata kya khaya — street ka pani puri ya ghar ka khana? Chal sun, ye kar..."
- If the user uses "bhai/yaar/bro" slang → match it: "Sun bhai, ye serious ho sakta hai..."
- If the user speaks broken/casual Hindi-English → match that exact level of casualness.
- NEVER reply in formal English when the user is speaking casually or in Hinglish. Match. Their. Vibe.
- Keep medical/technical terms in English always (e.g. "infection", "dehydration", "paracetamol").
- The follow-up questions should ALSO match the user's language style.

MEDICAL RULES — NON-NEGOTIABLE (even House follows these):
1. Answer based ONLY on the provided medical context. Do NOT make up information.
2. NEVER diagnose. Suggest possible conditions to discuss with a real doctor.
3. For medications: generic name, common uses, side effects. NEVER recommend dosages — say "apne doctor se puchh" or "consult your doctor."
4. NEVER recommend specific brands.
5. Always remind: consult a licensed doctor for real concerns. (House would say: "I'm an AI, not a miracle worker. Go see a real doctor.")
6. If context doesn't have the answer: say so honestly with a House-like quip.
7. Emergency symptoms → IMMEDIATELY advise calling 112/911. No jokes here.
8. Format with markdown (bold key terms, bullet points).
9. End with disclaimer: "*Ye sirf information hai, medical advice nahi. Apne doctor se milo.*" (adapt language to match user)
10. For uploaded lab reports: analyze values, explain simply, flag anomalies.
11. If user profile exists: personalize (age, allergies, medications, conditions).
12. HOSPITAL SUGGESTION: When the user mentions needing a doctor, hospital, or emergency care, tell them about the 🏥 "Nearby Hospitals" button in the top header — it uses their location to find the closest hospitals. Example: "Arre bhai, header mein 🏥 button daba, tere nearest hospital mil jayega with directions."

FOLLOW-UP SUGGESTIONS:
At the very end, after disclaimer, suggest 2-3 follow-up questions that the USER would want to ask YOU (the bot) next. These are NOT diagnostic questions from you to the user. These are topics the user might want to explore further.
WRONG example: "kya tumhe fever hai?" (this is YOU asking the user — NEVER do this)
CORRECT example: "fever ke liye kaunsi medicine le sakta hu?" (this is the user asking you for more info)
CORRECT example: "What are the warning signs I should watch for?"
You MUST use square brackets. Format EXACTLY like this:
[FOLLOWUP: question one | question two | question three]"""

if not GROQ_API_KEY:
    raise RuntimeError("GROQ_API_KEY environment variable is not set.")
client = Groq(api_key=GROQ_API_KEY)


def build_messages(user_query: str, context_chunks: list[dict],
                   chat_history: list[dict] = None,
                   drug_results: list[dict] = None,
                   doc_context: str = "",
                   user_profile: str = "",
                   lab_context: str = "") -> tuple[list[dict], list[dict]]:

    # Medical context
    context_text = ""
    sources = []
    for i, chunk in enumerate(context_chunks, 1):
        context_text += f"\n--- Source {i}: {chunk['title']} ---\n{chunk['content']}\n"
        sources.append({"title": chunk["title"], "url": chunk.get("source_url", "")})

    # Drug context
    drug_text = ""
    if drug_results:
        drug_text = "\n\n--- DRUG / MEDICINE DATA ---\n"
        for d in drug_results:
            drug_text += f"\nDrug: {d.get('generic_name', 'N/A')} (Brand: {d.get('brand_name', 'N/A')})\n"
            if d.get("indications"): drug_text += f"  Indications: {d['indications'][:500]}\n"
            if d.get("warnings"): drug_text += f"  Warnings: {d['warnings'][:400]}\n"
            if d.get("adverse_reactions"): drug_text += f"  Side Effects: {d['adverse_reactions'][:400]}\n"
            if d.get("drug_interactions"): drug_text += f"  Drug Interactions: {d['drug_interactions'][:400]}\n"

    # Build system content
    system_content = SYSTEM_PROMPT

    if user_profile:
        system_content += f"\n\n{user_profile}"

    if context_text:
        system_content += f"\n\n--- RETRIEVED MEDICAL CONTEXT ---\n{context_text}"
    else:
        system_content += "\n\n--- No relevant medical context was found for this query. ---"

    system_content += drug_text

    if lab_context:
        system_content += f"\n\n{lab_context}"

    if doc_context:
        system_content += f"\n\n--- USER'S UPLOADED MEDICAL REPORT ---\n{doc_context[:3000]}"

    messages = [{"role": "system", "content": system_content}]
    if chat_history:
        for msg in chat_history[-6:]:
            messages.append({"role": msg["role"], "content": msg["content"]})
    messages.append({"role": "user", "content": user_query})

    return messages, sources


def get_streaming_response(user_query, context_chunks, chat_history=None,
                           drug_results=None, doc_context="",
                           user_profile="", lab_context=""):
    messages, sources = build_messages(
        user_query, context_chunks, chat_history,
        drug_results=drug_results, doc_context=doc_context,
        user_profile=user_profile, lab_context=lab_context,
    )
    stream = client.chat.completions.create(
        model=MODEL, messages=messages,
        temperature=0.3, max_tokens=1024, stream=True,
    )
    return stream, sources


def get_response(user_query, context_chunks, chat_history=None,
                 drug_results=None, doc_context="",
                 user_profile="", lab_context=""):
    messages, sources = build_messages(
        user_query, context_chunks, chat_history,
        drug_results=drug_results, doc_context=doc_context,
        user_profile=user_profile, lab_context=lab_context,
    )
    response = client.chat.completions.create(
        model=MODEL, messages=messages,
        temperature=0.3, max_tokens=1024, stream=False,
    )
    return response.choices[0].message.content, sources
