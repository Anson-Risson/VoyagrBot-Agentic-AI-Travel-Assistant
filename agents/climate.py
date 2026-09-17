import os
import requests
from core.cache import get_cached_data, set_cached_data

class ClimateAgent:
    def __init__(self):
        self.api_key = os.getenv("OPENWEATHER_API_KEY")
        self.base_url = "http://api.openweathermap.org/data/2.5/forecast"
        
    def get_forecast(self, city: str) -> dict:
        """
        Fetch a 5-day forecast with persistent caching.
        """
        cached = get_cached_data("weather", city)
        if cached:
            return cached
            
        if not self.api_key:
            return {
                "city": city,
                "has_bad_weather": False,
                "forecasts": [{"date": "MockDate", "temp": "20.0°C", "weather": "Clear"}] * 5
            }
            
        params = {
            "q": city,
            "appid": self.api_key,
            "units": "metric"
        }
        
        try:
            response = requests.get(self.base_url, params=params)
            response.raise_for_status()
            data = response.json()
            
            forecasts = []
            has_bad_weather = False
            
            for item in data['list'][::8]:
                weather_desc = item['weather'][0]['main']
                if weather_desc in ["Rain", "Thunderstorm", "Snow"]:
                    has_bad_weather = True
                    
                forecasts.append({
                    "date": item['dt_txt'].split()[0],
                    "temp": f"{item['main']['temp']:.1f}°C",
                    "weather": weather_desc
                })
                
            res = {
                "city": city,
                "has_bad_weather": has_bad_weather,
                "forecasts": forecasts
            }
            set_cached_data("weather", res, city)
            return res
        except Exception as e:
            print(f"ClimateAgent Error: {e}")
            return {
                "city": city,
                "has_bad_weather": False,
                "forecasts": []
            }
