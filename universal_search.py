"""
Universal Place Search System
A domain-aware search system that handles all types of place queries
"""

import re
from typing import Dict, List, Tuple, Any, Optional
from dataclasses import dataclass, field
from enum import Enum

# ==================== Phase 1: Domain Detection & Query Parser ====================

class PlaceDomain(Enum):
    """Domains for different place categories"""
    FOOD = "food"
    STUDY_WORK = "study_work"
    FITNESS = "fitness"
    ENTERTAINMENT = "entertainment"
    SERVICES = "services"
    SHOPPING = "shopping"
    HEALTHCARE = "healthcare"
    TRANSPORTATION = "transportation"
    ACCOMMODATION = "accommodation"
    BEAUTY = "beauty"

@dataclass
class ParsedQuery:
    """Universal parsed query structure"""
    raw_query: str
    domain: PlaceDomain
    place_types: List[str] = field(default_factory=list)
    attributes: Dict[str, List[str]] = field(default_factory=dict)
    specific_items: List[str] = field(default_factory=list)
    constraints: List[str] = field(default_factory=list)
    location_modifiers: List[str] = field(default_factory=list)
    
    def to_dict(self):
        return {
            'raw_query': self.raw_query,
            'domain': self.domain.value,
            'place_types': self.place_types,
            'attributes': self.attributes,
            'specific_items': self.specific_items,
            'constraints': self.constraints,
            'location_modifiers': self.location_modifiers
        }

class DomainDetector:
    """Detects the domain of a place search query"""
    
    def __init__(self):
        self.domain_keywords = {
            PlaceDomain.FOOD: {
                'keywords': ['restaurant', 'cafe', 'coffee', 'bar', 'pub', 'bakery', 'food', 
                           'eat', 'dine', 'lunch', 'dinner', 'breakfast', 'brunch', 'meal',
                           'cuisine', 'bistro', 'diner', 'grill', 'pizza', 'burger', 'sushi'],
                'weight': 1.0
            },
            PlaceDomain.STUDY_WORK: {
                'keywords': ['study', 'work', 'library', 'coworking', 'laptop', 'wifi', 
                           'quiet', 'meeting', 'workspace', 'desk', 'productive', 'focus'],
                'weight': 0.9
            },
            PlaceDomain.FITNESS: {
                'keywords': ['gym', 'fitness', 'yoga', 'pilates', 'crossfit', 'workout',
                           'exercise', 'pool', 'swimming', 'sports', 'martial', 'dance',
                           'training', 'wellness', 'health club'],
                'weight': 1.0
            },
            PlaceDomain.ENTERTAINMENT: {
                'keywords': ['movie', 'theater', 'cinema', 'park', 'museum', 'zoo',
                           'aquarium', 'bowling', 'arcade', 'club', 'nightclub', 'concert',
                           'gallery', 'attraction', 'amusement'],
                'weight': 1.0
            },
            PlaceDomain.SERVICES: {
                'keywords': ['bank', 'post', 'atm', 'insurance', 'repair', 'service',
                           'laundry', 'dry clean', 'print', 'ship', 'notary', 'tax'],
                'weight': 0.8
            },
            PlaceDomain.SHOPPING: {
                'keywords': ['shop', 'store', 'mall', 'market', 'grocery', 'supermarket',
                           'boutique', 'outlet', 'buy', 'purchase', 'retail'],
                'weight': 0.9
            },
            PlaceDomain.HEALTHCARE: {
                'keywords': ['hospital', 'clinic', 'doctor', 'medical', 'dentist', 
                           'pharmacy', 'urgent care', 'emergency', 'health', 'veterinary',
                           'vet', 'optometry', 'therapy'],
                'weight': 1.0
            },
            PlaceDomain.TRANSPORTATION: {
                'keywords': ['gas', 'petrol', 'parking', 'car', 'rental', 'taxi',
                           'uber', 'lyft', 'bus', 'train', 'metro', 'subway'],
                'weight': 0.9
            },
            PlaceDomain.ACCOMMODATION: {
                'keywords': ['hotel', 'motel', 'hostel', 'inn', 'resort', 'lodge',
                           'accommodation', 'stay', 'airbnb', 'bed breakfast', 'b&b'],
                'weight': 1.0
            },
            PlaceDomain.BEAUTY: {
                'keywords': ['salon', 'spa', 'barber', 'hair', 'nail', 'beauty',
                           'makeup', 'cosmetic', 'massage', 'facial', 'wax'],
                'weight': 0.9
            }
        }
    
    def detect(self, query: str) -> PlaceDomain:
        """Detect the primary domain of the query"""
        query_lower = query.lower()
        scores = {}
        
        for domain, config in self.domain_keywords.items():
            score = 0
            for keyword in config['keywords']:
                if keyword in query_lower:
                    # Give more weight to exact word matches
                    if re.search(r'\b' + re.escape(keyword) + r'\b', query_lower):
                        score += 2 * config['weight']
                    else:
                        score += config['weight']
            scores[domain] = score
        
        # If no clear domain, check for food-related queries (most common)
        if max(scores.values()) == 0:
            # Check for cuisine types
            cuisines = ['indian', 'chinese', 'italian', 'mexican', 'thai', 'japanese', 
                       'korean', 'vietnamese', 'french', 'american', 'mediterranean']
            for cuisine in cuisines:
                if cuisine in query_lower:
                    return PlaceDomain.FOOD
            
            # Default to food if mentions common food terms
            food_terms = ['vegetarian', 'vegan', 'halal', 'kosher', 'organic']
            for term in food_terms:
                if term in query_lower:
                    return PlaceDomain.FOOD
            
            # Default to services for general queries
            return PlaceDomain.SERVICES
        
        return max(scores.items(), key=lambda x: x[1])[0]

