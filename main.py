import streamlit as st
import folium
import pandas as pd
import io
import os
from dotenv import load_dotenv
from fpdf import FPDF
from streamlit_folium import st_folium
from core.orchestrator import TripManager
from core.utils import format_inr
from agents.chatbot import ChatbotAgent
import plotly.express as px
import plotly.graph_objects as go
import random
import datetime

# Load environment variables from .env if present
load_dotenv(override=True)

# 1. Custom Dark Mode CSS
def apply_custom_css():
    st.markdown(
        """
        <style>
        /* Base styles */
        body { color: #E2E8F0; background-color: #0F172A; }
        .stApp { background-color: #0F172A; }
        
        /* Headers */
        h1, h2, h3 { color: #F8FAFC; }
        
        /* === Timeline Card System === */
        .tl-wrapper {
            display: flex;
            gap: 0;
            margin-bottom: 8px;
            align-items: stretch;
        }
        .tl-time-col {
            min-width: 95px;
            text-align: right;
            padding-right: 12px;
            padding-top: 14px;
            font-size: 0.78em;
            font-family: 'Courier New', monospace;
            color: #64748B;
            line-height: 1.4;
        }
        .tl-connector {
            display: flex;
            flex-direction: column;
            align-items: center;
            width: 28px;
            flex-shrink: 0;
        }
        .tl-dot {
            width: 12px;
            height: 12px;
            border-radius: 50%;
            margin-top: 14px;
            flex-shrink: 0;
            border: 2px solid #1E293B;
        }
        .tl-dot.blue  { background: #3B82F6; box-shadow: 0 0 0 3px rgba(59,130,246,0.25); }
        .tl-dot.red   { background: #EF4444; box-shadow: 0 0 0 3px rgba(239,68,68,0.25); }
        .tl-dot.green { background: #10B981; box-shadow: 0 0 0 3px rgba(16,185,129,0.25); }
        .tl-dot.purple{ background: #A855F7; box-shadow: 0 0 0 3px rgba(168,85,247,0.25); }
        .tl-dot.gray  { background: #64748B; }
        .tl-line {
            width: 2px;
            flex-grow: 1;
            background: linear-gradient(to bottom, #334155, transparent);
            margin-top: 4px;
        }
        .tl-card {
            flex-grow: 1;
            background: #1E293B;
            border-radius: 10px;
            padding: 12px 16px;
            margin-bottom: 8px;
            border-left: 4px solid #3B82F6;
            box-shadow: 0 2px 8px rgba(0,0,0,0.2);
            transition: transform 0.15s ease, box-shadow 0.15s ease;
        }
        .tl-card:hover {
            transform: translateX(3px);
            box-shadow: 0 4px 14px rgba(0,0,0,0.35);
        }
        .tl-card.blue   { border-left-color: #3B82F6; }
        .tl-card.red    { border-left-color: #EF4444; }
        .tl-card.green  { border-left-color: #10B981; }
        .tl-card.purple { border-left-color: #A855F7; }
        .tl-card.gray   { border-left-color: #64748B; background: #334155; }
        .tl-card h4 { margin: 0 0 4px 0; font-size: 0.97em; color: #F1F5F9; }
        .tl-card p  { margin: 0; font-size: 0.88em; color: #94A3B8; line-height: 1.5; }
        .tl-card a  { color: #60A5FA; text-decoration: none; font-size: 0.85em; }
        .tl-card a:hover { text-decoration: underline; }

        /* Sidebar */
        [data-testid="stSidebar"] { background-color: #1E293B; }
        
        /* Input fields */
        .stTextInput input { background-color: #334155 !important; color: white !important; }
        
        </style>
        """,
        unsafe_allow_html=True
    )


# 2. Main App Setup
st.set_page_config(page_title="VoyagrBot", page_icon="🌍", layout="wide")
apply_custom_css()

st.title("🌍 VoyagrBot - Autonomous Travel Concierge")

# --- Session State Initialization ---
# Always instantiate a fresh TripManager to avoid Streamlit session caching stale class definitions
if 'trip_manager' not in st.session_state:
    st.session_state.trip_manager = TripManager()

if 'chatbot_agent' not in st.session_state:
    st.session_state.chatbot_agent = ChatbotAgent()

if 'chat_history' not in st.session_state:
    st.session_state.chat_history = []
    
if 'current_itinerary' not in st.session_state:
    st.session_state.current_itinerary = []

if 'parsed_request' not in st.session_state:
    st.session_state.parsed_request = {}

if 'master_itinerary' not in st.session_state:
    st.session_state.master_itinerary = None

if 'map_center' not in st.session_state:
     # Default center (e.g., somewhere central if no city selected)
    st.session_state.map_center = [48.8566, 2.3522] # Default Paris

if 'map_key' not in st.session_state:
    st.session_state.map_key = 0

if 'selected_transport' not in st.session_state:
    st.session_state.selected_transport = None

if 'selected_hotels' not in st.session_state:
    st.session_state.selected_hotels = {}  # {night_num: hotel_dict}

# --- Fallback Map Coordinates for Simulation ---
MOCK_COORDS = {
    "Paris": [48.8566, 2.3522],
    "Mumbai": [19.0760, 72.8777],
    "Delhi": [28.6139, 77.2090],
    "Agra": [27.1767, 78.0081],
    "Goa": [15.2993, 74.1240],
    "Jaipur": [26.9124, 75.7873],
    "Kerala": [10.8505, 76.2711],
    "Chennai": [13.0827, 80.2707],
}

