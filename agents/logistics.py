import os
import random
from openai import OpenAI
from amadeus import Client, ResponseError
from core.utils import convert_eur_to_inr
import json
from core.cache import get_cached_data, set_cached_data
from dotenv import load_dotenv

# Load env in case it wasn't loaded by the runner
load_dotenv()

class LogisticsAgent:
    def __init__(self):
        self.api_key = os.getenv("AMADEUS_API_KEY")
        self.api_secret = os.getenv("AMADEUS_API_SECRET")
        self.tavily_key = os.getenv("TAVILY_API_KEY")
        self.openai_key = os.getenv("OPENAI_API_KEY")
        self.google_api_key = os.getenv("GOOGLE_API_KEY")
        
        # Initialize Amadeus
        if self.api_key and self.api_secret:
            self.amadeus = Client(
                client_id=self.api_key,
                client_secret=self.api_secret
            )
        else:
            self.amadeus = None

        # Initialize LLM Clients for research-based extraction
        self.gemini_client = None
        if self.google_api_key:
            try:
                from google import genai
                self.gemini_client = genai.Client(api_key=self.google_api_key)
            except:
                pass
        
        self.oai_api_key = os.getenv("LLM_STUDIO_API_KEY", "lm-studio")
        self.oai_base_url = os.getenv("LLM_STUDIO_BASE_URL", "http://localhost:1234/v1")
        self.oai_model = os.getenv("LLM_STUDIO_MODEL", "google/gemma-3-1b")
        self.oai_client = OpenAI(base_url=self.oai_base_url, api_key=self.oai_api_key)
            
    def _fetch_hotels_tavily(self, city_name: str, check_in: str, check_out: str, days: int = 1, nearby_attractions: list = None) -> list:
        """Fetch hotel recommendations via Tavily web search + LLM extraction.
        Now requests unique hotels near specific attraction areas for each night."""
        num_hotels = max(3, days + 2)  # Enough unique hotels for all nights + choices
        
        if not self.tavily_key or not (self.openai_key or self.google_api_key or self.oai_api_key):
            from agents.fallback import FallbackAgent
            return FallbackAgent().get_hotels(city_name, check_in, check_out)
            
        try:
            from tavily import TavilyClient
            tavily = TavilyClient(api_key=self.tavily_key)
            
            # Build area-aware query if we have attraction locations
            area_hint = ""
            if nearby_attractions and len(nearby_attractions) > 0:
                area_names = [a.get('title', '') for a in nearby_attractions[:5] if a.get('title')]
                if area_names:
                    area_hint = f" near areas like {', '.join(area_names[:3])}"
            
            query = f"Best {num_hotels} highly rated hotels in {city_name}{area_hint} with nightly price in INR, including budget, mid-range, and luxury options for {days} nights from {check_in} to {check_out}"
            search_result = tavily.search(query, max_results=5)
            context = "\n".join([res['content'] for res in search_result.get('results', [])])
            
            sys_prompt = f'''You are a strict JSON-only travel extractor.
Extract {num_hotels} distinct real hotels from the context for {city_name}.
The traveler is staying for {days} night(s) from {check_in} to {check_out}.
Hotels should be in DIFFERENT areas/neighborhoods of the city for variety.
Return ONLY valid JSON:
{{
  "options": [
    {{
      "name": "Exact Real Hotel Name",
      "area": "Neighborhood/Area name in the city",
      "price": <float_NIGHTLY_price_in_INR>,
      "currency": "INR",
      "safety_score": <int_rating_out_of_100>,
      "rating": <float_out_of_5>,
      "check_in": "14:00",
      "check_out": "11:00",
      "website_url": "official hotel website URL if known, else empty string",
      "nearby_landmark": "nearest famous landmark or attraction"
    }}
  ]
}}
CRITICAL: 
- Return {num_hotels} UNIQUE hotels in DIFFERENT neighborhoods/areas
- Price must be per-night in INR
- Include a mix: budget (₹1000-3000), mid-range (₹3000-6000), premium (₹6000-15000)
- Each hotel should be a real hotel that actually exists in {city_name}
- "area" field is MANDATORY - which part of {city_name} is this hotel in'''

            GEMINI_FALLBACK_MODELS = ["gemini-2.5-flash-lite", "gemini-2.5-flash", "gemini-2.0-flash", "gemini-2.0-flash-lite"]
            # 1. Try Gemini (with model fallback)
            if self.gemini_client:
                from google import genai
                models_to_try = [os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite")] + [m for m in GEMINI_FALLBACK_MODELS if m != os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite")]
                data = None
                for model_name in models_to_try:
                    try:
                        response = self.gemini_client.models.generate_content(
                            model=model_name,
                            contents=f"Context: {context}\nCity: {city_name}\nStay: {days} nights from {check_in} to {check_out}",
                            config=genai.types.GenerateContentConfig(
                                system_instruction=sys_prompt,
                                response_mime_type="application/json",
                            )
                        )
                        text = response.text.replace('```json', '').replace('```', '').strip()
                        data = json.loads(text, strict=False)
                        if data:
                            break
                    except Exception as e:
                        print(f"Gemini Logistics Error ({model_name}): {e}")
                        continue
            else:
                data = None

            # 2. Fallback to OpenAI Cloud API
            if not data and self.openai_key:
                try:
                    oai_cloud = OpenAI(api_key=self.openai_key)
                    response = oai_cloud.chat.completions.create(
                        model="gpt-4o-mini",
                        messages=[
                            {"role": "system", "content": sys_prompt},
                            {"role": "user", "content": f"Context: {context}\nCity: {city_name}\nStay: {days} nights"}
                        ],
                        temperature=0,
                        timeout=15
                    )
                    raw = response.choices[0].message.content
                    raw = raw.replace('```json', '').replace('```', '').strip()
                    data = json.loads(raw, strict=False)
                except Exception as e:
                    print(f"OpenAI Cloud hotel extraction error: {e}")
                    data = None

            # 3. Fallback to Local LLM
            if not data:
                try:
                    response = self.oai_client.chat.completions.create(
                        model=self.oai_model,
                        messages=[
                            {"role": "system", "content": sys_prompt},
                            {"role": "user", "content": f"Context: {context}\nCity: {city_name}"}
                        ],
                        temperature=0,
                        timeout=12
                    )
                    raw = response.choices[0].message.content
                    data = json.loads(raw)
                except Exception as e:
                    print(f"Logistics Critical Fallback Fail: {e}")
                    data = {"options": []}
                
            if 'options' in data and len(data['options']) > 0:
                opts = data['options']
                for o in opts:
                    o['hotelId'] = str(random.randint(1000,9999))
                    o['data_source'] = 'tavily_llm'
                    
                    hotel_name = o.get('name', city_name)
                    hotel_search = hotel_name.replace(' ', '+')
                    city_search = city_name.replace(' ', '+')
                    
                    # Generate Google Maps link for the hotel
                    o['map_url'] = f"https://www.google.com/maps/search/{hotel_search}+{city_search}"
                    
                    # Use official website if available, otherwise Google Travel search
                    website = o.get('website_url', '')
                    if not website or 'example.com' in str(website):
                        o['url'] = f"https://www.google.com/travel/hotels/{city_search}?q={hotel_search}"
                    else:
                        o['url'] = website
                    
                    # Ensure area field exists
                    if not o.get('area'):
                        o['area'] = city_name
                    
                    # Generate a secondary booking link
                    o['booking_search_url'] = f"https://www.booking.com/searchresults.html?ss={hotel_search}+{city_search}"
                    
                return opts
        except Exception as e:
            print(f"Tavily Hotel fallback error: {e}")
            
        from agents.fallback import FallbackAgent
        return FallbackAgent().get_hotels(city_name, check_in, check_out)
            
    def get_flights(self, origin: str, destination: str, departure_date: str, adults: int = 1, origin_name: str="Origin", dest_name: str="Destination", return_date: str = None) -> list:
        """
        Fetch real-time flight estimates with persistent caching.
        Now always includes round-trip pricing when return_date is provided.
        """
        cached = get_cached_data("flights", origin, destination, departure_date, adults, return_date)
        if cached:
            return cached
        
        if not self.amadeus:
            # Robust Simulation Mode for Flights
            # Use Tavily+LLM for realistic flight pricing
            researched_flights = self._research_flights_tavily(origin_name, dest_name, departure_date, return_date, adults)
            if researched_flights:
                set_cached_data("flights", researched_flights, origin, destination, departure_date, adults, return_date)
                return researched_flights
            
            # Scale Mock price by number of adults
            base_multiplier = 2 if return_date else 1
            
            # More realistic base prices based on route type
            base_prices = [
                random.randint(3500, 5500),
                random.randint(4500, 7000),
                random.randint(5500, 9000),
            ]
            
            trip_type = "Round Trip" if return_date else "One Way"
            
            flights = [
                {
                    "airline": "IndiGo",
                    "flight_number": f"6E-{random.randint(100,999)}",
                    "departure": "06:30 AM",
                    "arrival": "08:45 AM",
                    "duration": "2h 15m",
                    "price": base_prices[0] * adults * base_multiplier,
                    "currency": "INR",
                    "mode": "Flight",
                    "trip_type": trip_type,
                    "route": f"[{trip_type}] From {origin_name} at 06:30 AM to {dest_name}" + (f" (Return: {return_date})" if return_date else ""),
                    "booking_url": f"https://www.goindigo.in/",
                    "search_url": f"https://www.google.com/travel/flights?q={origin_name}+to+{dest_name}+{departure_date}",
                },
                {
                    "airline": "Air India",
                    "flight_number": f"AI-{random.randint(100,999)}",
                    "departure": "10:15 AM",
                    "arrival": "12:40 PM",
                    "duration": "2h 25m",
                    "price": base_prices[1] * adults * base_multiplier,
                    "currency": "INR",
                    "mode": "Flight",
                    "trip_type": trip_type,
                    "route": f"[{trip_type}] From {origin_name} at 10:15 AM to {dest_name}" + (f" (Return: {return_date})" if return_date else ""),
                    "booking_url": f"https://www.airindia.com/",
                    "search_url": f"https://www.google.com/travel/flights?q={origin_name}+to+{dest_name}+{departure_date}",
                },
                {
                    "airline": "Vistara/Air India Express",
                    "flight_number": f"UK-{random.randint(100,999)}",
                    "departure": "04:00 PM",
                    "arrival": "06:10 PM",
                    "duration": "2h 10m",
                    "price": base_prices[2] * adults * base_multiplier,
                    "currency": "INR",
                    "mode": "Flight",
                    "trip_type": trip_type,
                    "route": f"[{trip_type}] From {origin_name} at 04:00 PM to {dest_name}" + (f" (Return: {return_date})" if return_date else ""),
                    "booking_url": f"https://www.airindia.com/",
                    "search_url": f"https://www.google.com/travel/flights?q={origin_name}+to+{dest_name}+{departure_date}",
                }
            ]
            set_cached_data("flights", flights, origin, destination, departure_date, adults, return_date)
            return flights
            
        rapidapi_key = os.getenv("RAPIDAPI_KEY")
        if rapidapi_key:
            import requests, datetime
            try:
                # Prepare date formats
                dep_dt = datetime.datetime.strptime(departure_date, "%Y-%m-%d")
                d_str = dep_dt.strftime("%Y-%m-%d")
                r_str = None
                if return_date:
                    ret_dt = datetime.datetime.strptime(return_date, "%Y-%m-%d")
                    r_str = ret_dt.strftime("%Y-%m-%d")
                else:
                    # flights-sky requires a return date for roundtrip endpoint, mock 3 days later if missing
                    r_str = (dep_dt + datetime.timedelta(days=3)).strftime("%Y-%m-%d")
                    
                url = 'https://flights-sky.p.rapidapi.com/flights/search-roundtrip'
                headers = {
                    'x-rapidapi-key': rapidapi_key,
                    'x-rapidapi-host': 'flights-sky.p.rapidapi.com'
                }
                qs = {
                    'fromEntityId': origin, 
                    'toEntityId': destination,
                    'departDate': d_str,
                    'returnDate': r_str,
                    'currency': 'INR'
                }
                res = requests.get(url, headers=headers, params=qs)
                data = res.json()
                
                real_flights = []
                if data.get('data') and data['data'].get('itineraries'):
                    trip_type = "Round Trip" if return_date else "One Way"
                    for itin in data['data']['itineraries'][:4]:  # Get up to 4 flights
                        price_raw = itin.get('price', {}).get('raw', 0)
                        
                        leg = itin.get('legs', [{}])[0]
                        duration_mins = leg.get('durationInMinutes', 120)
                        dep_time = leg.get('departure', '10:00:00').split('T')[-1][:5]
                        arr_time = leg.get('arrival', '12:00:00').split('T')[-1][:5]
                        
                        carriers = leg.get('carriers', {}).get('marketing', [{}])
                        airline_name = carriers[0].get('name', 'Airline') if carriers else 'Airline'
                        
                        segments = leg.get('segments', [{}])
                        flight_num = segments[0].get('flightNumber', '101') if segments else '101'
                        
                        real_flights.append({
                            "airline": f"{airline_name} (Live)",
                            "flight_number": flight_num,
                            "departure": dep_time,
                            "arrival": arr_time,
                            "duration": f"{duration_mins // 60}h {duration_mins % 60}m",
                            "price": round(float(price_raw) * adults, 2),
                            "currency": "INR",
                            "mode": "Flight",
                            "trip_type": trip_type,
                            "route": f"[{trip_type}] From {origin} at {dep_time} to {destination}",
                            "booking_url": f"https://www.google.com/travel/flights?q={origin_name}+to+{dest_name}+{departure_date}",
                            "search_url": f"https://www.google.com/travel/flights?q={origin_name}+to+{dest_name}+{departure_date}",
                        })
                
                if real_flights:
                    return real_flights
            except Exception as e:
                print(f"RapidAPI Flights ERROR: {e}")
                
        # Existing Amadeus Fallback Logic
        try:
            kwargs = {
                "originLocationCode": origin,
                "destinationLocationCode": destination,
                "departureDate": departure_date,
                "adults": adults,
                "currencyCode": "INR"
            }
            if return_date:
                kwargs["returnDate"] = return_date
                
            response = self.amadeus.shopping.flight_offers_search.get(**kwargs)
            res = response.data[:4]  # Return top 4 options
            set_cached_data("flights", res, origin, destination, departure_date, adults, return_date)
            return res
        except Exception as error:
            print(f"Amadeus Flight Error: {error}")
            return []

    def _research_flights_tavily(self, origin_name: str, dest_name: str, departure_date: str, return_date: str, adults: int) -> list:
        """Research realistic flight prices using Tavily + LLM."""
        if not self.tavily_key:
            return []
        
        try:
            from tavily import TavilyClient
            tavily = TavilyClient(api_key=self.tavily_key)
            
            trip_type = "round trip" if return_date else "one way"
            query = f"Flight ticket price from {origin_name} to {dest_name} {trip_type} {departure_date} in INR, airlines like IndiGo Air India Vistara"
            search_result = tavily.search(query, max_results=3)
            context = "\n".join([res['content'] for res in search_result.get('results', [])])
            
            if not context.strip():
                return []
            
            sys_prompt = f'''Extract real flight options from {origin_name} to {dest_name}.
Return ONLY valid JSON:
{{
  "flights": [
    {{
      "airline": "Airline Name",
      "price": <total_price_in_INR_for_{adults}_adults_{trip_type}>,
      "departure": "HH:MM AM/PM",
      "arrival": "HH:MM AM/PM",
      "duration": "Xh Ym"
    }}
  ]
}}
Include 3-4 different airlines. Prices must be realistic for {trip_type} tickets in INR for {adults} adult(s).'''

            data = None
            if self.gemini_client:
                from google import genai
                MODELS = ["gemini-2.5-flash-lite", "gemini-2.5-flash", "gemini-2.0-flash"]
                for model_name in MODELS:
                    try:
                        response = self.gemini_client.models.generate_content(
                            model=model_name,
                            contents=f"Context: {context}\nRoute: {origin_name} to {dest_name}\nDate: {departure_date}",
                            config=genai.types.GenerateContentConfig(
                                system_instruction=sys_prompt,
                                response_mime_type="application/json",
                            )
                        )
                        text = response.text.replace('```json', '').replace('```', '').strip()
                        data = json.loads(text, strict=False)
                        if data and data.get('flights'):
                            break
                    except:
                        continue
            
            if not data and self.openai_key:
                try:
                    oai_cloud = OpenAI(api_key=self.openai_key)
                    response = oai_cloud.chat.completions.create(
                        model="gpt-4o-mini",
                        messages=[
                            {"role": "system", "content": sys_prompt},
                            {"role": "user", "content": f"Context: {context}"}
                        ],
                        temperature=0, timeout=12
                    )
                    raw = response.choices[0].message.content.replace('```json', '').replace('```', '').strip()
                    data = json.loads(raw, strict=False)
                except:
                    pass
            
            if data and data.get('flights'):
                rt = "Round Trip" if return_date else "One Way"
                results = []
                for f in data['flights'][:4]:
                    results.append({
                        "airline": f.get("airline", "Airline"),
                        "flight_number": f"FL-{random.randint(100,999)}",
                        "departure": f.get("departure", "08:00 AM"),
                        "arrival": f.get("arrival", "10:00 AM"),
                        "duration": f.get("duration", "2h 0m"),
                        "price": round(float(f.get("price", 5000)), 2),
                        "currency": "INR",
                        "mode": "Flight",
                        "trip_type": rt,
                        "route": f"[{rt}] From {origin_name} to {dest_name}",
                        "booking_url": f"https://www.google.com/travel/flights?q={origin_name}+to+{dest_name}",
                        "search_url": f"https://www.google.com/travel/flights?q={origin_name}+to+{dest_name}+{departure_date}",
                    })
                return results
        except Exception as e:
            print(f"Flight Tavily research error: {e}")
        
        return []

    def get_hotels(self, cityCode: str, city_name: str = "", check_in: str = None, check_out: str = None, days: int = 1, nearby_attractions: list = None) -> list:
        """
        Fetch hotel options with persistent caching.
        Now fetches enough unique hotels for all trip nights in different areas.
        """
        cached = get_cached_data("hotels", cityCode, city_name, check_in, check_out, days)
        if cached:
            return cached

        import random
        import requests
        from agents.fallback import FallbackAgent
        
        rapidapi_key = os.getenv("RAPIDAPI_KEY")
        if not rapidapi_key or not check_in or not check_out:
            return self._fetch_hotels_tavily(city_name or cityCode, check_in, check_out, days=days, nearby_attractions=nearby_attractions)
            
        try:
            # 1. Get dest_id for the city
            url_dest = 'https://booking-com15.p.rapidapi.com/api/v1/hotels/searchDestination'
            headers = {
                'x-rapidapi-key': rapidapi_key,
                'x-rapidapi-host': 'booking-com15.p.rapidapi.com'
            }
            res_dest = requests.get(url_dest, headers=headers, params={'query': city_name or cityCode})
            dest_data = res_dest.json()
            
            dest_id = None
            if dest_data.get('status') and dest_data.get('data'):
                dest_id = dest_data['data'][0].get('dest_id')
                
            if not dest_id:
                 print("Booking API: Could not find dest_id")
                 return self._fetch_hotels_tavily(city_name or cityCode, check_in, check_out, days=days, nearby_attractions=nearby_attractions)
                 
            # 2. Search hotels using dest_id
            url_hotels = 'https://booking-com15.p.rapidapi.com/api/v1/hotels/searchHotels'
            qs_hotels = {
                'dest_id': dest_id,
                'search_type': 'city',
                'arrival_date': check_in,
                'departure_date': check_out,
                'adults': '1',
                'room_qty': '1',
                'currency_code': 'INR'
            }
            res_hotels = requests.get(url_hotels, headers=headers, params=qs_hotels)
            hotels_data = res_hotels.json()
            
            num_needed = max(4, days + 2)  # Extra options for variety
            deep_hotels = []
            if hotels_data.get('data') and hotels_data['data'].get('hotels'):
                for item in hotels_data['data']['hotels'][:num_needed]:
                    prop = item.get('property', {})
                    price_info = prop.get('priceBreakdown', {}).get('grossPrice', {})
                    price_val = price_info.get('value', 5000)
                    h_name = prop.get('name', 'Hotel')
                    rating = prop.get('reviewScore', 8.0) * 10
                    
                    hotel_search = h_name.replace(' ', '+')
                    city_search = (city_name or cityCode).replace(' ', '+')
                    
                    deep_hotels.append({
                        "hotelId": str(prop.get('id', random.randint(1000,9999))),
                        "name": h_name,
                        "area": prop.get('countryCode', city_name),  # Area info from API
                        "price": round(float(price_val), 2),
                        "currency": "INR",
                        "safety_score": int(rating) if rating else random.randint(80, 95),
                        "rating": round(float(prop.get('reviewScore', 4.0)), 1),
                        "check_in": prop.get('checkin', {}).get('fromTime', '14:00'),
                        "check_out": prop.get('checkout', {}).get('untilTime', '11:00'),
                        "url": f"https://www.google.com/travel/hotels/{city_search}?q={hotel_search}",
                        "map_url": f"https://www.google.com/maps/search/{hotel_search}+{city_search}",
                        "booking_search_url": f"https://www.booking.com/searchresults.html?ss={hotel_search}+{city_search}",
                        "data_source": "rapidapi_booking"
                    })
            
            if deep_hotels:
                set_cached_data("hotels", deep_hotels, cityCode, city_name, check_in, check_out, days)
                return deep_hotels
                
            res = self._fetch_hotels_tavily(city_name or cityCode, check_in, check_out, days=days, nearby_attractions=nearby_attractions)
            set_cached_data("hotels", res, cityCode, city_name, check_in, check_out, days)
            return res
            
        except Exception as e:
            print(f"RapidAPI Booking.com Error: {e}")
            res = self._fetch_hotels_tavily(city_name or cityCode, check_in, check_out, days=days, nearby_attractions=nearby_attractions)
            set_cached_data("hotels", res, cityCode, city_name, check_in, check_out, days)
            return res
