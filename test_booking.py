import os
import requests
from dotenv import load_dotenv

load_dotenv(override=True)
rapidapi_key = os.getenv("RAPIDAPI_KEY")

def test_booking_dest():
    if not rapidapi_key:
        print("No RAPIDAPI_KEY found.")
        return
    
    print(f"Testing Booking.com SearchDestination with key: {rapidapi_key[:10]}...")
    url = 'https://booking-com15.p.rapidapi.com/api/v1/hotels/searchDestination'
    headers = {
        'x-rapidapi-key': rapidapi_key,
        'x-rapidapi-host': 'booking-com15.p.rapidapi.com'
    }
    try:
        res = requests.get(url, headers=headers, params={'query': 'Paris'})
        print(f"Status Code: {res.status_code}")
        print(f"Response: {res.text[:500]}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_booking_dest()