class UniversalQueryParser:
    """Parses queries across all domains"""
    
    def __init__(self):
        self.detector = DomainDetector()
        self.initialize_parsers()
    
    def initialize_parsers(self):
        """Initialize domain-specific parsing rules"""
        
        # Cuisine types for food domain
        self.cuisines = [
            'indian', 'chinese', 'italian', 'mexican', 'thai', 'japanese', 'korean',
            'vietnamese', 'french', 'american', 'mediterranean', 'greek', 'turkish',
            'lebanese', 'ethiopian', 'spanish', 'german', 'brazilian', 'peruvian',
            'pakistani', 'bangladeshi', 'nepalese', 'sri lankan', 'south indian',
            'north indian', 'punjabi', 'gujarati', 'bengali', 'tamil'
        ]
        
        # Dietary preferences
        self.dietary = [
            'vegetarian', 'vegan', 'halal', 'kosher', 'gluten-free', 'dairy-free',
            'nut-free', 'organic', 'healthy', 'keto', 'paleo'
        ]
        
        # Ambiance/atmosphere attributes
        self.ambiance = [
            'quiet', 'lively', 'romantic', 'casual', 'formal', 'cozy', 'modern',
            'traditional', 'trendy', 'authentic', 'upscale', 'budget', 'family-friendly',
            'kid-friendly', 'pet-friendly', 'outdoor', 'indoor', 'rooftop', 'waterfront'
        ]
        
        # Common features
        self.features = [
            'wifi', 'internet', 'parking', 'delivery', 'takeout', 'reservation',
            'live music', 'tv', 'games', 'pool table', 'dance floor', 'karaoke',
            'happy hour', 'brunch', 'buffet', 'drive-thru', 'curbside', 'patio',
            'terrace', 'garden', 'view', 'fireplace', 'bar', 'lounge'
        ]
        
        # Time-related constraints
        self.time_constraints = [
            '24 hour', '24-hour', '24/7', 'late night', 'early morning', 'open now',
            'open late', 'breakfast', 'lunch', 'dinner', 'weekend', 'weekday'
        ]
        
        # Service/equipment keywords for different domains
        self.gym_equipment = [
            'treadmill', 'weights', 'pool', 'sauna', 'steam', 'yoga', 'pilates',
            'cycling', 'spinning', 'crossfit', 'personal trainer', 'classes',
            'shower', 'locker', 'towel service'
        ]
        
        self.study_features = [
            'quiet', 'wifi', 'outlets', 'power outlets', 'seating', 'tables',
            'natural light', 'coffee', 'snacks', 'printer', 'meeting room',
            'whiteboard', 'monitor', 'ergonomic'
        ]
        
        # Specific dish/item mentions for food
        self.indian_dishes = [
            'dosa', 'idli', 'sambar', 'vada', 'uttapam', 'biryani', 'curry',
            'naan', 'tandoori', 'tikka', 'masala', 'chai', 'lassi', 'chutney',
            'paneer', 'dal', 'roti', 'paratha', 'kulfi', 'samosa', 'pakora',
            'thali', 'puri', 'bhaji', 'korma', 'vindaloo', 'palak', 'bhel',
            'pav bhaji', 'chole', 'rajma', 'kheer', 'halwa', 'gulab jamun'
        ]
        
        # South Indian specific dishes
        self.south_indian_dishes = [
            'dosa', 'idli', 'sambar', 'vada', 'uttapam', 'rasam', 'chettinad',
            'appam', 'coconut rice', 'lemon rice', 'tamarind rice', 'payasam',
            'medu vada', 'rava dosa', 'masala dosa', 'mysore pak', 'filter coffee'
        ]
    
    def parse(self, query: str) -> ParsedQuery:
        """Parse a query into structured components"""
        query_lower = query.lower()
        
        # Detect domain
        domain = self.detector.detect(query)
        
        # Create parsed query object
        parsed = ParsedQuery(
            raw_query=query,
            domain=domain
        )
        
        # Extract place types based on domain
        parsed.place_types = self.extract_place_types(query_lower, domain)
        
        # Extract attributes
        parsed.attributes = self.extract_attributes(query_lower, domain)
        
        # Extract specific items
        parsed.specific_items = self.extract_specific_items(query_lower, domain)
        
        # Extract constraints
        parsed.constraints = self.extract_constraints(query_lower)
        
        # Extract location modifiers
        parsed.location_modifiers = self.extract_location_modifiers(query_lower)
        
        return parsed
    
    def extract_place_types(self, query: str, domain: PlaceDomain) -> List[str]:
        """Extract place types from query"""
        types = []
        
        if domain == PlaceDomain.FOOD:
            food_types = ['restaurant', 'cafe', 'coffee shop', 'bar', 'pub', 
                         'bakery', 'diner', 'bistro', 'food truck', 'buffet']
            for ft in food_types:
                if ft in query:
                    types.append(ft.replace(' ', '_'))
            
            # If no specific type but domain is food, default to restaurant
            if not types:
                types = ['restaurant']
                
        elif domain == PlaceDomain.FITNESS:
            fitness_types = ['gym', 'yoga studio', 'fitness center', 'health club',
                           'crossfit', 'martial arts', 'dance studio', 'pilates studio']
            for ft in fitness_types:
                if ft in query:
                    types.append(ft.replace(' ', '_'))
            if not types:
                types = ['gym']
                
        elif domain == PlaceDomain.STUDY_WORK:
            study_types = ['library', 'coffee shop', 'cafe', 'coworking space', 'workspace']
            for st in study_types:
                if st in query:
                    types.append(st.replace(' ', '_'))
            if not types:
                types = ['cafe', 'library']
        
        # Add more domain-specific type extraction...
        
        return types
    
    def extract_attributes(self, query: str, domain: PlaceDomain) -> Dict[str, List[str]]:
        """Extract attributes from query"""
        attributes = {}
        
        # Extract cuisine (for food domain)
        if domain == PlaceDomain.FOOD:
            cuisines_found = [c for c in self.cuisines if c in query]
            if cuisines_found:
                attributes['cuisine'] = cuisines_found
        
        # Extract dietary preferences
        dietary_found = [d for d in self.dietary if d in query]
        if dietary_found:
            attributes['dietary'] = dietary_found
        
        # Extract ambiance
        ambiance_found = [a for a in self.ambiance if a in query]
        if ambiance_found:
            attributes['ambiance'] = ambiance_found
        
        # Extract features
        features_found = [f for f in self.features if f in query]
        if features_found:
            attributes['features'] = features_found
        
        # Domain-specific attributes
        if domain == PlaceDomain.FITNESS:
            equipment_found = [e for e in self.gym_equipment if e in query]
            if equipment_found:
                attributes['equipment'] = equipment_found
                
        elif domain == PlaceDomain.STUDY_WORK:
            study_features_found = [s for s in self.study_features if s in query]
            if study_features_found:
                attributes['study_features'] = study_features_found
        
        return attributes
    
    def extract_specific_items(self, query: str, domain: PlaceDomain) -> List[str]:
        """Extract specific items mentioned in query"""
        items = []
        
        if domain == PlaceDomain.FOOD:
            # Check for Indian dishes
            items.extend([d for d in self.indian_dishes if d in query])
            
            # Add common food items
            common_items = ['coffee', 'tea', 'chai', 'beer', 'wine', 'cocktail',
                          'breakfast', 'lunch', 'dinner', 'brunch', 'dessert']
            items.extend([i for i in common_items if i in query])
        
        return list(set(items))  # Remove duplicates
    
    def extract_constraints(self, query: str) -> List[str]:
        """Extract constraints from query"""
        constraints = []
        
        # Time constraints
        for tc in self.time_constraints:
            if tc in query:
                constraints.append(tc)
        
        # Price constraints
        if any(word in query for word in ['cheap', 'budget', 'affordable', 'inexpensive']):
            constraints.append('budget')
        elif any(word in query for word in ['expensive', 'upscale', 'luxury', 'premium']):
            constraints.append('upscale')
        
        # Other constraints
        if 'near' in query or 'close' in query or 'nearby' in query:
            constraints.append('nearby')
        
        return constraints
    
    def extract_location_modifiers(self, query: str) -> List[str]:
        """Extract location-related modifiers and specific cities"""
        modifiers = []
        
        # Extract specific cities/areas
        # Pattern: "in [city]" or "near [city]" - case insensitive
        city_pattern = r'\b(?:in|near|around|at)\s+([a-zA-Z\s]+?)(?:\s|$|,|\.|!|\?)'
        cities = re.findall(city_pattern, query, re.IGNORECASE)
        
        # Common city names in DFW area
        known_cities = ['frisco', 'plano', 'dallas', 'mckinney', 'allen', 'richardson', 
                       'garland', 'irving', 'carrollton', 'lewisville', 'flower mound',
                       'the colony', 'little elm', 'prosper', 'celina', 'addison']
        
        # Check for city matches
        query_lower = query.lower()
        for city in known_cities:
            if city in query_lower:
                modifiers.append(f"city:{city}")
        
        # Also check extracted cities
        for city in cities:
            city_clean = city.strip().lower()
            if city_clean:
                modifiers.append(f"city:{city_clean}")
        
        # Common location terms
        location_terms = ['near', 'in', 'around', 'close to', 'nearby', 'within']
        for term in location_terms:
            if term in query:
                modifiers.append(term)
        
        # Distance modifiers
        distance_pattern = r'\d+\s*(mile|miles|km|kilometer|block|blocks|minute|minutes)'
        distances = re.findall(distance_pattern, query)
        modifiers.extend(distances)
        
        return modifiers


# ==================== Testing the Parser ====================

def test_parser():
    """Test the universal query parser with various queries"""
    parser = UniversalQueryParser()
    
    test_queries = [
        "Can you suggest a few Indian vegetarian restaurants which serve south indian meals and good tea in Frisco",
        "Quiet coffee shop with good WiFi for studying",
        "24-hour gym with swimming pool and yoga classes",
        "Family-friendly restaurant with outdoor seating",
        "Bank with ATM near me open on weekends",
        "Pet-friendly cafe with vegan options",
        "Romantic Italian restaurant for date night",
        "Urgent care clinic open now",
        "Budget hotel with free breakfast and parking"
    ]
    
    for query in test_queries:
        parsed = parser.parse(query)
        print(f"\nQuery: {query}")
        print(f"Domain: {parsed.domain.value}")
        print(f"Place Types: {parsed.place_types}")
        print(f"Attributes: {parsed.attributes}")
        print(f"Specific Items: {parsed.specific_items}")
        print(f"Constraints: {parsed.constraints}")
        print("-" * 50)

if __name__ == "__main__":
    test_parser()