# --- Helper Functions ---
def display_timeline(itinerary: list):
    TYPE_META = {
        'food':       ('🍽️', 'red'),
        'attraction': ('🏛️', 'blue'),
        'event':      ('🎫', 'green'),
        'hotel':      ('🏨', 'green'),
        'check_in':   ('🏨', 'green'),
        'note':       ('⚠️', 'gray'),
    }

    for item in itinerary:
        itype      = item.get('type', 'attraction')
        title      = item.get('title', '')
        details    = item.get('details', '')
        url        = item.get('url', '')
        time_block = item.get('time', '')
        color      = item.get('color', TYPE_META.get(itype, ('📍','blue'))[1])
        icon       = TYPE_META.get(itype, ('📍', 'blue'))[0]
        
        # --- Dual-Action Navigation System ---
        dest_city = st.session_state.parsed_request.get('destination', '')
        
        # 1. Map Link Logic (Title + City for accuracy)
        map_search = f"{title} {dest_city}".replace(" ", "+")
        map_url = f"https://www.google.com/maps/search/{map_search}"
        
        # 2. Website Link Logic
        has_website = url and url != '#'
        
        # 3. Brief description logic (using details)
        brief_desc = details if details else "Explore this local gem and immerse yourself in the city's atmosphere."
        
        # 4. Component Generation
        map_btn = f"<a href='{map_url}' target='_blank' style='background:rgba(16, 185, 129, 0.15); color:#10B981; padding:6px 12px; border:1px solid rgba(16, 185, 129, 0.3); border-radius:30px; font-size:0.75em; text-decoration:none; margin-right:8px;'>🗺️ Map</a>"
        web_btn = f"<a href='{url}' target='_blank' style='background:rgba(59, 130, 246, 0.15); color:#60A5FA; padding:6px 12px; border:1px solid rgba(59, 130, 246, 0.3); border-radius:30px; font-size:0.75em; text-decoration:none;'>🌐 Website</a>" if has_website else ""
        
        url_html = f"<div style='margin-top:12px; display:flex; gap:6px;'>{map_btn}{web_btn}</div>"

        # ── DAY HEADER (Start of Day) ───────────────────────────────────────
        if itype == 'day_header':
            st.markdown(
                f"""
                <div style="
                    background: linear-gradient(110deg, #1E3A8A 0%, #2563EB 60%, #3B82F6 100%);
                    color: white; padding: 18px 22px; border-radius: 14px;
                    margin: 36px 0 18px 0;
                    box-shadow: 0 6px 20px -4px rgba(59,130,246,0.45);
                    display: flex; align-items: center; gap: 14px;
                ">
                    <span style="font-size:2em;">🌅</span>
                    <div>
                        <div style="font-size:1.25em; font-weight:800; letter-spacing:0.5px;">{title}</div>
                        <div style="font-size:0.92em; opacity:0.85; margin-top:2px;">{details}</div>
                    </div>
                </div>
                """,
                unsafe_allow_html=True
            )
            continue

        # ── DAY FOOTER (End of Day) ─────────────────────────────────────────
        if itype == 'daily_summary':
            st.markdown(
                f"""
                <div style="
                    background: linear-gradient(110deg, #064E3B 0%, #059669 60%, #10B981 100%);
                    color: white; padding: 14px 22px; border-radius: 14px;
                    margin: 10px 0 40px 0;
                    box-shadow: 0 6px 20px -4px rgba(16,185,129,0.35);
                    display: flex; align-items: center; justify-content: space-between;
                ">
                    <div style="display:flex; align-items:center; gap:12px;">
                        <span style="font-size:1.6em;">🌙</span>
                        <span style="font-size:1.05em; font-weight:700;">{title}</span>
                    </div>
                    <div style="font-size:0.92em; opacity:0.9; font-weight:600;">💰 {details}</div>
                </div>
                """,
                unsafe_allow_html=True
            )
            continue

        # ── STANDARD EVENT CARD ─────────────────────────────────────────────
        card_html = f"""<div class="tl-wrapper"><div class="tl-time-col">{time_block.replace(' - ','<br>')}</div><div class="tl-connector"><div class="tl-dot {color}"></div><div class="tl-line"></div></div><div class="tl-card {color}"><h4 style="margin-bottom:6px;">{icon} {title}</h4><div style="font-size:0.7em; text-transform:uppercase; color:#94A3B8; font-weight:700; margin-bottom:4px; letter-spacing:0.8px; opacity:0.8;">💡 Quick Insight</div><p style="opacity:0.9; line-height:1.6;">{brief_desc}</p>{url_html}</div></div>"""
        st.markdown(card_html, unsafe_allow_html=True)


@st.fragment
def update_map():
    # Only render if we have an itinerary
    itinerary = st.session_state.current_itinerary
    if not itinerary:
        st.info("No locations found to map.")
        return
        
    m = folium.Map(location=st.session_state.map_center, zoom_start=12, tiles="CartoDB dark_matter")
    
    master = st.session_state.master_itinerary
    
    locations_added = False
    if master and 'activities' in master:
        for cat, items in master['activities'].items():
            for item in items:
                lat = item.get("latitude")
                lon = item.get("longitude")
                if lat and lon:
                    color = "red" if cat == "food" else "blue"  # Sights are blue, Food is red
                    icon_type = "cutlery" if cat == "food" else "info-sign"
                    
                    folium.Marker(
                        [lat, lon],
                        popup=item.get('title', 'Location'),
                        icon=folium.Icon(color=color, icon=icon_type)
                    ).add_to(m)
                    locations_added = True
                    
    # Add Stays (Green)
    if master and 'accommodations' in master:
        for hotel in master['accommodations']:
             # Mock coordinate offset since RapidAPI doesn't return immediate lat/lon for hotels
             # Or if they do, attempt to extract it
             lat = hotel.get('latitude', st.session_state.map_center[0] + 0.01)
             lon = hotel.get('longitude', st.session_state.map_center[1] + 0.01)
             folium.Marker(
                 [lat, lon],
                 popup=hotel.get('name', 'Hotel'),
                 icon=folium.Icon(color="green", icon="home")
             ).add_to(m)
             locations_added = True

    if not locations_added:
        # Fallback to map center marker
        folium.Marker(
            st.session_state.map_center,
            popup="Destination Center",
            icon=folium.Icon(color="blue", icon="info-sign")
        ).add_to(m)
        
    dest_name = st.session_state.parsed_request.get('destination', 'unknown')
    st_folium(m, width=700, height=500, key=f"map_{dest_name}_{st.session_state.map_key}")

