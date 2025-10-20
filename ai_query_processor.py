"""
AI-powered query understanding using OpenAI
Replaces pattern matching with intelligent natural language processing
"""

import json
import openai
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
import os
from dotenv import load_dotenv

load_dotenv()

class AIQueryProcessor:
    """Uses OpenAI to understand and extract intent from place search queries"""
    
    def __init__(self):
        self.client = openai.OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
    
    def extract_intent(self, query: str) -> Dict[str, Any]:
        """Extract structured intent from natural language query with multi-entity and spatial analysis"""
        
        system_prompt = """You are an expert at understanding complex place search queries. 
        Analyze queries to extract entities, constraints, and spatial relationships.
        
        Return a JSON object with this exact structure:
        {
            "query_type": "single_entity|multi_entity",
            "entities": [
                {
                    "type": "restaurant|cafe|gym|park|hotel|library|etc",
                    "role": "primary|reference",
                    "constraints": [
                        "any requirement or feature mentioned in the query",
                        "examples: stroller_parking, fiction_books, vegetarian_options, wifi, family_friendly, etc"
                    ]
                }
            ],
            "spatial_relationships": [
                {
                    "primary_entity": "restaurant",
                    "relationship": "near|close_to|within_walking_distance|in_same_area",
                    "reference_entity": "park",
                    "max_distance_meters": 500
                }
            ] or null,
            "location_constraints": {
                "type": "near_user|specific_area|relative_to_entity",
                "value": "frisco|dallas|current_location",
                "proximity": "very_close|close|moderate|far" or null
            },
            "primary_intent": "brief description of what user wants",
            "confidence": "high|medium|low"
        }
        
        EXAMPLES:
        
        Query: "family friendly restaurant near a park with playground"
        - query_type: "multi_entity"
        - entities: [
            {"type": "restaurant", "role": "primary", "constraints": ["family_friendly"]},
            {"type": "park", "role": "reference", "constraints": ["playground"]}
          ]
        - spatial_relationships: [{"primary_entity": "restaurant", "relationship": "near", "reference_entity": "park", "max_distance_meters": 500}]
        
        Query: "restaurant with stroller parking near me"
        - query_type: "single_entity"
        - entities: [{"type": "restaurant", "role": "primary", "constraints": ["stroller_parking"]}]
        - location_constraints: {"type": "near_user", "value": "current_location", "proximity": "close"}
        
        Query: "library with fiction books in downtown"
        - query_type: "single_entity"
        - entities: [{"type": "library", "role": "primary", "constraints": ["fiction_books"]}]
        - location_constraints: {"type": "specific_area", "value": "downtown"}
        
        Query: "indian vegetarian restaurants in frisco"
        - query_type: "single_entity"
        - entities: [{"type": "restaurant", "role": "primary", "constraints": ["indian_cuisine", "vegetarian_options"]}]
        - location_constraints: {"type": "specific_area", "value": "frisco"}
        """
        
        user_prompt = f"""Extract intent from this place search query: "{query}"
        
        Analyze intelligently:
        1. How many entities/places are mentioned? (single_entity or multi_entity)
        2. For each entity, what type is it? (restaurant, park, library, gym, hotel, etc.)
        3. What are the specific requirements/constraints for each entity?
        4. Are there spatial relationships between entities? (near, close to, etc.)
        5. What are the location constraints? (near me, in Dallas, downtown, etc.)
        
        Extract constraints as simple, searchable terms:
        - "restaurant with stroller parking and changing table" → constraints: ["stroller_parking", "changing_table"]
        - "family friendly restaurant" → constraints: ["family_friendly"]
        - "library with fiction books" → constraints: ["fiction_books"] 
        - "park with playground and swings" → constraints: ["playground", "swings"]
        - "indian vegetarian restaurant" → constraints: ["indian_cuisine", "vegetarian_options"]
        - "hotels with ev charging" → constraints: ["ev_charging"]
        - "hotels with pools and gyms" → constraints: ["pool", "gym"]
        
        Focus on:
        1. What type of place they want
        2. Any cuisine or specific requirements
        3. Location preferences
        4. Specific foods/drinks/services mentioned
        5. Atmosphere or features needed
        
        Return only the JSON object, no explanation."""
        
        try:
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.1,
                max_tokens=500
            )
            
            result = response.choices[0].message.content.strip()
            
            # Extract JSON from response
            if result.startswith('```json'):
                result = result[7:-3]
            elif result.startswith('```'):
                result = result[3:-3]
            
            return json.loads(result)
            
        except Exception as e:
            print(f"OpenAI API error: {e}")
            return self._fallback_extraction(query)
    
    def _fallback_extraction(self, query: str) -> Dict[str, Any]:
        """Fallback pattern matching if OpenAI fails"""
        query_lower = query.lower()
        
        # Basic fallback
        result = {
            "place_category": "restaurant",
            "specific_type": None,
            "cuisine_type": None,
            "subcuisine": None,
            "dietary_requirements": None,
            "specific_foods_drinks": None,
            "atmosphere_preferences": None,
            "features_needed": None,
            "location_specific": None,
            "budget_preference": None,
            "time_constraints": None,
            "primary_intent": query,
            "confidence": "low"
        }
        
        # Basic cuisine detection
        if 'indian' in query_lower:
            result['cuisine_type'] = ['indian']
        if 'vegetarian' in query_lower:
            result['dietary_requirements'] = ['vegetarian']
        if 'frisco' in query_lower:
            result['location_specific'] = 'frisco'
        
        return result
    
    def build_search_parameters(self, intent: Dict[str, Any]) -> Dict[str, Any]:
        """Build API search parameters from extracted intent with multi-entity support"""
        
        # Get primary entity (the one user wants to find)
        primary_entity = None
        for entity in intent.get('entities', []):
            if entity.get('role') == 'primary':
                primary_entity = entity
                break
        
        if not primary_entity:
            # Fallback for single entity
            primary_entity = intent.get('entities', [{}])[0]
        
        google_params = {
            'query': self._build_google_query(intent, primary_entity),
            'type': 'establishment'
        }
        
        yelp_params = {
            'term': self._build_yelp_term(intent, primary_entity),
            'sort_by': 'rating'
        }
        
        # Add location constraints
        location_constraints = intent.get('location_constraints', {})
        if location_constraints:
            location_type = location_constraints.get('type')
            location_value = location_constraints.get('value')
            
            if location_type == 'specific_area' and location_value:
                google_params['query'] += f" {location_value}"
                yelp_params['location'] = f"{location_value}, TX"
        
        return {
            'google': google_params,
            'yelp': yelp_params,
            'intent': intent
        }
    
    def _build_google_query(self, intent: Dict[str, Any], primary_entity: Dict[str, Any]) -> str:
        """Build Google Places search query focused on primary entity"""
        entity_type = primary_entity.get('type', 'restaurant')
        
        # Special handling for hotels - search for entity type only to avoid getting charging stations
        if entity_type.lower() == 'hotel':
            return 'hotel'
        
        # For other entity types, include constraints in search
        parts = [entity_type]
        constraints = primary_entity.get('constraints', [])
        for constraint in constraints:
            if constraint:
                parts.append(str(constraint))
        
        return ' '.join(parts)
    
    def _build_yelp_term(self, intent: Dict[str, Any], primary_entity: Dict[str, Any]) -> str:
        """Build Yelp search term focused on primary entity"""
        entity_type = primary_entity.get('type', 'restaurant')
        
        # Special handling for hotels - search for entity type only to avoid getting charging stations
        if entity_type.lower() == 'hotel':
            return 'hotel'
        
        # For other entity types, include constraints in search
        parts = [entity_type]
        constraints = primary_entity.get('constraints', [])
        for constraint in constraints:
            if constraint:
                parts.append(str(constraint))
        
        return ' '.join(parts)
    
    
    def analyze_place_relevance(self, place: Dict, intent: Dict[str, Any]) -> Dict[str, Any]:
        """Use AI to analyze how well a place matches the intent"""
        
        # Prepare place information for AI analysis
        place_info = {
            'name': place.get('name'),
            'categories': place.get('categories', []),
            'yelp_categories': place.get('yelp_categories', []),
            'types': place.get('types', []),
            'address': place.get('address'),
            'rating': place.get('rating'),
            'review_count': place.get('review_count', 0),
            'reviews': [r.get('text', '') for r in place.get('reviews', [])[:10]]
        }
        
        system_prompt = """You are an expert at matching places to user requirements. Analyze places based on all available information including categories, reviews, and context.

        GUIDELINES:
        - Use categories, reviews, and place information to determine if requirements are met
        - Consider real-world knowledge about what different types of establishments typically offer
        - Look for evidence in reviews and descriptions rather than relying only on category labels
        - Be intelligent about dietary requirements - many restaurants serve options they don't explicitly advertise
        - Score based on likelihood that user needs will be satisfied at this establishment
        
        Return JSON with this structure:
        {
            "is_match": true/false,
            "confidence": "high|medium|low", 
            "match_score": 0-100,
            "specific_matches": {
                "cuisine_match": true/false,
                "dietary_match": true/false,
                "location_match": true/false,
                "specific_items_match": true/false
            },
            "match_reasons": ["reason1", "reason2"],
            "concerns": ["concern1", "concern2"] or null,
            "relevant_review_quotes": ["quote1", "quote2"] or null
        }
        """
        
        user_prompt = f"""
        User Intent: {json.dumps(intent, indent=2)}
        
        Place Information: {json.dumps(place_info, indent=2)}
        
        Analyze comprehensively:
        1. Does this place match what the user is looking for based on all available information?
        2. Check categories, reviews, and place type against user requirements
        3. Look for evidence in reviews that supports or contradicts the match
        4. Consider what this type of establishment typically offers
        5. Score based on likelihood of user satisfaction
        
        **CRITICAL: EVIDENCE-BASED ANALYSIS REQUIRED**
        
        You MUST find explicit evidence in reviews, descriptions, or categories to mark specific amenities as available.
        DO NOT make assumptions based on establishment type alone.
        
        **For specific amenities/features, look for explicit mentions:**
        
        **Changing Stations/Baby Facilities:** Look for:
        - "changing station", "changing table", "baby changing", "diaper changing"
        - "family restroom", "baby-friendly bathroom", "baby facilities"
        - "stroller friendly", "high chairs", "booster seats"
        - If NO explicit mention found, mark specific_items_match: false
        
        **EV Charging:** Look for:
        - "EV", "electric vehicle", "Tesla", "charging station", "car charging", "vehicle charging"
        - "ChargePoint", "Blink", "Electrify America" (charging networks)
        - If NO explicit mention found, mark specific_items_match: false
        
        **Other Amenities:** Look for explicit mentions only:
        - Pools: "pool", "swimming", "aquatic center"
        - Gyms: "fitness", "workout", "gym", "exercise equipment"
        - WiFi: "wifi", "internet", "wireless"
        
        **SCORING RULES:**
        - specific_items_match: true ONLY if you find explicit evidence in reviews/descriptions
        - If no evidence found for required amenities, score 30% or lower
        - Include relevant quotes that support your findings
        - Be honest about lack of evidence rather than making assumptions
        """
        
        try:
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.1,
                max_tokens=400
            )
            
            result = response.choices[0].message.content.strip()
            
            # Extract JSON
            if result.startswith('```json'):
                result = result[7:-3]
            elif result.startswith('```'):
                result = result[3:-3]
            
            return json.loads(result)
            
        except Exception as e:
            print(f"AI analysis error: {e}")
            return self._fallback_analysis(place, intent)
    
    def _fallback_analysis(self, place: Dict, intent: Dict[str, Any]) -> Dict[str, Any]:
        """Fallback analysis if AI fails"""
        return {
            "is_match": True,
            "confidence": "low",
            "match_score": 50,
            "specific_matches": {
                "cuisine_match": False,
                "dietary_match": False,
                "location_match": False,
                "specific_items_match": False
            },
            "match_reasons": ["Fallback match"],
            "concerns": ["Unable to perform AI analysis"],
            "relevant_review_quotes": []
        }