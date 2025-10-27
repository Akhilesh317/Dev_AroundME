# app.py (Places API v1 + Yelp + OpenAI)
from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
import requests
import os
import json
import urllib.parse
from dotenv import load_dotenv
from typing import List, Dict, Any
from ai_query_processor import AIQueryProcessor
from chatgpt_places import ChatGPTPlacesSuggester
import re
from difflib import SequenceMatcher
import math
from chat_api import chat_bp



load_dotenv()

app = Flask(__name__)
CORS(app)
app.register_blueprint(chat_bp)  # <-- add this line


GOOGLE_PLACES_API_KEY = os.getenv("GOOGLE_PLACES_API_KEY")
YELP_API_KEY = os.getenv("YELP_API_KEY")

# ---- Google Places v1 base ----
PLACES_V1_BASE = "https://places.googleapis.com/v1"

# ---- Yelp endpoints ----
YELP_SEARCH_URL = "https://api.yelp.com/v3/businesses/search"
YELP_BUSINESS_BASE = "https://api.yelp.com/v3/businesses"

# Initialize AI processors
ai_processor = AIQueryProcessor()
chatgpt_suggester = ChatGPTPlacesSuggester()


# ==========================
# Helpers: Google Places v1
# ==========================
def _gplaces_headers(field_mask: str) -> dict:
    return {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": GOOGLE_PLACES_API_KEY,
        "X-Goog-FieldMask": field_mask,
    }


def gplaces_search_text(text_query: str, lat: float | None = None, lng: float | None = None, radius_m: int | None = None) -> list[dict]:
    """
    POST /v1/places:searchText
    Returns a list under "places"
    """
    url = f"{PLACES_V1_BASE}/places:searchText"
    payload: dict[str, Any] = {"textQuery": text_query}

    # Optional location bias
    if lat is not None and lng is not None:
        payload["locationBias"] = {
            "circle": {
                "center": {"latitude": float(lat), "longitude": float(lng)},
                "radius": float(radius_m or 3000),
            }
        }

    field_mask = ",".join(
        [
            "places.name",
            "places.id",
            "places.displayName",
            "places.formattedAddress",
            "places.location",
            "places.rating",
            "places.userRatingCount",
            "places.priceLevel",
            "places.primaryType",
            "places.currentOpeningHours.weekdayDescriptions",
        ]
    )

    r = requests.post(url, headers=_gplaces_headers(field_mask), json=payload, timeout=25)
    r.raise_for_status()
    return r.json().get("places", [])


def gplaces_search_nearby(lat: float, lng: float, radius_m: int, included_primary_types: list[str] | None = None) -> list[dict]:
    """
    POST /v1/places:searchNearby
    """
    url = f"{PLACES_V1_BASE}/places:searchNearby"
    payload: dict[str, Any] = {
        "location": {"latitude": float(lat), "longitude": float(lng)},
        "radius": int(radius_m),
    }
    if included_primary_types:
        payload["includedPrimaryTypes"] = included_primary_types

    field_mask = ",".join(
        [
            "places.name",
            "places.id",
            "places.displayName",
            "places.formattedAddress",
            "places.location",
            "places.rating",
            "places.userRatingCount",
            "places.priceLevel",
            "places.primaryType",
            "places.currentOpeningHours.weekdayDescriptions",
        ]
    )

    r = requests.post(url, headers=_gplaces_headers(field_mask), json=payload, timeout=25)
    r.raise_for_status()
    return r.json().get("places", [])


def gplaces_get_details(place_name: str) -> dict:
    """
    GET /v1/{name=places/*}
    place_name must be like "places/ChIJ..."
    """
    encoded = urllib.parse.quote(place_name, safe="/")
    url = f"{PLACES_V1_BASE}/{encoded}"

    field_mask = ",".join(
        [
            "displayName",
            "formattedAddress",
            "internationalPhoneNumber",
            "nationalPhoneNumber",
            "websiteUri",
            "rating",
            "userRatingCount",
            "priceLevel",
            "currentOpeningHours.weekdayDescriptions",
            "regularOpeningHours.weekdayDescriptions",
            "location",
            "reviews",  # best-effort; may require additional permissions in some projects
        ]
    )

    r = requests.get(url, headers=_gplaces_headers(field_mask), timeout=25)
    r.raise_for_status()
    return r.json()


# ==========================
# Helpers: Yelp formatting
# ==========================
def format_yelp_hours(hours_data):
    """Format Yelp hours data into a Google-like weekday_text format."""
    if not hours_data or not hours_data[0].get("open"):
        return None

    days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    formatted_hours = []
    regular_hours = hours_data[0].get("open", [])

    hours_by_day: dict[int, list[str]] = {}
    for hour in regular_hours:
        day_num = hour.get("day")
        start = hour.get("start", "")
        end = hour.get("end", "")
        if day_num is not None and start and end:
            disp = f"{_format_time_hhmm(start)} - {_format_time_hhmm(end)}"
            hours_by_day.setdefault(day_num, []).append(disp)

    for i, day in enumerate(days):
        if i in hours_by_day:
            formatted_hours.append(f"{day}: {', '.join(hours_by_day[i])}")
        else:
            formatted_hours.append(f"{day}: Closed")

    return {"weekday_text": formatted_hours}


def _format_time_hhmm(time_str: str) -> str:
    if not time_str or len(time_str) != 4 or not time_str.isdigit():
        return "Closed"
    hour = int(time_str[:2])
    minute = int(time_str[2:])
    suffix = "AM"
    if hour == 0:
        hour_disp = 12
    elif hour < 12:
        hour_disp = hour
    elif hour == 12:
        hour_disp = 12
        suffix = "PM"
    else:
        hour_disp = hour - 12
        suffix = "PM"
    return f"{hour_disp}:{minute:02d} {suffix}"


# ==========================
# Routes
# ==========================

