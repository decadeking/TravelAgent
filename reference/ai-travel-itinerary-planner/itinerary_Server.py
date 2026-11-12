from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
import os
from dotenv import load_dotenv
from fastapi import FastAPI
from langserve import add_routes
import uvicorn


def load_environment():
    load_dotenv()

    if os.getenv("OPENAI_API_KEY"):
        os.environ["OPENAI_API_KEY"] = os.getenv("OPENAI_API_KEY")
    else:
        raise EnvironmentError("OPENAI_API_KEY is missing from environment / .env file")


def get_travel_itinerary_system_api_prompts():

    ITINERARY_SYSTEM = """You are an expert travel planner. Given a destination and travel dates, produce a structured day-by-day itinerary.

STRICT OUTPUT FORMAT — follow exactly, no deviations:

---
**Assumptions:** [State any assumptions made, e.g. solo traveller, moderate pace. One line.]

Day 1 — [One-sentence theme for the day]
Morning
[1–2 activities. For each: name the place/area, what to do, why it's worth it. Include walking/transit time to next stop if relevant.]

Afternoon
[1–2 activities. Same format.]

Evening
[1 activity or neighbourhood recommendation. Mention type of dining area, atmosphere.]

Day 2 — [One-sentence theme]
Morning
...

[Continue for all days]

---
Planner's Notes
- [Logistics tip 1: what to book in advance]
- [Logistics tip 2: best day/time to visit a specific site]
- [Logistics tip 3: pacing or transport advice]
- [Add more bullets as needed]
---

RULES:
- Always use exactly "Day N — " (with an em dash) to open each day
- Always use exactly "Morning", "Afternoon", "Evening" as sub-headings (no ##, no bold, no colon)
- Keep each activity description to 2–4 sentences: what, where, why
- Include approximate travel times between locations when they exceed 10 minutes
- Do not name specific restaurants unless asked — refer to neighbourhoods and cuisine types instead
- Tone: warm, confident, like advice from a well-travelled friend
- Never add extra sections or change the format"""

    itinerary_prompt = ChatPromptTemplate.from_messages([
        ("system", ITINERARY_SYSTEM),
        ("human",
         "Destination: {destination}\n"
         "Travel dates: {start_date} to {end_date}\n\n"
         "Generate the full itinerary now.")
    ])

    return itinerary_prompt


def create_travel_itinerary_system_api():
    app = FastAPI(
        title="Travel Itinerary Planner API",
        version="1.0.0",
        description="LangServe-powered travel itinerary generator",
    )

    itinerary_prompt = get_travel_itinerary_system_api_prompts()
    model = ChatOpenAI(model="gpt-4o", temperature=0.7)

    add_routes(
        app,
        itinerary_prompt | model,
        path="/trip/itinerary_openai",
    )

    uvicorn.run(app, host="localhost", port=8000)


if __name__ == "__main__":
    load_environment()
    create_travel_itinerary_system_api()