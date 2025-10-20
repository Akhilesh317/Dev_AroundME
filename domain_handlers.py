"""
Domain-specific handlers for place search
Each handler knows how to search, validate, and score places for its domain
"""

from typing import Dict, List, Any, Optional
from abc import ABC, abstractmethod
import re
from universal_search import PlaceDomain, ParsedQuery

class DomainHandler(ABC):
    """Abstract base class for domain handlers"""
    
    @abstractmethod
    def build_search_terms(self, parsed: ParsedQuery) -> Dict[str, Any]:
        """Build API-specific search parameters"""
        pass
    
    @abstractmethod
    def validate_place(self, place: Dict, parsed: ParsedQuery) -> bool:
        """Validate if a place matches the query requirements"""
        pass
    
    @abstractmethod
    def score_place(self, place: Dict, parsed: ParsedQuery) -> Dict[str, Any]:
        """Score how well a place matches the query"""
        pass
    
    @abstractmethod
    def get_category_mappings(self) -> Dict[str, List[str]]:
        """Get category mappings for this domain"""
        pass

class FoodDomainHandler(DomainHandler):
    """Handler for food/restaurant domain"""
    
    def __init__(self):
        self.cuisine_categories = {
            'indian': ['indpak', 'indian', 'pakistani', 'bangladeshi', 'indian_restaurant'],
            'chinese': ['chinese', 'szechuan', 'cantonese', 'dimsum'],
            'italian': ['italian', 'pizza', 'pasta'],
            'mexican': ['mexican', 'tex-mex', 'tacos'],
            'japanese': ['japanese', 'sushi', 'ramen', 'izakaya'],
            'thai': ['thai', 'thai_restaurant'],
            'vietnamese': ['vietnamese', 'pho'],
            'korean': ['korean', 'bbq_korean'],
            'mediterranean': ['mediterranean', 'greek', 'middle_eastern'],
            'american': ['american', 'newamerican', 'tradamerican', 'burgers']
        }
        
        self.negative_indicators = {
            'indian': ['mexican', 'italian', 'chinese', 'japanese', 'thai', 'vietnamese', 'french', 'american'],
            'vegetarian': ['steakhouse', 'bbq', 'seafood', 'chicken', 'wings'],
            'vegan': ['steakhouse', 'bbq', 'seafood', 'dairy']
        }
    
    def build_search_terms(self, parsed: ParsedQuery) -> Dict[str, Any]:
        """Build search terms for food domain"""
        search_params = {
            'google': {},
            'yelp': {}
        }
        
        # Build Google search terms
        google_terms = []
        yelp_terms = []
        
        # Add cuisine if specified
        if 'cuisine' in parsed.attributes:
            cuisines = parsed.attributes['cuisine']
            google_terms.extend(cuisines)
            yelp_terms.extend(cuisines)
            
            # For Yelp, use category codes
            yelp_categories = []
            for cuisine in cuisines:
                if cuisine in self.cuisine_categories:
                    yelp_categories.extend(self.cuisine_categories[cuisine])
            if yelp_categories:
                search_params['yelp']['categories'] = ','.join(yelp_categories[:3])
        
        # Add dietary preferences
        if 'dietary' in parsed.attributes:
            dietary = parsed.attributes['dietary']
            google_terms.extend(dietary)
            yelp_terms.extend(dietary)
        
        # Add place type
        if parsed.place_types:
            google_terms.append(parsed.place_types[0].replace('_', ' '))
        else:
            google_terms.append('restaurant')
        
        # Add specific items (like "tea", "dosa")
        if parsed.specific_items:
            google_terms.extend(parsed.specific_items)
            yelp_terms.extend(parsed.specific_items)
        
        # Extract city from location modifiers
        city = None
        for modifier in parsed.location_modifiers:
            if modifier.startswith('city:'):
                city = modifier.replace('city:', '').strip()
                break
        
        # Build search strings with location
        base_google_query = ' '.join(google_terms)
        base_yelp_term = ' '.join(yelp_terms) if yelp_terms else ' '.join(google_terms)
        
        if city:
            search_params['google']['query'] = f"{base_google_query} {city}"
            search_params['yelp']['location'] = city
            search_params['yelp']['term'] = base_yelp_term
        else:
            search_params['google']['query'] = base_google_query
            search_params['yelp']['term'] = base_yelp_term
        
        search_params['google']['type'] = 'restaurant'
        
        return search_params
    
    def validate_place(self, place: Dict, parsed: ParsedQuery) -> bool:
        """Validate if a restaurant matches requirements"""
        
        # Check if place has required attributes
        if 'cuisine' in parsed.attributes:
            required_cuisines = parsed.attributes['cuisine']
            
            # Check in categories
            place_categories = place.get('categories', [])
            place_types = place.get('types', [])
            
            # Combine all category info
            all_categories = ' '.join([str(c).lower() for c in place_categories + place_types])
            
            # Check place name
            place_name = place.get('name', '').lower()
            
            # Check if it's the right cuisine
            cuisine_match = False
            for cuisine in required_cuisines:
                # Direct category match
                if cuisine in all_categories or cuisine in place_name:
                    cuisine_match = True
                    break
                    
                # Check category mappings
                if cuisine in self.cuisine_categories:
                    for cat_variant in self.cuisine_categories[cuisine]:
                        if cat_variant in all_categories:
                            cuisine_match = True
                            break
            
            if not cuisine_match:
                # Check for negative indicators
                for cuisine in required_cuisines:
                    if cuisine in self.negative_indicators:
                        for negative in self.negative_indicators[cuisine]:
                            if negative in all_categories or negative in place_name:
                                return False  # Definitely wrong cuisine
                
                # If no positive match and name doesn't suggest it, likely wrong
                if not any(cuisine in place_name for cuisine in required_cuisines):
                    return False
        
        # Dietary validation
        if 'dietary' in parsed.attributes:
            dietary_prefs = parsed.attributes['dietary']
            
            # Check if place explicitly contradicts dietary preferences
            place_name = place.get('name', '').lower()
            place_desc = ' '.join([str(r.get('text', '')).lower() for r in place.get('reviews', [])])
            
            for pref in dietary_prefs:
                if pref == 'vegetarian':
                    # Reject steakhouses, BBQ places, etc.
                    if any(word in place_name.lower() for word in ['steakhouse', 'bbq', 'chicken', 'seafood']):
                        return False
                elif pref == 'vegan':
                    if any(word in place_name.lower() for word in ['steakhouse', 'bbq', 'dairy', 'creamery']):
                        return False
        
        return True
    
    def score_place(self, place: Dict, parsed: ParsedQuery) -> Dict[str, Any]:
        """Score a restaurant based on query match - Rating prioritized"""
        base_score = 0
        match_reasons = []
        confidence = 'low'
        
        # Start with rating as foundation (30 points max)
        rating = place.get('rating', 0)
        rating_score = 0
        if rating >= 4.5:
            rating_score = 30
            match_reasons.append(f"Excellent rating ({rating}/5)")
        elif rating >= 4.0:
            rating_score = 25
            match_reasons.append(f"Very good rating ({rating}/5)")
        elif rating >= 3.5:
            rating_score = 20
            match_reasons.append(f"Good rating ({rating}/5)")
        elif rating >= 3.0:
            rating_score = 10
        
        base_score += rating_score
        
        # Location match bonus (20 points max)
        location_score = self._score_location_match(place, parsed)
        base_score += location_score
        if location_score > 15:
            match_reasons.append("Located in requested area")
        
        # Cuisine match (25 points max)
        cuisine_score = 0
        if 'cuisine' in parsed.attributes:
            cuisine_score = self._score_cuisine_match(place, parsed.attributes['cuisine'])
            base_score += cuisine_score
            if cuisine_score > 20:
                match_reasons.append(f"Confirmed {', '.join(parsed.attributes['cuisine'])} cuisine")
                confidence = 'high'
            elif cuisine_score > 10:
                match_reasons.append(f"Likely {', '.join(parsed.attributes['cuisine'])} restaurant")
                confidence = 'medium'
        
        # Dietary match (15 points max)
        dietary_score = 0
        if 'dietary' in parsed.attributes:
            dietary_score = self._score_dietary_match(place, parsed.attributes['dietary'])
            base_score += dietary_score
            if dietary_score > 8:
                match_reasons.append(f"{', '.join(parsed.attributes['dietary'])} options confirmed")
        
        # Specific items match (10 points max)
        items_score = 0
        if parsed.specific_items:
            items_score = self._score_specific_items(place, parsed.specific_items)
            base_score += items_score
            if items_score > 5:
                matched_items = [item for item in parsed.specific_items 
                                if self._check_item_in_place(place, item)]
                if matched_items:
                    match_reasons.append(f"Serves {', '.join(matched_items)}")
        
        # Review count bonus
        review_count = place.get('review_count', 0)
        if review_count > 50:
            base_score += 5
            match_reasons.append(f"Well-reviewed ({review_count} reviews)")
        
        # Calculate final score with rating emphasis
        final_score = min(base_score, 100)
        
        return {
            'score': final_score,
            'match_reasons': match_reasons,
            'confidence': confidence,
            'breakdown': {
                'rating_score': rating_score,
                'location_score': location_score,
                'cuisine_score': cuisine_score,
                'dietary_score': dietary_score,
                'items_score': items_score
            }
        }
    
    def _score_location_match(self, place: Dict, parsed: ParsedQuery) -> int:
        """Score how well place matches requested location"""
        score = 0
        
        # Check if specific city was requested
        requested_cities = []
        for modifier in parsed.location_modifiers:
            if modifier.startswith('city:'):
                requested_cities.append(modifier.replace('city:', '').strip())
        
        if requested_cities:
            place_address = place.get('address', '').lower()
            for city in requested_cities:
                if city.lower() in place_address:
                    score += 20  # Perfect city match
                    break
            else:
                # If requested city not in address, penalize
                score -= 10
        
        return score
    
    def _score_cuisine_match(self, place: Dict, required_cuisines: List[str]) -> int:
        """Score cuisine match (40 points max)"""
        score = 0
        place_name = place.get('name', '').lower()
        place_categories = ' '.join([str(c).lower() for c in place.get('categories', [])])
        place_types = ' '.join([str(t).lower() for t in place.get('types', [])])
        
        for cuisine in required_cuisines:
            # Name match (strongest signal)
            if cuisine in place_name:
                score += 20
            
            # Category match
            if cuisine in place_categories or cuisine in place_types:
                score += 15
            
            # Check mapped categories
            if cuisine in self.cuisine_categories:
                for cat in self.cuisine_categories[cuisine]:
                    if cat in place_categories:
                        score += 10
                        break
            
            # Review mentions
            reviews_text = ' '.join([r.get('text', '').lower() for r in place.get('reviews', [])])
            if reviews_text and cuisine in reviews_text:
                score += 5
        
        return min(40, score)
    
    def _score_dietary_match(self, place: Dict, dietary_prefs: List[str]) -> int:
        """Score dietary preferences match (20 points max)"""
        score = 0
        reviews_text = ' '.join([r.get('text', '').lower() for r in place.get('reviews', [])])
        place_name = place.get('name', '').lower()
        
        for pref in dietary_prefs:
            if pref in place_name:
                score += 10
            elif pref in reviews_text:
                score += 7
        
        return min(20, score)
    
    def _score_specific_items(self, place: Dict, items: List[str]) -> int:
        """Score specific item mentions (15 points max)"""
        score = 0
        reviews_text = ' '.join([r.get('text', '').lower() for r in place.get('reviews', [])])
        place_name = place.get('name', '').lower()
        
        # Enhanced item checking with synonyms
        item_synonyms = {
            'tea': ['tea', 'chai', 'masala tea', 'ginger tea'],
            'south indian': ['dosa', 'idli', 'sambar', 'vada', 'uttapam', 'south indian', 'chettinad'],
            'coffee': ['coffee', 'espresso', 'cappuccino', 'latte']
        }
        
        for item in items:
            # Direct match
            if item.lower() in reviews_text or item.lower() in place_name:
                score += 8
            else:
                # Check synonyms
                synonyms = item_synonyms.get(item.lower(), [item.lower()])
                for synonym in synonyms:
                    if synonym in reviews_text or synonym in place_name:
                        score += 6
                        break
        
        return min(15, score)
    
    def _check_item_in_place(self, place: Dict, item: str) -> bool:
        """Check if an item is mentioned in place data"""
        reviews_text = ' '.join([r.get('text', '').lower() for r in place.get('reviews', [])])
        return item.lower() in reviews_text
    
    def _score_features(self, place: Dict, features: List[str]) -> int:
        """Score feature matches (10 points max)"""
        score = 0
        for feature in features:
            if self._check_feature_in_place(place, feature):
                score += 5
        return min(10, score)
    
    def _check_feature_in_place(self, place: Dict, feature: str) -> bool:
        """Check if a feature is available"""
        reviews_text = ' '.join([r.get('text', '').lower() for r in place.get('reviews', [])])
        return feature.lower() in reviews_text
    
    def _check_ambiance(self, place: Dict, ambiance: str) -> bool:
        """Check if place has specified ambiance"""
        reviews_text = ' '.join([r.get('text', '').lower() for r in place.get('reviews', [])])
        return ambiance.lower() in reviews_text
    
    def get_category_mappings(self) -> Dict[str, List[str]]:
        """Get category mappings for food domain"""
        return self.cuisine_categories


