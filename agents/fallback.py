import random

MOCK_COORDS = {
    "Paris": [48.8566, 2.3522],
    "Mumbai": [19.0760, 72.8777],
    "Delhi": [28.6139, 77.2090],
    "Agra": [27.1767, 78.0081],
    "Goa": [15.2993, 74.1240],
    "Jaipur": [26.9124, 75.7873],
    "Kerala": [10.8505, 76.2711],
    "Chennai": [13.0827, 80.2707],
    "Manali": [32.2396, 77.1887]
}

class FallbackAgent:
    def __init__(self):
        pass
        
    def _get_coords(self, city: str):
        base_lat, base_lon = MOCK_COORDS.get(city.strip().title(), [15.0, 75.0])
        return base_lat + random.uniform(-0.02, 0.02), base_lon + random.uniform(-0.02, 0.02)
        
    def get_hotels(self, city: str, check_in: str = None, check_out: str = None) -> list:
        city_title = city.strip().title()
        
        prefixes_1 = ["The Grand", "Royal", "Taj", "Premium", "Elite", "Crown"]
        suffixes_1 = ["Resort", "Palace", "Hotel", "Plaza", "Suites"]
        
        prefixes_2 = ["Heritage", "Classic", "Vintage", "Boutique", "Majestic"]
        suffixes_2 = ["Stay", "Inn", "Villa", "Retreat", "Lodge"]
        
        prefixes_3 = ["Backpackers", "Chill", "Nomad", "Wanderers", "Urban"]
        suffixes_3 = ["Hostel", "Dorms", "Basecamp", "Stay", "Hub"]
        
        name_1 = f"{random.choice(prefixes_1)} {city_title} {random.choice(suffixes_1)}"
        name_2 = f"{city_title} {random.choice(prefixes_2)} {random.choice(suffixes_2)}"
        name_3 = f"{random.choice(prefixes_3)} {random.choice(suffixes_3)} {city_title}"
        
        return [
            {
                "name": name_1, 
                "price": random.randint(3000, 8000), 
                "currency": "INR", 
                "safety_score": random.randint(80, 95),
                "check_in": "14:00",
                "check_out": "11:00"
            },
            {
                "name": name_2, 
                "price": random.randint(2500, 6000), 
                "currency": "INR", 
                "safety_score": random.randint(75, 90),
                "check_in": "15:00",
                "check_out": "12:00"
            },
            {
                "name": name_3, 
                "price": random.randint(800, 1500), 
                "currency": "INR", 
                "safety_score": random.randint(70, 85),
                "check_in": "13:00",
                "check_out": "10:00"
            }
        ]

    def get_attractions(self, city: str):
        city_title = city.strip().title()
        lat1, lon1 = self._get_coords(city)
        lat2, lon2 = self._get_coords(city)
        lat3, lon3 = self._get_coords(city)
        return [
            {"title": f"Historic Monuments of {city_title}", "content": f"Explore the rich cultural heritage and ancient architecture unique to {city_title}.", "url": "https://example.com/attraction1", "latitude": lat1, "longitude": lon1, "price": random.randint(200, 800)},
            {"title": f"{city_title} Central Park & Lake", "content": f"A beautiful spot for an evening stroll and boating right in the heart of {city_title}.", "url": "https://example.com/attraction2", "latitude": lat2, "longitude": lon2, "price": random.randint(50, 250)},
            {"title": f"Local Markets of {city_title}", "content": f"The bustling streets where you can find the best local handicrafts and souvenirs.", "url": "https://example.com/attraction3", "latitude": lat3, "longitude": lon3, "price": random.randint(100, 400)}
        ]

    def get_food(self, city: str, is_veg=False, is_jain=False):
        city_title = city.strip().title()
        pref = "Pure Veg" if is_veg else "Jain" if is_jain else "Local Authentic"
        lat1, lon1 = self._get_coords(city)
        lat2, lon2 = self._get_coords(city)
        lat3, lon3 = self._get_coords(city)
        return [
            {"title": f"Famous {city_title} Street Food", "content": f"Taste the best {pref.lower()} street-side delicacies {city_title} has to offer.", "url": "https://example.com/food1", "latitude": lat1, "longitude": lon1, "price": random.randint(300, 900)},
            {"title": f"Old {city_title} Traditional Dine-in", "content": f"A historic restaurant serving century-old {pref.lower()} recipes.", "url": "https://example.com/food2", "latitude": lat2, "longitude": lon2, "price": random.randint(600, 1500)},
            {"title": f"{city_title} Modern Cafe", "content": f"A modern aesthetic cafe offering fusion {pref.lower()} cuisines.", "url": "https://example.com/food3", "latitude": lat3, "longitude": lon3, "price": random.randint(500, 1200)}
        ]

    def get_festivals(self, city: str):
        city_title = city.strip().title()
        lat1, lon1 = self._get_coords(city)
        lat2, lon2 = self._get_coords(city)
        lat3, lon3 = self._get_coords(city)
        return [
            {"title": f"{city_title} Cultural Festival 2026", "content": f"A grand celebration of music, dance, and art originating from {city_title}.", "url": "https://example.com/fest1", "latitude": lat1, "longitude": lon1, "price": random.randint(800, 2500)},
            {"title": f"Spring Food Carnival in {city_title}", "content": f"The biggest seasonal food festival attracting foodies across the region to {city_title}.", "url": "https://example.com/fest2", "latitude": lat2, "longitude": lon2, "price": random.randint(400, 1000)},
            {"title": f"{city_title} Heritage Walk & Night Market", "content": f"An evening of vibrant celebrations highlighting the local culture of {city_title}.", "url": "https://example.com/fest3", "latitude": lat3, "longitude": lon3, "price": random.randint(200, 600)}
        ]

    def get_instagrammable(self, city: str):
        city_title = city.strip().title()
        lat1, lon1 = self._get_coords(city)
        lat2, lon2 = self._get_coords(city)
        lat3, lon3 = self._get_coords(city)
        return [
            {"title": f"Sunset Viewpoint in {city_title}", "content": f"The most breathtaking sunset views overlooking the city.", "image_url": "https://images.unsplash.com/photo-1526778548025-fa2f459cd5ce?w=500&auto=format&fit=crop", "latitude": lat1, "longitude": lon1},
            {"title": f"{city_title} Colorful Streets", "content": f"Vibrant, art-filled alleys perfect for your Instagram feed.", "image_url": "https://images.unsplash.com/photo-1506461883276-594a12b11dc3?w=500&auto=format&fit=crop", "latitude": lat2, "longitude": lon2},
            {"title": f"Iconic {city_title} Bridge", "content": f"An architectural marvel that looks stunning during golden hour.", "image_url": "https://images.unsplash.com/photo-1476514525535-07fb3b4ae5f1?w=500&auto=format&fit=crop", "latitude": lat3, "longitude": lon3}
        ]
