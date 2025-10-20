let map;
let userLocation = { lat: 37.7749, lng: -122.4194 }; // Default to San Francisco
let markers = [];
let userLocationMarker = null; // Track user location marker separately
let places = [];

// Initialize map
function initMap() {
    map = L.map('map').setView([userLocation.lat, userLocation.lng], 14);
    
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '© OpenStreetMap contributors'
    }).addTo(map);
    
    // Add user location marker with blue Google Maps-style pin
    const blueIcon = L.icon({
        iconUrl: 'https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-2x-blue.png',
        shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/0.7.7/images/marker-shadow.png',
        iconSize: [25, 41],
        iconAnchor: [12, 41],
        popupAnchor: [1, -34],
        shadowSize: [41, 41]
    });
    
    userLocationMarker = L.marker([userLocation.lat, userLocation.lng], { icon: blueIcon })
        .addTo(map).bindPopup('Your Location').openPopup();
}

// Get current location
function getCurrentLocation() {
    const statusElement = document.getElementById('locationStatus');
    const coordsElement = document.getElementById('coordinates');
    
    if (navigator.geolocation) {
        statusElement.textContent = 'Getting location...';
        
        navigator.geolocation.getCurrentPosition(
            (position) => {
                userLocation.lat = position.coords.latitude;
                userLocation.lng = position.coords.longitude;
                
                statusElement.textContent = 'Location found!';
                coordsElement.textContent = `${userLocation.lat.toFixed(6)}, ${userLocation.lng.toFixed(6)}`;
                
                // Update map
                map.setView([userLocation.lat, userLocation.lng], 14);
                
                // Clear existing search result markers only
                markers.forEach(marker => map.removeLayer(marker));
                markers = [];
                
                // Remove old user location marker if exists
                if (userLocationMarker) {
                    map.removeLayer(userLocationMarker);
                }
                
                // Add new user location marker with blue Google Maps-style pin
                const blueIcon = L.icon({
                    iconUrl: 'https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-2x-blue.png',
                    shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/0.7.7/images/marker-shadow.png',
                    iconSize: [25, 41],
                    iconAnchor: [12, 41],
                    popupAnchor: [1, -34],
                    shadowSize: [41, 41]
                });
                
                userLocationMarker = L.marker([userLocation.lat, userLocation.lng], { icon: blueIcon })
                    .addTo(map).bindPopup('Your Location');
                
                // Don't automatically search - wait for user to enter query
            },
            (error) => {
                statusElement.textContent = 'Location access denied. Using default location.';
                console.error('Error getting location:', error);
            }
        );
    } else {
        statusElement.textContent = 'Geolocation not supported. Using default location.';
    }
}

// Set query from example chips
function setQuery(query) {
    document.getElementById('searchQuery').value = query;
}

// Search with AI
async function searchWithAI() {
    const query = document.getElementById('searchQuery').value.trim();
    
    if (!query) {
        alert('Please describe what you\'re looking for');
        return;
    }
    
    const placesList = document.getElementById('placesList');
    placesList.innerHTML = '<div class="loading">Analyzing your preferences and finding the best matches...</div>';
    
    try {
        const response = await fetch('/api/ai-search', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                query: query,
                lat: userLocation.lat,
                lng: userLocation.lng
            })
        });
        
        const data = await response.json();
        
        if (data.error) {
            placesList.innerHTML = `<div class="error">Error: ${data.error}</div>`;
            return;
        }
        
        places = data.places || [];
        
        // Log detailed scoring information
        console.log('=== SEARCH RESULTS ANALYSIS ===');
        console.log('Query Intent:', data.query_intent);
        console.log('Scoring Breakdown:', data.scoring_breakdown);
        console.log('Search Debug:', data.search_debug);
        console.log('=== PLACES DATA STRUCTURE ===');
        console.log('Places array:', places);
        console.log('First place structure:', places[0]);
        
        displayAIRecommendations(places, data.scoring_breakdown);
        addMarkersToMap(places);
        
    } catch (error) {
        placesList.innerHTML = `<div class="error">Failed to search: ${error.message}</div>`;
    }
}