@app.get("/chat-test")
def chat_test_page():
    return render_template("chat_test.html")  # serves templates/chat_test.html


@app.get("/healthz")             # <-- optional quick health check
def healthz():
    return {"ok": True}


@app.get("/chat")
def chat_page():
    # Pass-through route; template reads query params itself
    return render_template("chat.html")



@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/places", methods=["GET"])
def api_places():
    """
    Nearby-like search using Places v1.
    Params: lat, lng, radius (m), type (primaryType like 'restaurant', 'cafe', ...)
    """
    lat = request.args.get("lat", type=float)
    lng = request.args.get("lng", type=float)
    radius = request.args.get("radius", default=1000, type=int)
    place_type = request.args.get("type", default="restaurant", type=str)

    if lat is None or lng is None:
        return jsonify({"error": "Latitude and longitude are required"}), 400

    try:
        results = gplaces_search_nearby(lat, lng, radius, included_primary_types=[place_type])

        def norm(p: dict) -> dict:
            disp = (p.get("displayName") or {}).get("text")
            addr = p.get("formattedAddress")
            loc = p.get("location") or {}
            return {
                "place_id": p.get("name"),  # "places/ChIJ..."
                "name": disp,
                "formatted_address": addr,
                "rating": p.get("rating"),
                "user_ratings_total": p.get("userRatingCount"),
                "price_level": p.get("priceLevel"),
                "types": [p.get("primaryType")] if p.get("primaryType") else [],
                "geometry": {"location": {"lat": loc.get("latitude"), "lng": loc.get("longitude")}},
                "source": "google",
            }

        return jsonify({"places": [norm(p) for p in results]})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/place-details/<path:place_id>", methods=["GET"])
def api_place_details(place_id):
    """
    Details for either Google (v1) or Yelp.
    Google place_id should be passed as the full name: "places/ChIJ..."
    Yelp IDs are typically 22 chars (no slash).
    """
    # Detect Yelp-ish vs Google v1
    is_yelp_like = (len(place_id) == 22) and ("/" not in place_id)

    try:
        if not is_yelp_like:
            # Google v1 details
            details = gplaces_get_details(place_id)
            opening = (details.get("currentOpeningHours") or {}).get("weekdayDescriptions") or (
                (details.get("regularOpeningHours") or {}).get("weekdayDescriptions")
            )

            loc = details.get("location") or {}
            # Normalize to your previous response shape
            result = {
                "source": "google",
                "place_id": place_id,
                "name": (details.get("displayName") or {}).get("text"),
                "formatted_address": details.get("formattedAddress"),
                "international_phone_number": details.get("internationalPhoneNumber"),
                "phone_number": details.get("nationalPhoneNumber"),
                "website": details.get("websiteUri"),
                "rating": details.get("rating"),
                "user_ratings_total": details.get("userRatingCount"),
                "price_level": details.get("priceLevel"),
                "opening_hours": {"weekday_text": opening} if opening else None,
                "geometry": {"location": {"lat": loc.get("latitude"), "lng": loc.get("longitude")}},
                # Reviews (best-effort)
                "reviews": [
                    {
                        "author_name": (rv.get("authorAttribution") or {}).get("displayName"),
                        "rating": rv.get("rating"),
                        "text": (rv.get("text") or {}).get("text"),
                        "publish_time": rv.get("publishTime"),
                    }
                    for rv in details.get("reviews", [])[:5]
                ],
            }
            return jsonify(result)

        # Yelp details
        if not YELP_API_KEY:
            return jsonify({"error": "Yelp API not configured"}), 500

        headers = {"Authorization": f"Bearer {YELP_API_KEY}"}

        biz_resp = requests.get(f"{YELP_BUSINESS_BASE}/{place_id}", headers=headers, timeout=25)
        biz_data = biz_resp.json()
        if biz_resp.status_code != 200:
            return jsonify({"error": biz_data.get("error", {}).get("description", "Yelp API error")}), 500

        rev_resp = requests.get(f"{YELP_BUSINESS_BASE}/{place_id}/reviews", headers=headers, timeout=25)
        rev_data = rev_resp.json()

        result = {
            "source": "yelp",
            "name": biz_data.get("name"),
            "rating": biz_data.get("rating"),
            "formatted_address": ", ".join(biz_data.get("location", {}).get("display_address", [])),
            "formatted_phone_number": biz_data.get("display_phone"),
            "website": biz_data.get("url"),
            "price_level": len(biz_data.get("price", "")),
            "categories": [c["title"] for c in biz_data.get("categories", [])],
            "review_count": biz_data.get("review_count", 0),
            "photos": biz_data.get("photos", []),
            "opening_hours": format_yelp_hours(biz_data.get("hours", [])),
            "is_open_now": (biz_data.get("hours", [{}])[0].get("is_open_now") if biz_data.get("hours") else None),
            "reviews": [
                {
                    "author_name": rv.get("user", {}).get("name"),
                    "rating": rv.get("rating"),
                    "text": rv.get("text"),
                    "time_description": rv.get("time_created"),
                }
                for rv in rev_data.get("reviews", [])[:5]
            ],
        }
        return jsonify(result)

    except Exception as e:
        import traceback

        print("place-details error:", e)
        print(traceback.format_exc())
        return jsonify({"error": str(e)}), 500


