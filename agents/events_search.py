"""
Events Search Agent for VoyagrBot.

Performs targeted Tavily web searches to find real events, festivals,
concerts, and celebrations happening in a destination city during
specific travel dates.
"""

import os
import json
from core.cache import get_cached_data, set_cached_data
from dotenv import load_dotenv

load_dotenv()


class EventsSearchAgent:
    def __init__(self):
        self.tavily_key = os.getenv("TAVILY_API_KEY")
        self.google_api_key = os.getenv("GOOGLE_API_KEY")
        self.model_name = os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite")

        # Initialize Gemini
        self.gemini_client = None
        if self.google_api_key:
            try:
                from google import genai
                self.gemini_client = genai.Client(api_key=self.google_api_key)
            except Exception:
                pass

        # Fallback OpenAI/LM Studio
        self.oai_api_key = os.getenv("LLM_STUDIO_API_KEY", "lm-studio")
        self.oai_base_url = os.getenv("LLM_STUDIO_BASE_URL", "http://localhost:1234/v1")
        self.oai_model = os.getenv("LLM_STUDIO_MODEL", "google/gemma-3-1b")
        try:
            from openai import OpenAI
            self.oai_client = OpenAI(base_url=self.oai_base_url, api_key=self.oai_api_key)
        except Exception:
            self.oai_client = None

    def search_events(self, city: str, start_date: str, end_date: str) -> list:
        """
        Search for real events, festivals, and celebrations in a city during
        the given travel date range using Tavily web search + LLM extraction.

        Returns a list of dicts with keys:
            title, content, url, category, date_info
        """
        cached = get_cached_data("events_live", city, start_date, end_date)
        if cached:
            return cached

        if not self.tavily_key:
            print("EventsSearch: No Tavily API key. Returning empty list.")
            return []

        # Perform multiple targeted searches for better coverage
        search_results = []

        try:
            from tavily import TavilyClient
            tavily = TavilyClient(api_key=self.tavily_key)

            # Search 1: Events and festivals
            query1 = f"events festivals celebrations happening in {city} during {start_date} to {end_date} 2026"
            try:
                res1 = tavily.search(query=query1, search_depth="advanced", max_results=5)
                search_results.extend(res1.get('results', []))
            except Exception as e:
                print(f"EventsSearch query 1 error: {e}")

            # Search 2: Concerts, exhibitions, local happenings
            query2 = f"concerts exhibitions markets cultural events in {city} {start_date} {end_date}"
            try:
                res2 = tavily.search(query=query2, search_depth="basic", max_results=5)
                search_results.extend(res2.get('results', []))
            except Exception as e:
                print(f"EventsSearch query 2 error: {e}")

            # Search 3: Trending things to do
            query3 = f"what's happening in {city} this week trending things to do {start_date}"
            try:
                res3 = tavily.search(query=query3, search_depth="basic", max_results=3)
                search_results.extend(res3.get('results', []))
            except Exception as e:
                print(f"EventsSearch query 3 error: {e}")

        except Exception as e:
            print(f"EventsSearch Tavily initialization error: {e}")
            return []

        if not search_results:
            return []

        # Deduplicate by URL
        seen_urls = set()
        unique_results = []
        for r in search_results:
            url = r.get('url', '')
            if url not in seen_urls:
                seen_urls.add(url)
                unique_results.append(r)

        # Use LLM to extract structured event data
        events = self._extract_events_with_llm(unique_results, city, start_date, end_date)

        if events:
            set_cached_data("events_live", events, city, start_date, end_date)

        return events

    def _extract_events_with_llm(self, search_results: list, city: str, start_date: str, end_date: str) -> list:
        """Use LLM to extract structured event data from raw search results."""

        # Prepare context for LLM
        simplified = []
        for r in search_results[:12]:  # Limit to 12 results for LLM context
            simplified.append({
                "title": r.get('title', ''),
                "content": r.get('content', '')[:300],  # Truncate long content
                "url": r.get('url', '')
            })

        context = json.dumps(simplified, indent=2)

        system_prompt = f"""You are an event extraction AI for VoyagrBot travel planner.
From the search results about {city} during {start_date} to {end_date}, extract REAL events, festivals, celebrations, concerts, exhibitions, or cultural happenings.

CRITICAL RULES:
1. Only extract REAL events with actual names - do NOT invent or fabricate events
2. If the search results don't contain any real events, return an empty list
3. Each event must have a real title from the search results
4. Prefer events with specific dates that fall within or near the travel window

Return ONLY valid JSON in this format:
{{
  "events": [
    {{
      "title": "Exact Real Event Name",
      "content": "Brief 1-2 sentence description of the event (max 30 words)",
      "url": "actual_url_from_search_results",
      "category": "festival|concert|exhibition|market|cultural|sports|food_festival|other",
      "date_info": "Any date information available, or 'During travel dates'"
    }}
  ]
}}

Extract up to 6 events maximum. If no real events are found, return {{"events": []}}"""

        events = None

        GEMINI_FALLBACK_MODELS = ["gemini-2.5-flash-lite", "gemini-2.5-flash", "gemini-2.0-flash", "gemini-2.0-flash-lite"]
        # Try Gemini first (with model fallback)
        if self.gemini_client:
            from google import genai
            models_to_try = [self.model_name] + [m for m in GEMINI_FALLBACK_MODELS if m != self.model_name]
            for model_name in models_to_try:
                try:
                    response = self.gemini_client.models.generate_content(
                        model=model_name,
                        contents=f"Search results for events in {city}:\n{context}",
                        config=genai.types.GenerateContentConfig(
                            system_instruction=system_prompt,
                            response_mime_type="application/json",
                        )
                    )
                    text = response.text.replace('```json', '').replace('```', '').strip()
                    data = json.loads(text, strict=False)
                    events = data.get('events', [])
                    if events is not None:
                        break
                except Exception as e:
                    print(f"EventsSearch Gemini extraction error ({model_name}): {e}")
                    continue

        # Fallback to OpenAI/LM Studio
        if events is None and self.oai_client:
            try:
                response = self.oai_client.chat.completions.create(
                    model=self.oai_model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": f"Search results for events in {city}:\n{context}"}
                    ],
                    temperature=0,
                    timeout=12
                )
                raw = response.choices[0].message.content
                # Clean potential markdown wrapping
                raw = raw.replace('```json', '').replace('```', '').strip()
                data = json.loads(raw, strict=False)
                events = data.get('events', [])
            except Exception as e:
                print(f"EventsSearch LLM fallback error: {e}")
                events = []

        if events is None:
            events = []

        # Validate and clean results
        cleaned = []
        for event in events:
            if isinstance(event, dict) and event.get('title'):
                cleaned.append({
                    "title": event.get('title', 'Event'),
                    "content": event.get('content', 'An exciting event happening in the city.'),
                    "url": event.get('url', '#'),
                    "category": event.get('category', 'other'),
                    "date_info": event.get('date_info', 'During travel dates'),
                })

        return cleaned[:6]  # Max 6 events
