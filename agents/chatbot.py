import os
import json
from dotenv import load_dotenv
from core.cache import get_cached_data, set_cached_data

load_dotenv()

class ChatbotAgent:
    # Ordered fallback chain of Gemini models to try when primary is rate-limited
    GEMINI_FALLBACK_MODELS = [
        "gemini-2.5-flash-lite",
        "gemini-2.5-flash",
        "gemini-2.0-flash",
        "gemini-2.0-flash-lite",
    ]

    def __init__(self, model=None):
        self.google_api_key = os.getenv("GOOGLE_API_KEY")
        self.model_name = model or os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite")
        self.openai_api_key = os.getenv("OPENAI_API_KEY")
        
        # Initialize Gemini if key is present
        self.gemini_client = None
        if self.google_api_key:
            try:
                from google import genai
                self.gemini_client = genai.Client(api_key=self.google_api_key)
            except Exception:
                pass

        # Initialize OpenAI Cloud as middle fallback
        self.oai_cloud_client = None
        if self.openai_api_key:
            try:
                from openai import OpenAI
                self.oai_cloud_client = OpenAI(api_key=self.openai_api_key)
            except Exception:
                pass

        # Initialize local LLM as last resort fallback
        self.oai_api_key = os.getenv("LLM_STUDIO_API_KEY", "lm-studio")
        self.oai_base_url = os.getenv("LLM_STUDIO_BASE_URL", "http://localhost:1234/v1")
        self.oai_model = os.getenv("LLM_STUDIO_MODEL", "google/gemma-3-1b")
        self.oai_client = None
        try:
            from openai import OpenAI
            self.oai_client = OpenAI(base_url=self.oai_base_url, api_key=self.oai_api_key)
        except Exception:
            pass
        
        self.kb_path = os.path.join(os.path.dirname(__file__), "..", "knowledge_base", "trip_info.json")
        self.knowledge_base = self._load_kb()

    def _load_kb(self):
        try:
            with open(self.kb_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading knowledge base: {e}")
            return {}

    def _retrieve_context(self, query, dest=None):
        """
        Hyper-Efficient RAG: Context-aware retrieval with destination boosting and stop-word filtering.
        """
        stop_words = {"the", "a", "an", "is", "are", "was", "were", "to", "for", "of", "in", "on", "at", "with"}
        query_words = set(w for w in query.lower().split() if w not in stop_words)
        candidates = []
        dest_lower = dest.lower() if dest else ""
        
        def calculate_advanced_score(text, item_dest=None):
            text_lower = text.lower()
            text_words = set(text_lower.replace('[', ' ').replace(']', ' ').replace(':', ' ').split())
            overlap = query_words.intersection(text_words)
            score = len(overlap)
            
            # Destination Boost (Critical for RAG Precision)
            if dest_lower and item_dest and dest_lower in item_dest.lower():
                score *= 5 
            elif dest_lower and dest_lower in text_lower:
                score *= 3
            return score

        # 1. Check Safety Rules
        for rule in self.knowledge_base.get("safety_rules", []):
            item_dest = rule.get('destination', '')
            content = f"[Safety - {item_dest}]: {', '.join(rule.get('tips', []))}"
            score = calculate_advanced_score(content, item_dest)
            if score > 0: candidates.append((content, score))

        # 2. Check Packing Lists
        for p_list in self.knowledge_base.get("packing_lists", []):
            item_cat = p_list.get('category', '')
            content = f"[Packing - {item_cat}]: {', '.join(p_list.get('items', []))}"
            score = calculate_advanced_score(content, item_cat)
            if score > 0: candidates.append((content, score))

        # 3. Check Emergency Contacts
        for contact in self.knowledge_base.get("emergency_contacts", []):
            item_dest = contact.get('destination', '')
            content = f"[Emergency - {item_dest}]: {contact}"
            score = calculate_advanced_score(content, item_dest)
            if score > 0: candidates.append((content, score))

        # 4. Check Visa Info
        for visa in self.knowledge_base.get("visa_info", []):
            item_route = visa.get('route', '')
            content = f"[Visa - {item_route}]: {visa.get('requirement')}"
            score = calculate_advanced_score(content, item_route)
            if score > 0: candidates.append((content, score))
        
        # Rank by score descending
        sorted_candidates = sorted(candidates, key=lambda x: x[1], reverse=True)
        return "\n".join([c[0] for c in sorted_candidates[:5]])

    def _build_trip_context(self, trip_context: dict) -> str:
        """Build a rich trip context string from the master itinerary for the LLM."""
        if not trip_context:
            return ""
        
        parts = []
        req = trip_context.get('request', {})
        parts.append(f"Destination: {req.get('destination', 'N/A')}")
        parts.append(f"Origin: {req.get('origin', 'N/A')}")
        parts.append(f"Dates: {req.get('start_date', '')} to {req.get('end_date', '')}")
        parts.append(f"Duration: {req.get('days', 0)} days")
        parts.append(f"Travelers: {req.get('travelers', 1)}")
        parts.append(f"Budget: INR {req.get('budget_limit', 'N/A')}")
        
        # Weather
        weather = trip_context.get('weather', {})
        forecasts = weather.get('forecasts', [])
        if forecasts:
            parts.append(f"Weather: {forecasts[0].get('weather', 'Unknown')} ({forecasts[0].get('temp', 'N/A')})")
        
        # Hotels per night
        nightly = trip_context.get('nightly_hotels', [])
        if nightly:
            parts.append("\nHotels per night:")
            for nh in nightly:
                h = nh.get('hotel', {})
                parts.append(f"  Night {nh.get('night')}: {h.get('name', 'Hotel')} - INR {h.get('price', 'N/A')}/night")
        
        # Transport options
        transport = trip_context.get('transport_options', [])
        if transport:
            parts.append("\nTransport options:")
            for t in transport[:3]:
                parts.append(f"  {t.get('provider', t.get('airline', 'Transport'))} - INR {t.get('price', 'N/A')} - {t.get('route', '')}")
        
        # Activities summary
        activities = trip_context.get('activities', {})
        if activities.get('attractions'):
            atts = [a.get('title', '') for a in activities['attractions'][:5]]
            parts.append(f"\nTop Attractions: {', '.join(atts)}")
        if activities.get('food'):
            foods = [f.get('title', '') for f in activities['food'][:4]]
            parts.append(f"Food Spots: {', '.join(foods)}")
        if activities.get('festivals'):
            fests = [f.get('title', '') for f in activities['festivals'][:3]]
            parts.append(f"Events/Festivals: {', '.join(fests)}")
        
        # Timeline summary (compact)
        timeline = trip_context.get('timeline', [])
        if timeline:
            parts.append("\nDay-by-day schedule:")
            current_day = ""
            for item in timeline:
                day = item.get('day', '')
                if day != current_day and item.get('type') != 'daily_summary':
                    current_day = day
                itype = item.get('type', '')
                if itype in ('day_header', 'daily_summary'):
                    continue
                parts.append(f"  [{day}] {item.get('time', '')} - {item.get('title', '')}")
        
        # Safety, Packing, Visa
        parts.append(f"\nVisa Info: {trip_context.get('visa_info', 'N/A')}")
        safety = trip_context.get('safety_tips', [])
        if safety:
            parts.append(f"Safety Tips: {'; '.join(safety[:3])}")
        packing = trip_context.get('packing_list', [])
        if packing:
            parts.append(f"Packing: {', '.join(packing[:8])}")
        
        # Emergency contacts
        ec = trip_context.get('emergency_contacts', {})
        if ec:
            parts.append(f"Emergency: Police={ec.get('police', '100')}, Ambulance={ec.get('ambulance', ec.get('medical', '102'))}, Universal={ec.get('universal', '112')}")
        
        # Airport info
        ai = trip_context.get('airport_info', {})
        if ai.get('dest_needs_transfer'):
            parts.append(f"Airport Note: {ai.get('dest_transfer_info', '')}")
        
        return "\n".join(parts)

    def get_safety_tips(self, destination):
        tips = self.knowledge_base.get("safety_rules", [])
        # Find specific then default
        dest_tips = next((t['tips'] for t in tips if t['destination'].lower() in destination.lower()), [])
        default_tips = next((t['tips'] for t in tips if t['destination'] == 'default'), [])
        return dest_tips or default_tips

    def get_packing_list(self, destination, weather_desc="", temp_str=""):
        p_lists = self.knowledge_base.get("packing_lists", [])
        items = set(next((l['items'] for l in p_lists if l['category'] == 'General'), []))
        
        # Add category specific items
        for l in p_lists:
            if any(word in destination.lower() for word in l['category'].lower().split()):
                items.update(l['items'])
        
        # Add weather specific items
        if any(w in weather_desc.lower() for w in ["rain", "storm", "drizzle", "cloudy"]):
            items.update(["Umbrella", "Rain Jacket", "Waterproof Cover"])
        
        # Add temperature specific items
        try:
            temp = float(temp_str.replace('°C', '').strip())
            if temp > 28:
                items.update(["Sunscreen", "Sunglasses", "Cotton Clothing", "Hat"])
            elif temp < 15:
                items.update(["Heavy Jacket", "Gloves", "Scarf", "Thermals"])
        except:
            pass
        
        return list(items)

    def get_emergency_contacts(self, destination):
        contacts = self.knowledge_base.get("emergency_contacts", [])
        dest_contacts = next((c for c in contacts if c['destination'].lower() in destination.lower()), 
                            next((c for c in contacts if c['destination'] == 'default'), {}))
        return dest_contacts

    def get_visa_info(self, origin, destination):
        info = self.knowledge_base.get("visa_info", [])
        # Check domestic
        if origin.lower() in ["india", "delhi", "mumbai", "chennai", "jaipur"] and \
           destination.lower() in ["india", "delhi", "mumbai", "chennai", "jaipur", "goa", "kerala"]:
            return next((v['requirement'] for v in info if "Domestic" in v['route']), "No visa required.")
        
        # Check specific routes
        for v in info:
            if origin.lower() in v['route'].lower() and destination.lower() in v['route'].lower():
                return v['requirement']
                
        return "Visa might be required. Please check official embassy websites for international travel."

    def chat(self, user_input, chat_history=[], trip_context=None):
        """
        Main chat method with 3-tier LLM fallback:
        1. Gemini (primary)
        2. OpenAI Cloud (middle fallback)
        3. Local LLM Studio (last resort)
        
        Includes enriched trip context and RAG knowledge.
        """
        # Extract destination for boosted RAG
        dest = trip_context.get('request', {}).get('destination') if trip_context else None
        rag_context = self._retrieve_context(user_input, dest=dest)
        
        # Build comprehensive trip context
        trip_details = self._build_trip_context(trip_context)
            
        # Optimization: If it's a very simple direct query matched in RAG, return it directly
        if len(rag_context.split('\n')) == 1 and rag_context and not chat_history:
             return f"According to our knowledge base: {rag_context}"

        system_prompt = f"""You are VoyagrBot's AI Travel Assistant. You have FULL access to the traveler's current trip plan.

CURRENT TRIP DETAILS:
{trip_details if trip_details else "No trip planned yet."}

KNOWLEDGE BASE CONTEXT:
{rag_context if rag_context else "No specific knowledge base match found."}

INSTRUCTIONS:
1. Answer questions about the planned trip accurately using the trip details above
2. For questions about hotels, transport, activities — reference the actual data from the trip plan
3. For safety, packing, visa, emergency — use the knowledge base context
4. For food/restaurant recommendations — reference the food spots in the itinerary
5. Be concise but informative. Use bullet points for lists.
6. If asked to change something (hotel, activity), explain what can be changed and suggest alternatives from the available options.
7. Always be helpful and travel-expert-like in tone."""

        messages = [{"role": "system", "content": system_prompt}]
        
        # Add a slice of recent history if provided
        for msg in chat_history[-5:]:
            messages.append(msg)
            
        messages.append({"role": "user", "content": user_input})

        # === TIER 1: Try Gemini First (with multi-model fallback) ===
        if self.gemini_client:
            from google import genai
            prompt_text = ""
            for msg in chat_history[-5:]:
                prompt_text += f"{msg['role'].capitalize()}: {msg['content']}\n\n"
            prompt_text += f"User: {user_input}\n"
            
            # Build ordered model list: configured model first, then fallbacks
            models_to_try = [self.model_name]
            for m in self.GEMINI_FALLBACK_MODELS:
                if m != self.model_name:
                    models_to_try.append(m)
            
            for model_name in models_to_try:
                try:
                    response = self.gemini_client.models.generate_content(
                        model=model_name,
                        contents=prompt_text,
                        config=genai.types.GenerateContentConfig(
                            system_instruction=system_prompt,
                        )
                    )
                    if response.text:
                        return response.text
                except Exception as e:
                    print(f"Chatbot Gemini Error ({model_name}): {e}")
                    continue  # Try next model in the fallback chain

        # === TIER 2: Try OpenAI Cloud ===
        if self.oai_cloud_client:
            try:
                response = self.oai_cloud_client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=messages,
                    temperature=0.7,
                    max_tokens=500,
                    timeout=15
                )
                if response.choices and response.choices[0].message.content:
                    return response.choices[0].message.content
            except Exception as e:
                print(f"Chatbot OpenAI Cloud Error: {e}")

        # === TIER 3: Fallback to Local LLM Studio ===
        if self.oai_client:
            try:
                response = self.oai_client.chat.completions.create(
                    model=self.oai_model,
                    messages=messages,
                    temperature=0.7,
                    timeout=10
                )
                if response.choices and response.choices[0].message.content:
                    return response.choices[0].message.content
            except Exception as e:
                print(f"Chatbot Local LLM Error: {e}")

        # === All LLMs failed — provide a helpful static response ===
        return self._static_fallback(user_input, trip_context, rag_context)

    def _static_fallback(self, query: str, trip_context: dict, rag_context: str) -> str:
        """Provide useful response even when all LLMs are unavailable."""
        query_lower = query.lower()
        
        if rag_context:
            return f"Based on our knowledge base:\n{rag_context}"
        
        if trip_context:
            dest = trip_context.get('request', {}).get('destination', 'your destination')
            
            if any(w in query_lower for w in ['hotel', 'stay', 'accommodation', 'sleep']):
                nightly = trip_context.get('nightly_hotels', [])
                if nightly:
                    lines = [f"🏨 Your hotel assignments for this trip:"]
                    for nh in nightly:
                        h = nh.get('hotel', {})
                        lines.append(f"  Night {nh['night']}: {h.get('name', 'Hotel')} — INR {h.get('price', 'N/A')}/night")
                    return "\n".join(lines)
            
            if any(w in query_lower for w in ['pack', 'bring', 'carry', 'luggage']):
                packing = trip_context.get('packing_list', [])
                if packing:
                    return f"🧳 Packing list for {dest}:\n" + "\n".join(f"  ✔ {item}" for item in packing)
            
            if any(w in query_lower for w in ['safe', 'danger', 'precaution', 'careful']):
                tips = trip_context.get('safety_tips', [])
                if tips:
                    return f"🛡️ Safety tips for {dest}:\n" + "\n".join(f"  ⚠ {tip}" for tip in tips)
            
            if any(w in query_lower for w in ['emergency', 'help', 'police', 'hospital', 'ambulance']):
                ec = trip_context.get('emergency_contacts', {})
                return f"🚨 Emergency contacts for {dest}:\n  Police: {ec.get('police', '100')}\n  Medical: {ec.get('ambulance', ec.get('medical', '102'))}\n  Universal: {ec.get('universal', '112')}"
            
            if any(w in query_lower for w in ['food', 'eat', 'restaurant', 'dine', 'cuisine']):
                foods = trip_context.get('activities', {}).get('food', [])
                if foods:
                    return f"🍽️ Food spots in {dest}:\n" + "\n".join(f"  • {f.get('title', 'Restaurant')}" for f in foods[:5])
        
        return "I'm having trouble connecting to my AI services right now. Please try again in a moment, or use the quick-access buttons (Packing, Safety, Food, Emergency) above."
