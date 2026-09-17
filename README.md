# 🌍 VoyagrBot

**An Agentic AI-Powered Travel Assistant for Smart Recommendations and Budget-Aware Trip Planning**

VoyagrBot is a multi-agent travel planning application built with Python and Streamlit. It combines specialized AI agents, travel APIs, weather information, route/logistics services, points of interest, events, and budget-aware itinerary generation into a single travel assistant.

## ✨ Features

- 🤖 Multi-agent travel planning and orchestration
- 🗺️ Interactive travel maps with Folium
- 💰 Budget-aware itinerary generation
- 🏨 Hotel and travel-related recommendations
- 📍 Points-of-interest search
- 🌦️ Weather/climate information
- ✈️ Airport and transport assistance
- 🎫 Event discovery
- 💬 AI travel chatbot
- 🧭 Route and logistics planning
- 📄 Itinerary/report generation
- 🔄 Fallback handling for unavailable services

## 🧠 Main Agents

- Master Planner
- Budget Itinerary
- Chatbot
- Climate
- Events Search
- Airport Resolver
- Search POI
- Logistics
- Ground Transport
- Fallback

## 🛠️ Tech Stack

- **Python**
- **Streamlit**
- **OpenAI / Google GenAI**
- **Amadeus API**
- **Tavily**
- **Requests**
- **Folium**
- **Streamlit-Folium**
- **Pandas**
- **Plotly**
- **FPDF**

## 📁 Project Structure

```text
VoyagrBot/
├── agents/
├── core/
├── knowledge_base/
│   └── trip_info.json
├── main.py
├── architecture_diagram.html
├── requirements.txt
├── .env.template
├── .gitignore
└── README.md
```

## 🚀 Installation

### 1. Clone the repository

```bash
git clone <YOUR_GITHUB_REPOSITORY_URL>
cd VoyagrBot
```

### 2. Create a virtual environment

Windows PowerShell:

```powershell
python -m venv venv
.env\Scripts\Activate.ps1
```

### 3. Install dependencies

```powershell
pip install -r requirements.txt
```

### 4. Configure API keys

Copy `.env.template` to `.env` and add your own API credentials.

**Never commit `.env` or API keys to GitHub.**

### 5. Run VoyagrBot

```powershell
streamlit run main.py
```

The application will normally open at:

```text
http://localhost:8501
```

## 🔐 Environment Variables

The application may use credentials such as:

```text
AMADEUS_API_KEY=
AMADEUS_API_SECRET=
TAVILY_API_KEY=
OPENWEATHER_API_KEY=
OPENAI_API_KEY=
```

Add valid values only to your local `.env` file.

## 📌 Academic Project

VoyagrBot was developed as a final-year project exploring agentic AI, multi-agent orchestration, intelligent travel recommendations, API integration, and budget-aware trip planning.

## 👥 Team

Add your final team-member names here.

## 📜 License

Add the license required by your project/college here.