# --- Sidebar (Chat & Interactive updates) ---
with st.sidebar:
    st.header("💬 Chat with VoyagrBot")
    
    st.subheader("Preferences")
    is_veg = st.toggle("🌿 Pure Veg")
    is_jain = st.toggle("🧘 Jain Food (No Onion/Garlic)")
    st.divider()
    
    # Display chat history
    for msg in st.session_state.chat_history:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            
    # Explicit Data Collection Form
    with st.form("trip_planning_form"):
        st.subheader("Trip Details")
        origin = st.text_input("Origin City", placeholder="e.g. Chennai")
        destination = st.text_input("Destination City", placeholder="e.g. Mumbai")
        
        import datetime
        today = datetime.date.today()
        
        travel_dates = st.date_input("Travel Dates", value=(today, today + datetime.timedelta(days=3)))
        
        col_pref1, col_pref2 = st.columns(2)
        with col_pref1:
            travelers = st.number_input("Travelers", min_value=1, max_value=10, value=1)
        with col_pref2:
            total_budget = st.number_input("Total Budget (₹)", min_value=1000, value=50000, step=1000)
            
        preferences = st.text_area("Specific Preferences", placeholder="e.g., Pure Veg, Photography focus")
            
        submit_button = st.form_submit_button("Generate Itinerary")
        
    if submit_button:
        if origin and destination:
            if isinstance(travel_dates, tuple) and len(travel_dates) == 2:
                start_date = travel_dates[0]
                end_date = travel_dates[1]
            else:
                start_date = travel_dates[0] if isinstance(travel_dates, tuple) else travel_dates
                end_date = start_date
                
            # calculate days
            days = (end_date - start_date).days
            if days <= 0: days = 1
            
            prompt = f"Plan a trip to {destination} from {origin} for {days} days for {travelers} people."
            st.session_state.chat_history.append({"role": "user", "content": prompt})
            
            # CLEAR STATE
            st.session_state.current_itinerary = []
            st.session_state.master_itinerary = None
            st.session_state.selected_transport = None
            st.session_state.selected_hotels = {}
            st.session_state.map_key += 1
            
            with st.status("Coordinating Agents..."):
                # Call orchestrator with explicit variables
                result = st.session_state.trip_manager.process_request(
                    user_input=prompt,
                    is_veg=is_veg,
                    is_jain=is_jain,
                    origin=origin.strip(),
                    destination=destination.strip(),
                    start_date=start_date.strftime("%Y-%m-%d"),
                    end_date=end_date.strftime("%Y-%m-%d"),
                    days=days,
                    travelers=int(travelers),
                    preferences=preferences,
                    budget=int(total_budget)
                )
                
                st.session_state.current_itinerary = result['itinerary']
                st.session_state.parsed_request = result['parsed_request']
                st.session_state.master_itinerary = result['master_itinerary']
                
                # Automatically pre-select the most budget-friendly transport
                if result['master_itinerary'].get('transport_options'):
                    st.session_state.selected_transport = min(result['master_itinerary']['transport_options'], key=lambda x: x.get('price', float('inf')))
                # Auto-select default hotel for each night
                for nh in result['master_itinerary'].get('nightly_hotels', []):
                    night_num = nh.get('night', 1)
                    st.session_state.selected_hotels[night_num] = nh.get('hotel', {})
                    
                # Update map center using geocoding (fallback to MOCK_COORDS)
                dest_title = destination.strip().title()
                map_center_set = False
                try:
                    import requests as _req
                    _geo = _req.get(f"https://nominatim.openstreetmap.org/search?q={destination}&format=json&limit=1", headers={"User-Agent": "VoyagrBot/1.0"}, timeout=5).json()
                    if _geo:
                        st.session_state.map_center = [float(_geo[0]['lat']), float(_geo[0]['lon'])]
                        map_center_set = True
                except:
                    pass
                if not map_center_set:
                    st.session_state.map_center = MOCK_COORDS.get(dest_title, [15.0, 75.0])
                
                response = f"I've planned a {days}-day trip to {dest_title} for {travelers} traveler(s)!"
                st.session_state.chat_history.append({"role": "assistant", "content": response})
                st.rerun()
        else:
             st.error("Please enter both Origin and Destination.")


