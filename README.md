# 🩺 MedAssist — Healthcare AI Chatbot

A full-stack AI-powered healthcare chatbot with multilingual support, Dr. House personality, symptom checking, drug interaction analysis, lab report analysis, and more.

![MedAssist Screenshot](frontend/screenshot.png)

## ✨ Features

| Feature | Description |
|---------|-------------|
| 🤖 **AI Chat** | RAG-powered responses using Groq (Llama 3.3 70B) + MedlinePlus knowledge base |
| 🌐 **11 Indian Languages** | Sarvam AI translation (Hindi, Kannada, Tamil, Telugu, Bengali, etc.) |
| 🗣️ **Adaptive Speech** | Mirrors user's tone — formal English, Hinglish, bhai-speak, etc. |
| 🏨 **Dr. House Personality** | Sarcastic, witty, but genuinely helpful medical advice |
| 🩻 **Symptom Checker** | Guided 3-step modal (age, symptoms, severity) |
| 💊 **Drug Interaction Checker** | FDA drug database (339 drugs) with interaction analysis |
| 🧪 **Lab Report Analyzer** | Upload blood report PDF → auto-detect 20+ values, flag abnormals |
| 🏥 **Nearby Hospital Finder** | Geolocation + OpenStreetMap to find hospitals within 5km |
| 📤 **Export Chat as PDF** | Download branded consultation report with timestamps |
| 👤 **Health Profile Memory** | Auto-extracts age, allergies, medications, conditions from conversation |
| 🎙️ **Voice Input** | Web Speech API for hands-free queries |
| 🚨 **Emergency Detection** | Detects critical symptoms and shows emergency alert |
| 💬 **Follow-up Suggestions** | Context-aware clickable chips for next questions |
| 📚 **Medical Tooltips** | Hover over 45 medical terms for instant definitions |
| 💾 **Chat Persistence** | Conversations saved in localStorage |

## 🛠️ Tech Stack

- **Backend**: Python, FastAPI, SQLite FTS5, Groq API, Sarvam AI API
- **Frontend**: HTML, CSS, Vanilla JavaScript
- **LLM**: Llama 3.3 70B Versatile (via Groq)
- **Translation**: Sarvam AI Mayura v1
- **Knowledge Base**: MedlinePlus + OpenFDA drug data

## 🚀 Setup

### 1. Clone
```bash
git clone https://github.com/Gauravguddeti/healthcare-bot.git
cd healthcare-bot
```

### 2. Install Dependencies
```bash
cd backend
pip install -r requirements.txt
```

### 3. Build Knowledge Base
```bash
python scraper.py        # Scrape MedlinePlus (700+ medical topics)
python scrape_drugs.py   # Fetch FDA drug data (339 drugs)
```

### 4. Set API Keys
Edit `backend/groq_client.py` and `backend/sarvam_client.py` with your API keys:
- **Groq**: Get key at [console.groq.com](https://console.groq.com)
- **Sarvam AI**: Get key at [sarvam.ai](https://www.sarvam.ai)

### 5. Run Backend
```bash
cd backend
python -m uvicorn main:app --host 0.0.0.0 --port 8000
```

### 6. Open Frontend
Open `frontend/index.html` in your browser. That's it!

## 📁 Project Structure

```
healthcare-chatbot/
├── backend/
│   ├── main.py              # FastAPI server (chat, upload, profile)
│   ├── groq_client.py       # LLM integration with Dr. House prompt
│   ├── sarvam_client.py     # Multilingual translation (chunked)
│   ├── lab_analyzer.py      # Blood report value extraction
│   ├── database.py          # SQLite FTS5 search engine
│   ├── scraper.py           # MedlinePlus topic scraper
│   ├── scrape_drugs.py      # OpenFDA drug data fetcher
│   └── requirements.txt
├── frontend/
│   ├── index.html           # Main app UI
│   ├── style.css            # Design system
│   ├── script.js            # All frontend logic
│   └── medical_terms.js     # Tooltip definitions
├── .gitignore
└── README.md
```

## ⚠️ Disclaimer

This chatbot provides **informational health content only**. It is **not** a substitute for professional medical advice, diagnosis, or treatment. Always consult a licensed healthcare provider.

## 📄 License

MIT License
