"""
Airport Resolver Agent for VoyagrBot.

Resolves cities to their nearest commercial airport, handling cities that
don't have their own airport by finding the nearest one and providing
ground transfer information.
"""

import math
import requests
from core.cache import get_cached_data, set_cached_data

# Comprehensive IATA mapping: city_name (lowercase) -> (IATA code, airport_city_name, lat, lon)
AIRPORT_DATABASE = {
    # Major Indian Cities with Airports
    "delhi": ("DEL", "Delhi", 28.5562, 77.1000),
    "new delhi": ("DEL", "Delhi", 28.5562, 77.1000),
    "mumbai": ("BOM", "Mumbai", 19.0896, 72.8656),
    "chennai": ("MAA", "Chennai", 12.9941, 80.1709),
    "kolkata": ("CCU", "Kolkata", 22.6547, 88.4467),
    "bangalore": ("BLR", "Bengaluru", 13.1986, 77.7066),
    "bengaluru": ("BLR", "Bengaluru", 13.1986, 77.7066),
    "hyderabad": ("HYD", "Hyderabad", 17.2403, 78.4294),
    "ahmedabad": ("AMD", "Ahmedabad", 23.0773, 72.6347),
    "pune": ("PNQ", "Pune", 18.5822, 73.9197),
    "goa": ("GOI", "Goa (Dabolim/Mopa)", 15.3808, 73.8314),
    "jaipur": ("JAI", "Jaipur", 26.8242, 75.8122),
    "lucknow": ("LKO", "Lucknow", 26.7606, 80.8893),
    "kochi": ("COK", "Kochi", 10.1520, 76.4019),
    "cochin": ("COK", "Kochi", 10.1520, 76.4019),
    "kerala": ("COK", "Kochi", 10.1520, 76.4019),
    "thiruvananthapuram": ("TRV", "Thiruvananthapuram", 8.4821, 76.9199),
    "trivandrum": ("TRV", "Thiruvananthapuram", 8.4821, 76.9199),
    "varanasi": ("VNS", "Varanasi", 25.4524, 82.8593),
    "bhopal": ("BHO", "Bhopal", 23.2875, 77.3374),
    "indore": ("IDR", "Indore", 22.7218, 75.8011),
    "chandigarh": ("IXC", "Chandigarh", 30.6735, 76.7885),
    "amritsar": ("ATQ", "Amritsar", 31.7096, 74.7973),
    "patna": ("PAT", "Patna", 25.5913, 85.0880),
    "ranchi": ("IXR", "Ranchi", 23.3143, 85.3217),
    "bhubaneswar": ("BBI", "Bhubaneswar", 20.2444, 85.8178),
    "guwahati": ("GAU", "Guwahati", 26.1061, 91.5858),
    "srinagar": ("SXR", "Srinagar", 33.9871, 74.7742),
    "jammu": ("IXJ", "Jammu", 32.6891, 74.8374),
    "dehradun": ("DED", "Dehradun", 30.1899, 78.1803),
    "udaipur": ("UDR", "Udaipur", 24.6177, 73.8961),
    "jodhpur": ("JDH", "Jodhpur", 26.2511, 73.0489),
    "nagpur": ("NAG", "Nagpur", 21.0922, 79.0472),
    "visakhapatnam": ("VTZ", "Visakhapatnam", 17.7215, 83.2245),
    "vizag": ("VTZ", "Visakhapatnam", 17.7215, 83.2245),
    "coimbatore": ("CJB", "Coimbatore", 11.0300, 77.0434),
    "madurai": ("IXM", "Madurai", 9.8345, 78.0934),
    "mangalore": ("IXE", "Mangalore", 12.9614, 74.8901),
    "raipur": ("RPR", "Raipur", 21.1804, 81.7388),
    "imphal": ("IMF", "Imphal", 24.7600, 93.8967),
    "agartala": ("IXA", "Agartala", 23.8870, 91.2404),
    "silchar": ("IXS", "Silchar", 24.9129, 92.9787),
    "dibrugarh": ("DIB", "Dibrugarh", 27.4839, 95.0169),
    "bagdogra": ("IXB", "Bagdogra", 26.6812, 88.3286),
    "port blair": ("IXZ", "Port Blair", 11.6413, 92.7297),
    "leh": ("IXL", "Leh", 34.1359, 77.5465),
    "kullu": ("KUU", "Kullu (Bhuntar)", 31.8767, 77.1544),
    "bhuntar": ("KUU", "Kullu (Bhuntar)", 31.8767, 77.1544),
    "dharamshala": ("DHM", "Dharamshala (Gaggal)", 32.1651, 76.2634),
    "kangra": ("DHM", "Dharamshala (Gaggal)", 32.1651, 76.2634),
    "aurangabad": ("IXU", "Aurangabad", 19.8627, 75.3981),
    "tiruchirappalli": ("TRZ", "Tiruchirappalli", 10.7654, 78.7097),
    "trichy": ("TRZ", "Tiruchirappalli", 10.7654, 78.7097),
    "rajkot": ("RAJ", "Rajkot", 22.3092, 70.7795),
    "vadodara": ("BDQ", "Vadodara", 22.3362, 73.2264),
    "surat": ("STV", "Surat", 21.1141, 72.7418),

    # International Hubs
    "paris": ("CDG", "Paris (Charles de Gaulle)", 49.0097, 2.5479),
    "london": ("LHR", "London (Heathrow)", 51.4700, -0.4543),
    "new york": ("JFK", "New York (JFK)", 40.6413, -73.7781),
    "dubai": ("DXB", "Dubai", 25.2532, 55.3657),
    "singapore": ("SIN", "Singapore (Changi)", 1.3644, 103.9915),
    "bangkok": ("BKK", "Bangkok (Suvarnabhumi)", 13.6900, 100.7501),
    "tokyo": ("NRT", "Tokyo (Narita)", 35.7647, 140.3864),
    "hong kong": ("HKG", "Hong Kong", 22.3080, 113.9185),
    "kuala lumpur": ("KUL", "Kuala Lumpur", 2.7456, 101.7099),
    "sydney": ("SYD", "Sydney", -33.9461, 151.1772),
    "toronto": ("YYZ", "Toronto (Pearson)", 43.6777, -79.6248),
    "istanbul": ("IST", "Istanbul", 41.2619, 28.7419),
    "rome": ("FCO", "Rome (Fiumicino)", 41.8003, 12.2389),
    "frankfurt": ("FRA", "Frankfurt", 50.0379, 8.5622),
    "amsterdam": ("AMS", "Amsterdam (Schiphol)", 52.3105, 4.7683),
    "doha": ("DOH", "Doha (Hamad)", 25.2609, 51.6138),
    "abu dhabi": ("AUH", "Abu Dhabi", 24.4330, 54.6511),
    "colombo": ("CMB", "Colombo (Bandaranaike)", 7.1808, 79.8841),
    "kathmandu": ("KTM", "Kathmandu (Tribhuvan)", 27.6966, 85.3591),
    "dhaka": ("DAC", "Dhaka (Hazrat Shahjalal)", 23.8433, 90.3978),
    "male": ("MLE", "Malé (Velana)", 4.1918, 73.5290),
    "maldives": ("MLE", "Malé (Velana)", 4.1918, 73.5290),
    "bali": ("DPS", "Bali (Ngurah Rai)", -8.7482, 115.1672),
    "cairo": ("CAI", "Cairo", 30.1219, 31.4056),
    "nairobi": ("NBO", "Nairobi (Jomo Kenyatta)", -1.3192, 36.9278),
    "los angeles": ("LAX", "Los Angeles (LAX)", 33.9425, -118.4081),
    "san francisco": ("SFO", "San Francisco", 37.6213, -122.3790),
    "beijing": ("PEK", "Beijing (Capital)", 40.0799, 116.6031),
    "shanghai": ("PVG", "Shanghai (Pudong)", 31.1443, 121.8083),
    "seoul": ("ICN", "Seoul (Incheon)", 37.4602, 126.4407),
    "moscow": ("SVO", "Moscow (Sheremetyevo)", 55.9726, 37.4146),
}