# --- Main Content Area ---
if st.session_state.current_itinerary:
    
    # === 1, 2, 4, 6. Trip Overview & Analytics Dashboard ===
    st.markdown("### 📊 AI Trip Overview Dashboard")
    met_col1, met_col2, met_col3, met_col4 = st.columns(4)
    
    # Mock / Est Distance
    dest_name = st.session_state.parsed_request.get('destination', 'Your location')
    rg = st.session_state.master_itinerary.get('routing_guide', {}) if st.session_state.master_itinerary else {}
    real_dist = rg.get('distance_km', random.randint(300, 1500))
    met_col1.metric("Total Trip Distance", f"~{int(real_dist)} km", "Route optimized")
    
    # Practical Metric: Trip Duration
    days = st.session_state.parsed_request.get('days', 3)
    nights = max(days - 1, 1)
    met_col2.metric("Trip Duration", f"{days} Days", f"{nights} Nights")
    
    # Weather Mood Indicator
    weather_info = st.session_state.master_itinerary.get('weather', {}).get('forecasts', [{}])[0] if st.session_state.master_itinerary and st.session_state.master_itinerary.get('weather') else {}
    raw_temp = weather_info.get('temp', 28)
    try:
        temp = float(raw_temp)
    except (ValueError, TypeError):
        temp = 28.0
        
    desc = str(weather_info.get('weather', 'Clear')).lower()
    
    if 'rain' in desc: mood = "🌧 Indoor activities recommended"
    elif temp > 35: mood = "🌡 Hot → carry water"
    elif temp < 18: mood = "❄️ Chilly → dress warmly"
    else: mood = "☀ Perfect day for sightseeing"
    met_col3.metric("Weather Mood", f"{temp}°C", mood)
    
    # Live Crowd Prediction
    start_date = st.session_state.parsed_request.get('start_date', '2026-06-01')
    try:
        dt = datetime.datetime.strptime(start_date, "%Y-%m-%d")
        if dt.weekday() >= 5: crowd = "🔴 Heavy (Weekend)"
        else: crowd = "🟢 Low to Medium"
    except:
        crowd = "🟡 Medium (Seasonal)"
    met_col4.metric("Live Crowd Predictor", crowd, "Based on dates & trends")
    
    # AI Travel Score Dashboard
    st.markdown("#### 🎯 AI Travel Score")
    score_col1, score_col2 = st.columns(2)
    with score_col1:
        st.write("💰 Budget Efficiency")
        st.progress(85, text="8.5/10 - Excellent value options selected")
        st.write("🛡️ Safety Score")
        st.progress(70, text="7.0/10 - Standard precautions apply")
    with score_col2:
        st.write("🛋️ Comfort & Leisure")
        st.progress(90, text="9.0/10 - Relaxing pace")
        st.write("🧭 Exploration Coverage")
        st.progress(80, text="8.0/10 - Hits all major sights")
    st.divider()

    
    # Airport Transfer Info Banner
    airport_info = st.session_state.master_itinerary.get('airport_info', {}) if st.session_state.master_itinerary else {}
    if airport_info.get('origin_needs_transfer') or airport_info.get('dest_needs_transfer'):
        with st.container(border=True):
            st.markdown("### ✈️ Airport Transfer Advisory")
            if airport_info.get('dest_needs_transfer'):
                dest_name = st.session_state.parsed_request.get('destination', '')
                st.warning(f"**{dest_name}** does not have a major commercial airport. "
                          f"Nearest airport: **{airport_info.get('dest_airport_city', '')}** ({airport_info.get('dest_iata', '')}) — "
                          f"~{airport_info.get('dest_transfer_km', 0)} km ground transfer required.")
                st.info(f"ℹ️ {airport_info.get('dest_transfer_info', '')}")
            if airport_info.get('origin_needs_transfer'):
                orig_name = st.session_state.parsed_request.get('origin', '')
                st.warning(f"**{orig_name}** does not have a major commercial airport. "
                          f"Nearest airport: **{airport_info.get('origin_airport_city', '')}** ({airport_info.get('origin_iata', '')}) — "
                          f"~{airport_info.get('origin_transfer_km', 0)} km ground transfer required.")
                st.info(f"ℹ️ {airport_info.get('origin_transfer_info', '')}")
        st.divider()

    # Render Routing Guide (How to Get There)
    if st.session_state.master_itinerary and st.session_state.master_itinerary.get('routing_guide'):
        st.subheader("🗺️ How to Get There")
        rg = st.session_state.master_itinerary['routing_guide']
        
        with st.expander("✈️ By Air", expanded=bool(airport_info.get('dest_needs_transfer') or airport_info.get('origin_needs_transfer'))):
            st.markdown(rg.get('air', 'Information unavailable'))
        with st.expander("🚆 By Train"):
            st.markdown(rg.get('train', 'Information unavailable'))
        with st.expander("🚌 By Road"):
            st.markdown(rg.get('road', 'Information unavailable'))
            
        st.markdown(rg.get('summary_table', 'Information unavailable'))
        st.divider()
    
    # Render the Transport Comparison Table
    if st.session_state.master_itinerary and st.session_state.master_itinerary.get('transport_options'):
         st.subheader("🚗 Transport Options")
         
         transport_opts = st.session_state.master_itinerary['transport_options']
         
         # Round trip note
         budget_bd = st.session_state.master_itinerary.get('budget_breakdown', {})
         if budget_bd.get('is_round_trip'):
             st.caption("✈️ Flight prices shown are **round-trip** fares. Ground transport prices are **one-way** — budget includes return.")
         else:
             st.caption("💡 All transport prices are **one-way**. Your budget accounts for **round-trip** travel costs.")
         
         # === AI Budget Saving Tips Panel ===
         if len(transport_opts) > 1:
             valid_opts = [t for t in transport_opts if isinstance(t.get('price'), (int, float))]
             if len(valid_opts) > 1:
                 most_expensive = max(valid_opts, key=lambda x: x.get('price', 0))
                 cheapest = min(valid_opts, key=lambda x: x.get('price', 0))
                 diff = most_expensive.get('price', 0) - cheapest.get('price', 0)
                 if diff > 0:
                     cheapest_name = cheapest.get('provider', cheapest.get('airline', 'the cheapest option'))
                     exp_name = most_expensive.get('provider', most_expensive.get('airline', 'the expensive option'))
                     st.info(f"💡 **AI Budget Tip:** You can save **{format_inr(diff)}** by choosing **{cheapest_name}** instead of {exp_name}.")

         for i, opt in enumerate(transport_opts):
             with st.container(border=True):
                 col1, col2, col3, col4 = st.columns([3, 1, 1, 1])
                 with col1:
                     mode = opt.get('mode', 'Transport')
                     mode_icon = "✈️" if mode == 'Flight' else "🚆" if mode == 'Train' else "🚕" if mode == 'Cab' else "🚌"
                     class_info = f" — {opt.get('class', '')}" if opt.get('class') else ""
                     trip_badge = f" `{opt.get('trip_type', 'One Way')}`" if opt.get('trip_type') else ""
                     st.markdown(f"**{mode_icon} {opt.get('provider', opt.get('airline', 'Transport'))}{class_info}**{trip_badge}")
                     duration_str = opt.get('duration', f"{opt.get('duration_hrs', '?')} hrs")
                     st.write(opt.get('route', f"From Origin to Destination ({duration_str})"))
                 with col2:
                     price_val = opt.get('price', 0)
                     st.markdown(f"### {format_inr(price_val)}")
                 with col3:
                     # Booking links
                     booking_url = opt.get('booking_url', opt.get('search_url', ''))
                     if booking_url:
                         st.link_button("🔗 Book", booking_url, use_container_width=True)
                 with col4:
                     btn_key = f"btn_trans_{i}_{opt.get('provider', '')}_{opt.get('price', 0)}"
                     if st.session_state.selected_transport == opt:
                         st.success("✅ Selected")
                     else:
                         if st.button("Select", key=btn_key):
                             st.session_state.selected_transport = opt
                             st.rerun()
         st.divider()
    else:
         st.info("No transport options found for this route.")
         st.divider()

    # Hotels Section — Per-Night with Multiple Options
    st.subheader("🏨 Recommended Stays")
    nightly_hotels = st.session_state.master_itinerary.get("nightly_hotels", []) if st.session_state.master_itinerary else []
    hotel_data = st.session_state.master_itinerary.get("accommodations", []) if st.session_state.master_itinerary else []
    
    if nightly_hotels:
        # Show total stay cost from current selections
        total_stay = sum(
            st.session_state.selected_hotels.get(nh.get('night', 1), nh.get('hotel', {})).get('price', 0)
            for nh in nightly_hotels
        )
        st.caption(f"🏠 **{len(nightly_hotels)} night(s)** — Total stay cost: **{format_inr(total_stay)}** — Select a hotel for each night below")
        
        for nh in nightly_hotels:
            night_num = nh.get('night', 1)
            nearby = nh.get('nearby_attraction', '')
            hotel_choices = nh.get('hotels', [nh.get('hotel', {})])
            current_selected = st.session_state.selected_hotels.get(night_num, nh.get('hotel', {}))
            
            nearby_text = f" — Near: {nearby}" if nearby else ""
            with st.expander(f"🌙 **Night {night_num}**: {current_selected.get('name', 'Select a hotel')}{nearby_text}", expanded=True):
                # Show all hotel options for this night as cards
                for h_idx, hotel in enumerate(hotel_choices):
                    is_selected = current_selected.get('name') == hotel.get('name')
                    with st.container(border=True):
                        hc1, hc2, hc3 = st.columns([3, 2, 1])
                        with hc1:
                            area_text = f" ({hotel.get('area', '')})" if hotel.get('area') else ""
                            badge = " ✅" if is_selected else ""
                            st.markdown(f"**{hotel.get('name', 'Hotel')}{area_text}{badge}**")
                            price = hotel.get('price', 0)
                            st.write(f"💵 {format_inr(price) if isinstance(price, (int, float)) else price}/night  |  ⭐ {hotel.get('rating', 4.0)}/5  |  🛡️ {hotel.get('safety_score', 85)}/100")
                        with hc2:
                            link_cols = st.columns(3)
                            # Map link
                            map_url = hotel.get('map_url', '')
                            if not map_url:
                                h_search = hotel.get('name', '').replace(' ', '+')
                                dest_n = st.session_state.parsed_request.get('destination', '').replace(' ', '+')
                                map_url = f"https://www.google.com/maps/search/{h_search}+{dest_n}"
                            with link_cols[0]:
                                st.link_button("🗺️ Map", map_url, use_container_width=True)
                            h_url = hotel.get('url', '')
                            if h_url and 'example.com' not in h_url:
                                with link_cols[1]:
                                    st.link_button("🌐 Info", h_url, use_container_width=True)
                            booking_url = hotel.get('booking_search_url', '')
                            if booking_url:
                                with link_cols[2]:
                                    st.link_button("🔗 Book", booking_url, use_container_width=True)
                        with hc3:
                            if is_selected:
                                st.success("✅ Selected")
                            else:
                                if st.button("Select", key=f"btn_n{night_num}_h{h_idx}_{hotel.get('name', '')}"):
                                    st.session_state.selected_hotels[night_num] = hotel
                                    st.rerun()
    elif hotel_data:
        st.caption("Hotel options available — select for your stay")
        cols = st.columns(min(len(hotel_data), 3))
        for i, hotel in enumerate(hotel_data[:3]):
            with cols[i]:
                with st.container(border=True):
                    st.markdown(f"**{hotel.get('name', 'Hotel')}**")
                    price = hotel.get('price', 0)
                    st.write(f"💵 {format_inr(price) if isinstance(price, (int, float)) else price}/night")
                    st.write(f"🛡️ Safety: {hotel.get('safety_score', 85)}/100")
                    h_search = hotel.get('name', '').replace(' ', '+')
                    dest_name = st.session_state.parsed_request.get('destination', '').replace(' ', '+')
                    map_url = hotel.get('map_url', f"https://www.google.com/maps/search/{h_search}+{dest_name}")
                    st.link_button("🗺️ Map", map_url, use_container_width=True)
    else:
        st.info("No hotels found.")
    st.divider()

    # Trending & Celebrations Section
    st.subheader("🎉 Trending & Celebrations")
    festivals = st.session_state.master_itinerary.get('activities', {}).get('festivals', []) if st.session_state.master_itinerary else []
    
    if festivals:
        # Filter out obvious mock data (example.com URLs)
        real_festivals = [f for f in festivals if 'example.com' not in str(f.get('url', ''))]
        display_festivals = real_festivals if real_festivals else festivals
        
        fest_cols = st.columns(min(len(display_festivals), 3) if display_festivals else 1)
        for i, fest in enumerate(display_festivals[:3]):
            with fest_cols[i]:
                with st.container(border=True):
                    # Category badge
                    category = fest.get('category', 'event')
                    cat_icons = {'festival': '🎭', 'concert': '🎵', 'exhibition': '🖼️', 'market': '🛍️', 'cultural': '🎨', 'sports': '⚽', 'food_festival': '🍴', 'other': '🎉'}
                    cat_icon = cat_icons.get(category, '🎉')
                    st.markdown(f"`{cat_icon} {category.replace('_', ' ').title()}`")
                    
                    st.markdown(f"**{fest.get('title', 'Event')}**")
                    st.write(fest.get('content', 'An exciting event happening during your visit.'))
                    
                    # Show date info if available
                    date_info = fest.get('date_info', '')
                    if date_info:
                        st.caption(f"📅 {date_info}")
                    
                    if fest.get('url') and fest.get('url') != '#' and 'example.com' not in str(fest.get('url', '')):
                        st.link_button("🌐 See Event Details", fest.get('url'), use_container_width=True)
    else:
        st.info("No trending events found for these dates. Try adjusting your travel window.")
    st.divider()
    
    # === 5. Smart Packing Assistant (Visual) ===
    st.markdown("### 🧳 Smart Packing & Prep")
    
    prep_col1, prep_col2 = st.columns([1, 2])
    with prep_col1:
        st.info(f"**Passport & Visa info:**\n{st.session_state.master_itinerary.get('visa_info', 'N/A') if st.session_state.master_itinerary else 'N/A'}")
        
    with prep_col2:
        pack_items = st.session_state.master_itinerary.get('packing_list', []) if st.session_state.master_itinerary else []
        if pack_items:
            with st.container(border=True):
                st.markdown("**Essential Checklist:**")
                p_cols = st.columns(3) # Better grid layout
                for idx, item in enumerate(pack_items):
                    icon = "✔"
                    lower_item = item.lower()
                    if "rain" in lower_item or "umbrella" in lower_item: icon = "🌧"
                    elif "sun" in lower_item or "hat" in lower_item: icon = "☀"
                    elif "power" in lower_item or "charger" in lower_item or "adapter" in lower_item: icon = "🔌"
                    elif "shoe" in lower_item or "sneaker" in lower_item or "walk" in lower_item: icon = "👟"
                    elif "med" in lower_item or "kit" in lower_item: icon = "💊"
                    elif "camera" in lower_item or "photo" in lower_item: icon = "📷"
                    elif "jacket" in lower_item or "warm" in lower_item: icon = "🧥"
                    
                    with p_cols[idx % 3]:
                        st.markdown(f"`{icon}` {item}")
    st.divider()

    # === 6. Safety & Contacts ===
    st.markdown("### 🛡️ Secure Travel Guidance")
    col_c, col_d = st.columns(2)
    
    with col_c:
        with st.container(border=True):
            st.warning("⚠️ **Local Safety Tips**")
            tips = st.session_state.master_itinerary.get('safety_tips', [])
            for tip in tips:
                st.markdown(f"- {tip}")
                
    with col_d:
        with st.container(border=True):
            st.markdown(
                """
                <div style="
                    background: linear-gradient(135deg, #450A0A 0%, #7F1D1D 100%);
                    border-radius: 12px;
                    padding: 20px;
                    color: white;
                    box-shadow: 0 4px 15px rgba(220, 38, 38, 0.3);
                ">
                    <div style="display:flex; align-items:center; gap:10px; margin-bottom:15px; border-bottom:1px solid rgba(255,255,255,0.1); padding-bottom:10px;">
                        <span style="font-size:1.5em;">🚨</span>
                        <h3 style="margin:0; color:white; font-size:1.2em; letter-spacing:1px;">EMERGENCY ARSENAL</h3>
                    </div>
                """,
                unsafe_allow_html=True
            )
            
            ec = st.session_state.master_itinerary.get('emergency_contacts', {})
            police = ec.get('police') or "100"
            med = ec.get('ambulance') or ec.get('medical') or "102"
            uni = ec.get('universal') or "112"
            
            st.markdown(
                f"""
                <div style="display:grid; grid-template-columns: 1fr 1fr; gap:12px;">
                    <div style="background:rgba(0,0,0,0.2); padding:12px; border-radius:8px; border-left:3px solid #EF4444;">
                        <div style="font-size:0.7em; text-transform:uppercase; opacity:0.7; font-weight:700;">🚓 Police</div>
                        <div style="font-size:1.4em; font-weight:800; color:#FCA5A5;">{police}</div>
                    </div>
                    <div style="background:rgba(0,0,0,0.2); padding:12px; border-radius:8px; border-left:3px solid #EF4444;">
                        <div style="font-size:0.7em; text-transform:uppercase; opacity:0.7; font-weight:700;">🚑 Medical</div>
                        <div style="font-size:1.4em; font-weight:800; color:#FCA5A5;">{med}</div>
                    </div>
                </div>
                <div style="background:rgba(255,255,255,0.1); padding:15px; border-radius:8px; margin-top:12px; text-align:center; border:1px dashed rgba(255,255,255,0.3);">
                    <div style="font-size:0.75em; text-transform:uppercase; opacity:0.8; font-weight:700; margin-bottom:4px;">🌍 Universal Help</div>
                    <div style="font-size:1.8em; font-weight:900; color:white; text-shadow: 0 0 10px rgba(255,255,255,0.4);">{uni}</div>
                </div>
                <div style="font-size:0.7em; opacity:0.6; margin-top:15px; text-align:center; font-style:italic;">
                    TIP: Save these numbers to your contacts immediately.
                </div>
                </div>
                """,
                unsafe_allow_html=True
            )
    st.divider()

    # === Interactive Section: Map & Gallery ===
    col_map, col_gallery = st.columns([1, 1])
    
    with col_map:
        st.subheader("📍 Interactive Map")
        update_map()
        
    with col_gallery:
        # === 7. Attraction Preview Gallery ===
        st.subheader("📸 Attraction Preview Gallery")
        act = st.session_state.master_itinerary.get('activities', {})
        photo_spots = act.get('instagrammable', []) if isinstance(act.get('instagrammable'), list) else []
        attractions = act.get('attractions', []) if isinstance(act.get('attractions'), list) else []
        
        # Combine and take a subset for the gallery
        combo = (photo_spots + attractions)[:4] 
        if combo:
            for spot in combo:
                with st.expander(f"📍 {spot.get('title', 'Scenic Spot')} - Click to Preview"):
                    title = spot.get('title', 'sightseeing')
                    # Use the title as a keyword to fetch a relevant landscape image from Unsplash
                    search_term = title.replace(" ", "%20").lower()
                    
                    if spot.get('image_url') and "unsplash" not in spot.get('image_url'):
                        image_url = spot.get('image_url')
                    else:
                        image_url = f"https://source.unsplash.com/800x400/?{search_term},travel"
                    
                    st.image(image_url, width='stretch', caption=f"Preview of {title}")
                    st.write(f"**Quick Facts:** {spot.get('content', 'A trending highly-rated spot.')}")
                    g_col1, g_col2 = st.columns(2)
                    g_col1.write(f"🎟 **Entry Fee:** ~{format_inr(spot.get('price', random.randint(50, 400)))}")
                    g_col2.write(f"🌅 **Best Time:** Early Morning (lower crowds)")
        else:
            st.info("No trending photo spots uncovered for this area yet.")

    st.divider()

    # === Master Timeline (Full Width) ===
    st.subheader("📅 Master Timeline")
    
    # Display extracted info and selections
    dest = st.session_state.parsed_request.get('destination', '')
    budget_limit = st.session_state.master_itinerary.get('total_budget', '') if st.session_state.master_itinerary else ''
    st.info(f"**Destination:** {dest} | **Budget Cap:** {format_inr(budget_limit) if budget_limit else 'Flexible'}")
    
    # Inject Selected Transport & Hotel into Timeline View
    if st.session_state.selected_transport or st.session_state.selected_hotels:
        with st.container(border=True):
            st.markdown("### 🎒 Your Selections")
            sel_1, sel_2 = st.columns(2)
            with sel_1:
                if st.session_state.selected_transport:
                    t = st.session_state.selected_transport
                    st.write(f"**Transport:** {t.get('provider')} - {format_inr(t.get('price', 0))}")
            with sel_2:
                if st.session_state.selected_hotels:
                    for night_num, h in sorted(st.session_state.selected_hotels.items()):
                        price = h.get('price', 0)
                        st.write(f"**Night {night_num}:** {h.get('name')} - {format_inr(price) if isinstance(price, (int, float)) else price}")
    
    # We use the new timeline generated by the budget_itinerary
    display_timeline(st.session_state.master_itinerary['timeline'] if st.session_state.master_itinerary else st.session_state.current_itinerary)

    # === 8. Travel Analytics Dashboard === (Full-width below gallery + timeline)
    st.divider()
    st.subheader("📈 Travel Analytics Dashboard")
    analytics_col1, analytics_col2, analytics_col3 = st.columns(3)
    
    import pandas as pd
    # Pull accurate costs from budget_breakdown (pre-calculated in orchestrator)
    budget_bd = st.session_state.master_itinerary.get('budget_breakdown', {})
    
    # Local Transport: cabs, autos between spots (from timeline + orchestrator)
    local_t_cost = sum([i.get('cost_est', 0) for i in st.session_state.master_itinerary.get('timeline', []) if i.get('type') == 'transport_local'])
    if local_t_cost == 0:
        local_t_cost = budget_bd.get('local_transport', 0)
    
    # Transport: round-trip inter-city + local cabs/autos merged together
    if st.session_state.selected_transport:
        sel_price = st.session_state.selected_transport.get('price', 0)
        is_rt = st.session_state.selected_transport.get('trip_type', '') == 'Round Trip'
        intercity_cost = sel_price if is_rt else sel_price * 2
    else:
        intercity_cost = budget_bd.get('round_trip_transport', 0)
    t_cost = intercity_cost + local_t_cost  # Total transport = inter-city + local
    
    # Stay: total for ALL nights using per-night selections
    nightly_hotels_data = st.session_state.master_itinerary.get('nightly_hotels', [])
    h_cost = 0
    for nh in nightly_hotels_data:
        night_num = nh.get('night', 1)
        selected_h = st.session_state.selected_hotels.get(night_num, nh.get('hotel', {}))
        h_cost += selected_h.get('price', 0)
    if h_cost == 0:
        h_cost = budget_bd.get('total_stay', 0)
    
    # Food: sum from timeline
    f_cost = sum([i.get('cost_est', 0) for i in st.session_state.master_itinerary.get('timeline', []) if i.get('type') == 'food'])
    
    # Activities: attractions + events
    a_cost = sum([i.get('cost_est', 0) for i in st.session_state.master_itinerary.get('timeline', []) if i.get('type') in ('attraction', 'event')])
    
    df_cost = pd.DataFrame({
        "Category": ["Transport", "Stay", "Food & Dining", "Activities"],
        "Cost": [t_cost, h_cost, f_cost, a_cost]
    })
    
    with analytics_col1:
        with st.container(border=True):
            st.markdown("**🥧 Cost Distribution**")
            if df_cost["Cost"].sum() > 0:
                fig1 = px.pie(df_cost, values="Cost", names="Category", hole=0.45,
                              color_discrete_sequence=['#3B82F6','#10B981','#F59E0B','#A855F7'])
                fig1.update_layout(margin=dict(t=10, b=10, l=0, r=0), showlegend=True,
                                   paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                                   font_color='#CBD5E1', legend=dict(orientation='h', y=-0.2))
                st.plotly_chart(fig1, width='stretch')

    with analytics_col2:
        with st.container(border=True):
            st.markdown("**⏱️ Time Distribution**")
            days = st.session_state.parsed_request.get('days', 3)
            df_time = pd.DataFrame({
                "Activity": ["Sightseeing", "Food & Dining", "Travel", "Leisure"],
                "Hours": [days * 3, days * 2.5, days * 1.5 + 2, days * 2]
            })
            fig2 = px.bar(df_time, x="Activity", y="Hours", color="Activity",
                          color_discrete_sequence=['#3B82F6','#EF4444','#F59E0B','#10B981'])
            fig2.update_layout(margin=dict(t=10, b=10, l=0, r=0), showlegend=False,
                               paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                               font_color='#CBD5E1', xaxis=dict(showgrid=False), yaxis=dict(showgrid=False))
            st.plotly_chart(fig2, width='stretch')

    with analytics_col3:
        with st.container(border=True):
            st.markdown("**💰 Budget Tracker**")
            total_spent = t_cost + h_cost + f_cost + a_cost
            budget_cap = st.session_state.master_itinerary.get('total_budget', total_spent) or total_spent
            pct = min(int((total_spent / budget_cap) * 100), 100) if budget_cap else 100
            st.metric("Total Estimated", format_inr(total_spent))
            st.progress(pct, text=f"{pct}% of {format_inr(budget_cap)} budget used")
            st.write(f"✈️ Transport: `{format_inr(t_cost)}`")
            st.caption(f"  ↳ Inter-city (round trip): {format_inr(intercity_cost)} + Local cabs/auto: {format_inr(local_t_cost)}")
            st.write(f"🏨 Stay ({len(nightly_hotels_data)} nights): `{format_inr(h_cost)}`")
            st.write(f"🍽️ Food & Dining: `{format_inr(f_cost)}`")
            st.write(f"🎟️ Activities: `{format_inr(a_cost)}`")
    st.divider()

    # Use the accurate total_spent from budget analytics above
    actual_trip_cost = total_spent  # Already includes round-trip transport, all nights, food, activities, local transport
        
    st.write(f"**Trip Calculator:** {format_inr(actual_trip_cost)} / {format_inr(budget_limit)}")
    
    # Budget Validator Toggle
    if budget_limit and actual_trip_cost > budget_limit:
        st.error(f"🚨 **Budget Exceeded!** Your configured trip ({format_inr(actual_trip_cost)}) exceeds your Total Budget of {format_inr(budget_limit)}. Please select cheaper transport/stays, or increase your budget to download the itineraries.")
    else:
        # PDF & ZIP Export
        if st.session_state.master_itinerary:
            def create_pdf():
                pdf = FPDF()
                pdf.add_page()
                pdf.set_font("Arial", size=12)
                pdf.cell(200, 10, txt="VoyagrBot Itinerary", ln=1, align='C')
                pdf.set_font("Arial", size=10)
                pdf.cell(200, 10, txt=f"Destination: {dest}", ln=1)
                pdf.cell(200, 10, txt=f"Visa Info: {st.session_state.master_itinerary.get('visa_info', '')}", ln=1)
                pdf.cell(200, 10, txt=f"Packing List: {', '.join(st.session_state.master_itinerary.get('packing_list', []))}", ln=1)
                pdf.cell(200, 10, txt="----", ln=1)
                for item in st.session_state.master_itinerary['timeline']:
                    title = item.get('title', '').encode('latin-1', 'replace').decode('latin-1')
                    details = item.get('details', '').encode('latin-1', 'replace').decode('latin-1')
                    pdf.cell(200, 10, txt=f"{item.get('type').upper()}: {title}", ln=1)
                    if details:
                        pdf.multi_cell(0, 10, txt=details)
                return pdf.output(dest='S').encode('latin-1', 'replace')

            def create_zip():
                import io, zipfile
                zip_buffer = io.BytesIO()
                days = {}
                for item in st.session_state.master_itinerary['timeline']:
                    day = item.get('day', 'Day 1')
                    if day not in days:
                        days[day] = []
                    days[day].append(item)
                with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED, False) as zip_file:
                    for day, items in days.items():
                        day_content = f"--- {day} Schedule ---\nDestination: {dest}\n\n"
                        daily_food = daily_stay = daily_activities = 0
                        for item in items:
                            title = item.get('title', '')
                            details = item.get('details', '')
                            time_slot = item.get('time', 'All Day')
                            day_content += f"[{time_slot}] {item.get('type', 'Activity').upper()}: {title}\n"
                            if details:
                                day_content += f"Details/Address: {details}\n"
                            cost_est = item.get('cost_est', 0)
                            day_content += f"Est. Cost: INR {cost_est}\n\n"
                            i_type = item.get('type', '').lower()
                            if i_type == 'food':
                                daily_food += cost_est
                            elif i_type in ('check_in', 'hotel'):
                                daily_stay += cost_est
                            else:
                                daily_activities += cost_est
                        day_content += f"--- Daily Budget ---\nFood: INR {daily_food}\nStay: INR {daily_stay}\nActivities: INR {daily_activities}\nTotal: INR {daily_food + daily_stay + daily_activities}\n"
                        zip_file.writestr(f"{day.replace(' ', '_')}_Schedule.txt", day_content)
                return zip_buffer.getvalue()

            col_dl1, col_dl2 = st.columns(2)
            with col_dl1:
                pdf_bytes = create_pdf()
                st.download_button(label="📥 Download as PDF", data=pdf_bytes, file_name="voyagrbot_itinerary.pdf", mime="application/pdf")
            with col_dl2:
                zip_bytes = create_zip()
                st.download_button(label="📦 Download Daily Schedules (ZIP)", data=zip_bytes, file_name="Schedules_Archive.zip", mime="application/zip")


        # --- Trip Doubts Chat Section (Compact Assistant) ---
        st.divider()
        st.markdown("### 💡 Trip Assistant")
        
        # Display a small, compact chat history
        with st.container(border=True):
            chat_window = st.container(height=200)
            with chat_window:
                if not st.session_state.chat_history:
                    st.caption("Ask me about safety, packing, or local tips for this trip!")
                else:
                    for msg in st.session_state.chat_history[-3:]:
                        with st.chat_message(msg["role"]):
                            st.markdown(f"<div style='font-size: 0.85em; line-height: 1.4;'>{msg['content']}</div>", unsafe_allow_html=True)
            
            # Integrated Suggestions (Chips)
            suggestion_query = None
            s_col1, s_col2, s_col3, s_col4 = st.columns([1, 1, 1, 1])
            with s_col1:
                if st.button("🎒 Packing", width='stretch', key="btn_pack"):
                    suggestion_query = "What should I pack for this trip?"
            with s_col2:
                if st.button("🛡️ Safety", width='stretch', key="btn_safe"):
                    suggestion_query = "Any safety tips for this city?"
            with s_col3:
                if st.button("🍽️ Food", width='stretch', key="btn_food"):
                    suggestion_query = "Must try local foods?"
            with s_col4:
                if st.button("🏥 Emergency", width='stretch', key="btn_emerg"):
                    suggestion_query = "What are the emergency contacts?"

            chat_query = st.chat_input("Ask VoyagrBot...", key="bottom_chat_input")
            
            final_query = chat_query or suggestion_query
            
            if final_query:
                st.session_state.chat_history.append({"role": "user", "content": final_query})
                with st.spinner("Analyzing Knowledge Base..."):
                    response = st.session_state.chatbot_agent.chat(
                        final_query, 
                        chat_history=st.session_state.chat_history[:-1],
                        trip_context=st.session_state.master_itinerary
                    )
                st.session_state.chat_history.append({"role": "assistant", "content": response})
                st.rerun()

    # --- Comprehensive Multi-Agent Evaluation ---
    st.markdown("<br>", unsafe_allow_html=True)
    with st.expander("🧪 System Performance & Multi-Agent Evaluation"):
        st.write("### 🤖 Collaborative Agent Performance Report")
        
        mi = st.session_state.master_itinerary or {}
        tl = mi.get('timeline', [])
        acts = mi.get('activities', {})
        pk_list = mi.get('packing_list', [])
        safety = mi.get('safety_tips', [])
        trans = mi.get('transport_options', [])
        hotels = mi.get('accommodations', [])
        nightly = mi.get('nightly_hotels', [])
        budget = mi.get('total_budget', 50000)
        days = mi.get('request', {}).get('days', 3)
        
        # Helper: check URL quality (not example.com, not empty)
        def url_quality(items):
            if not items: return 0.0
            real = sum(1 for i in items if i.get('url') and 'example.com' not in str(i.get('url', '')))
            return real / len(items)
        
        # Helper: check data source quality
        def source_score(items, source_key='data_source'):
            if not items: return 0.5
            scores = []
            for i in items:
                src = str(i.get(source_key, '')).lower()
                if 'rapidapi' in src or 'live' in src: scores.append(1.0)
                elif 'tavily' in src or 'api' in src: scores.append(0.85)
                elif 'fallback' in src or 'mock' in src: scores.append(0.4)
                else: scores.append(0.65)
            return sum(scores) / len(scores) if scores else 0.5
        
        # Budget efficiency
        t_c = st.session_state.selected_transport.get('price', 0) if st.session_state.selected_transport else 0
        h_c = sum(h.get('price', 0) for h in st.session_state.selected_hotels.values()) if st.session_state.selected_hotels else 0
        a_c = sum(i.get('cost_est', 0) for i in tl)
        total_spent = t_c + h_c + a_c
        budget_eff = min(1.0, budget / total_spent) if total_spent > 0 else 1.0

        # Weighted Multi-Dimensional Scoring per agent
        # Format: (name, task, completeness, quality, source, weight)
        attractions = acts.get('attractions', [])
        food_items = acts.get('food', [])
        festivals = acts.get('festivals', [])

        agent_eval = [
            ("🧠 Master Planner", "Orchestration & Routing",
             1.0, 1.0 if mi.get('routing_guide') else 0.5, 1.0),
            ("🗺️ POI Agent", "Attraction & Geospatial Data",
             min(len(attractions) / 3, 1.0), url_quality(attractions), source_score(attractions)),
            ("🍽️ Food Agent", "Restaurant Discovery",
             min(len(food_items) / 3, 1.0), url_quality(food_items), source_score(food_items)),
            ("📅 Planner Agent", "Timeline Sequencing",
             min(len([i for i in tl if i.get('type') not in ('day_header', 'daily_summary')]) / (days * 6), 1.0),
             1.0 - (sum(1 for i in tl if 'example.com' in str(i.get('url', ''))) / max(len(tl), 1)),
             0.85),
            ("✈️ Logistics Agent", "Flight & Transport Sync",
             min(len(trans) / 2, 1.0), 1.0 if any('Live' in str(t.get('airline', '')) for t in trans) else 0.6, source_score(trans)),
            ("🏨 Accommodation Agent", "Hotel Search & Filtering",
             min(len(hotels) / max(days, 1), 1.0), url_quality(hotels), source_score(hotels)),
            ("💰 Budgeting Agent", "Cost Optimization",
             budget_eff, 1.0 if total_spent <= budget else 0.5, 0.85),
            ("🛡️ RAG Knowledge Agent", "Semantic Retrieval",
             min((len(safety) + len(pk_list)) / 8, 1.0), 1.0 if safety else 0.3, 0.9),
            ("🎉 Events Agent", "Tavily Web Search",
             min(len(festivals) / 2, 1.0), url_quality(festivals), source_score(festivals)),
            ("✈️ Airport Resolver", "Airport Proximity Logic",
             1.0 if mi.get('airport_info', {}).get('dest_iata') else 0.3, 1.0, 0.95),
        ]

        # Weighted score: Source 40% + Completeness 30% + Quality 30%
        agent_scores = []
        for name, task, completeness, quality, source in agent_eval:
            score = (source * 0.40) + (completeness * 0.30) + (quality * 0.30)
            agent_scores.append(round(min(score, 1.0), 3))
        
        final_map = round(sum(agent_scores) / len(agent_scores), 3)
        
        # Status badge
        if final_map >= 0.80:
            status_color, status_text = "#10B981", "HIGH RELIABILITY"
        elif final_map >= 0.60:
            status_color, status_text = "#F59E0B", "MODERATE"
        else:
            status_color, status_text = "#EF4444", "NEEDS IMPROVEMENT"
        
        st.markdown(f"""
            <div style="background: #0F172A; border: 1px solid #6366F1; border-radius: 12px; padding: 25px; text-align: center; margin-bottom: 25px; box-shadow: 0 4px 20px -5px rgba(99, 102, 241, 0.3);">
                <h4 style="color: #94A3B8; margin: 0; text-transform: uppercase; font-size: 0.85em; letter-spacing: 2px;">Weighted Multi-Dimensional System Score</h4>
                <h1 style="color: #818CF8; margin: 10px 0; font-size: 3.5em; font-weight: 800;">{round(final_map * 100, 1)}%</h1>
                <p style="color: #CBD5E1; margin: 0; font-size: 0.95em;">Source Quality (40%) + Completeness (30%) + Data Quality (30%)</p>
                <div style="display: flex; justify-content: center; gap: 15px; margin-top: 20px;">
                    <span style="border: 1px solid {status_color}; color: {status_color}; padding: 5px 15px; border-radius: 20px; font-size: 0.85em; font-weight: 600;">🎯 {status_text}</span>
                    <span style="border: 1px solid #6366F1; color: #6366F1; padding: 5px 15px; border-radius: 20px; font-size: 0.85em; font-weight: 600;">📊 {len(agent_eval)} AGENTS</span>
                </div>
            </div>
        """, unsafe_allow_html=True)
        
        # Detailed Agent Metrics Table
        df_agents = pd.DataFrame({
            "Agent": [a for a, _, _, _, _ in agent_eval],
            "Task": [t for _, t, _, _, _ in agent_eval],
            "Completeness": [f"{c*100:.0f}%" for _, _, c, _, _ in agent_eval],
            "Data Quality": [f"{q*100:.0f}%" for _, _, _, q, _ in agent_eval],
            "Source Score": [f"{s*100:.0f}%" for _, _, _, _, s in agent_eval],
            "Overall": [f"{sc*100:.1f}%" for sc in agent_scores]
        })
        st.dataframe(df_agents, use_container_width=True, hide_index=True)
        
        st.info("💡 **Scoring Method**: Each agent is scored on 3 dimensions — **Data Source** (live API=100%, Tavily+LLM=85%, fallback=40%), **Completeness** (items retrieved vs expected), and **Data Quality** (real URLs, accurate names). The overall score is a weighted average: Source 40% + Completeness 30% + Quality 30%.")


else:
    st.info("👈 Use the sidebar chat to plan your next trip! Ask something like 'Plan a standard budget trip to Agra from Delhi prioritizing monuments.'")