@app.route("/api/ai-search", methods=["POST"])
def ai_search():
    """
    ChatGPT-enhanced search pipeline:
    1) Validate query is location-related
    2) Get ChatGPT place suggestions
    3) Search for specific places via Google/Yelp
    4) Fallback to general search if needed
    5) Analyze and rank results
    """
    data = request.json or {}
    query = data.get("query", "")
    lat = data.get("lat")
    lng = data.get("lng")

    if not query or lat is None or lng is None:
        return jsonify({"error": "Query and location are required"}), 400

    try:
        # Phase 1: Validate query with ChatGPT
        validation = chatgpt_suggester.validate_location_query(query)
        print(f"=== DEBUG: Query Validation ===")
        print(f"Original Query: {query}")
        print(f"Validation: {validation}")
        
        if not validation.get("is_valid") or not validation.get("is_location_related"):
            return jsonify({
                "error": f"Invalid query: {validation.get('reason', 'Not a location search')}",
                "suggestion": "Please ask about finding places, restaurants, hotels, or other locations."
            }), 400
        
        # Use cleaned query
        clean_query = validation.get("cleaned_query", query)
        
        # Phase 2: Enhanced location context for Dallas metro area
        # Parse specific Dallas area from query
        dallas_areas = ["frisco", "arlington", "irving", "plano", "dallas", "fort worth", "richardson", 
                       "garland", "mckinney", "allen", "addison", "carrollton", "lewisville", 
                       "flower mound", "grapevine", "southlake", "colleyville", "mesquite", "denton",
                       "cedar hill", "desoto", "duncanville", "grand prairie", "euless", "bedford", 
                       "hurst", "coppell", "farmers branch", "university park", "highland park",
                       "rowlett", "wylie", "rockwall", "the colony", "little elm", "prosper", "celina"]
        
        query_lower = clean_query.lower()
        specific_area = None
        for area in dallas_areas:
            if area in query_lower:
                specific_area = area.title()
                break
        
        # Create enhanced location context
        if specific_area:
            location_context = f"in {specific_area}, Dallas metro area, Texas (lat: {lat}, lng: {lng})"
        else:
            location_context = f"Dallas metro area, Texas near user location (lat: {lat}, lng: {lng})"
        
        suggestions = chatgpt_suggester.suggest_places(clean_query, location_context)
        print(f"=== DEBUG: ChatGPT Suggestions ===")
        print(f"Number of suggestions: {len(suggestions)}")
        for i, suggestion in enumerate(suggestions[:3]):
            print(f"  {i+1}. {suggestion.get('name')} ({suggestion.get('type')})")
        
        # Phase 3: Search for ChatGPT suggested places - YELP FIRST approach
        yelp_places_found = []
        google_locations = {}  # To store Google location data by place name
        
        # Search for specific place names suggested by ChatGPT
        for suggestion in suggestions[:10]:  # Search more suggestions
            place_name = suggestion.get("name")
            if place_name:
                print(f"=== DEBUG: Searching for ChatGPT suggestion: {place_name} ===")
                
                # PRIORITY 1: Get Google Places data as primary source (Yelp unavailable)
                # Note: Using Google Places as primary data source since Yelp trial expired
                # Use larger radius for Dallas metro area but filter results
                search_radius = 25000 if specific_area else 15000  # 25km for specific areas, 15km for general
                google_results_raw = gplaces_search_text(place_name, lat=float(lat), lng=float(lng), radius_m=search_radius)
                for p in google_results_raw[:3]:  # Top 3 results per suggestion
                    disp = (p.get("displayName") or {}).get("text")
                    addr = p.get("formattedAddress")
                    loc = p.get("location") or {}
                    if disp and loc.get("latitude") and loc.get("longitude") and addr:
                        # Filter: Only include places with Texas addresses to ensure Dallas metro area
                        if not any(keyword in addr.lower() for keyword in ["texas", "tx", "dallas", "fort worth"]):
                            continue
                        
                        # Create a Yelp-style place object from Google data
                        google_as_yelp_place = {
                            "name": disp,
                            "address": addr,
                            "rating": p.get("rating", 0),
                            "price_level": p.get("priceLevel", 0),
                            "place_id": p.get("name"),  # Google place ID
                            "google_place_id": p.get("name"),
                            "geometry": {"location": {"lat": loc.get("latitude"), "lng": loc.get("longitude")}},
                            "types": [p.get("primaryType")] if p.get("primaryType") else [],
                            "source": "google_as_yelp",  # Mark as Google data used as Yelp substitute
                            "review_count": p.get("userRatingCount", 0),
                            "categories": [p.get("primaryType")] if p.get("primaryType") else [],
                            "yelp_categories": [],
                            "chatgpt_suggestion": suggestion,
                            "openai_reasons": suggestion.get("description", "")
                        }
                        yelp_places_found.append(google_as_yelp_place)
                        print(f"Found Google place as Yelp substitute: {disp} (Rating: {p.get('rating', 0)})")
        
        print(f"=== DEBUG: Google-as-Yelp search results ===")
        print(f"Total places found: {len(yelp_places_found)}")
        
        # Phase 4: Since we're using Google data directly, no enhancement needed
        enhanced_places = yelp_places_found
        
        # Phase 5: Fallback to traditional search if needed
        if len(enhanced_places) < 5:  # If we don't have enough specific results
            print(f"=== DEBUG: Fallback search (insufficient ChatGPT results) ===")
            intent = ai_processor.extract_intent(clean_query)
            search_params = ai_processor.build_search_parameters(intent)
            
            # Do traditional Google search for fallback with Dallas metro constraints
            fallback_radius = 20000  # 20km for fallback search
            google_fallback_raw = gplaces_search_text(search_params['google']['query'], lat=float(lat), lng=float(lng), radius_m=fallback_radius)
            for p in google_fallback_raw[:5]:  # Top 5 fallback results
                disp = (p.get("displayName") or {}).get("text")
                addr = p.get("formattedAddress")
                loc = p.get("location") or {}
                if disp and loc.get("latitude") and loc.get("longitude") and addr:
                    # Filter: Only include places with Texas addresses to ensure Dallas metro area
                    if not any(keyword in addr.lower() for keyword in ["texas", "tx", "dallas", "fort worth"]):
                        continue
                    fallback_place = {
                        "name": disp,
                        "address": addr,
                        "rating": p.get("rating", 0),
                        "price_level": p.get("priceLevel", 0),
                        "place_id": p.get("name"),
                        "google_place_id": p.get("name"),
                        "geometry": {"location": {"lat": loc.get("latitude"), "lng": loc.get("longitude")}},
                        "types": [p.get("primaryType")] if p.get("primaryType") else [],
                        "source": "google_fallback",
                        "review_count": p.get("userRatingCount", 0),
                        "categories": [p.get("primaryType")] if p.get("primaryType") else [],
                        "yelp_categories": [],
                        "chatgpt_suggestion": {"type": "fallback", "description": "Traditional search result"},
                        "openai_reasons": "Found through traditional search as fallback"
                    }
                    enhanced_places.append(fallback_place)
            print(f"Fallback found {len(google_fallback_raw)} additional Google places")
        
        # Remove duplicates
        all_places = []
        seen_names = set()
        for place in enhanced_places:
            place_name = place.get("name", "").lower()
            if place_name not in seen_names:
                seen_names.add(place_name)
                all_places.append(place)
        print(f"=== DEBUG: Combined Results ===")
        print(f"Combined places count: {len(all_places)}")
        
        # Phase 6: Add OpenAI reasons and sort by Yelp ratings
        for place in all_places:
            # Add OpenAI suggestion context
            chatgpt_suggestion = place.get("chatgpt_suggestion", {})
            place["openai_reasons"] = [
                chatgpt_suggestion.get("description", "Recommended by OpenAI"),
                f"Type: {chatgpt_suggestion.get('type', 'establishment')}",
                f"Confidence: {chatgpt_suggestion.get('confidence', 'medium')}"
            ]
            
            # Ensure we have Yelp rating for sorting
            if not place.get("rating"):
                place["rating"] = 0
            
            # Keep original source (google_as_yelp or google_fallback)
            # Don't override source
            
            print(f"=== DEBUG: Place prepared: {place.get('name')} (Rating: {place.get('rating')}) ===")
        
        # Phase 7: Smart sorting - distance first for "near me" queries, rating otherwise
        is_near_me_query = "near me" in clean_query.lower() or "nearby" in clean_query.lower() or "close to me" in clean_query.lower()
        
        if is_near_me_query:
            print(f"=== DEBUG: 'Near me' query detected - sorting by distance first ===")
            # For "near me" queries: sort by distance first, then rating
            for place in all_places:
                place_location = place.get('geometry', {}).get('location', {})
                place_lat = place_location.get('lat')
                place_lng = place_location.get('lng')
                
                if place_lat and place_lng and lat and lng:
                    distance = calculate_distance(float(lat), float(lng), float(place_lat), float(place_lng))
                    place['distance_meters'] = distance
                    place['distance_km'] = round(distance / 1000, 2)
                else:
                    place['distance_meters'] = float('inf')  # Unknown distance goes to end
                    place['distance_km'] = 999.99
            
            # Sort by distance first, then by rating
            all_places.sort(key=lambda x: (
                x.get("distance_meters", float('inf')),  # Primary sort: Distance (closest first)
                -x.get("rating", 0)  # Secondary sort: Rating (highest first, negative for reverse)
            ))
            
            print(f"Sorted by distance - closest places first")
        else:
            print(f"=== DEBUG: Regular query - sorting by rating first ===")
            # For regular queries: sort by rating first, then review count
            all_places.sort(key=lambda x: (
                x.get("rating", 0),  # Primary sort: Rating
                x.get("review_count", 0)  # Secondary sort: Review count
            ), reverse=True)
            
            print(f"Sorted by rating - highest rated first")
        
        if is_near_me_query:
            print(f"=== DEBUG: Final Results (sorted by distance) ===")
            print(f"Total places: {len(all_places)}")
            for i, place in enumerate(all_places[:5]):
                distance_km = place.get('distance_km', 'Unknown')
                print(f"  {i+1}. {place.get('name')} - Distance: {distance_km}km - Rating: {place.get('rating')} ({place.get('review_count')} reviews)")
        else:
            print(f"=== DEBUG: Final Results (sorted by rating) ===")
            print(f"Total places: {len(all_places)}")
            for i, place in enumerate(all_places[:5]):
                print(f"  {i+1}. {place.get('name')} - Rating: {place.get('rating')} ({place.get('review_count')} reviews)")
        
        # Prepare final results with sorting-appropriate data
        final_places = []
        for place in all_places[:10]:  # Top 10 by current sort method
            # Format OpenAI reasons as list if it's a string
            openai_reasons = place.get("openai_reasons", [])
            if isinstance(openai_reasons, str):
                openai_reasons = [openai_reasons]
            
            # Calculate match score based on sorting method
            if is_near_me_query:
                # For distance-based sorting, closer places get higher scores
                distance_m = place.get("distance_meters", float('inf'))
                if distance_m == float('inf'):
                    distance_score = 0
                else:
                    # Score decreases with distance: 100 for 0m, 80 for 1km, 60 for 2km, etc.
                    distance_score = max(0, 100 - (distance_m / 1000) * 20)
                match_score = int(distance_score)
            else:
                # For rating-based sorting, use rating * 20
                match_score = int(place.get("rating", 0) * 20)
            
            place.update({
                "match_score": match_score,
                "match_reasons": openai_reasons,
                "confidence": "high" if place.get("rating", 0) >= 4.0 else "medium",
                "relevant_reviews": []  # Can be populated if needed
            })
            final_places.append(place)

        return jsonify(
            {
                "places": final_places[:8],  # Top 8 places by distance or rating
                "query_intent": {
                    "original_query": query,
                    "cleaned_query": clean_query,
                    "primary_intent": f"Find places for: {clean_query}"
                },
                "chatgpt_context": {
                    "original_query": query,
                    "cleaned_query": clean_query,
                    "validation": validation,
                    "suggestions_count": len(suggestions),
                    "yelp_places_found": len(yelp_places_found),
                    "google_locations_cached": len(google_locations),
                    "final_places_count": len(final_places)
                },
                "scoring_breakdown": {
                    "total_candidates": len(all_places),
                    "ai_validated": len(final_places),  # All places are considered validated in new pipeline
                    "sorted_by": "distance_first" if is_near_me_query else "rating_first",
                    "sorting_method": "Distance (closest first), then rating" if is_near_me_query else "Rating (highest first), then review count",
                    "top_place": final_places[0].get("name") if final_places else None,
                    "rating_range": f"{final_places[-1].get('rating', 0)} - {final_places[0].get('rating', 0)}" if final_places else "N/A",
                    "distance_range": f"{final_places[0].get('distance_km', 'N/A')} - {final_places[-1].get('distance_km', 'N/A')}km" if is_near_me_query and final_places else None,
                    "note": "Using Google ratings as Yelp substitute due to API limitations"
                },
                "search_debug": {
                    "chatgpt_suggestions": len(suggestions),
                    "google_places_found": len(yelp_places_found),
                    "combined_total": len(all_places),
                    "final_results": len(final_places),
                    "data_source": "google_places_as_yelp_substitute"
                },
            }
        )

    except Exception as e:
        import traceback

        print("Error in ai_search:", e)
        print(traceback.format_exc())
        return jsonify({"error": str(e)}), 500


