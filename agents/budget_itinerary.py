class BudgetItineraryAgent:
    def _fix_url(self, url: str, title: str, dest_city: str) -> str:
        """Replace example.com/broken URLs with Google Maps search links."""
        if not url or url == '#' or 'example.com' in str(url):
            search_term = f"{title} {dest_city}".replace(' ', '+')
            return f"https://www.google.com/maps/search/{search_term}"
        return url

    def synthesize_itinerary(self, request_data: dict, flight_data: list, hotel_data: list, poi_data: dict, weather_data: dict, daily_allowance: float = 4000.0, local_transport: dict = None, nightly_hotels: list = None) -> list:
        """
        Synthesizes all gathered data into a structured Day-by-Day timeline.
        Now includes:
        - Hotel check-in per night using smart nightly_hotels assignment
        - Local transport items (morning cab, afternoon auto, evening transport)
        - Accurate cost estimates based on daily allowance
        - Website and map links for all items
        """
        itinerary = []
        days = request_data.get('days', 3)
        start_date = request_data.get('start_date', 'Day 1')
        dest_city = request_data.get('destination', '')
        
        # Determine POI pools
        attractions = poi_data.get('attractions', [])
        food = poi_data.get('food', [])
        festivals = poi_data.get('festivals', [])
        events = poi_data.get('events', [])
        photo_spots = poi_data.get('instagrammable', [])
        
        has_bad_weather = weather_data.get('has_bad_weather', False)
        forecasts = weather_data.get('forecasts', [])
        
        # Local transport breakdown per day
        local_daily = {}
        if local_transport:
            local_daily = local_transport.get('breakdown', {})
        daily_local_total = local_transport.get('daily_estimate', 500) if local_transport else 500
        
        # General Warnings
        if has_bad_weather:
            itinerary.append({
                 "type": "note",
                 "title": "Weather Alert",
                 "details": "Rain/Storm expected during your trip. Prioritizing indoor POIs.",
                 "color": "red"
            })
            
        # Build Day-by-Day Schedule
        for day in range(1, days + 1):
            daily_weather = forecasts[day - 1] if day - 1 < len(forecasts) else (forecasts[0] if forecasts else {})
            weather_desc = daily_weather.get('weather', 'Clear')
            temp_str = daily_weather.get('temp', '25.0°C')
            daily_expense = 0
            scale_factor = daily_allowance / 4000.0 if daily_allowance > 0 else 0.1
            
            # Setup Day Header
            day_label = ""
            if day == 1:
                day_label = "Arrival & Exploration"
            elif day == days:
                day_label = "Final Day & Departure"
            else:
                day_label = f"Full Day Exploration"
            
            itinerary.append({
                "day": f"Day {day}",
                "time": "08:00 AM",
                "type": "day_header",
                "title": f"Day {day} — {day_label}",
                "details": f"Weather: {weather_desc} ({temp_str})",
                "cost_est": 0,
                "color": "gray"
            })
            
            # --- Morning Local Transport (Cab/Auto to first destination) ---
            morning_transport_cost = local_daily.get('morning_cab', round(daily_local_total * 0.35))
            daily_expense += morning_transport_cost
            itinerary.append({
                "day": f"Day {day}",
                "time": "08:00 AM - 08:30 AM",
                "type": "transport_local",
                "title": f"🚕 Cab/Auto to Day {day} Destination",
                "details": f"Local transport from hotel to first stop. Estimated fare: ₹{morning_transport_cost}",
                "url": f"https://www.google.com/maps/dir//{dest_city.replace(' ', '+')}",
                "cost_est": morning_transport_cost,
                "color": "gray"
            })
            
            # --- Breakfast ---
            breakfast_item = None
            if food:
                 breakfast_item = food[(day * 4 - 4) % len(food)]
            
            if breakfast_item:
                cost = int(250 * scale_factor)
                daily_expense += cost
                itinerary.append({
                    "day": f"Day {day}",
                    "time": "08:30 AM - 09:30 AM",
                    "type": "food",
                    "title": f"Breakfast at {breakfast_item.get('title', 'Local Cafe')}",
                    "details": breakfast_item.get('content', ''),
                    "url": self._fix_url(breakfast_item.get('url', ''), breakfast_item.get('title', ''), dest_city),
                    "cost_est": cost,
                    "color": "red"
                })

            # --- Morning: Attraction or Photo Spot ---
            morning_item = None
            if len(attractions) >= day:
                morning_item = attractions[day - 1]
            elif photo_spots:
                morning_item = photo_spots[(day - 1) % len(photo_spots)]
                
            if morning_item:
                cost = int(500 * scale_factor)
                daily_expense += cost
                itinerary.append({
                    "day": f"Day {day}",
                    "time": "10:00 AM - 01:00 PM",
                    "type": "attraction",
                    "title": morning_item.get('title', 'Local Sights'),
                    "details": morning_item.get('content', ''),
                    "url": self._fix_url(morning_item.get('url', ''), morning_item.get('title', ''), dest_city),
                    "cost_est": cost,
                    "color": "blue"
                })

            # --- Lunch ---
            lunch_item = None
            if food:
                lunch_item = food[(day * 4 - 3) % len(food)]
                
            if lunch_item:
                cost = int(350 * scale_factor)
                daily_expense += cost
                itinerary.append({
                    "day": f"Day {day}",
                    "time": "01:30 PM - 03:00 PM",
                    "type": "food",
                    "title": f"Lunch at {lunch_item.get('title', 'Local Diner')}",
                    "details": lunch_item.get('content', ''),
                    "url": self._fix_url(lunch_item.get('url', ''), lunch_item.get('title', ''), dest_city),
                    "cost_est": cost,
                    "color": "red"
                })
            
            # --- Afternoon Local Transport ---
            afternoon_transport_cost = local_daily.get('afternoon_auto', round(daily_local_total * 0.30))
            daily_expense += afternoon_transport_cost
            itinerary.append({
                "day": f"Day {day}",
                "time": "03:00 PM - 03:30 PM",
                "type": "transport_local",
                "title": f"🛺 Auto/Metro to Afternoon Spots",
                "details": f"Local transport between attractions. Estimated fare: ₹{afternoon_transport_cost}",
                "url": f"https://www.google.com/maps/dir//{dest_city.replace(' ', '+')}",
                "cost_est": afternoon_transport_cost,
                "color": "gray"
            })
                
            # --- Afternoon Snacks ---
            snack_item = None
            if food:
                snack_item = food[(day * 4 - 2) % len(food)]
                
            if snack_item:
                cost = int(150 * scale_factor)
                daily_expense += cost
                itinerary.append({
                    "day": f"Day {day}",
                    "time": "04:00 PM - 04:45 PM",
                    "type": "food",
                    "title": f"Snacks/Coffee at {snack_item.get('title', 'Local Bakery')}",
                    "details": snack_item.get('content', ''),
                    "url": self._fix_url(snack_item.get('url', ''), snack_item.get('title', ''), dest_city),
                    "cost_est": cost,
                    "color": "red"
                })

            # --- Photo / Instagrammable Spot ---
            if photo_spots:
                spot_item = photo_spots[(day - 1) % len(photo_spots)]
                itinerary.append({
                    "day": f"Day {day}",
                    "time": "05:00 PM - 05:45 PM",
                    "type": "attraction",
                    "title": f"Photo Walk: {spot_item.get('title', 'Scenic Spot')}",
                    "details": spot_item.get('content', ''),
                    "url": self._fix_url(spot_item.get('url', ''), spot_item.get('title', ''), dest_city),
                    "cost_est": 0,
                    "color": "purple"
                })

            # --- Evening: Event or Festival ---
            evening_item = None
            if len(festivals) >= day:
                evening_item = festivals[day - 1]
            elif len(events) >= day:
                evening_item = events[day - 1]
                
            if evening_item:
                cost = int(800 * scale_factor)
                daily_expense += cost
                itinerary.append({
                    "day": f"Day {day}",
                    "time": "06:00 PM - 08:00 PM",
                    "type": "event",
                    "title": evening_item.get('title', 'Evening Event'),
                    "details": evening_item.get('content', ''),
                    "url": self._fix_url(evening_item.get('url', ''), evening_item.get('title', ''), dest_city),
                    "cost_est": cost,
                    "color": "green"
                })
            
            # --- Evening Local Transport (return to hotel) ---
            evening_transport_cost = local_daily.get('evening_transport', round(daily_local_total * 0.35))
            daily_expense += evening_transport_cost
            itinerary.append({
                "day": f"Day {day}",
                "time": "08:00 PM - 08:30 PM",
                "type": "transport_local",
                "title": f"🚕 Cab back to Hotel",
                "details": f"Return transport to accommodation. Estimated fare: ₹{evening_transport_cost}",
                "url": f"https://www.google.com/maps/dir//{dest_city.replace(' ', '+')}",
                "cost_est": evening_transport_cost,
                "color": "gray"
            })
                
            # --- Dinner ---
            dinner_item = None
            if food:
                dinner_item = food[(day * 4 - 1) % len(food)]
                
            if dinner_item:
                cost = int(400 * scale_factor)
                daily_expense += cost
                itinerary.append({
                    "day": f"Day {day}",
                    "time": "08:30 PM - 10:00 PM",
                    "type": "food",
                    "title": f"Dinner at {dinner_item.get('title', 'Fine Dining')}",
                    "details": dinner_item.get('content', ''),
                    "url": self._fix_url(dinner_item.get('url', ''), dinner_item.get('title', ''), dest_city),
                    "cost_est": cost,
                    "color": "red"
                })

            # --- Hotel Check-in for the Night ---
            # Use the smart nightly_hotels assignment if available (excludes last night)
            night_hotel = None
            if nightly_hotels and day <= len(nightly_hotels):
                nh_entry = nightly_hotels[day - 1]
                night_hotel = nh_entry.get('hotel', {})
                nearby_info = nh_entry.get('nearby_attraction', '')
            elif hotel_data:
                night_hotel = hotel_data[(day - 1) % len(hotel_data)]
                nearby_info = ''
            
            if night_hotel and day < days:  # No check-in on last day (departure)
                hotel_cost = night_hotel.get('price', 0)
                hotel_name = night_hotel.get('name', f'Hotel in {dest_city}')
                hotel_area = night_hotel.get('area', '')
                hotel_url = night_hotel.get('url', '')
                hotel_map_url = night_hotel.get('map_url', '')
                
                if not hotel_url or 'example.com' in str(hotel_url):
                    hotel_url = f"https://www.google.com/travel/hotels/{dest_city.replace(' ', '+')}?q={hotel_name.replace(' ', '+')}"
                if not hotel_map_url:
                    hotel_map_url = f"https://www.google.com/maps/search/{hotel_name.replace(' ', '+')}+{dest_city.replace(' ', '+')}"
                
                area_text = f" ({hotel_area})" if hotel_area else ""
                nearby_text = f" | Near: {nearby_info}" if nearby_info else ""
                
                itinerary.append({
                    "day": f"Day {day}",
                    "time": "10:00 PM",
                    "type": "check_in",
                    "title": f"Night {day}: {hotel_name}{area_text}",
                    "details": f"Check-in at your accommodation for Night {day}. Rating: {night_hotel.get('rating', night_hotel.get('safety_score', 85)/20):.1f}/5 | Safety: {night_hotel.get('safety_score', 85)}/100{nearby_text}",
                    "url": hotel_url,
                    "map_url": hotel_map_url,
                    "cost_est": int(hotel_cost) if isinstance(hotel_cost, (int, float)) else 0,
                    "color": "green"
                })
                daily_expense += int(hotel_cost) if isinstance(hotel_cost, (int, float)) else 0
                
            # Add Daily Summary
            itinerary.append({
                "day": f"Day {day}",
                "time": "11:00 PM",
                "type": "daily_summary",
                "title": f"End of Day {day}",
                "details": f"Estimated Day Cost: ₹{daily_expense:,}",
                "cost_est": 0,
                "color": "gray"
            })
                
        return itinerary

    def generate_packing_list(self, weather_data: dict, destination: str) -> list:
        """
        Generates a basic packing list based on the forecast.
        """
        packing_list = ["Passport/ID", "Phone Charger", "Comfortable Walking Shoes", "Toiletries"]
        
        has_bad_weather = weather_data.get('has_bad_weather', False)
        
        is_hot = False
        is_cold = False
        for f in weather_data.get('forecasts', []):
             temp_str = f.get('temp', '25°C')
             try:
                 temp = float(temp_str.replace('°C', ''))
                 if temp > 30: is_hot = True
                 if temp < 15: is_cold = True
             except: pass
             
        if has_bad_weather:
             packing_list.extend(["Umbrella", "Rain Jacket", "Waterproof Bag"])
        if is_hot:
             packing_list.extend(["Sunscreen", "Sunglasses", "Light Cotton Clothes", "Water Bottle"])
        if is_cold:
             packing_list.extend(["Heavy Jacket", "Thermals", "Beanie/Gloves"])
             
        # Optional: International logic placeholder
        if destination.lower() not in ["india", "delhi", "mumbai", "bangalore", "agra", "jaipur", "goa"]:
             packing_list.extend(["Universal Power Adapter", "Travel Insurance Docs"])
             
        return list(set(packing_list))