// Display AI recommendations with explanations
function displayAIRecommendations(places, scoringBreakdown) {
    const placesList = document.getElementById('placesList');
    
    if (places.length === 0) {
        placesList.innerHTML = '<div class="error">No places found matching your criteria.</div>';
        return;
    }
    
    // Add header with search summary
    let headerHtml = '';
    if (scoringBreakdown) {
        headerHtml = `
            <div style="background: #f0f4f8; padding: 15px; border-radius: 8px; margin-bottom: 15px; font-size: 13px;">
                <strong>Search Results:</strong> Found ${scoringBreakdown.total_candidates} candidates, 
                ${scoringBreakdown.ai_validated} AI-validated matches
            </div>
        `;
    }
    
    const placesHtml = places.map((place, index) => {
        const matchReasons = place.match_reasons || [];
        const reviewHighlights = place.relevant_reviews || [];
        const detailedScoring = place.detailed_scoring || {};
        
        return `
            <div class="place-card" onclick="showPlaceDetails('${place.place_id || place.yelp_id}', ${index})">
                <div class="place-name">${place.name}</div>
                <div class="place-address">${place.address}</div>
                <div class="place-info">
                    ${place.rating ? `<span class="place-rating">★ ${place.rating}</span>` : ''}
                    ${place.price_level ? `<span class="place-price">${'$'.repeat(Math.min(place.price_level, 4))}</span>` : ''}
                    ${place.review_count ? `<span style="color: #666; font-size: 12px;">${place.review_count} reviews</span>` : ''}
                </div>
                ${matchReasons.length > 0 ? `
                    <div class="why-recommended">
                        <strong>Why recommended:</strong><br>
                        ${matchReasons.map(reason => `• ${reason}`).join('<br>')}
                    </div>
                ` : ''}
                ${reviewHighlights.length > 0 ? `
                    <div class="review-highlights">
                        <strong>From reviews:</strong>
                        ${reviewHighlights.map(review => `
                            <div class="review-highlight">"${review}"</div>
                        `).join('')}
                    </div>
                ` : ''}
            </div>
        `;
    }).join('');
    
    placesList.innerHTML = headerHtml + placesHtml;
}

// Display places in the list
function displayPlaces(places) {
    const placesList = document.getElementById('placesList');
    
    if (places.length === 0) {
        placesList.innerHTML = '<div class="error">No places found in this area.</div>';
        return;
    }
    
    placesList.innerHTML = places.map((place, index) => `
        <div class="place-card" onclick="showPlaceDetails('${place.place_id}', ${index})">
            <div class="place-name">${place.name}</div>
            <div class="place-address">${place.address}</div>
            <div class="place-info">
                ${place.rating !== 'N/A' ? `<span class="place-rating">★ ${place.rating}</span>` : ''}
                ${place.price_level !== 'N/A' ? `<span class="place-price">${'$'.repeat(place.price_level)}</span>` : ''}
                ${place.open_now !== null ? `<span class="place-status ${place.open_now ? 'open' : 'closed'}">${place.open_now ? 'Open' : 'Closed'}</span>` : ''}
            </div>
        </div>
    `).join('');
}