# ==========================
# Yelp search + merge + reviews
# ==========================
def search_yelp_places_ai(lat: float, lng: float, search_params: Dict) -> List[Dict]:
    """Universal Yelp search using parsed parameters."""
    if not YELP_API_KEY:
        return []

    headers = {"Authorization": f"Bearer {YELP_API_KEY}"}

    # Prefer specific city location if provided; else use coordinates
    if "location" in search_params and search_params["location"]:
        params = {
            "location": f"{search_params['location']}, TX",
            "radius": 10000,
            "limit": 20,
            "term": search_params.get("term", "restaurant"),
            "sort_by": "rating",
        }
    else:
        params = {
            "latitude": lat,
            "longitude": lng,
            "radius": 3000,
            "limit": 15,
            "term": search_params.get("term", "restaurant"),
            "sort_by": "rating",
        }

    if "categories" in search_params and search_params["categories"]:
        params["categories"] = search_params["categories"]

    try:
        print(f"=== DEBUG: Yelp API Request ===")
        print(f"URL: {YELP_SEARCH_URL}")
        print(f"Params: {params}")
        print(f"Headers: {headers}")
        
        r = requests.get(YELP_SEARCH_URL, headers=headers, params=params, timeout=25)
        print(f"Response status: {r.status_code}")
        
        if r.status_code != 200:
            print(f"Yelp API error response: {r.text}")
            return []
        
        data = r.json()
        print(f"Yelp API response businesses count: {len(data.get('businesses', []))}")
        
        places: list[dict] = []
        for b in data.get("businesses", []):
            places.append(
                {
                    "name": b.get("name"),
                    "address": ", ".join(b.get("location", {}).get("display_address", [])),
                    "rating": b.get("rating", 0),
                    "price_level": len(b.get("price", "")),
                    "yelp_id": b.get("id"),
                    "geometry": {
                        "location": {
                            "lat": b.get("coordinates", {}).get("latitude"),
                            "lng": b.get("coordinates", {}).get("longitude"),
                        }
                    },
                    "source": "yelp",
                    "review_count": b.get("review_count", 0),
                    "categories": [c["title"] for c in b.get("categories", [])],
                    "yelp_categories": [c["alias"] for c in b.get("categories", [])],
                }
            )
        print(f"Processed {len(places)} Yelp places")
        return places
    except Exception as e:
        print("Yelp search error:", e)
        import traceback
        print(traceback.format_exc())
        return []