# Known cities WITHOUT airports -> nearest airport city
# This handles the most common "no airport" scenarios in Indian tourism
NEARBY_AIRPORT_MAP = {
    "agra": ("DEL", "Delhi (IGI Airport)", "Agra has Kheria Air Force base but limited commercial flights. Delhi IGI is the major hub.", 200),
    "manali": ("KUU", "Kullu (Bhuntar Airport)", "Bhuntar Airport is 50 km from Manali. Alternatively, Chandigarh (IXC) is 280 km away with more flight options.", 50),
    "shimla": ("IXC", "Chandigarh Airport", "Shimla's Jubbarhatti Airport has very limited flights. Chandigarh is the reliable option.", 115),
    "mussoorie": ("DED", "Dehradun (Jolly Grant Airport)", "Dehradun airport is about 60 km from Mussoorie.", 60),
    "rishikesh": ("DED", "Dehradun (Jolly Grant Airport)", "Jolly Grant Airport is about 35 km from Rishikesh.", 35),
    "haridwar": ("DED", "Dehradun (Jolly Grant Airport)", "Jolly Grant Airport is about 40 km from Haridwar.", 40),
    "nainital": ("PGH", "Pantnagar Airport", "Pantnagar Airport is about 70 km from Nainital. Alternatively, Delhi (DEL) has more flights.", 70),
    "ooty": ("CJB", "Coimbatore Airport", "Coimbatore Airport is about 88 km from Ooty.", 88),
    "kodaikanal": ("IXM", "Madurai Airport", "Madurai Airport is about 120 km from Kodaikanal.", 120),
    "munnar": ("COK", "Kochi Airport", "Kochi Airport is about 130 km from Munnar.", 130),
    "alleppey": ("COK", "Kochi Airport", "Kochi Airport is about 75 km from Alleppey (Alappuzha).", 75),
    "alappuzha": ("COK", "Kochi Airport", "Kochi Airport is about 75 km from Alappuzha.", 75),
    "thekkady": ("IXM", "Madurai Airport", "Madurai Airport is about 145 km from Thekkady.", 145),
    "varkala": ("TRV", "Thiruvananthapuram Airport", "Trivandrum Airport is about 50 km from Varkala.", 50),
    "wayanad": ("CCJ", "Calicut (Kozhikode) Airport", "Calicut Airport is about 95 km from Wayanad.", 95),
    "darjeeling": ("IXB", "Bagdogra Airport", "Bagdogra Airport is about 70 km from Darjeeling.", 70),
    "gangtok": ("IXB", "Bagdogra Airport", "Bagdogra Airport is about 125 km from Gangtok.", 125),
    "sikkim": ("IXB", "Bagdogra Airport", "Bagdogra Airport is about 125 km from Gangtok, Sikkim.", 125),
    "pelling": ("IXB", "Bagdogra Airport", "Bagdogra Airport is about 155 km from Pelling.", 155),
    "mcleodganj": ("DHM", "Dharamshala (Gaggal Airport)", "Gaggal Airport is about 18 km from McLeodGanj.", 18),
    "dalhousie": ("DHM", "Dharamshala (Gaggal Airport)", "Gaggal Airport is about 135 km from Dalhousie. Alternatively, use Amritsar (ATQ).", 135),
    "kasol": ("KUU", "Kullu (Bhuntar Airport)", "Bhuntar Airport is about 30 km from Kasol.", 30),
    "spiti": ("KUU", "Kullu (Bhuntar Airport)", "Bhuntar Airport is the nearest at about 200 km. Limited flights; Chandigarh (IXC) is more reliable.", 200),
    "tawang": ("IXB", "Bagdogra Airport", "Bagdogra Airport is about 450 km from Tawang. Guwahati (GAU) is also an option at ~520 km with more flights.", 450),
    "gulmarg": ("SXR", "Srinagar Airport", "Srinagar Airport is about 50 km from Gulmarg.", 50),
    "pahalgam": ("SXR", "Srinagar Airport", "Srinagar Airport is about 95 km from Pahalgam.", 95),
    "sonamarg": ("SXR", "Srinagar Airport", "Srinagar Airport is about 80 km from Sonamarg.", 80),
    "coorg": ("IXE", "Mangalore Airport", "Mangalore Airport is about 160 km from Coorg (Kodagu). Mysore Airport is closer but has limited flights.", 160),
    "hampi": ("BLR", "Bengaluru Airport", "Bengaluru Airport is about 350 km from Hampi. Hubli Airport (HBX) is closer at ~140 km but with fewer flights.", 350),
    "pondicherry": ("MAA", "Chennai Airport", "Chennai Airport is about 150 km from Pondicherry.", 150),
    "puducherry": ("MAA", "Chennai Airport", "Chennai Airport is about 150 km from Puducherry.", 150),
    "mahabalipuram": ("MAA", "Chennai Airport", "Chennai Airport is about 60 km from Mahabalipuram.", 60),
    "lonavala": ("PNQ", "Pune Airport", "Pune Airport is about 65 km from Lonavala. Mumbai (BOM) is about 85 km.", 65),
    "mahabaleshwar": ("PNQ", "Pune Airport", "Pune Airport is about 120 km from Mahabaleshwar.", 120),
    "alibaug": ("BOM", "Mumbai Airport", "Mumbai Airport is about 100 km from Alibaug (via road).", 100),
    "mount abu": ("UDR", "Udaipur Airport", "Udaipur Airport is about 165 km from Mount Abu.", 165),
    "pushkar": ("JAI", "Jaipur Airport", "Jaipur Airport is about 145 km from Pushkar. Ajmer is 11 km from Pushkar.", 145),
    "ajmer": ("JAI", "Jaipur Airport", "Jaipur Airport is about 135 km from Ajmer.", 135),
    "ranthambore": ("JAI", "Jaipur Airport", "Jaipur Airport is about 180 km from Ranthambore.", 180),
    "jaisalmer": ("JDH", "Jodhpur Airport", "Jodhpur Airport is about 280 km from Jaisalmer.", 280),
    "bikaner": ("JDH", "Jodhpur Airport", "Jodhpur Airport is about 250 km from Bikaner.", 250),
    "khajuraho": ("HJR", "Khajuraho Airport", "Khajuraho has its own small airport with limited flights. Varanasi (VNS) is an alternative.", 0),
    "bodh gaya": ("GAY", "Gaya Airport", "Gaya Airport is about 15 km from Bodh Gaya.", 15),
    "andaman": ("IXZ", "Port Blair Airport", "Veer Savarkar Airport in Port Blair serves the Andaman Islands.", 0),
    "lakshadweep": ("AGX", "Agatti Airport", "Agatti Island has a small airport. Flights operate from Kochi (COK).", 0),
}


