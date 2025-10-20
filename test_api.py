import requests
import os
from dotenv import load_dotenv

load_dotenv()

# Test if API key is loaded
api_key = os.getenv('GOOGLE_PLACES_API_KEY')
print(f"API Key loaded: {'Yes' if api_key else 'No'}")
print(f"API Key length: {len(api_key) if api_key else 0}")

# Test Google Places API directly
if api_key:
    url = 'https://maps.googleapis.com/maps/api/place/nearbysearch/json'
    params = {
        'location': '32.9027430145737,-96.91479828767045',
        'radius': 1000,
        'type': 'restaurant',
        'key': api_key
    }
    
    print(f"\nTesting API with params: {params}")
    response = requests.get(url, params=params)
    print(f"Response status: {response.status_code}")
    
    data = response.json()
    print(f"API Status: {data.get('status')}")
    
    if data.get('error_message'):
        print(f"Error message: {data.get('error_message')}")
    
    if data.get('results'):
        print(f"Found {len(data.get('results'))} places")
        print(f"First place: {data.get('results')[0].get('name')}")
    else:
        print("No results found or error occurred")
        print(f"Full response: {data}")