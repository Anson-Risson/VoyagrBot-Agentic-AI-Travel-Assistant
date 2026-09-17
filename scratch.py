import requests
import math

def haversine(lat1, lon1, lat2, lon2):
    R = 6371  # Earth radius in km
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2) * math.sin(dlat/2) + math.cos(math.radians(lat1)) \
        * math.cos(math.radians(lat2)) * math.sin(dlon/2) * math.sin(dlon/2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    return R * c

def get_routing_info(origin, destination):
    # Get coords
    url_origin = f"https://nominatim.openstreetmap.org/search?q={origin}&format=json&limit=1"
    url_dest = f"https://nominatim.openstreetmap.org/search?q={destination}&format=json&limit=1"
    headers = {"User-Agent": "VoyagrBot/1.0"}
    
    try:
        res_orig = requests.get(url_origin, headers=headers).json()
        res_dest = requests.get(url_dest, headers=headers).json()
        
        lat1, lon1 = float(res_orig[0]['lat']), float(res_orig[0]['lon'])
        lat2, lon2 = float(res_dest[0]['lat']), float(res_dest[0]['lon'])
    except Exception as e:
        print("Geocoding failed", e)
        return None

    # Get Driving Route
    osrm_url = f"http://router.project-osrm.org/route/v1/driving/{lon1},{lat1};{lon2},{lat2}?overview=false"
    try:
        osrm_res = requests.get(osrm_url).json()
        if osrm_res.get('code') == 'Ok':
            driving_distance = osrm_res['routes'][0]['distance'] / 1000 # km
            driving_duration = osrm_res['routes'][0]['duration'] / 3600 # hours
        else:
            driving_distance = haversine(lat1, lon1, lat2, lon2) * 1.2
            driving_duration = driving_distance / 60
    except:
        driving_distance = haversine(lat1, lon1, lat2, lon2) * 1.2
        driving_duration = driving_distance / 60

    flight_distance = haversine(lat1, lon1, lat2, lon2)
    flight_duration = (flight_distance / 800) + 2 # Add 2 hours for airport transit
    train_duration = driving_distance / 60 # Assume 60 km/h avg train speed
    
    return {
        "flight_duration": flight_duration,
        "driving_distance": driving_distance,
        "driving_duration": driving_duration,
        "train_duration": train_duration
    }

print(get_routing_info("Thrissur", "Mumbai"))