def _haversine(lat1, lon1, lat2, lon2):
    """Calculate the great-circle distance between two points on Earth (km)."""
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


def _geocode_city(city_name: str):
    """Use Nominatim to get coordinates for a city."""
    try:
        headers = {"User-Agent": "VoyagrBot/1.0"}
        res = requests.get(
            f"https://nominatim.openstreetmap.org/search?q={city_name}&format=json&limit=1",
            headers=headers,
            timeout=5
        ).json()
        if res:
            return float(res[0]['lat']), float(res[0]['lon'])
    except Exception as e:
        print(f"Airport Resolver geocode error for '{city_name}': {e}")
    return None, None


def _find_nearest_airport(lat: float, lon: float, exclude_city: str = ""):
    """Find the nearest airport from the database given coordinates."""
    best_dist = float('inf')
    best_code = None
    best_city = None

    for city_key, (iata, airport_city, a_lat, a_lon) in AIRPORT_DATABASE.items():
        if city_key == exclude_city.lower():
            continue
        dist = _haversine(lat, lon, a_lat, a_lon)
        if dist < best_dist:
            best_dist = dist
            best_code = iata
            best_city = airport_city

    return best_code, best_city, round(best_dist)


def resolve_airports(origin: str, destination: str) -> dict:
    """
    Resolve origin and destination cities to their nearest commercial airports.

    Returns a dict with:
        origin_iata, origin_airport_city, origin_needs_transfer, origin_transfer_info,
        dest_iata, dest_airport_city, dest_needs_transfer, dest_transfer_info,
        origin_transfer_km, dest_transfer_km
    """
    cache_key_data = get_cached_data("airport", origin.lower(), destination.lower())
    if cache_key_data:
        return cache_key_data

    result = {
        "origin_iata": None,
        "origin_airport_city": origin.strip().title(),
        "origin_needs_transfer": False,
        "origin_transfer_info": "",
        "origin_transfer_km": 0,
        "dest_iata": None,
        "dest_airport_city": destination.strip().title(),
        "dest_needs_transfer": False,
        "dest_transfer_info": "",
        "dest_transfer_km": 0,
    }

    # --- Resolve Origin ---
    origin_lower = origin.strip().lower()
    if origin_lower in AIRPORT_DATABASE:
        db = AIRPORT_DATABASE[origin_lower]
        result["origin_iata"] = db[0]
        result["origin_airport_city"] = db[1]
    elif origin_lower in NEARBY_AIRPORT_MAP:
        nearby = NEARBY_AIRPORT_MAP[origin_lower]
        result["origin_iata"] = nearby[0]
        result["origin_airport_city"] = nearby[1]
        result["origin_needs_transfer"] = True
        result["origin_transfer_info"] = nearby[2]
        result["origin_transfer_km"] = nearby[3]
    else:
        # Unknown city: geocode and find nearest
        lat, lon = _geocode_city(origin)
        if lat is not None:
            code, airport_city, dist = _find_nearest_airport(lat, lon)
            result["origin_iata"] = code
            result["origin_airport_city"] = airport_city
            if dist > 30:  # More than 30 km means a transfer is needed
                result["origin_needs_transfer"] = True
                result["origin_transfer_info"] = f"Nearest airport to {origin.title()} is {airport_city} ({code}), approximately {dist} km away."
                result["origin_transfer_km"] = dist
        else:
            # Last resort: 3-char truncation (legacy behavior)
            result["origin_iata"] = origin.strip()[:3].upper()

    # --- Resolve Destination ---
    dest_lower = destination.strip().lower()
    if dest_lower in AIRPORT_DATABASE:
        db = AIRPORT_DATABASE[dest_lower]
        result["dest_iata"] = db[0]
        result["dest_airport_city"] = db[1]
    elif dest_lower in NEARBY_AIRPORT_MAP:
        nearby = NEARBY_AIRPORT_MAP[dest_lower]
        result["dest_iata"] = nearby[0]
        result["dest_airport_city"] = nearby[1]
        result["dest_needs_transfer"] = True
        result["dest_transfer_info"] = nearby[2]
        result["dest_transfer_km"] = nearby[3]
    else:
        # Unknown city: geocode and find nearest
        lat, lon = _geocode_city(destination)
        if lat is not None:
            code, airport_city, dist = _find_nearest_airport(lat, lon)
            result["dest_iata"] = code
            result["dest_airport_city"] = airport_city
            if dist > 30:
                result["dest_needs_transfer"] = True
                result["dest_transfer_info"] = f"Nearest airport to {destination.title()} is {airport_city} ({code}), approximately {dist} km away."
                result["dest_transfer_km"] = dist
        else:
            result["dest_iata"] = destination.strip()[:3].upper()

    set_cached_data("airport", result, origin.lower(), destination.lower())
    return result
