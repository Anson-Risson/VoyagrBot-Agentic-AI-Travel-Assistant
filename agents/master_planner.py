import os
import json
from google import genai
from openai import OpenAI
from core.cache import get_cached_data, set_cached_data
from dotenv import load_dotenv

load_dotenv()

GEMINI_FALLBACK_MODELS = ["gemini-2.5-flash-lite", "gemini-2.5-flash", "gemini-2.0-flash", "gemini-2.0-flash-lite"]

class MasterPlannerAgent:
    def __init__(self):
        self.google_api_key = os.getenv("GOOGLE_API_KEY")
        self.model_name = os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite")
        
        # Initialize Gemini if key is present
        self.gemini_client = None
        if self.google_api_key:
            try:
                self.gemini_client = genai.Client(api_key=self.google_api_key)
            except:
                pass

        # Always initialize OpenAI/LM Studio as secondary/fallback
        self.oai_api_key = os.getenv("LLM_STUDIO_API_KEY", "lm-studio")
        self.oai_base_url = os.getenv("LLM_STUDIO_BASE_URL", "http://localhost:1234/v1")
        self.oai_model = os.getenv("LLM_STUDIO_MODEL", "qwen2.5-coder-7b-instruct")
        self.oai_client = OpenAI(base_url=self.oai_base_url, api_key=self.oai_api_key)
        # Persistent cache is handled by core.cache
        
    def parse_request(self, user_input: str) -> dict:
        """
        Extracts destination, start_date, end_date, budget_tier, and interests.
        """
        system_prompt = """
        You are the Master Planner Agent for VoyagrBot.
        Extract the following information from the user's travel request:
        - destination (string)
        - start_date (YYYY-MM-DD)
        - end_date (YYYY-MM-DD)
        - budget_tier (extract as Budget, Standard, or Luxury)
        - interests (list of strings)
        
        Respond only with a valid JSON object containing these keys.
        """
        
        # Try Gemini First (with model fallback)
        if self.gemini_client:
            models_to_try = [self.model_name] + [m for m in GEMINI_FALLBACK_MODELS if m != self.model_name]
            for model_name in models_to_try:
                try:
                    response = self.gemini_client.models.generate_content(
                        model=model_name,
                        contents=user_input,
                        config=genai.types.GenerateContentConfig(
                            system_instruction=system_prompt,
                            response_mime_type="application/json",
                        )
                    )
                    text = response.text.replace('```json', '').replace('```', '').strip()
                    return json.loads(text, strict=False)
                except Exception as e:
                    print(f"Gemini MasterPlanner Error ({model_name}): {e}")
                    continue

        # Fallback to Local LLM (OpenAI Client)
        try:
            response = self.oai_client.chat.completions.create(
                model=self.oai_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_input}
                ],
                temperature=0,
                timeout=8
            )
            return json.loads(response.choices[0].message.content, strict=False)
        except Exception as e:
            print(f"MasterPlanner Critical Fail: {e}")
            return {"destination": "Paris", "start_date": "2026-06-01", "end_date": "2026-06-05", "budget_tier": "Standard", "interests": []}

    def generate_routing_guide(self, origin: str, destination: str, airport_info: dict = None) -> dict:
        """
        Generates a detailed, mindtrip-style routing guide using real APIs (Nominatim + OSRM).
        Now includes airport transfer information for cities without airports.
        """
        cached = get_cached_data("route", origin, destination)
        if cached:
            return cached
            
        import requests
        import math
        
        def haversine(lat1, lon1, lat2, lon2):
            R = 6371
            dlat = math.radians(lat2 - lat1)
            dlon = math.radians(lon2 - lon1)
            a = math.sin(dlat/2) * math.sin(dlat/2) + math.cos(math.radians(lat1)) \
                * math.cos(math.radians(lat2)) * math.sin(dlon/2) * math.sin(dlon/2)
            c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
            return R * c
            
        headers = {"User-Agent": "VoyagrBot/1.0"}
        lat1, lon1, lat2, lon2 = None, None, None, None
        
        try:
            res_orig = requests.get(f"https://nominatim.openstreetmap.org/search?q={origin}&format=json&limit=1", headers=headers, timeout=5).json()
            res_dest = requests.get(f"https://nominatim.openstreetmap.org/search?q={destination}&format=json&limit=1", headers=headers, timeout=5).json()
            if res_orig and res_dest:
                lat1, lon1 = float(res_orig[0]['lat']), float(res_orig[0]['lon'])
                lat2, lon2 = float(res_dest[0]['lat']), float(res_dest[0]['lon'])
        except Exception as e:
            print(f"Geocoding error: {e}")

        driving_distance = 0
        driving_duration = 0
        flight_duration = 0
        train_duration = 0
        
        if lat1 is not None and lat2 is not None:
            try:
                osrm_url = f"http://router.project-osrm.org/route/v1/driving/{lon1},{lat1};{lon2},{lat2}?overview=false"
                osrm_res = requests.get(osrm_url, timeout=5).json()
                if osrm_res.get('code') == 'Ok':
                    driving_distance = osrm_res['routes'][0]['distance'] / 1000
                    driving_duration = osrm_res['routes'][0]['duration'] / 3600
                else:
                    driving_distance = haversine(lat1, lon1, lat2, lon2) * 1.2
                    driving_duration = driving_distance / 60
            except:
                driving_distance = haversine(lat1, lon1, lat2, lon2) * 1.2
                driving_duration = driving_distance / 60
                
            flight_distance = haversine(lat1, lon1, lat2, lon2)
            flight_duration = (flight_distance / 800) + 2
            train_duration = driving_distance / 60
        else:
            # Fallback mock data if geocoding fails
            driving_distance = 1000
            driving_duration = 20
            flight_duration = 3
            train_duration = 18

        # Build airport-aware route descriptions
        origin_airport = origin
        dest_airport = destination
        air_steps = []
        origin_transfer_note = ""
        dest_transfer_note = ""

        if airport_info:
            origin_airport = airport_info.get("origin_airport_city", origin)
            dest_airport = airport_info.get("dest_airport_city", destination)
            origin_iata = airport_info.get("origin_iata", "")
            dest_iata = airport_info.get("dest_iata", "")

            if airport_info.get("origin_needs_transfer"):
                origin_km = airport_info.get("origin_transfer_km", 0)
                air_steps.append(f"**Step 1:** Travel from {origin} to {origin_airport} ({origin_iata}) — ~{origin_km} km by road/taxi.")
                air_steps.append(f"**Step 2:** Fly from {origin_airport} ({origin_iata}) to {dest_airport} ({dest_iata}) (~{int(flight_duration)}-{int(flight_duration)+1} hours).")
                origin_transfer_note = f"\n\n> ℹ️ **{airport_info.get('origin_transfer_info', '')}**"
            else:
                air_steps.append(f"**Step 1:** Head to {origin_airport} Airport ({origin_iata}).")
                air_steps.append(f"**Step 2:** Fly direct to {dest_airport} ({dest_iata}) (~{int(flight_duration)}-{int(flight_duration)+1} hours).")

            if airport_info.get("dest_needs_transfer"):
                dest_km = airport_info.get("dest_transfer_km", 0)
                air_steps.append(f"**Step 3:** Upon arrival at {dest_airport} ({dest_iata}), travel ~{dest_km} km by taxi/bus to {destination}.")
                dest_transfer_note = f"\n\n> ℹ️ **{airport_info.get('dest_transfer_info', '')}**"
            else:
                air_steps.append(f"**Step 3:** Take a taxi to the city center.")
        else:
            air_steps = [
                f"**Step 1:** Head to {origin} Airport.",
                f"**Step 2:** Fly direct to {destination} Airport (~{int(flight_duration)}-{int(flight_duration)+1} hours).",
                f"**Step 3:** Take a taxi to the city center."
            ]

        air_text = "\n".join(air_steps) + origin_transfer_note + dest_transfer_note

        # Summary table with airport names
        origin_col = f"{origin}" if not airport_info or not airport_info.get("origin_needs_transfer") else f"{origin} → {origin_airport}"
        dest_col = f"{destination}" if not airport_info or not airport_info.get("dest_needs_transfer") else f"{dest_airport} → {destination}"

        res = {
           "air": air_text,
           "train": f"**Step 1:** Board a direct express train from {origin} to {destination}.\n**Duration:** {int(train_duration)}-{int(train_duration)+4} hours depending on the route.\n**Arrival:** {destination} Central Railway Station.",
           "road": f"**Distance:** ~{int(driving_distance)} km.\n**Duration:** {int(driving_duration)}-{int(driving_duration)+2} hours of driving. Not recommended unless you enjoy long road trips.",
           "summary_table": f"| Mode | Route | Total Estimated Time | Notes |\n|---|---|---|---|\n| ✈️ Air | {origin_col} ✈ {dest_col} | {int(flight_duration)}-{int(flight_duration)+1} hours | Fastest & most comfortable |\n| 🚆 Train | {origin} → {destination} | {int(train_duration)}-{int(train_duration)+4} hours | Scenic, budget-friendly |\n| 🚌 Road | Driving | {int(driving_duration)}+ hours | Only for the adventurous |",
           "distance_km": driving_distance
        }
        
        set_cached_data("route", res, origin, destination)
        return res
    def refine_itinerary(self, timeline: list, destination: str) -> list:
        """
        Takes a raw timeline and turns descriptions into catchy, one-sentence "Quick Insights".
        Uses a single batch call for speed.
        """
        if not timeline: return []
        
        # Prepare a minimal version for the LLM to process
        simplified = [{"title": item.get('title'), "details": item.get('details')} for item in timeline if item.get('type') not in ['day_header', 'daily_summary', 'note']]
        
        system_prompt = f"""
        You are a travel editor for VoyagrBot.
        Refine the 'details' for each spot in {destination} into a single, catchy, brief "Quick Insight" (max 15 words).
        Make them sound exciting and premium.
        Return ONLY a JSON list of strings in the exact same order as the input.
        Example: ["The most breathtaking sunset views overlooking the city.", "Vibrant bazaar famous for authentic spices and silks."]
        """
        
        content_to_refine = json.dumps(simplified)
        
        refined_details = []
        # Try Gemini (with model fallback)
        if self.gemini_client:
            models_to_try = [self.model_name] + [m for m in GEMINI_FALLBACK_MODELS if m != self.model_name]
            for model_name in models_to_try:
                try:
                    response = self.gemini_client.models.generate_content(
                        model=model_name,
                        contents=content_to_refine,
                        config=genai.types.GenerateContentConfig(
                            system_instruction=system_prompt,
                            response_mime_type="application/json",
                        )
                    )
                    text = response.text.replace('```json', '').replace('```', '').strip()
                    refined_details = json.loads(text, strict=False)
                    if refined_details:
                        break
                except Exception as e:
                    print(f"Gemini Refine Error ({model_name}): {e}")
                    continue
                
        # Fallback to Local LLM
        if not refined_details:
            try:
                response = self.oai_client.chat.completions.create(
                    model=self.oai_model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": content_to_refine}
                    ],
                    temperature=0.3,
                    timeout=15
                )
                refined_details = json.loads(response.choices[0].message.content, strict=False)
            except Exception as e:
                print(f"Refine Critical Fail: {e}")
                return timeline

        # Map refined details back to original timeline
        if isinstance(refined_details, list) and len(refined_details) > 0:
            idx = 0
            for item in timeline:
                if item.get('type') not in ['day_header', 'daily_summary', 'note'] and idx < len(refined_details):
                    item['details'] = refined_details[idx]
                    idx += 1
                    
        return timeline