def normalize_place_name(name: str) -> str:
    """Normalize place names for better matching"""
    if not name:
        return ""
    
    # Remove common suffixes and prefixes
    name = re.sub(r'\b(restaurant|cafe|bar|grill|kitchen|bistro|eatery)\b', '', name, flags=re.IGNORECASE)
    # Remove punctuation and extra spaces
    name = re.sub(r'[^\w\s]', '', name)
    # Normalize whitespace
    name = re.sub(r'\s+', ' ', name).strip().lower()
    
    # Handle common chain variations
    chain_mappings = {
        'mcdonalds': 'mcdonalds',
        'mc donalds': 'mcdonalds', 
        'mcdonald s': 'mcdonalds',
        'starbucks coffee': 'starbucks',
        'subway sandwiches': 'subway',
        'taco bell': 'tacobell',
        'burger king': 'burgerking',
        'pizza hut': 'pizzahut',
        'dominos pizza': 'dominos',
        'kfc': 'kfc',
        'kentucky fried chicken': 'kfc'
    }
    
    for variation, canonical in chain_mappings.items():
        if variation in name:
            return canonical
    
    return name

def calculate_distance(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Calculate distance between two points in meters using Haversine formula"""
    if None in [lat1, lng1, lat2, lng2]:
        return float('inf')
    
    # Convert to radians
    lat1, lng1, lat2, lng2 = map(math.radians, [lat1, lng1, lat2, lng2])
    
    # Haversine formula
    dlat = lat2 - lat1
    dlng = lng2 - lng1
    a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlng/2)**2
    c = 2 * math.asin(math.sqrt(a))
    r = 6371000  # Earth's radius in meters
    
    return c * r

def are_places_duplicates(place1: Dict, place2: Dict, distance_threshold: float = 100) -> bool:
    """Check if two places are duplicates using multiple criteria"""
    
    # Get coordinates
    loc1 = place1.get('geometry', {}).get('location', {})
    loc2 = place2.get('geometry', {}).get('location', {})
    
    lat1, lng1 = loc1.get('lat'), loc1.get('lng')
    lat2, lng2 = loc2.get('lat'), loc2.get('lng')
    
    # If both have coordinates, check distance
    if all(coord is not None for coord in [lat1, lng1, lat2, lng2]):
        distance = calculate_distance(lat1, lng1, lat2, lng2)
        
        # If very close, check name similarity
        if distance <= distance_threshold:
            name1 = normalize_place_name(place1.get('name', ''))
            name2 = normalize_place_name(place2.get('name', ''))
            
            # High similarity threshold for close places
            similarity = SequenceMatcher(None, name1, name2).ratio()
            if similarity >= 0.8:
                return True
    
    # Exact name match (after normalization)
    name1 = normalize_place_name(place1.get('name', ''))
    name2 = normalize_place_name(place2.get('name', ''))
    
    if name1 and name2 and name1 == name2:
        return True
    
    return False

def combine_places_smart(google_places: List[Dict], yelp_places: List[Dict]) -> List[Dict]:
    """Combine & dedupe using enhanced duplicate detection"""
    all_places = []
    
    # Add Google places
    for place in google_places:
        all_places.append(place)
    
    # Add Yelp places, checking for duplicates
    for yelp_place in yelp_places:
        is_duplicate = False
        
        for i, existing_place in enumerate(all_places):
            if are_places_duplicates(existing_place, yelp_place):
                # Merge Yelp data into existing place
                existing_place["yelp_id"] = yelp_place.get("yelp_id")
                existing_place["yelp_rating"] = yelp_place.get("rating")
                existing_place["review_count"] = yelp_place.get("review_count", 0)
                existing_place["categories"] = list(set(
                    (existing_place.get("categories") or []) + 
                    (yelp_place.get("categories") or [])
                ))
                existing_place["yelp_categories"] = list(set(
                    (existing_place.get("yelp_categories") or []) + 
                    (yelp_place.get("yelp_categories") or [])
                ))
                is_duplicate = True
                break
        
        if not is_duplicate:
            all_places.append(yelp_place)
    
    return all_places


def apply_must_have_filters(places: List[Dict], intent: Dict[str, Any]) -> List[Dict]:
    """Filter places based on strict must-have requirements"""
    filtered_places = []
    
    for place in places:
        # Check if place meets all must-have criteria
        if meets_must_have_requirements(place, intent):
            filtered_places.append(place)
    
    return filtered_places

def meets_must_have_requirements(place: Dict, intent: Dict[str, Any]) -> bool:
    """Check if a place meets all mandatory requirements"""
    
    # Check dietary requirements (strict enforcement)
    dietary_reqs = intent.get('dietary_requirements', [])
    if dietary_reqs:
        place_categories = (place.get('categories', []) + 
                          place.get('yelp_categories', []) + 
                          place.get('types', []))
        place_categories_str = ' '.join(place_categories).lower()
        
        for dietary in dietary_reqs:
            if dietary.lower() == 'vegetarian':
                # Must have vegetarian indicators
                veg_indicators = ['vegetarian', 'vegan', 'plant', 'veggie']
                if not any(indicator in place_categories_str for indicator in veg_indicators):
                    # Check reviews for vegetarian mentions
                    reviews_text = ' '.join([r.get('text', '') for r in place.get('reviews', [])]).lower()
                    if not any(indicator in reviews_text for indicator in veg_indicators):
                        return False
            
            elif dietary.lower() == 'vegan':
                # Must have vegan indicators
                vegan_indicators = ['vegan', 'plant-based']
                if not any(indicator in place_categories_str for indicator in vegan_indicators):
                    reviews_text = ' '.join([r.get('text', '') for r in place.get('reviews', [])]).lower()
                    if not any(indicator in reviews_text for indicator in vegan_indicators):
                        return False
            
            elif dietary.lower() == 'halal':
                # Must have halal indicators
                halal_indicators = ['halal', 'islamic', 'muslim']
                if not any(indicator in place_categories_str for indicator in halal_indicators):
                    reviews_text = ' '.join([r.get('text', '') for r in place.get('reviews', [])]).lower()
                    if not any(indicator in reviews_text for indicator in halal_indicators):
                        return False
    
    # Check cuisine requirements (strict for specific cuisines)
    required_cuisines = intent.get('cuisine_type', [])
    if required_cuisines:
        place_categories = (place.get('categories', []) + 
                          place.get('yelp_categories', []) + 
                          place.get('types', []))
        place_categories_str = ' '.join(place_categories).lower()
        
        cuisine_found = False
        for cuisine in required_cuisines:
            cuisine_indicators = get_cuisine_indicators(cuisine.lower())
            if any(indicator in place_categories_str for indicator in cuisine_indicators):
                cuisine_found = True
                break
        
        if not cuisine_found:
            return False
    
    # Check minimum rating requirements
    min_rating = extract_minimum_rating(intent)
    if min_rating and place.get('rating', 0) < min_rating:
        return False
    
    # Check budget constraints
    budget_pref = intent.get('budget_preference')
    if budget_pref:
        place_price = place.get('price_level', 0)
        if not meets_budget_requirement(place_price, budget_pref):
            return False
    
    return True

def get_cuisine_indicators(cuisine: str) -> List[str]:
    """Get indicators for a specific cuisine type"""
    indicators_map = {
        'indian': ['indian', 'india', 'curry', 'tandoor', 'biryani', 'dosa', 'samosa'],
        'chinese': ['chinese', 'china', 'szechuan', 'cantonese', 'dim sum', 'wok'],
        'italian': ['italian', 'pizza', 'pasta', 'pizzeria', 'trattoria'],
        'mexican': ['mexican', 'taco', 'burrito', 'quesadilla', 'tex-mex'],
        'thai': ['thai', 'thailand', 'pad thai', 'curry', 'som tam'],
        'japanese': ['japanese', 'sushi', 'ramen', 'tempura', 'sashimi'],
        'korean': ['korean', 'korea', 'bbq', 'kimchi', 'bulgogi'],
        'vietnamese': ['vietnamese', 'vietnam', 'pho', 'banh mi'],
        'mediterranean': ['mediterranean', 'greek', 'falafel', 'hummus', 'gyro'],
        'american': ['american', 'burger', 'barbecue', 'steakhouse']
    }
    
    return indicators_map.get(cuisine, [cuisine])

def extract_minimum_rating(intent: Dict[str, Any]) -> float:
    """Extract minimum rating requirement from intent"""
    primary_intent = intent.get('primary_intent', '').lower()
    
    # Look for rating keywords
    if 'highly rated' in primary_intent or 'best' in primary_intent:
        return 4.0
    elif 'good' in primary_intent and 'rating' in primary_intent:
        return 3.5
    elif 'excellent' in primary_intent:
        return 4.5
    
    return 0.0

def meets_budget_requirement(price_level: int, budget_pref: str) -> bool:
    """Check if price level meets budget preference"""
    if not price_level:
        return True  # No price info available
    
    budget_map = {
        'budget': [1],
        'moderate': [1, 2],
        'upscale': [2, 3],
        'luxury': [3, 4]
    }
    
    allowed_levels = budget_map.get(budget_pref.lower(), [1, 2, 3, 4])
    return price_level in allowed_levels


def apply_geographic_diversity_filter(places: List[Dict], max_same_chain: int = 2, min_distance: float = 200) -> List[Dict]:
    """Apply geographic diversity filtering to avoid chain clustering"""
    if not places:
        return places
    
    # Group places by normalized chain name
    chain_groups = {}
    independent_places = []
    
    for place in places:
        normalized_name = normalize_place_name(place.get('name', ''))
        
        # Check if it's a known chain
        is_chain = False
        for chain_name in ['mcdonalds', 'starbucks', 'subway', 'tacobell', 'burgerking', 'pizzahut', 'dominos', 'kfc']:
            if chain_name in normalized_name:
                if chain_name not in chain_groups:
                    chain_groups[chain_name] = []
                chain_groups[chain_name].append(place)
                is_chain = True
                break
        
        if not is_chain:
            independent_places.append(place)
    
    # For each chain, select the best locations with distance constraints
    final_places = independent_places.copy()
    
    for chain_name, chain_places in chain_groups.items():
        # Sort by rating and match score
        chain_places.sort(key=lambda x: (
            x.get('detailed_scoring', {}).get('final_composite_score', 0),
            x.get('rating', 0)
        ), reverse=True)
        
        selected_chain_places = []
        for place in chain_places:
            if len(selected_chain_places) >= max_same_chain:
                break
            
            # Check distance from already selected chain locations
            too_close = False
            for selected in selected_chain_places:
                if places_too_close(place, selected, min_distance):
                    too_close = True
                    break
            
            if not too_close:
                selected_chain_places.append(place)
        
        final_places.extend(selected_chain_places)
    
    return final_places

def places_too_close(place1: Dict, place2: Dict, min_distance: float) -> bool:
    """Check if two places are too close together"""
    loc1 = place1.get('geometry', {}).get('location', {})
    loc2 = place2.get('geometry', {}).get('location', {})
    
    lat1, lng1 = loc1.get('lat'), loc1.get('lng')
    lat2, lng2 = loc2.get('lat'), loc2.get('lng')
    
    if None in [lat1, lng1, lat2, lng2]:
        return False  # Can't determine distance
    
    distance = calculate_distance(lat1, lng1, lat2, lng2)
    return distance < min_distance

def enhanced_scoring(places: List[Dict], intent: Dict[str, Any], user_lat: float = None, user_lng: float = None) -> List[Dict]:
    """Apply constraint-focused scoring algorithm"""
    
    for place in places:
        score = 0
        scoring_breakdown = {}
        
        # 1. CONSTRAINT SATISFACTION (40% weight) - HIGHEST PRIORITY
        constraint_score = calculate_constraint_satisfaction_score(place, intent)
        score += constraint_score * 0.4
        scoring_breakdown['constraints'] = constraint_score * 0.4
        
        # 2. LOCATION CONSTRAINTS (30% weight) - SECOND PRIORITY  
        location_score = calculate_location_constraint_score(place, intent, user_lat, user_lng)
        score += location_score * 0.3
        scoring_breakdown['location'] = location_score * 0.3
        
        # 3. AI RELEVANCE ANALYSIS (20% weight) - THIRD PRIORITY
        ai_score = place.get('match_score', 0)
        score += ai_score * 0.2
        scoring_breakdown['ai_match'] = ai_score * 0.2
        
        # 4. QUALITY INDICATORS (10% weight) - LOWEST PRIORITY (TIEBREAKER)
        quality_score = calculate_quality_score(place)
        score += quality_score * 0.1
        scoring_breakdown['quality'] = quality_score * 0.1
        
        # Update place with new scoring
        place['enhanced_score'] = score
        place['scoring_breakdown'] = scoring_breakdown
    
    return places

def calculate_constraint_satisfaction_score(place: Dict, intent: Dict[str, Any]) -> float:
    """Calculate constraint satisfaction score (0-100) based on primary entity requirements"""
    
    # Get primary entity constraints
    primary_entity = None
    for entity in intent.get('entities', []):
        if entity.get('role') == 'primary':
            primary_entity = entity
            break
    
    if not primary_entity:
        return 80  # High score if no entity structure
    
    constraints = primary_entity.get('constraints', [])
    if not constraints:
        return 85  # High score if no specific constraints
    
    # Create searchable text from place data
    place_text = ' '.join(
        place.get('categories', []) + 
        place.get('yelp_categories', []) + 
        place.get('types', []) +
        [r.get('text', '') for r in place.get('reviews', [])]
    ).lower()
    
    # Check constraint satisfaction with simple word matching
    total_constraints = len(constraints)
    satisfied_constraints = 0
    
    for constraint in constraints:
        if constraint and is_constraint_satisfied(str(constraint), place_text):
            satisfied_constraints += 1
    
    if total_constraints == 0:
        return 85  # High score if no constraints to check
    
    # Calculate satisfaction percentage
    satisfaction_ratio = satisfied_constraints / total_constraints
    
    # Return score 0-100 based on constraint satisfaction
    # If ALL constraints are met = 100 points
    # If NO constraints are met = 0 points
    return satisfaction_ratio * 100

def is_constraint_satisfied(constraint: str, place_text: str) -> bool:
    """Simple constraint matching - check if constraint words appear in place text"""
    constraint_words = constraint.lower().replace('_', ' ').split()
    
    # Check if any significant words from the constraint appear in place text
    for word in constraint_words:
        if len(word) > 2 and word in place_text:
            return True
    
    return False

def calculate_location_constraint_score(place: Dict, intent: Dict[str, Any], user_lat: float = None, user_lng: float = None) -> float:
    """Calculate location constraint satisfaction score (0-100)"""
    
    location_constraints = intent.get('location_constraints', {})
    if not location_constraints:
        return 80  # Default good score if no location constraints
    
    place_location = place.get('geometry', {}).get('location', {})
    place_lat = place_location.get('lat')
    place_lng = place_location.get('lng')
    
    if None in [place_lat, place_lng]:
        return 50  # Medium score if can't determine location
    
    location_type = location_constraints.get('type')
    proximity = location_constraints.get('proximity', 'close')
    
    if location_type == 'near_user' and user_lat and user_lng:
        # Calculate distance from user
        distance = calculate_distance(user_lat, user_lng, place_lat, place_lng)
        
        # Score based on proximity requirement and actual distance
        proximity_scores = {
            'very_close': {'max_distance': 500, 'ideal_distance': 200},
            'close': {'max_distance': 1500, 'ideal_distance': 500},
            'moderate': {'max_distance': 5000, 'ideal_distance': 2000},
            'far': {'max_distance': 20000, 'ideal_distance': 10000}
        }
        
        proximity_config = proximity_scores.get(proximity, proximity_scores['close'])
        max_distance = proximity_config['max_distance']
        ideal_distance = proximity_config['ideal_distance']
        
        if distance <= ideal_distance:
            return 100  # Perfect score for ideal distance
        elif distance <= max_distance:
            # Linear decay from ideal to max distance
            return 100 * (1 - (distance - ideal_distance) / (max_distance - ideal_distance))
        else:
            return 0  # Too far
    
    elif location_type == 'specific_area':
        # For specific areas, assume places found in search are reasonably located
        return 90  # High score since search was area-specific
    
    return 70  # Default score for other cases

def calculate_quality_score(place: Dict) -> float:
    """Calculate quality score (0-100) based on rating and review count"""
    rating = place.get('rating', 0)
    review_count = place.get('review_count', 0)
    
    if rating == 0:
        return 50  # Default score if no rating
    
    # Base score from rating (0-5 stars -> 0-100 points)
    base_score = (rating / 5.0) * 100
    
    # Confidence factor based on review count
    confidence = min(1.0, review_count / 50)  # Full confidence at 50+ reviews
    
    # Apply confidence to base score
    return base_score * confidence

def calculate_review_relevance_score(place: Dict, intent: Dict[str, Any]) -> float:
    """Calculate relevance score based on review content - generic approach"""
    reviews = place.get('reviews', [])
    if not reviews:
        return 5  # Default score if no reviews
    
    # Collect all intent keywords dynamically
    relevance_keywords = []
    for key, value in intent.items():
        if value and key not in ['primary_intent', 'confidence', 'location_specific']:
            if isinstance(value, list):
                relevance_keywords.extend([str(v) for v in value if v])
            elif isinstance(value, str):
                relevance_keywords.append(value)
    
    if not relevance_keywords:
        return 10  # Default score if no specific keywords
    
    relevant_mentions = 0
    total_reviews = len(reviews)
    
    for review in reviews:
        review_text = review.get('text', '').lower()
        for keyword in relevance_keywords:
            if keyword.lower() in review_text:
                relevant_mentions += 1
                break  # Count each review only once
    
    # Score based on percentage of relevant reviews
    relevance_ratio = relevant_mentions / total_reviews if total_reviews > 0 else 0
    return relevance_ratio * 20  # Max 20 points


def get_all_reviews(place: Dict) -> List[Dict]:
    """Fetch up to ~3 reviews from Google details (v1) and Yelp if available."""
    reviews: list[dict] = []

    # Google reviews (best-effort; requires the "reviews" field in FieldMask)
    gpid = place.get("google_place_id") or place.get("place_id")
    if gpid and isinstance(gpid, str) and gpid.startswith("places/"):
        try:
            details = gplaces_get_details(gpid)
            for rv in details.get("reviews", [])[:5]:
                reviews.append(
                    {
                        "text": (rv.get("text") or {}).get("text", ""),
                        "rating": rv.get("rating", 0),
                        "source": "google",
                        "author": (rv.get("authorAttribution") or {}).get("displayName"),
                    }
                )
        except Exception as e:
            print("Google reviews fetch error:", e)

    # Yelp reviews
    if place.get("yelp_id") and YELP_API_KEY:
        headers = {"Authorization": f"Bearer {YELP_API_KEY}"}
        try:
            r = requests.get(f"{YELP_BUSINESS_BASE}/{place['yelp_id']}/reviews", headers=headers, timeout=25)
            data = r.json()
            for rv in data.get("reviews", [])[:5]:
                reviews.append(
                    {
                        "text": rv.get("text", ""),
                        "rating": rv.get("rating", 0),
                        "source": "yelp",
                        "author": rv.get("user", {}).get("name", "Anonymous"),
                    }
                )
        except Exception as e:
            print("Yelp reviews fetch error:", e)

    return reviews


# ==========================
# Main
# ==========================
if __name__ == "__main__":
    # On Windows this will bind cleanly; if port 5000 is in use, change to 5001.
    app.run(debug=True, port=5000, host="127.0.0.1")
