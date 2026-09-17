from agents.master_planner import MasterPlannerAgent
from agents.search_poi import SearchPOIAgent
from agents.logistics import LogisticsAgent
from agents.climate import ClimateAgent
from agents.budget_itinerary import BudgetItineraryAgent
from agents.transport_ground import GroundTransportAgent
from agents.chatbot import ChatbotAgent
from agents.airport_resolver import resolve_airports
from agents.events_search import EventsSearchAgent
import concurrent.futures
import random
from core.cache import get_cached_data, set_cached_data


class TripManager:
    def __init__(self):
        self._master_planner = None
        self._search_poi = None
        self._logistics = None
        self._climate = None
        self._budget_itinerary = None
        self._ground_transport = None
        self._rag_engine = None
        self._events_search = None

    @property
    def master_planner(self):
        if self._master_planner is None:
            self._master_planner = MasterPlannerAgent()
        return self._master_planner

    @property
    def search_poi(self):
        if self._search_poi is None:
            self._search_poi = SearchPOIAgent()
        return self._search_poi

    @property
    def logistics(self):
        if self._logistics is None:
            self._logistics = LogisticsAgent()
        return self._logistics

    @property
    def climate(self):
        if self._climate is None:
            self._climate = ClimateAgent()
        return self._climate

    @property
    def budget_itinerary(self):
        if self._budget_itinerary is None:
            self._budget_itinerary = BudgetItineraryAgent()
        return self._budget_itinerary

    @property
    def ground_transport(self):
        if self._ground_transport is None:
            self._ground_transport = GroundTransportAgent()
        return self._ground_transport

    @property
    def rag_engine(self):
        if self._rag_engine is None:
            self._rag_engine = ChatbotAgent()
        return self._rag_engine

    @property
    def events_search(self):
        if self._events_search is None:
            self._events_search = EventsSearchAgent()
        return self._events_search
        
    def process_request(self, user_input: str, is_veg: bool = False, is_jain: bool = False, origin: str="DEL", destination: str="CDG", start_date: str="2026-06-01", end_date: str="2026-06-05", days: int=3, travelers: int=1, preferences: str="", budget: int=50000) -> dict:
        """
        Orchestrates the entire planning process with maximum parallelism.
        """
        # 0. Check High-Level Cache
        cached_master = get_cached_data("master_plan", user_input, origin, destination, start_date, end_date, days, travelers, budget, is_veg, is_jain)
        if cached_master:
            return cached_master

        # 1. Resolve Airports (smart - handles cities without airports)
        airport_info = resolve_airports(origin, destination)
        iata_origin = airport_info["origin_iata"]
        iata_dest = airport_info["dest_iata"]

        # 2. Prepare Data structure
        parsed_data = {
            "destination": destination,
            "origin": origin,
            "start_date": start_date,
            "end_date": end_date,
            "days": days,
            "travelers": travelers,
            "budget_limit": budget,
            "interests": [p.strip() for p in preferences.split(',')] if preferences else ["sightseeing", "food"]
        }

        # 3. Parallel Research Burst — Phase 1: Get routing + POIs first
        with concurrent.futures.ThreadPoolExecutor(max_workers=12) as executor:
            f_weather = executor.submit(self.climate.get_forecast, destination)
            f_poi = executor.submit(self.search_poi.search_all_pois, city=destination, is_veg=is_veg, is_jain=is_jain, dates=start_date)
            f_routing = executor.submit(self.master_planner.generate_routing_guide, origin, destination, airport_info)
            f_events = executor.submit(self.events_search.search_events, destination, start_date, end_date)

            # Wait for routing to get real distance
            routing_guide = f_routing.result()
            real_distance_km = routing_guide.get('distance_km', 500)
            
            # Now launch transport searches with real distance
            f_flights = executor.submit(
                self.logistics.get_flights,
                origin=iata_origin,
                destination=iata_dest,
                departure_date=start_date,
                return_date=end_date,
                adults=travelers,
                origin_name=airport_info["origin_airport_city"],
                dest_name=airport_info["dest_airport_city"]
            )
            f_ground = executor.submit(
                self.ground_transport.get_options,
                real_distance_km,
                origin_city=origin.title(),
                dest_city=destination.title(),
                travel_date=start_date
            )
            
            # Get local transport estimate for the destination city
            f_local_transport = executor.submit(
                self.ground_transport.get_local_transport_estimate,
                destination,
                days
            )
            
            # Wait for POI data so we can pass it to hotel search
            poi_data = f_poi.result()
            
            # Launch hotel search with nearby attractions for location-awareness
            attractions_for_hotels = poi_data.get('attractions', [])
            f_hotels = executor.submit(
                self.logistics.get_hotels,
                cityCode=iata_dest,
                city_name=destination,
                check_in=start_date,
                check_out=end_date,
                days=days,
                nearby_attractions=attractions_for_hotels
            )

            # Collect remaining results
            weather_data = f_weather.result()
            flight_data = f_flights.result()
            hotel_data = f_hotels.result()
            ground_data = f_ground.result()
            local_transport = f_local_transport.result()
            live_events = f_events.result()

        # 4. Merge live events into POI data
        if live_events:
            # Replace fallback/mock festivals with real events
            poi_data['festivals'] = live_events
            # Also enrich events category
            if not poi_data.get('events') or all(
                'example.com' in str(e.get('url', '')) for e in poi_data.get('events', [])
            ):
                poi_data['events'] = live_events

        # 5. Transport Processing — include all modes
        transport_options = []
        if flight_data:
            for flight in flight_data:
                if isinstance(flight, dict) and ('airline' in flight or 'mode' in flight):
                    flight['mode'] = flight.get('mode', 'Flight')
                    transport_options.append(flight)
        
        # Add ground transport options
        for g_opt in ground_data:
            g_opt['mode'] = g_opt.get('mode', 'Ground')
            transport_options.append(g_opt)
        
        # Filter by budget (45% max for transport — slightly higher to account for round trip)
        max_trans_budget = budget * 0.45
        budget_filtered = [opt for opt in transport_options if opt.get('price', 0) <= max_trans_budget]
        if budget_filtered:
            transport_options = budget_filtered
        elif not transport_options:
            transport_options = [{"mode": "Budget Option", "provider": "Generic", "price": int(max_trans_budget*0.5), "currency": "INR", "route": "Standard Route"}]

        # 6. Accommodation Processing — ensure enough unique hotels for all nights
        max_hotel_budget_per_night = (budget * 0.3) / max(days, 1)
        filtered_hotels = [h for h in hotel_data if h.get('price', 0) <= max_hotel_budget_per_night] if hotel_data else []
        
        if len(filtered_hotels) < 2:
            # If budget filter removed too many, use all hotels
            filtered_hotels = hotel_data if hotel_data else []
        
        if not filtered_hotels:
            filtered_hotels = [
                {"name": f"Comfort Stay {destination} - Central", "area": "City Center", "price": int(max_hotel_budget_per_night*0.5), "safety_score": 88, "rating": 4.2, "data_source": "fallback",
                 "url": f"https://www.google.com/travel/hotels/{destination.replace(' ', '+')}",
                 "map_url": f"https://www.google.com/maps/search/hotels+{destination.replace(' ', '+')}",
                 "booking_search_url": f"https://www.booking.com/searchresults.html?ss={destination.replace(' ', '+')}"},
                {"name": f"Budget Inn {destination} - Station Area", "area": "Station Area", "price": int(max_hotel_budget_per_night*0.35), "safety_score": 82, "rating": 3.8, "data_source": "fallback",
                 "url": f"https://www.google.com/travel/hotels/{destination.replace(' ', '+')}",
                 "map_url": f"https://www.google.com/maps/search/budget+hotels+{destination.replace(' ', '+')}",
                 "booking_search_url": f"https://www.booking.com/searchresults.html?ss={destination.replace(' ', '+')}"},
            ]
        
        # Smart nightly hotel assignment — assign different hotels near different areas
        nightly_hotels = self._assign_nightly_hotels(filtered_hotels, poi_data, days)

        # 7. Calculate accurate budget breakdown
        # Transport: cheapest option × 2 for round trip (or use trip_type if available)
        cheapest_transport = min(transport_options, key=lambda x: x.get('price', float('inf')))
        transport_price = cheapest_transport.get('price', 0)
        is_round_trip = cheapest_transport.get('trip_type', '') == 'Round Trip'
        round_trip_transport = transport_price if is_round_trip else transport_price * 2
        
        # Stay: sum of all nightly hotel prices
        total_stay_cost = sum(nh['hotel'].get('price', 0) for nh in nightly_hotels)
        
        # Local transport
        local_transport_total = local_transport.get('total_estimate', 0)
        
        # Remaining budget for activities + food
        remaining_for_daily = budget - round_trip_transport - total_stay_cost - local_transport_total
        daily_allowance = remaining_for_daily / days if remaining_for_daily > 0 else 1000

        # 8. Synthesis
        itinerary = self.budget_itinerary.synthesize_itinerary(
            request_data=parsed_data,
            flight_data=flight_data,
            hotel_data=filtered_hotels,
            poi_data=poi_data,
            weather_data=weather_data,
            daily_allowance=daily_allowance,
            local_transport=local_transport,
            nightly_hotels=nightly_hotels,
        )

        # 9. Final RAG Enrichment (Fast local JSON/logic)
        visa_info = self.rag_engine.get_visa_info(origin, destination)
        
        # Safe weather check
        weather_info = weather_data.get('forecasts', [{}])[0] if weather_data.get('forecasts') else {}
        weather_desc = weather_info.get('weather', 'Clear')
        temp_str = weather_info.get('temp', '25')
        packing_list = self.rag_engine.get_packing_list(destination, weather_desc, temp_str)
        
        safety_tips = self.rag_engine.get_safety_tips(destination)
        emergency_contacts = self.rag_engine.get_emergency_contacts(destination)

        master_itinerary = {
            "request": parsed_data,
            "transport_options": transport_options,
            "accommodations": filtered_hotels,
            "nightly_hotels": nightly_hotels,
            "activities": poi_data,
            "weather": weather_data,
            "timeline": itinerary,
            "visa_info": visa_info,
            "packing_list": packing_list,
            "safety_tips": safety_tips,
            "emergency_contacts": emergency_contacts,
            "routing_guide": routing_guide,
            "total_budget": budget,
            "airport_info": airport_info,
            "local_transport": local_transport,
            # Pre-calculated budget breakdown for accurate analytics
            "budget_breakdown": {
                "round_trip_transport": round_trip_transport,
                "total_stay": total_stay_cost,
                "local_transport": local_transport_total,
                "daily_allowance": daily_allowance,
                "is_round_trip": is_round_trip,
            }
        }
        
        res = {
            "parsed_request": parsed_data,
            "itinerary": itinerary,
            "raw_weather": weather_data,
            "master_itinerary": master_itinerary
        }
        set_cached_data("master_plan", res, user_input, origin, destination, start_date, end_date, days, travelers, budget, is_veg, is_jain)
        return res

    def _assign_nightly_hotels(self, hotel_data: list, poi_data: dict, days: int) -> list:
        """
        Smart hotel assignment: assign different hotels for different nights.
        Tries to vary hotels so each night has a unique stay near relevant attractions.
        Excludes travel days (first and last) from stay count and assigns stays for touring days.
        """
        nightly_hotels = []
        attractions = poi_data.get('attractions', [])
        
        # Number of nights = days - 1 (last day is return/departure)
        num_nights = max(days - 1, 1)
        
        if not hotel_data:
            return nightly_hotels
        
        # Deduplicate hotels by name
        seen_names = set()
        unique_hotels = []
        for h in hotel_data:
            name = h.get('name', '')
            if name not in seen_names:
                seen_names.add(name)
                unique_hotels.append(h)
        
        # Provide ALL hotel options for EACH night so the user can choose per night
        for night_idx in range(num_nights):
            # Find the day's primary attraction for proximity info
            nearby_attraction = None
            if night_idx < len(attractions):
                nearby_attraction = attractions[night_idx].get('title', '')
            
            # Provide all unique hotels as choices for this night
            # Mark a recommended default (different per night for variety)
            default_idx = night_idx % len(unique_hotels)
            
            nightly_hotels.append({
                "night": night_idx + 1,
                "hotels": unique_hotels,  # ALL hotels available for this night
                "default_hotel_idx": default_idx,  # Pre-selected default
                "hotel": unique_hotels[default_idx],  # Default selection (backward compat)
                "nearby_attraction": nearby_attraction or f"City Center"
            })
        
        return nightly_hotels