class StudyWorkDomainHandler(DomainHandler):
    """Handler for study/work places"""
    
    def build_search_terms(self, parsed: ParsedQuery) -> Dict[str, Any]:
        """Build search terms for study/work domain"""
        search_params = {
            'google': {
                'query': 'coffee shop wifi quiet study',
                'type': 'cafe'
            },
            'yelp': {
                'term': 'coffee wifi study',
                'categories': 'coffee,cafes'
            }
        }
        
        if 'study_features' in parsed.attributes:
            features = ' '.join(parsed.attributes['study_features'])
            search_params['google']['query'] = f"coffee shop {features}"
            search_params['yelp']['term'] = f"cafe {features}"
        
        return search_params
    
    def validate_place(self, place: Dict, parsed: ParsedQuery) -> bool:
        """Validate study/work place"""
        # Accept cafes, coffee shops, libraries
        place_types = place.get('types', [])
        place_categories = place.get('categories', [])
        
        valid_types = ['cafe', 'coffee', 'library', 'coworking']
        all_categories = ' '.join([str(c).lower() for c in place_categories + place_types])
        
        return any(vt in all_categories for vt in valid_types)
    
    def score_place(self, place: Dict, parsed: ParsedQuery) -> Dict[str, Any]:
        """Score study/work place"""
        score = 0
        match_reasons = []
        
        # Check for WiFi (critical for study)
        reviews_text = ' '.join([r.get('text', '').lower() for r in place.get('reviews', [])])
        
        if 'wifi' in reviews_text or 'internet' in reviews_text:
            score += 30
            match_reasons.append("Has WiFi")
        
        if 'quiet' in reviews_text:
            score += 20
            match_reasons.append("Quiet environment")
        
        if any(word in reviews_text for word in ['study', 'work', 'laptop']):
            score += 20
            match_reasons.append("Good for studying/working")
        
        if 'outlet' in reviews_text or 'power' in reviews_text:
            score += 10
            match_reasons.append("Has power outlets")
        
        # Rating bonus
        rating = place.get('rating', 0)
        if rating >= 4.0:
            score += 10
            match_reasons.append(f"Highly rated ({rating}/5)")
        
        return {
            'score': min(score, 100),
            'match_reasons': match_reasons,
            'confidence': 'high' if score > 50 else 'medium'
        }
    
    def get_category_mappings(self) -> Dict[str, List[str]]:
        return {
            'cafe': ['coffee', 'coffeeshop', 'cafe'],
            'library': ['library', 'libraries'],
            'coworking': ['coworking', 'shared_office']
        }


