---
title: Vocalyx AI Telephony
emoji: 🎙️
colorFrom: green
colorTo: blue
sdk: gradio
sdk_version: 5.12.0
app_file: app.py
pinned: false
---

# Vocalyx — Local AI Voice Agent & Lead Qualification Platform

Vocalyx is a complete, local-first SaaS prototype that enables business owners to clone their voice locally, conduct real-time AI-powered phone sales calls directly in the browser, maintain persistent structured contact memory, analyze calls for lead scoring & qualification, and receive instant Telegram alerts.

---

## 🌟 Key Features

1. **Local Voice Cloning (TTS):** Uses `chatterbox-tts` (Resemble AI) running locally with PyTorch on NVIDIA CUDA (`cuda` with automatic `cpu` fallback).
2. **Zero-Latency Browser Speech-to-Text (STT):** Leverages the browser Web Speech API (`webkitSpeechRecognition`) for local, free, zero-overhead speech recognition.
3. **Conversational LLM Intelligence:** Powered by Groq (`openai/gpt-oss-20b`) for ultra-fast, natural conversational turns and structured JSON post-call analysis.
4. **Retrieval-Augmented Generation (RAG):** Local document search using `faiss-cpu` and `sentence-transformers` (`all-MiniLM-L6-v2`) to ground conversations in your business documents (PDF, TXT, MD).
5. **Persistent Contact Memory:** Tracks conversation state, last topic, interest level, customer concerns, and commitments across calls in SQLite.
6. **Automated Lead Intelligence:** Calculates lead scores (0–100), reasoning, sentiment, and outcomes (*Interested, Not Interested, Requested Callback, Time-Waster, Needs Follow-up*).
7. **Instant Telegram Alerts:** Sends instant post-call scorecards and summaries to your phone.
8. **Modern Glassmorphism UI:** Ultra-clean dark theme dashboard featuring an active Call Simulator, Contacts Manager, Knowledge Base uploader, Voice Studio with CFG sliders, and Call History with searchable analytics.

---

## 🏗️ Architecture & Directory Layout

```
vocalyx/
├── main.py                  # Entrypoint (runs Uvicorn on 0.0.0.0:8080)
├── requirements.txt         # Project dependencies
├── voice_clone.mp3          # Reference audio sample for voice cloning
├── backend/
│   ├── __init__.py
│   ├── requirements.txt     # Backend Python dependencies
│   ├── main.py              # FastAPI application, static mounts & REST API
│   ├── config.py            # API keys (Groq, Telegram), CUDA device & paths
│   ├── database.py          # SQLAlchemy SQLite connection & session maker
│   ├── models.py            # ORM models (Contact, Script, Document, Call)
│   ├── tts_engine.py        # Chatterbox TTS with CUDA acceleration & caching
│   ├── rag_engine.py        # FAISS vector store + SentenceTransformers
│   ├── llm_engine.py        # Groq client for conversation & call analysis
│   ├── telegram_alert.py    # Formatted Telegram alert dispatcher
│   ├── vocalyx.db           # SQLite database (auto-generated)
│   ├── tts_output/          # Generated speech WAV files
│   └── uploaded_docs/       # Knowledge base documents
└── frontend/
    ├── index.html           # Single-Page Application (SPA)
    ├── style.css            # Dark glassmorphism styling
    └── script.js            # UI logic, Web Speech API & API client
```

---

## 🚀 Quickstart Guide

### 1. Environment Setup & Installation

Create a virtual environment and install the required dependencies:

```bash
# Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r backend/requirements.txt
```

> **Note on PyTorch & CUDA:**
> If you have an NVIDIA GPU (e.g. GTX 1650 Ti), ensure PyTorch is installed with CUDA support:
> ```bash
> pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu124
> ```

### 2. Configuration

Set your environment variables or update `backend/config.py`:

```bash
export GROQ_API_KEY="your-groq-api-key"
export GROQ_MODEL="openai/gpt-oss-20b"
export TELEGRAM_BOT_TOKEN="your-bot-token"     # Optional
export TELEGRAM_CHAT_ID="your-chat-id"         # Optional
```

### 3. Voice Cloning Sample

Place a short audio clip (~5–15 seconds of clear speech) as `voice_clone.mp3` in the project root, or upload one directly in the **Voice Studio** tab in the web interface.

### 4. Running the Application

Launch the server:

```bash
python main.py
```

Then open your browser (Google Chrome recommended for Web Speech API support) and navigate to:
```
http://localhost:8080
```

---

## 🧭 Dashboard Modules

- **Dashboard:** High-level metrics showing Total Calls, Contacts, Average Lead Score, and Recent Hot Leads.
- **Call Simulator:** Select a contact, click "Start Call", and speak into your microphone. The AI will respond with your cloned voice. Click "End Call" to trigger instant analysis.
- **Contacts:** Create, manage, and view contacts along with their accumulated conversational memory fields.
- **Knowledge Base:** Upload business collateral (PDFs, product sheets, FAQs). The RAG engine chunks and indexes them with FAISS for semantic grounding.
- **Voice Studio:** Upload reference samples, tweak Exaggeration and CFG guidance sliders, and generate test cloned audio clips.
- **Call History:** Comprehensive call logs with transcripts, lead scores, sentiment, outcomes, and Telegram delivery indicators.

