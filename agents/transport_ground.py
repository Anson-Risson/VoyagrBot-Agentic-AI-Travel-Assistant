import os
import random
import json
from typing import List
from dotenv import load_dotenv

load_dotenv()

class GroundTransportAgent:
    def __init__(self):
        self.tavily_key = os.getenv("TAVILY_API_KEY")
        self.google_api_key = os.getenv("GOOGLE_API_KEY")
        self.openai_key = os.getenv("OPENAI_API_KEY")
        
        # Fallback rate-per-km pricing (used when API/LLM fails)
        self.train_rates = {
            "sleeper": 1.2,
            "3ac": 2.8,
            "2ac": 4.0,
            "1ac": 6.5,
            "chair_car": 2.0,
        }
        self.bus_rates = {
            "ordinary": 1.5,
            "semi_sleeper": 2.2,
            "sleeper_ac": 3.0,
            "volvo_ac": 3.8,
        }
        self.cab_rate_per_km = 12.0  # Average cab rate
        self.train_speed_kmh = 75
        self.bus_speed_kmh = 50

    def _get_booking_links(self, origin_city: str, dest_city: str, travel_date: str) -> dict:
        """Generate real booking/search links for each transport mode."""
        origin_enc = origin_city.replace(" ", "+")
        dest_enc = dest_city.replace(" ", "+")
        return {
            "train": f"https://www.irctc.co.in/nget/train-search",
            "train_search": f"https://www.google.com/search?q={origin_enc}+to+{dest_enc}+train+tickets+{travel_date}",
            "bus": f"https://www.redbus.in/bus-tickets/{origin_city.lower().replace(' ','-')}-to-{dest_city.lower().replace(' ','-')}",
            "bus_search": f"https://www.google.com/search?q={origin_enc}+to+{dest_enc}+bus+tickets",
            "cab": f"https://www.google.com/search?q={origin_enc}+to+{dest_enc}+cab+booking",
            "map": f"https://www.google.com/maps/dir/{origin_enc}/{dest_enc}",
        }

    def _research_prices_tavily(self, origin_city: str, dest_city: str, distance_km: float, travel_date: str) -> list:
        """Use Tavily + LLM to research real transport prices for the route."""
        if not self.tavily_key:
            return []
        
        try:
            from tavily import TavilyClient
            tavily = TavilyClient(api_key=self.tavily_key)
            
            query = f"Train and bus ticket prices from {origin_city} to {dest_city} in INR, including different classes and operators, for travel around {travel_date}"
            search_result = tavily.search(query, max_results=5)
            context = "\n".join([res['content'] for res in search_result.get('results', [])])
            
            if not context.strip():
                return []
            
            sys_prompt = f'''You are a strict JSON-only transport price extractor for Indian travel.
Extract real transport options from {origin_city} to {dest_city} (approx {int(distance_km)} km).
Return ONLY valid JSON:
{{
  "options": [
    {{
      "mode": "Train" or "Bus" or "Cab",
      "provider": "Operator name (e.g. IRCTC Shatabdi Express, RedBus VRL Travels)",
      "class": "Sleeper/3AC/2AC/AC Seater/Volvo AC/etc",
      "price": <float_price_in_INR_per_person>,
      "duration_hrs": <float_estimated_hours>,
      "frequency": "Daily/Twice daily/etc",
      "departure_time": "HH:MM format or 'Various'"
    }}
  ]
}}
RULES:
- Include at least 2 train options (different classes: Sleeper, 3AC, 2AC, Chair Car)
- Include at least 2 bus options (Ordinary, AC Sleeper/Volvo)
- Include 1 cab/taxi option
- Prices MUST be realistic for the {int(distance_km)} km distance in India
- If exact prices not in context, estimate based on standard Indian railway/bus rates for this distance
- Train Sleeper ~₹{int(distance_km * 1.2)}, 3AC ~₹{int(distance_km * 2.8)}, 2AC ~₹{int(distance_km * 4.0)}
- Bus Ordinary ~₹{int(distance_km * 1.5)}, Volvo AC ~₹{int(distance_km * 3.5)}
- Cab ~₹{int(distance_km * 12)}'''

            data = None
            
            # Try Gemini
            if self.google_api_key:
                try:
                    from google import genai
                    gemini_client = genai.Client(api_key=self.google_api_key)
                    MODELS = ["gemini-2.5-flash-lite", "gemini-2.5-flash", "gemini-2.0-flash", "gemini-2.0-flash-lite"]
                    for model_name in MODELS:
                        try:
                            response = gemini_client.models.generate_content(
                                model=model_name,
                                contents=f"Context: {context}\nRoute: {origin_city} to {dest_city}, ~{int(distance_km)} km\nDate: {travel_date}",
                                config=genai.types.GenerateContentConfig(
                                    system_instruction=sys_prompt,
                                    response_mime_type="application/json",
                                )
                            )
                            text = response.text.replace('```json', '').replace('```', '').strip()
                            data = json.loads(text, strict=False)
                            if data and data.get('options'):
                                break
                        except Exception as e:
                            print(f"Gemini Transport Error ({model_name}): {e}")
                            continue
                except Exception as e:
                    print(f"Gemini init error: {e}")
            
            # Fallback to OpenAI
            if not data and self.openai_key:
                try:
                    from openai import OpenAI
                    oai = OpenAI(api_key=self.openai_key)
                    response = oai.chat.completions.create(
                        model="gpt-4o-mini",
                        messages=[
                            {"role": "system", "content": sys_prompt},
                            {"role": "user", "content": f"Context: {context}\nRoute: {origin_city} to {dest_city}"}
                        ],
                        temperature=0,
                        timeout=15
                    )
                    raw = response.choices[0].message.content.replace('```json', '').replace('```', '').strip()
                    data = json.loads(raw, strict=False)
                except Exception as e:
                    print(f"OpenAI Transport Error: {e}")
            
            if data and data.get('options'):
                return data['options']
                
        except Exception as e:
            print(f"Tavily Transport Research Error: {e}")
        
        return []

    def _fallback_options(self, distance_km: float, origin_city: str, dest_city: str, travel_date: str = "") -> List[dict]:
        """Generate rate-based fallback options with multiple classes."""
        options = []
        links = self._get_booking_links(origin_city, dest_city, travel_date)
        
        hill_stations = ['manali', 'shimla', 'munnar', 'ooty', 'darjeeling', 'leh', 'gulmarg', 'spiti', 'kasol', 'mcleodganj']
        is_hill = dest_city.strip().lower() in hill_stations
        
        if not is_hill:
            # Multiple train options with different classes
            train_names = ['Shatabdi Exp', 'Tejas Express', 'Rajdhani Exp', 'Vande Bharat', 'Duronto Exp']
            train_duration = distance_km / self.train_speed_kmh
            
            # Sleeper class
            options.append({
                "mode": "Train",
                "provider": f"IRCTC ({random.choice(train_names)}) - Sleeper",
                "price": round(distance_km * self.train_rates["sleeper"], 2),
                "currency": "INR",
                "duration_hrs": round(train_duration, 1),
                "class": "Sleeper",
                "route": f"From {origin_city} Jn to {dest_city} Central (~{round(train_duration)}h)",
                "booking_url": links["train"],
                "search_url": links["train_search"],
            })
            
            # 3AC class
            options.append({
                "mode": "Train",
                "provider": f"IRCTC ({random.choice(train_names)}) - 3AC",
                "price": round(distance_km * self.train_rates["3ac"], 2),
                "currency": "INR",
                "duration_hrs": round(train_duration, 1),
                "class": "3AC",
                "route": f"From {origin_city} Jn to {dest_city} Central (~{round(train_duration)}h)",
                "booking_url": links["train"],
                "search_url": links["train_search"],
            })
            
            # 2AC class (for longer distances)
            if distance_km > 200:
                options.append({
                    "mode": "Train",
                    "provider": f"IRCTC ({random.choice(train_names)}) - 2AC",
                    "price": round(distance_km * self.train_rates["2ac"], 2),
                    "currency": "INR",
                    "duration_hrs": round(train_duration, 1),
                    "class": "2AC",
                    "route": f"From {origin_city} Jn to {dest_city} Central (~{round(train_duration)}h)",
                    "booking_url": links["train"],
                    "search_url": links["train_search"],
                })

        # Bus options - multiple types
        bus_duration = distance_km / self.bus_speed_kmh
        
        # Ordinary bus
        options.append({
            "mode": "Bus",
            "provider": f"RedBus (Ordinary/Non-AC)",
            "price": round(distance_km * self.bus_rates["ordinary"], 2),
            "currency": "INR",
            "duration_hrs": round(bus_duration, 1),
            "class": "Ordinary",
            "route": f"From {origin_city} ISBT to {dest_city} Bus Stand (~{round(bus_duration)}h)",
            "booking_url": links["bus"],
            "search_url": links["bus_search"],
        })
        
        # AC Sleeper/Volvo
        bus_operators = ['VRL Travels', 'Orange Tours', 'SRS Travels', 'KPN Travels']
        options.append({
            "mode": "Bus",
            "provider": f"RedBus ({random.choice(bus_operators)}) - Volvo AC",
            "price": round(distance_km * self.bus_rates["volvo_ac"], 2),
            "currency": "INR",
            "duration_hrs": round(bus_duration * 0.9, 1),  # AC buses slightly faster
            "class": "Volvo AC",
            "route": f"From {origin_city} to {dest_city} (~{round(bus_duration * 0.9)}h)",
            "booking_url": links["bus"],
            "search_url": links["bus_search"],
        })

        # Cab option
        cab_price = distance_km * self.cab_rate_per_km
        cab_duration = distance_km / 60  # ~60 km/h average
        options.append({
            "mode": "Cab",
            "provider": "Ola/Uber Outstation Cab",
            "price": round(cab_price, 2),
            "currency": "INR",
            "duration_hrs": round(cab_duration, 1),
            "class": "Sedan",
            "route": f"Door-to-door from {origin_city} to {dest_city} (~{round(cab_duration)}h)",
            "booking_url": links["cab"],
            "search_url": links["map"],
        })
        
        return options

    def get_options(self, distance_km: float, origin_city: str = "Origin", dest_city: str = "Destination", travel_date: str = "Tomorrow") -> List[dict]:
        """
        Get transport options with Tavily+LLM research, falling back to rate-based calculations.
        Returns multiple options across Train, Bus, and Cab modes.
        """
        links = self._get_booking_links(origin_city, dest_city, travel_date)
        
        # 1. Try Tavily+LLM research for real prices
        researched = self._research_prices_tavily(origin_city, dest_city, distance_km, travel_date)
        
        if researched and len(researched) >= 3:
            options = []
            for opt in researched:
                mode = opt.get("mode", "Train")
                mode_lower = mode.lower()
                
                # Assign booking links based on mode
                if "train" in mode_lower:
                    booking_url = links["train"]
                    search_url = links["train_search"]
                elif "bus" in mode_lower:
                    booking_url = links["bus"]
                    search_url = links["bus_search"]
                else:
                    booking_url = links["cab"]
                    search_url = links["map"]
                
                duration = opt.get("duration_hrs", distance_km / 60)
                options.append({
                    "mode": mode,
                    "provider": opt.get("provider", f"{mode} Service"),
                    "price": round(float(opt.get("price", 0)), 2),
                    "currency": "INR",
                    "duration_hrs": round(float(duration), 1),
                    "class": opt.get("class", "Standard"),
                    "route": f"From {origin_city} to {dest_city} (~{round(float(duration))}h)",
                    "booking_url": booking_url,
                    "search_url": search_url,
                })
            return options
        
        # 2. Try IRCTC RapidAPI for trains
        rapidapi_key = os.getenv("RAPIDAPI_KEY")
        api_options = []
        
        if rapidapi_key:
            try:
                import requests, datetime
                try:
                    dt_obj = datetime.datetime.strptime(travel_date, "%Y-%m-%d")
                    irctc_date = dt_obj.strftime("%d/%m/%Y")
                except:
                    irctc_date = "10/06/2026"
                
                station_map = {
                    "delhi": "NDLS", "new delhi": "NDLS", "mumbai": "BCT", "bangalore": "SBC",
                    "bengaluru": "SBC", "chennai": "MAS", "kolkata": "HWH", "agra": "AGC",
                    "jaipur": "JP", "goa": "MAO", "hyderabad": "SC", "pune": "PUNE",
                    "ahmedabad": "ADI", "lucknow": "LKO", "varanasi": "BSB",
                    "kochi": "ERS", "trivandrum": "TVC", "thiruvananthapuram": "TVC",
                }
                origin_code = station_map.get(origin_city.lower().strip(), "NDLS")
                dest_code = station_map.get(dest_city.lower().strip(), "BCT")
                
                url = "https://irctc1.p.rapidapi.com/api/v1/searchTrain"
                qs = {"source": origin_code, "destination": dest_code, "journeyDate": irctc_date}
                headers = {
                    "x-rapidapi-key": rapidapi_key,
                    "x-rapidapi-host": "irctc1.p.rapidapi.com"
                }
                res = requests.get(url, headers=headers, params=qs, timeout=10)
                data = res.json()
                
                if data.get("data") and len(data["data"]) > 0:
                    # Take up to 3 trains
                    for train in data["data"][:3]:
                        train_name = train.get("trainName", "Express Train")
                        train_num = train.get("trainNumber", "")
                        dep_time = train.get("departureTime", "08:00")
                        arr_time = train.get("arrivalTime", "15:00")
                        duration = train.get("duration", "7:00")
                        
                        duration_hrs = distance_km / self.train_speed_kmh
                        if ':' in str(duration):
                            try:
                                pts = str(duration).split(':')
                                duration_hrs = float(pts[0]) + (float(pts[1]) / 60)
                            except:
                                pass
                        
                        # Add multiple class options for each train
                        for cls_name, rate in [("Sleeper", self.train_rates["sleeper"]), ("3AC", self.train_rates["3ac"])]:
                            price = distance_km * rate
                            api_options.append({
                                "mode": "Train",
                                "provider": f"IRCTC ({train_name} {train_num}) - {cls_name}",
                                "price": round(price, 2),
                                "currency": "INR",
                                "duration_hrs": round(duration_hrs, 1),
                                "class": cls_name,
                                "route": f"From {origin_code} at {dep_time} to {dest_code} at {arr_time}",
                                "booking_url": links["train"],
                                "search_url": links["train_search"],
                            })
            except Exception as e:
                print(f"RapidAPI IRCTC Error: {e}")
        
        if api_options:
            # Add bus and cab options from fallback
            fallback = self._fallback_options(distance_km, origin_city, dest_city, travel_date)
            bus_cab = [opt for opt in fallback if opt.get("mode") in ("Bus", "Cab")]
            return api_options + bus_cab
        
        # 3. Full fallback
        return self._fallback_options(distance_km, origin_city, dest_city, travel_date)

    def get_local_transport_estimate(self, city: str, days: int) -> dict:
        """
        Estimate daily local transport costs (cabs, autos, metro) within a city.
        Returns per-day and total estimates.
        """
        # City-tier based pricing
        tier1_cities = ['mumbai', 'delhi', 'bangalore', 'bengaluru', 'chennai', 'kolkata', 'hyderabad', 'pune']
        tier2_cities = ['jaipur', 'agra', 'lucknow', 'ahmedabad', 'kochi', 'goa', 'varanasi', 'chandigarh']
        
        city_lower = city.strip().lower()
        
        if city_lower in tier1_cities:
            daily_estimate = random.randint(800, 1200)
            metro_available = True
        elif city_lower in tier2_cities:
            daily_estimate = random.randint(500, 900)
            metro_available = False
        else:
            daily_estimate = random.randint(400, 700)
            metro_available = False
        
        return {
            "daily_estimate": daily_estimate,
            "total_estimate": daily_estimate * days,
            "metro_available": metro_available,
            "breakdown": {
                "morning_cab": round(daily_estimate * 0.35),
                "afternoon_auto": round(daily_estimate * 0.30),
                "evening_transport": round(daily_estimate * 0.35),
            }
        }