class FitnessDomainHandler(DomainHandler):
    """Handler for fitness/gym places"""
    
    def build_search_terms(self, parsed: ParsedQuery) -> Dict[str, Any]:
        """Build search terms for fitness domain"""
        equipment = parsed.attributes.get('equipment', [])
        
        search_params = {
            'google': {
                'query': f"gym {' '.join(equipment)}" if equipment else 'gym fitness center',
                'type': 'gym'
            },
            'yelp': {
                'term': f"gym {' '.join(equipment)}" if equipment else 'gym',
                'categories': 'gyms,fitness'
            }
        }
        
        return search_params
    
    def validate_place(self, place: Dict, parsed: ParsedQuery) -> bool:
        """Validate fitness place"""
        place_types = place.get('types', [])
        place_categories = place.get('categories', [])
        all_categories = ' '.join([str(c).lower() for c in place_categories + place_types])
        
        valid_types = ['gym', 'fitness', 'health_club', 'yoga', 'pilates', 'crossfit']
        return any(vt in all_categories for vt in valid_types)
    
    def score_place(self, place: Dict, parsed: ParsedQuery) -> Dict[str, Any]:
        """Score fitness place"""
        score = 0
        match_reasons = []
        
        reviews_text = ' '.join([r.get('text', '').lower() for r in place.get('reviews', [])])
        
        # Check for requested equipment
        if 'equipment' in parsed.attributes:
            for equipment in parsed.attributes['equipment']:
                if equipment.lower() in reviews_text:
                    score += 20
                    match_reasons.append(f"Has {equipment}")
        
        # Check for 24-hour
        if '24' in reviews_text or '24 hour' in reviews_text or '24/7' in reviews_text:
            score += 15
            match_reasons.append("24-hour access")
        
        # Rating
        rating = place.get('rating', 0)
        if rating >= 4.0:
            score += 10
            match_reasons.append(f"Highly rated ({rating}/5)")
        
        return {
            'score': min(score, 100),
            'match_reasons': match_reasons,
            'confidence': 'high' if score > 40 else 'medium'
        }
    
    def get_category_mappings(self) -> Dict[str, List[str]]:
        return {
            'gym': ['gym', 'gyms', 'fitness'],
            'yoga': ['yoga', 'yoga_studio'],
            'crossfit': ['crossfit'],
            'pilates': ['pilates']
        }


# Factory to get the right handler
def get_domain_handler(domain: PlaceDomain) -> DomainHandler:
    """Get the appropriate handler for a domain"""
    handlers = {
        PlaceDomain.FOOD: FoodDomainHandler(),
        PlaceDomain.STUDY_WORK: StudyWorkDomainHandler(),
        PlaceDomain.FITNESS: FitnessDomainHandler(),
        # Add more handlers as needed
    }
    
    # Default to food handler for unimplemented domains
    return handlers.get(domain, FoodDomainHandler())