# ✈️ AI Travel Itinerary Planner

**A production-ready LLM application** that generates structured, day-by-day travel itineraries using LangChain, OpenAI GPT-4o, FastAPI with LangServe, and Streamlit — all wired together in a clean client-server architecture.

> Built to demonstrate end-to-end LLM application development: prompt engineering, API serving with LangServe, and a minimal Streamlit frontend.

---

## 🔍 What This Project Demonstrates

This is not a wrapper around ChatGPT. It is a **full LLM application stack**:

- **Prompt engineering** — A structured system prompt that enforces consistent, parseable output format across any destination
- **LangChain orchestration** — `ChatPromptTemplate` + `ChatOpenAI` chained and served via LangServe
- **REST API design** — FastAPI backend exposing the LLM chain at a typed `/invoke` endpoint
- **Frontend integration** — Streamlit client that POSTs to the LangServe API and renders structured markdown output
- **Environment management** — `python-dotenv` with a clean `.env.example` pattern

**Input:** City name + travel dates  
**Output:** Day-by-day itinerary with Morning / Afternoon / Evening blocks, activity descriptions with travel times, and a Planner's Notes section

---

## 🗂️ Project Structure

```
ai-travel-itinerary-planner/
├── itinerary_Server.py          # FastAPI + LangServe backend
├── travel_itinerary_client.py   # Streamlit frontend
├── requirements.txt             # Pinned Python dependencies
├── .env.example                 # Environment variable template (safe to commit)
├── .gitignore                   # Keeps .env and secrets out of git
└── README.md
```

---

## ⚙️ Tech Stack

| Layer | Technology | Version |
|---|---|---|
| LLM | OpenAI GPT-4o | via API |
| Orchestration | LangChain + LangChain-OpenAI | 0.3.x |
| API Server | FastAPI + LangServe | 0.115 / 0.3.1 |
| Frontend | Streamlit | 1.45 |
| Runtime | Python | 3.9+ |
| Config | python-dotenv | 1.1.0 |

---

## 🚀 Quickstart

### 1. Clone
```bash
git clone https://github.com/YOUR_USERNAME/ai-travel-itinerary-planner.git
cd ai-travel-itinerary-planner
```

### 2. Virtual environment
```bash
# Windows
python -m venv venv && venv\Scripts\activate

# macOS / Linux
python -m venv venv && source venv/bin/activate
```

### 3. Install dependencies
```bash
pip install -r requirements.txt
```

### 4. Configure environment
```bash
cp .env.example .env
# Add your OpenAI API key to .env
```

```env
OPENAI_API_KEY=sk-your-key-here
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-4o
```

Get your key → https://platform.openai.com/api-keys

### 5. Run — two terminals required

**Terminal 1 — Backend**
```bash
python itinerary_Server.py
# Runs at http://localhost:8000
# Swagger docs at http://localhost:8000/docs
```

**Terminal 2 — Frontend**
```bash
streamlit run travel_itinerary_client.py
# Opens at http://localhost:8501
```

---

## 🧠 Architecture

```
Streamlit UI
    │
    │  POST /trip/itinerary_openai/invoke
    │  { destination, start_date, end_date }
    ▼
FastAPI + LangServe
    │
    │  ChatPromptTemplate | ChatOpenAI
    ▼
OpenAI GPT-4o API
    │
    │  Structured itinerary text
    ▼
Streamlit renders markdown output
```

### How LangServe works here
`add_routes()` takes the LangChain chain (`prompt | model`) and automatically exposes:
- `POST /trip/itinerary_openai/invoke` — synchronous call
- `POST /trip/itinerary_openai/stream` — streaming (available by default)
- `GET  /trip/itinerary_openai/input_schema` — JSON schema of expected input
- `GET  /trip/itinerary_openai/output_schema` — JSON schema of output

---

## 📐 Prompt Design

The system prompt enforces a **strict, parseable output format**:

```
Assumptions: [one line]

Day 1 — [theme]
Morning
[activities]

Afternoon
[activities]

Evening
[activity + area type]

Planner's Notes
- [logistics bullets]
```

Key design decisions:
- Em dash (`—`) separates day number from theme — makes regex parsing reliable
- `Morning` / `Afternoon` / `Evening` as plain words, no markdown — consistent splitting
- Activity descriptions capped at 2–4 sentences — avoids hallucination padding
- No specific restaurant names — reduces factual error risk

---

## 📋 API Reference

**Endpoint:** `POST http://localhost:8000/trip/itinerary_openai/invoke`

**Request body:**
```json
{
  "input": {
    "destination": "Kyoto, Japan",
    "start_date": "April 23, 2026",
    "end_date": "April 27, 2026"
  }
}
```

**Response:**
```json
{
  "output": {
    "content": "Assumptions: Solo traveller...\n\nDay 1 — ...",
    "type": "ai"
  }
}
```

---

## 🌐 Destinations Tested

Works for any city. Verified output quality for:

**India** — Mumbai · Delhi · Bengaluru · Hyderabad · Chennai · Pune · Kolkata · Jaipur · Nagpur · Ahmedabad · Kochi · Goa · Varanasi · Amritsar · Udaipur · Mysuru · Indore · Bhopal · Agra · Leh · Manali · Rishikesh · Darjeeling · Coimbatore · Surat

**Europe** — Amsterdam · Berlin · Paris · Rome · Barcelona · Lisbon · Vienna · Prague · Budapest · Athens · Dubrovnik · Split · Porto · Florence · Edinburgh · Kraków · Bruges · Rotterdam · Utrecht · Eindhoven · Munich · Zurich · Copenhagen · Stockholm · Oslo · Helsinki

**Southeast Asia** — Bangkok · Bali · Singapore · Kuala Lumpur · Hanoi · Ho Chi Minh City · Chiang Mai · Phuket · Phnom Penh · Luang Prabang · Jakarta · Penang

**East Asia** — Tokyo · Kyoto · Osaka · Seoul · Busan · Taipei · Hong Kong · Shanghai · Beijing

**Middle East & Africa** — Dubai · Istanbul · Cairo · Marrakech · Nairobi · Cape Town · Doha · Abu Dhabi

**Americas** — New York · Mexico City · Buenos Aires · Rio de Janeiro · Bogotá · Lima · Cartagena · Havana

---

## 🔧 Extending This Project

This codebase is intentionally minimal and easy to extend:

| Extension | What to change |
|---|---|
| Add streaming output | Use `/stream` endpoint + `st.write_stream()` in client |
| Add user preferences (trip style, group size) | Add variables to `ChatPromptTemplate` and input fields in Streamlit |
| Swap model | Change `model=` in `ChatOpenAI()` — works with any OpenAI-compatible endpoint |
| Add memory / multi-turn chat | Wrap chain with `RunnableWithMessageHistory` |
| Deploy backend | `uvicorn itinerary_Server:app` behind any reverse proxy (nginx, Caddy) |
| Containerise | Add `Dockerfile` — FastAPI + uvicorn are container-native |

---

## 📋 Requirements

- Python 3.9 or higher
- OpenAI API key with GPT-4o access
- Active internet connection for API calls

---

## ⚠️ Disclaimer

Travel itineraries are AI-generated suggestions based on the model's training data. Opening hours, prices, transport schedules, and safety conditions change — always verify through official sources before travelling. This tool does not book anything or access real-time data.

---

## 📄 License

MIT — free to use, modify, and distribute for personal and commercial projects.

---

## 🤝 Contributing

Issues and pull requests welcome. For significant changes, open an issue first to discuss the direction.
