"""
ChatGPT integration for intelligent place suggestions
Validates location queries and generates specific place recommendations
"""

import json
import openai
from typing import Dict, List, Any, Optional
import os
from dotenv import load_dotenv

load_dotenv()

class ChatGPTPlacesSuggester:
    """Uses ChatGPT to suggest specific places based on user queries"""
    
    def __init__(self):
        self.client = openai.OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
    
    def validate_location_query(self, query: str) -> Dict[str, Any]:
        """Validate that the query is location-related and safe"""
        
        system_prompt = """You are a query validator for a location search app. 
        
        Your job is to determine if a user query is:
        1. Related to finding places/locations
        2. Safe and appropriate
        3. Not asking for harmful, illegal, or inappropriate content
        
        Return JSON with this structure:
        {
            "is_valid": true/false,
            "is_location_related": true/false,
            "reason": "explanation if invalid",
            "cleaned_query": "clean version of query if valid"
        }
        
        VALID examples:
        - "restaurants near me"
        - "coffee shops in Dallas"
        - "hotels with pools"
        - "places to study"
        - "kid-friendly restaurants"
        
        INVALID examples:
        - "how to make bombs"
        - "best way to hack"
        - "write my essay"
        - general questions not about places
        """
        
        try:
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Validate this query: '{query}'"}
                ],
                temperature=0.1,
                max_tokens=200
            )
            
            result = response.choices[0].message.content.strip()
            if result.startswith('```json'):
                result = result[7:-3]
            elif result.startswith('```'):
                result = result[3:-3]
            
            return json.loads(result)
            
        except Exception as e:
            print(f"Query validation error: {e}")
            return {
                "is_valid": False,
                "is_location_related": False,
                "reason": "Unable to validate query",
                "cleaned_query": query
            }
    
    def suggest_places(self, query: str, location: str = None) -> List[Dict[str, Any]]:
        """Find real places in Dallas metro that actually meet requirements with proof"""
        
        system_prompt = """You are a Dallas metro expert. Parse the query, understand requirements, find REAL places that actually have those features.

**Dallas Metro Areas:** Dallas, Frisco, Plano, Arlington, Irving, Fort Worth, Richardson, Garland, McKinney, Allen, Addison, Carrollton, Lewisville, Flower Mound, Grapevine, Southlake, Colleyville, Mesquite, Denton, Cedar Hill, DeSoto, Duncanville, Grand Prairie, Euless, Bedford, Hurst, Coppell, Farmers Branch, University Park, Highland Park, Rowlett, Wylie, Rockwall, The Colony, Little Elm, Prosper, Celina

Return JSON:
{
    "suggestions": [
        {
            "name": "Exact business name",
            "type": "restaurant|cafe|hotel|gym|library|etc",
            "area": "Specific Dallas metro city", 
            "proof": "Evidence this place has the required features"
        }
    ]
}

Only suggest places you know actually meet the specific requirements."""
        
        user_prompt = f"""Query: "{query}"
Location context: {location or "Dallas metro area"}

Parse this query to understand:
1. What type of place they want
2. What specific requirements/constraints they have  
3. Location requirements:
   - If specific Dallas area mentioned (Frisco, Arlington, etc.) → focus on that area
   - If "near me" mentioned → focus on areas close to user's current location
   - If no location specified → search across Dallas metro

Find REAL places in Dallas metro that actually have the required features. Provide proof for each suggestion.

Return 8-12 real places with evidence they meet requirements."""
        
        try:
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.3,
                max_tokens=800
            )
            
            result = response.choices[0].message.content.strip()
            if result.startswith('```json'):
                result = result[7:-3]
            elif result.startswith('```'):
                result = result[3:-3]
            
            data = json.loads(result)
            return data.get('suggestions', [])
            
        except Exception as e:
            print(f"ChatGPT place suggestion error: {e}")
            return []
    
    def enhance_search_strategy(self, query: str, suggestions: List[Dict]) -> Dict[str, Any]:
        """Create an enhanced search strategy based on ChatGPT suggestions"""
        
        return {
            "primary_searches": [
                suggestion["name"] for suggestion in suggestions[:6]
            ],
            "fallback_searches": [
                f"{suggestion['type']} {' '.join(suggestion.get('likely_features', []))}"
                for suggestion in suggestions[:3]
            ],
            "search_terms": list(set([
                suggestion["type"] for suggestion in suggestions
            ])),
            "expected_features": list(set([
                feature for suggestion in suggestions
                for feature in suggestion.get('likely_features', [])
            ]))
        }