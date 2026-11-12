import streamlit as st
import requests
import json
from datetime import date, timedelta

st.set_page_config(page_title="Travel Planner", page_icon="✈️", layout="centered")

st.markdown("""
<style>
#MainMenu, footer, header {visibility: hidden;}
.block-container {padding-top: 2rem !important; max-width: 600px !important;}
</style>
""", unsafe_allow_html=True)

# Config
API_URL = "http://localhost:8000/trip/itinerary_openai/invoke"

# UI
st.title("✈️ Travel Itinerary Planner")
st.divider()

destination = st.text_input("Destination", placeholder="e.g. Kyoto, Japan")

col1, col2 = st.columns(2)
with col1:
    start_date = st.date_input("Start Date", value=date.today() + timedelta(days=7))
with col2:
    end_date = st.date_input("End Date", value=date.today() + timedelta(days=14))

if st.button("Generate Itinerary", type="primary", use_container_width=True):
    if not destination.strip():
        st.error("Please enter a destination.")
    elif end_date <= start_date:
        st.error("End date must be after start date.")
    else:
        with st.spinner("Generating your itinerary..."):
            try:
                resp = requests.post(
                    API_URL,
                    headers={"Content-Type": "application/json"},
                    data=json.dumps({
                        "input": {
                            "destination": destination.strip(),
                            "start_date": start_date.strftime("%B %d, %Y"),
                            "end_date": end_date.strftime("%B %d, %Y"),
                        }
                    }),
                    timeout=120,
                )
                resp.raise_for_status()
                result = resp.json()
                output = result.get("output", {})
                text = (output.get("content") if isinstance(output, dict) else output) or str(result)

                st.divider()
                st.subheader(f"{destination} · {(end_date - start_date).days} days")
                st.markdown(text)

            except requests.exceptions.ConnectionError:
                st.error("Could not connect to server. Is FastAPI running on port 8000?")
            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 403:
                    st.error("403 Forbidden — Check that OPENAI_API_KEY is set in the server environment.")
                else:
                    st.error(f"Server error {e.response.status_code}: {e.response.text[:200]}")
            except Exception as e:
                st.error(f"Error: {e}")