// Add markers to map
function addMarkersToMap(places) {
    console.log('=== ADDING MARKERS TO MAP ===');
    console.log('Number of places:', places.length);
    console.log('Current markers before clearing:', markers.length);
    
    // Clear existing search result markers only (preserve user location marker)
    console.log('🧹 Clearing existing search result markers...');
    markers.forEach(marker => map.removeLayer(marker));
    markers = [];
    console.log('✅ Search result markers cleared, user location marker preserved');
    
    let markersAdded = 0;
    
    // Add new markers for search results
    places.forEach((place, index) => {
        console.log(`Processing place ${index}:`, place.name);
        console.log('Full place object:', place);
        
        // Handle coordinate extraction
        let lat, lng;
        
        console.log(`=== Processing ${place.name} ===`);
        console.log('place.geometry:', place.geometry);
        console.log('place.location:', place.location);
        
        if (place.geometry && place.geometry.location) {
            lat = place.geometry.location.lat;
            lng = place.geometry.location.lng;
            console.log(`✅ Found coordinates in geometry.location: ${lat}, ${lng}`);
        } else if (place.location) {
            lat = place.location.lat;
            lng = place.location.lng;
            console.log(`✅ Found coordinates in location: ${lat}, ${lng}`);
        } else {
            console.log('❌ No coordinates found for place:', place.name);
            console.log('Available keys:', Object.keys(place));
        }
        
        if (lat && lng && lat !== null && lng !== null && !isNaN(lat) && !isNaN(lng)) {
            console.log(`🎯 CREATING MARKER for ${place.name} at [${lat}, ${lng}]`);
            
            try {
                // Create proper Google Maps-style pin icon for search results (red)
                const redIcon = L.icon({
                    iconUrl: 'https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-2x-red.png',
                    shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/0.7.7/images/marker-shadow.png',
                    iconSize: [25, 41],
                    iconAnchor: [12, 41],
                    popupAnchor: [1, -34],
                    shadowSize: [41, 41]
                });
                
                const marker = L.marker([lat, lng], { icon: redIcon });
                
                console.log(`📍 Red pin marker object created:`, marker);
                
                // Add to map
                marker.addTo(map);
                console.log(`🗺️ Marker added to map for ${place.name}`);
                
                // Create popup with place details
                marker.bindPopup(`
                    <div style="min-width: 200px;">
                        <strong>${place.name}</strong><br>
                        ${place.address}<br>
                        ${place.rating ? `Rating: ${place.rating}★<br>` : ''}
                        ${place.match_score ? `Match: ${place.match_score}%<br>` : ''}
                        <button onclick="showPlaceDetails('${place.place_id || place.yelp_id}', ${index})" 
                                style="margin-top: 8px; padding: 4px 8px; background: #1a73e8; color: white; border: none; border-radius: 3px; cursor: pointer;">
                            View Details
                        </button>
                    </div>
                `);
                
                markers.push(marker);
                markersAdded++;
                console.log(`✅ SUCCESS: Marker for ${place.name} added to markers array. Total markers: ${markers.length}`);
            } catch (error) {
                console.error(`❌ ERROR creating marker for ${place.name}:`, error);
            }
        } else {
            console.log(`❌ SKIP: ${place.name} - invalid coordinates: lat=${lat}, lng=${lng}`);
            console.log(`   lat type: ${typeof lat}, lng type: ${typeof lng}`);
            console.log(`   lat isNaN: ${isNaN(lat)}, lng isNaN: ${isNaN(lng)}`);
        }
    });
    
    console.log(`🎯 SUMMARY: Total markers added: ${markersAdded}`);
    console.log(`🎯 SUMMARY: Total markers on map: ${markers.length}`);
    console.log(`🎯 SUMMARY: Current map center:`, map.getCenter());
    console.log(`🎯 SUMMARY: Current map zoom:`, map.getZoom());
    
    // List all marker positions
    markers.forEach((marker, i) => {
        if (marker && marker.getLatLng) {
            console.log(`🎯 Marker ${i} position:`, marker.getLatLng());
        }
    });
    
    // Fit map to show all markers including user location
    if (markers.length > 0) {
        console.log(`🗺️ Attempting to fit bounds for ${markers.length} search markers + user location`);
        try {
            const allMarkers = [...markers];
            if (userLocationMarker) {
                allMarkers.push(userLocationMarker);
            }
            const group = L.featureGroup(allMarkers);
            const bounds = group.getBounds();
            console.log(`🗺️ Bounds:`, bounds);
            map.fitBounds(bounds.pad(0.1));
            console.log('✅ Map bounds adjusted to show all markers including user location');
        } catch (error) {
            console.error('❌ Error adjusting map bounds:', error);
        }
    } else {
        console.log('⚠️ No search result markers to fit bounds for');
    }
}

