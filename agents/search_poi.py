import os
import random
import json
from tavily import TavilyClient
from core.cache import get_cached_data, set_cached_data
from google import genai
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

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

class SearchPOIAgent:
    def __init__(self):
        self.api_key = os.getenv("TAVILY_API_KEY")
        self.client = TavilyClient(api_key=self.api_key) if self.api_key else None
        
        # LLM Clients for Intelligent Categorization
        self.google_api_key = os.getenv("GOOGLE_API_KEY")
        self.model_name = os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite")
        
        self.gemini_client = None
        if self.google_api_key:
            try:
                self.gemini_client = genai.Client(api_key=self.google_api_key)
            except:
                pass

        self.oai_api_key = os.getenv("LLM_STUDIO_API_KEY", "lm-studio")
        self.oai_base_url = os.getenv("LLM_STUDIO_BASE_URL", "http://localhost:1234/v1")
        self.oai_model = os.getenv("LLM_STUDIO_MODEL", "google/gemma-3-1b")
        try:
            self.oai_client = OpenAI(base_url=self.oai_base_url, api_key=self.oai_api_key)
        except:
            self.oai_client = None

    def search_all_pois(self, city: str, is_veg: bool = False, is_jain: bool = False, dates: str = "") -> dict:
        """
        One combined search to rule them all. Much faster than 5 separate parallel calls.
        Utilizes persistent caching to reduce time.
        """
        cached = get_cached_data("poi", city, is_veg, is_jain, dates)
        if cached:
            return cached

        query = f"Top attractions, local food secrets {'(vegetarian/jain)' if is_veg or is_jain else ''}, upcoming festivals, cultural celebrations, events, and instagrammable spots in {city} for {dates} 2026"
        
        results = self._execute_search(query, city)
        base_lat, base_lon = MOCK_COORDS.get(city.strip().title(), [15.0, 75.0])

        # 2. Intelligent Categorization utilizing LLM
        system_prompt = f"""
        You are a POI Categorization AI. Given a list of search results for {city}, categorize them into:
        - "attractions": Historical sites, landmarks, museums, parks.
        - "food": Iconic restaurants, cafes, street food spots.
        - "events": Concerts, exhibitions, markets happening around {dates}.
        - "festivals": Cultural celebrations or seasonal holidays.
        - "instagrammable": Aesthetic viewpoints, scenic spots, artistic streets.

        Each result should have: "title", "content", "url", "category".
        CRITICAL: The "content" field should be a catchy, one-sentence "Quick Insight" (max 15 words) for the traveler.
        Deduplicate items and pick only the highest quality/relevant ones (top 5-6 per category).
        Return ONLY a JSON object with category keys and lists of items.
        """
        
        # Prepare content for LLM
        simplified_results = [{"title": r.get('title'), "content": r.get('content'), "url": r.get('url')} for r in results]
        content_to_rank = json.dumps(simplified_results)

        GEMINI_FALLBACK_MODELS = ["gemini-2.5-flash-lite", "gemini-2.5-flash", "gemini-2.0-flash", "gemini-2.0-flash-lite"]
        poi_data = None
        # Try Gemini (with model fallback)
        if self.gemini_client:
             models_to_try = [self.model_name] + [m for m in GEMINI_FALLBACK_MODELS if m != self.model_name]
             for model_name in models_to_try:
                 try:
                    response = self.gemini_client.models.generate_content(
                        model=model_name,
                        contents=content_to_rank,
                        config=genai.types.GenerateContentConfig(
                            system_instruction=system_prompt,
                            response_mime_type="application/json",
                        )
                    )
                    text = response.text.replace('```json', '').replace('```', '').strip()
                    poi_data = json.loads(text)
                    if poi_data:
                        break
                 except Exception as e:
                    print(f"Gemini POI Rank Error ({model_name}): {e}")
                    continue

        # Fallback to Local LLM
        if not poi_data and self.oai_client:
            try:
                response = self.oai_client.chat.completions.create(
                    model=self.oai_model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": content_to_rank}
                    ],
                    temperature=0.1,
                    timeout=10
                )
                poi_data = json.loads(response.choices[0].message.content)
            except Exception as e:
                print(f"Local LLM POI Rank Error: {e}")

        # Final Fallback to Basic Mapping if LLM fails
        if not poi_data:
            poi_data = self._basic_categorization(results, is_veg, is_jain)

        # Inject coordinates into the final data
        categories = ["attractions", "food", "events", "festivals", "instagrammable"]
        for cat in categories:
            if cat in poi_data and isinstance(poi_data[cat], list):
                for item in poi_data[cat]:
                    item["latitude"] = base_lat + random.uniform(-0.02, 0.02)
                    item["longitude"] = base_lon + random.uniform(-0.02, 0.02)
                    # Preserve prices if they existed in raw results or default
                    item["price"] = next((r.get('price') for r in results if r.get('title') == item.get('title')), random.randint(100, 500))

        set_cached_data("poi", poi_data, city, is_veg, is_jain, dates)
        return poi_data

    def _basic_categorization(self, results: list, is_veg: bool, is_jain: bool) -> dict:
        def score_result(res, category_keywords):
            text = (res.get('title', '') + " " + res.get('content', '')).lower()
            return sum(1 for kw in category_keywords if kw in text)

        cat_map = {
            "attractions": ["temple", "museum", "palace", "fort", "park", "landmark", "monument", "historic", "architecture", "garden", "site", "ruins", "cathedral"],
            "food": ["food", "restaurant", "cafe", "dining", "dish", "cuisine", "eat", "bakery", "street food", "kitchen", "bar", "pub", "bistro", "authentic", "gastronomy", "flavor", "delicacy", "vegan", "vegetarian", "jain"],
            "events": ["event", "concert", "exhibition", "show", "performance", "theater", "expo", "fair", "workshop", "market", "bazaar"],
            "festivals": ["festival", "celebration", "tradition", "culture", "holiday", "ritual", "parade", "carnival"],
            "instagrammable": ["photo", "instagram", "view", "aesthetic", "scenic", "beautiful", "panoramic", "shot", "sunset", "skyline", "architecture"]
        }
        if is_veg or is_jain:
            cat_map["food"].extend(["veg", "pure veg", "no onion", "no garlic", "plant-based"])

        poi_data = {cat: [] for cat in cat_map}
        used_titles = set()
        for cat, keywords in cat_map.items():
            scored = []
            for res in results:
                if res.get('title') in used_titles: continue
                score = score_result(res, keywords)
                if score > 0: scored.append((res, score))
            sorted_res = sorted(scored, key=lambda x: x[1], reverse=True)
            final_cat_results = [r for r, s in sorted_res[:6]]
            poi_data[cat] = final_cat_results
            for r in final_cat_results: used_titles.add(r.get('title'))

        # Fill missing
        for cat in cat_map.keys():
            if len(poi_data[cat]) < 3:
                available = [r for r in results if r.get('title') not in used_titles]
                needed = 6 - len(poi_data[cat])
                fill = available[:needed]
                poi_data[cat].extend(fill)
                for r in fill: used_titles.add(r.get('title'))
        return poi_data

    def search_attractions(self, city: str) -> list:
        return self.search_all_pois(city).get("attractions", [])
        
    def search_food(self, city: str, is_veg: bool = False, is_jain: bool = False) -> list:
        return self.search_all_pois(city, is_veg, is_jain).get("food", [])
        
    def search_events(self, city: str, dates: str) -> list:
        return self.search_all_pois(city, dates=dates).get("events", [])
 
    def search_festivals(self, city: str, dates: str) -> list:
        return self.search_all_pois(city, dates=dates).get("festivals", [])
 
    def search_instagrammable(self, city: str) -> list:
        return self.search_all_pois(city).get("instagrammable", [])

    def _execute_search(self, query: str, city: str) -> list:
        base_lat, base_lon = MOCK_COORDS.get(city.strip().title(), [15.0, 75.0])
        rapidapi_key = os.getenv("RAPIDAPI_KEY")
        
        # Check if it's a combined search
        is_combined = sum(1 for kw in ["attractions", "food", "events", "festivals", "instagrammable"] if kw in query.lower()) > 1
        
        if rapidapi_key:
             if is_combined:
                  # Merge attractions and food for RapidAPI
                  results = self._fetch_rapidapi_poi("attractions", city, base_lat, base_lon, rapidapi_key)
                  results.extend(self._fetch_rapidapi_poi("food", city, base_lat, base_lon, rapidapi_key))
                  # Instagrammable spots from fallback (festivals now handled by EventsSearchAgent)
                  from agents.fallback import FallbackAgent
                  fallback = FallbackAgent()
                  results.extend(fallback.get_instagrammable(city))
                  return results
             if "instagram" in query.lower() or "photo" in query.lower():
                 from agents.fallback import FallbackAgent
                 return FallbackAgent().get_instagrammable(city)
             return self._fetch_rapidapi_poi(query, city, base_lat, base_lon, rapidapi_key)

        if not self.client:
            from agents.fallback import FallbackAgent
            fallback = FallbackAgent()
            if is_combined:
                # Merge multiple fallback categories (festivals now handled by EventsSearchAgent)
                results = []
                results.extend(fallback.get_attractions(city))
                results.extend(fallback.get_food(city, is_veg="veg" in query.lower(), is_jain="jain" in query.lower()))
                results.extend(fallback.get_instagrammable(city))
                return results
            if "instagram" in query.lower() or "photo" in query.lower(): return fallback.get_instagrammable(city)
            elif "festivals" in query.lower() or "celebration" in query.lower(): return fallback.get_festivals(city)
            elif "food" in query.lower(): return fallback.get_food(city, is_veg="veg" in query.lower(), is_jain="jain" in query.lower())
            else: return fallback.get_attractions(city)
            
        try:
            response = self.client.search(query=query, search_depth="advanced", max_results=30)
            results = response.get('results', [])
            if not results:
                from agents.fallback import FallbackAgent
                fallback = FallbackAgent()
                if is_combined:
                    results = []
                    results.extend(fallback.get_attractions(city))
                    results.extend(fallback.get_food(city))
                    results.extend(fallback.get_instagrammable(city))
                    return results
                if "instagram" in query.lower(): return fallback.get_instagrammable(city)
                if "food" in query.lower(): return fallback.get_food(city)
                return fallback.get_attractions(city)
                
            for res in results:
                res["latitude"] = base_lat + random.uniform(-0.02, 0.02)
                res["longitude"] = base_lon + random.uniform(-0.02, 0.02)
            return results
        except Exception as e:
            print(f"Tavily Search Error: {e}")
            from agents.fallback import FallbackAgent
            return FallbackAgent().get_attractions(city)


    def _fetch_rapidapi_poi(self, query: str, city: str, base_lat: float, base_lon: float, rapidapi_key: str) -> list:
        import requests
        try:
            url_loc = 'https://travel-advisor.p.rapidapi.com/locations/search'
            headers = {'x-rapidapi-key': rapidapi_key, 'x-rapidapi-host': 'travel-advisor.p.rapidapi.com'}
            res_loc = requests.get(url_loc, headers=headers, params={'query': city, 'limit': 1})
            loc_data = res_loc.json()
            loc_id = loc_data.get('data', [{}])[0].get('result_object', {}).get('location_id') if loc_data.get('data') else None
            if not loc_id:
                from agents.fallback import FallbackAgent
                return FallbackAgent().get_attractions(city)
            endpoint = 'restaurants/list' if 'food' in query.lower() else 'attractions/list'
            url_poi = f'https://travel-advisor.p.rapidapi.com/{endpoint}'
            res_poi = requests.get(url_poi, headers=headers, params={'location_id': loc_id, 'currency': 'INR', 'limit': 5})
            poi_data = res_poi.json()
            results = []
            if poi_data.get('data'):
                for item in poi_data['data']:
                    if not item.get('name'): continue
                    p_lvl = item.get('price_level', '$$')
                    p_est = 500 if p_lvl == '$' else (1500 if p_lvl == '$$' else 3100)
                    results.append({
                        "title": item.get('name'),
                        "content": item.get('description', f"Rating: {item.get('rating', '4.0')}/5"),
                        "url": item.get('web_url', f"https://www.tripadvisor.com/Search?q={item.get('name')}"),
                        "latitude": float(item.get('latitude', base_lat)),
                        "longitude": float(item.get('longitude', base_lon)),
                        "price": p_est
                    })
            return results if results else self._basic_fallback(city)
        except Exception as e:
            print(f"RapidAPI ERROR: {e}")
            return self._basic_fallback(city)

    def _basic_fallback(self, city: str):
        from agents.fallback import FallbackAgent
        return FallbackAgent().get_attractions(city)