// Show place details
async function showPlaceDetails(placeId, index) {
    const modal = document.getElementById('placeModal');
    const modalContent = document.getElementById('modalContent');
    
    modal.style.display = 'block';
    modalContent.innerHTML = '<div class="loading">Loading place details...</div>';
    
    try {
        const response = await fetch(`/api/place-details/${placeId}`);
        const details = await response.json();
        
        if (details.error) {
            modalContent.innerHTML = `<div class="error">Error: ${details.error}</div>`;
            return;
        }
        
        let hoursHtml = '';
        if (details.opening_hours && details.opening_hours.weekday_text) {
            hoursHtml = `
                <div class="detail-item" style="grid-column: span 2;">
                    <div class="detail-label">Opening Hours</div>
                    <div class="detail-value">
                        ${details.opening_hours.weekday_text.join('<br>')}
                    </div>
                </div>
            `;
        }
        
        let reviewsHtml = '';
        if (details.reviews && details.reviews.length > 0) {
            reviewsHtml = `
                <div style="margin-top: 20px;">
                    <h3 style="margin-bottom: 15px;">Recent Reviews</h3>
                    ${details.reviews.slice(0, 3).map(review => `
                        <div style="padding: 15px; background: #f8f9fa; border-radius: 5px; margin-bottom: 10px;">
                            <div style="display: flex; justify-content: space-between; margin-bottom: 10px;">
                                <strong>${review.author_name}</strong>
                                <span style="color: #f39c12;">★ ${review.rating}</span>
                            </div>
                            <div style="color: #666; font-size: 14px;">${review.text}</div>
                        </div>
                    `).join('')}
                </div>
            `;
        }
        
        // Create Google Maps-style modal content
        let photosHtml = '';
        if (details.photos && details.photos.length > 0) {
            photosHtml = `
                <div class="modal-photos">
                    <img src="${details.photos[0]}" alt="${details.name}" class="modal-photo" onerror="this.style.display='none'">
                </div>
            `;
        }
        
        let hoursDisplay = '';
        if (details.opening_hours && details.opening_hours.weekday_text) {
            hoursDisplay = details.opening_hours.weekday_text.join('<br>');
        } else if (details.hours && details.hours.length > 0) {
            hoursDisplay = details.hours.map(h => `${h.day}: ${h.start} - ${h.end}`).join('<br>');
        }
        
        modalContent.innerHTML = `
            ${photosHtml}
            
            <div class="modal-header">
                <div class="modal-place-name">${details.name}</div>
                
                <div class="modal-rating-info">
                    ${details.rating ? `
                        <span class="modal-rating">★ ${details.rating}</span>
                        ${details.review_count ? `<span class="modal-rating-count">(${details.review_count} reviews)</span>` : ''}
                    ` : ''}
                    <span class="source-badge">${details.source || 'unknown'}</span>
                </div>
                
                <div class="modal-place-address">${details.formatted_address || places[index]?.address || 'Address not available'}</div>
                
                ${details.categories ? `
                    <div class="modal-categories">
                        ${details.categories.map(cat => `<span class="modal-category">${cat}</span>`).join('')}
                    </div>
                ` : ''}
            </div>
            
            <div class="modal-body">
                <div class="modal-details-grid">
                    ${details.formatted_phone_number ? `
                        <div class="detail-row">
                            <div class="detail-icon">📞</div>
                            <div class="detail-info">
                                <div class="detail-label">Phone</div>
                                <div class="detail-value">${details.formatted_phone_number}</div>
                            </div>
                        </div>
                    ` : ''}
                    
                    ${details.website ? `
                        <div class="detail-row">
                            <div class="detail-icon">🌐</div>
                            <div class="detail-info">
                                <div class="detail-label">Website</div>
                                <div class="detail-value">
                                    <a href="${details.website}" target="_blank" style="color: #1a73e8; text-decoration: none;">Visit Website</a>
                                </div>
                            </div>
                        </div>
                    ` : ''}
                    
                    ${details.price_level && details.price_level > 0 ? `
                        <div class="detail-row">
                            <div class="detail-icon">💰</div>
                            <div class="detail-info">
                                <div class="detail-label">Price Level</div>
                                <div class="detail-value">${'$'.repeat(Math.min(details.price_level, 4))}</div>
                            </div>
                        </div>
                    ` : ''}
                    
                    ${hoursDisplay ? `
                        <div class="detail-row">
                            <div class="detail-icon">🕒</div>
                            <div class="detail-info">
                                <div class="detail-label">Hours</div>
                                <div class="detail-value">${hoursDisplay}</div>
                            </div>
                        </div>
                    ` : ''}
                </div>
                
                ${details.photos && details.photos.length > 1 ? `
                    <div class="place-photos">
                        ${details.photos.slice(1, 5).map(photo => `
                            <img src="${photo}" alt="${details.name}" class="place-photo" onerror="this.style.display='none'">
                        `).join('')}
                    </div>
                ` : ''}
                
                ${details.reviews && details.reviews.length > 0 ? `
                    <div class="reviews-section">
                        <div class="reviews-header">Reviews</div>
                        ${details.reviews.slice(0, 3).map(review => `
                            <div class="review-card">
                                <div class="review-header">
                                    <span class="review-author">${review.author_name || 'Anonymous'}</span>
                                    ${review.rating ? `<span class="review-rating">★ ${review.rating}</span>` : ''}
                                </div>
                                <div class="review-text">${review.text}</div>
                            </div>
                        `).join('')}
                    </div>
                ` : ''}
            </div>
        `;
        
    } catch (error) {
        modalContent.innerHTML = `<div class="error">Failed to fetch place details: ${error.message}</div>`;
    }
}

// Close modal
function closeModal() {
    document.getElementById('placeModal').style.display = 'none';
}

// Close modal when clicking outside
window.onclick = function(event) {
    const modal = document.getElementById('placeModal');
    if (event.target === modal) {
        modal.style.display = 'none';
    }
}

// Initialize when page loads
document.addEventListener('DOMContentLoaded', () => {
    initMap();
    getCurrentLocation();
});