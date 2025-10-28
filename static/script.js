// script.js

let map;
let userLocation = { lat: 37.7749, lng: -122.4194 }; // Default to San Francisco
let markers = [];
let userLocationMarker = null; // Track user location marker separately
let places = [];

/* ============================
   Explain normalizer helpers
   ============================ */

// Build a compact, provider-agnostic payload used for grounded “why” answers.
function normalizePlaceForExplain(place) {
  const source = place.source || (place.yelp_id ? 'yelp' : 'google');

  // Ratings / reviews
  const rating = Number(
    place.rating ??
    place.rate ??
    (place.details && place.details.rating) ??
    0
  );

  const reviews = Number(
    place.review_count ??
    place.user_ratings_total ??
    place.userRatingsTotal ??
    0
  );

  // Price
  let price_level = 0;
  if (typeof place.price_level === 'number') {
    price_level = place.price_level;
  } else if (typeof place.price === 'string') {
    // Yelp-style "$", "$$", "$$$"
    price_level = place.price.trim().length;
  }

  // Distance (if your backend computed it)
  const distance_m = Number(
    place.distance ??
    place.distance_m ??
    place.__distance_m ??
    0
  );

  // IDs / names
  const placeId = place.place_id || place.yelp_id || place.id || place.name || '';
  const name = place.name || '';

  // Optional ranking fields (if backend set them)
  const score = Number(place.match_score ?? place.__score ?? 0);
  const contributions = {
    rating: Number(place.__contrib?.rating ?? 0),
    distance: Number(place.__contrib?.distance ?? 0),
    price: Number(place.__contrib?.price ?? 0),
    reviews: Number(place.__contrib?.reviews ?? 0),
  };

  return {
    placeId,
    name,
    score,
    contributions,
    raw: {
      rating,
      distance_m,
      price_level,
      reviews,
      source
    }
  };
}

// Ensure attribute-safe JSON so quotes don’t break HTML attributes
function jsonForDataAttr(obj) {
  return JSON.stringify(obj).replace(/"/g, '&quot;');
}

/* ============================
   Map init + geolocation
   ============================ */

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

        // Add new user location marker with blue pin
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

/* ============================
   Query + search
   ============================ */

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

    // Debug logs
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

/* =========================================
   Renderers: list with explanation attributes
   ========================================= */

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

    // Build normalized payload for grounding
    const explain = normalizePlaceForExplain(place);

    return `
      <div class="place-card"
           onclick="showPlaceDetails('${place.place_id || place.yelp_id}', ${index})"
           data-name="${explain.name}"
           data-explain="${jsonForDataAttr(explain)}">
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
        <button class="why-btn" type="button" style="margin-top:8px;">Why?</button>
      </div>
    `;
  }).join('');

  placesList.innerHTML = headerHtml + placesHtml;
}

// Display places in the list (simpler renderer)
function displayPlaces(places) {
  const placesList = document.getElementById('placesList');

  if (places.length === 0) {
    placesList.innerHTML = '<div class="error">No places found in this area.</div>';
    return;
  }

  placesList.innerHTML = places.map((place, index) => {
    const explain = normalizePlaceForExplain(place);

    return `
      <div class="place-card"
           onclick="showPlaceDetails('${place.place_id || place.yelp_id || place.id}', ${index})"
           data-name="${explain.name}"
           data-explain="${jsonForDataAttr(explain)}">
        <div class="place-name">${place.name}</div>
        <div class="place-address">${place.address}</div>
        <div class="place-info">
          ${place.rating !== 'N/A' && place.rating != null ? `<span class="place-rating">★ ${place.rating}</span>` : ''}
          ${place.price_level !== 'N/A' && place.price_level != null ? `<span class="place-price">${'$'.repeat(Math.min(place.price_level, 4))}</span>` : ''}
          ${place.open_now !== null && place.open_now !== undefined ? `<span class="place-status ${place.open_now ? 'open' : 'closed'}">${place.open_now ? 'Open' : 'Closed'}</span>` : ''}
        </div>
        <button class="why-btn" type="button" style="margin-top:8px;">Why?</button>
      </div>
    `;
  }).join('');
}

/* ============================
   Map markers + details modal
   ============================ */

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
        // Red pin icon for search results
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

/* ============================
   Step 2: Chat streaming & UI
   ============================ */

let _chatAbortController = null;

function closeChatPanel() {
  if (_chatAbortController) { _chatAbortController.abort(); _chatAbortController = null; }
  const panel = document.getElementById('chatPanel');
  if (panel) panel.remove();
}


function ensureChatPanel() {
  // Create a minimal floating chat panel if it doesn't exist
  if (document.getElementById('chatPanel')) return;

  const panel = document.createElement('div');
  panel.id = 'chatPanel';
  panel.style.cssText = `
    position: fixed; right: 12px; bottom: 12px; width: 360px; max-height: 60vh;
    background: #fff; border: 1px solid #e5e7eb; border-radius: 10px;
    box-shadow: 0 10px 25px rgba(0,0,0,0.08); display: flex; flex-direction: column; overflow: hidden; z-index: 9999;
    font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif;
  `;

  // Header
  const header = document.createElement('div');
  header.style.cssText = `
    padding: 10px 12px; background:#f8fafc; border-bottom:1px solid #e5e7eb; 
    font-weight:600; display:flex; align-items:center; justify-content:space-between;
  `;
  const title = document.createElement('div');
  title.textContent = 'Why this ranking?';

  // Close (×)
  const closeBtn = document.createElement('button');
  closeBtn.type = 'button';
  closeBtn.setAttribute('aria-label', 'Close');
  closeBtn.title = 'Close';
  closeBtn.textContent = '×';
  closeBtn.style.cssText = `
    background:none; border:none; cursor:pointer; font-size:20px; line-height:20px;
    color:#6b7280; padding:0 2px;
  `;
  closeBtn.onclick = closeChatPanel;

  header.appendChild(title);
  header.appendChild(closeBtn);

  // Messages
  const msgs = document.createElement('div');
  msgs.id = 'chatMessages';
  msgs.style.cssText = `padding: 10px; overflow-y:auto; flex:1; display:flex; flex-direction:column; gap:10px;`;

  // Input row
  const inputRow = document.createElement('div');
  inputRow.style.cssText = `display:flex; gap:8px; padding:10px; border-top:1px solid #e5e7eb; background:#fafafa;`;

  const input = document.createElement('input');
  input.id = 'chatInput';
  input.placeholder = 'Ask a follow-up…';
  input.style.cssText = `flex:1; padding:8px 10px; border:1px solid #e5e7eb; border-radius:8px;`;

  const send = document.createElement('button');
  send.textContent = 'Send';
  send.style.cssText = `padding:8px 12px; border:none; border-radius:8px; background:#1a73e8; color:#fff; cursor:pointer;`;

  // Enter-to-send
  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      send.click();
    }
  });

  send.onclick = () => {
  const text = input.value.trim();
  if (!text) return;

  const lastExplain = window.__lastExplainPayload || null;
  if (!lastExplain) {
    appendChat('assistant', 'Select a place first, then ask a question.');
    return;
  }

  // Create contextual payload combining prior explain + new user constraints
  const contextMsg = `User follow-up: "${text}"\n\n` +
    `Re-evaluate this place based on these new preferences (e.g., time, price, ambience) ` +
    `using the provided structured context, but keep the tone friendly for a user.`;

  streamChat(contextMsg, { resultExplanation: lastExplain });
  input.value = '';
};


  inputRow.appendChild(input);
  inputRow.appendChild(send);

  panel.appendChild(header);
  panel.appendChild(msgs);
  panel.appendChild(inputRow);
  document.body.appendChild(panel);
}

function appendChat(role, text) {
  ensureChatPanel();
  const msgs = document.getElementById('chatMessages');
  const bubble = document.createElement('div');
  bubble.className = role === 'user' ? 'bubble-user' : 'bubble-assistant';
  bubble.style.cssText = `
    align-self:${role === 'user' ? 'flex-end' : 'flex-start'};
    max-width: 85%; white-space: pre-wrap; line-height:1.4;
    padding:10px 12px; border-radius:12px;
    background:${role === 'user' ? '#1a73e8' : '#f1f5f9'};
    color:${role === 'user' ? '#fff' : '#111827'};
    box-shadow:0 1px 2px rgba(0,0,0,0.05);
  `;
  bubble.textContent = text || '';
  msgs.appendChild(bubble);
  msgs.scrollTop = msgs.scrollHeight;
  return bubble;
}

// --- constraint parsing & utilities ---

// Parse "within 10 minutes drive", "within 8 min walk", "under $10", "less than $$"
function parseConstraints(text) {
  const out = {};
  const t = (text || '').toLowerCase();

  // Distance: minutes + mode
  const distMatch = t.match(/(?:within\s*)?(\d+)\s*min(?:ute)?s?\s*(drive|driving|walk|walking)?/);
  if (distMatch) {
    const mins = parseInt(distMatch[1], 10);
    const mode = (distMatch[2] || 'drive').startsWith('walk') ? 'walk' : 'drive';
    // rough averages: drive ~ 800 m/min (48 km/h), walk ~ 83 m/min (5 km/h)
    const mPerMin = mode === 'walk' ? 83 : 800;
    out.max_distance_m = mins * mPerMin;
    out.distance_mode = mode;
  }

  // Price: currency or price-level
  // under $10 / less than $10
  const priceNum = t.match(/(?:under|less than)\s*\$?\s*(\d+)/);
  if (priceNum) out.max_price_usd = parseFloat(priceNum[1]);

  // under $$  / less than $$
  const priceLevel = t.match(/(?:under|less than)\s*(\${1,4})/);
  if (priceLevel) out.max_price_level = priceLevel[1].length;

  return out;
}

// Haversine in meters (for deriving distance if API omitted it)
function haversineMeters(lat1, lon1, lat2, lon2) {
  if ([lat1, lon1, lat2, lon2].some(v => v == null || isNaN(v))) return null;
  const toRad = d => (d * Math.PI) / 180;
  const R = 6371000;
  const dLat = toRad(lat2 - lat1);
  const dLon = toRad(lon2 - lon1);
  const a = Math.sin(dLat/2)**2 +
            Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) *
            Math.sin(dLon/2)**2;
  const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a));
  return Math.round(R * c);
}

// Derive/normalize fields as needed on each place
function ensureDerivedFields(place) {
  // distance_m
  if (place.distance_m == null && place.distance == null) {
    const lat = place?.geometry?.location?.lat ?? place?.location?.lat;
    const lng = place?.geometry?.location?.lng ?? place?.location?.lng;
    const d = haversineMeters(userLocation.lat, userLocation.lng, lat, lng);
    if (d != null) place.distance_m = d;
  }
  // price_level from "$", "$$" if needed
  if (place.price_level == null && typeof place.price === 'string') {
    place.price_level = place.price.trim().length || null;
  }
  return place;
}

// Apply constraints with soft scoring (don’t nuke everything if a field is missing)
function refinePlacesWithConstraints(placesArr, constraints) {
  const out = [...placesArr].map(p => ensureDerivedFields({ ...p }));

  return out
    .map(p => {
      let penalty = 0;

      // distance
      if (constraints.max_distance_m != null) {
        if (p.distance_m != null) {
          // penalize more as distance exceeds max
          const over = Math.max(0, p.distance_m - constraints.max_distance_m);
          penalty += over / constraints.max_distance_m; // simple linear penalty
        } else {
          // unknown distance → small penalty instead of outright removal
          penalty += 0.25;
        }
      }

      // price: either numeric budget or price_level
      if (constraints.max_price_usd != null) {
        // If you have a menu price, you could compare; otherwise use price_level as proxy:
        if (p.price_level != null) {
          // assume $ ~ <= $10, $$ ~ <= $20, etc. (crude proxy)
          const approxCap = p.price_level * 10; // adjust if you have better mapping
          if (approxCap > constraints.max_price_usd) penalty += 0.5;
        } else {
          penalty += 0.15; // unknown price → tiny penalty
        }
      } else if (constraints.max_price_level != null) {
        if (p.price_level != null && p.price_level > constraints.max_price_level) penalty += 0.5;
        else if (p.price_level == null) penalty += 0.15;
      }

      // start from any server score if present; otherwise a baseline from rating & reviews
      const base =
        (typeof p.match_score === 'number' ? p.match_score : 0) ||
        (p.rating ? (p.rating * 10) : 0) + (p.review_count ? Math.min(p.review_count, 200) / 20 : 0);

      const refined_score = Math.max(0, Math.round(base - penalty * 20));
      return { ...p, refined_score };
    })
    .sort((a, b) => (b.refined_score ?? 0) - (a.refined_score ?? 0));
}

// Build a friendly one-liner after refinement
function formatRefineSummary(constraints) {
  const bits = [];
  if (constraints.max_distance_m != null) {
    const km = (constraints.max_distance_m / 1000);
    // present as “10-minute drive/walk” rather than meters
    if (constraints.distance_mode === 'walk') bits.push(`within your walking limit`);
    else bits.push(`within your driving limit`);
  }
  if (constraints.max_price_usd != null) bits.push(`around $${constraints.max_price_usd}`);
  if (constraints.max_price_level != null) bits.push(`under ${'$'.repeat(constraints.max_price_level)}`);
  if (!bits.length) return 'Updated the list based on your preferences.';
  return `Updated the list to prioritize places ${bits.join(' and ')}.`;
}


function streamChat(message, clientMeta) {
  ensureChatPanel();

  if (_chatAbortController) _chatAbortController.abort();
  _chatAbortController = new AbortController();

  appendChat('user', message);
  const assistantBubble = appendChat('assistant', ''); // empty; we’ll fill as we stream

  fetch('/api/chat/stream', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Accept': 'text/event-stream' // hint to server
    },
    body: JSON.stringify({ message, clientMeta }),
    signal: _chatAbortController.signal
  }).then(async (res) => {
    // If server didn't return a stream, show the body text to debug
    const ctype = res.headers.get('content-type') || '';
    if (!res.ok) {
      const txt = await res.text().catch(()=>'');
      assistantBubble.textContent = `HTTP ${res.status} ${res.statusText}\n${txt}`;
      return;
    }
    if (!res.body || !ctype.includes('event-stream')) {
      const txt = await res.text().catch(()=>'');
      assistantBubble.textContent = txt || '[No stream body]';
      return;
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let done = false;

    // helper: append any known content field
    const appendFromPayload = (p) => {
      // Tolerate various server field names
      const piece = p?.content ?? p?.delta ?? p?.token ?? p?.text ?? p?.message ?? '';
      if (piece) assistantBubble.textContent += piece;
    };

    while (!done) {
      const { value, done: streamDone } = await reader.read();
      done = streamDone;
      buffer += value ? decoder.decode(value, { stream: true }) : '';

      // Split into SSE frames
      let idx;
      while ((idx = buffer.indexOf('\n\n')) !== -1) {
        const frame = buffer.slice(0, idx).trim();
        buffer = buffer.slice(idx + 2);

        if (!frame) continue;

        // Debug: log raw frame (keep while diagnosing)
        // console.debug('[SSE frame]', frame);

        let ev = 'message';
        let dataLines = [];

        for (const line of frame.split('\n')) {
          if (line.startsWith('event:')) ev = line.slice(6).trim();
          else if (line.startsWith('data:')) dataLines.push(line.slice(5).trim());
        }

        const dataRaw = dataLines.join('\n');
        if (!dataRaw) continue;

        // Some servers send non-JSON text (e.g., “[DONE]”)
        try {
          const payload = JSON.parse(dataRaw);

          switch (ev) {
            case 'start':
              // optional typing indicator
              break;
            case 'delta':
              appendFromPayload(payload);
              break;
            case 'done':
              // finalize if needed
              break;
            case 'error':
              assistantBubble.textContent += `\n\n[Error] ${payload.message || JSON.stringify(payload)}`;
              break;
            default:
              // If event isn’t “delta” but payload has content-like fields, append
              appendFromPayload(payload);
          }
        } catch {
          // Not JSON — handle common sentinels or raw text
          if (dataRaw === '[DONE]' || dataRaw === 'DONE') {
            // end of stream
          } else {
            assistantBubble.textContent += dataRaw;
          }
        }
      }
    }
  }).catch(err => {
    assistantBubble.textContent += `\n\n[Network error] ${err.message}`;
  });
}

function humanizePrice(level) {
  if (!level || isNaN(level)) return null;
  return ({1:'budget-friendly',2:'moderate',3:'higher-end',4:'premium'}[Math.min(level,4)] || null);
}
function humanizeDistance(m) {
  if (!m || isNaN(m) || m <= 0) return null;
  if (m < 900) return `${Math.round(m)} m away`;
  return `${(m/1000).toFixed(1)} km away`;
}
function topDrivers(contrib) {
  if (!contrib) return [];
  const map = { rating:'ratings', reviews:'review volume', distance:'proximity', price:'price fit' };
  return Object.entries(contrib)
    .filter(([,v]) => typeof v === 'number' && v !== 0)
    .sort((a,b) => Math.abs(b[1]) - Math.abs(a[1]))
    .slice(0,3)
    .map(([k]) => map[k] || k);
}

// Build a gentle, user-facing intro that hides missing fields
function formatExplainIntro(explain, userQuery, extraHints = {}) {
  const parts = [];

  // Core facts
  const rating = (explain.raw && explain.raw.rating) ? `rated ${explain.raw.rating.toFixed ? explain.raw.rating.toFixed(1) : explain.raw.rating}★` : null;
  const reviews = (explain.raw && explain.raw.reviews) ? `${explain.raw.reviews} reviews` : null;
  const distance = humanizeDistance(explain.raw?.distance_m);
  const price = humanizePrice(explain.raw?.price_level);

  // Sentence 1 — name + primary drivers
  const drivers = topDrivers(explain.contributions);
  const dText = drivers.length ? `based on ${drivers.join(', ').replace(/, ([^,]*)$/, ' and $1')}` : (rating || reviews ? 'based on community ratings' : 'based on overall fit');

  parts.push(`“${explain.name}” ranks highly ${dText}.`);

  // Sentence 2 — concrete evidence we have
  const facts = [];
  if (rating) facts.push(rating);
  if (reviews) facts.push(reviews);
  if (price) facts.push(price);
  if (distance) facts.push(distance);
  if (facts.length) parts.push(`It’s ${facts.join(', ')}.`);

  // Sentence 3 — tie to the user’s intent if we have it
  const intent = (userQuery || '').trim();
  if (intent) {
    // Light touch: don’t claim facts we don’t have
    parts.push(`For “${intent}”, this option stands out for its overall reputation and fit.`);
  }

  // Optional hint for missing constraints (don’t mention zeros)
  if (extraHints && extraHints.suggestRefine) {
    parts.push(`If you care about distance or price, add those preferences (e.g., “within 10 minutes walk”, “under $$”) to refine the list.`);
  }

  return parts.join(' ');
}


// Public handler to explain a specific card
function explainWhyForCard(cardEl) {
  try {
    if (!cardEl) throw new Error('No card element found');
    const explainStr = cardEl.dataset.explain || '';
    // Open the panel immediately so you SEE errors
    ensureChatPanel();

    if (!explainStr) {
      appendChat('assistant', 'No context available on this card.');
      return;
    }

    let explain;
    try {
      // Parse HTML-escaped JSON
      explain = JSON.parse(explainStr.replace(/&quot;/g, '"'));
    } catch (parseErr) {
      console.error('Failed to parse data-explain:', parseErr, { explainStr });
      appendChat('assistant', 'Could not parse explanation payload. Check console for details.');
      return;
    }

    window.__lastExplainPayload = explain;

    const userQuery = (document.getElementById('searchQuery')?.value || '').trim();
const msg = formatExplainIntro(explain, userQuery, { suggestRefine: true });
// Then start the stream grounded on the same context:
streamChat(msg, { resultExplanation: explain });
  } catch (e) {
    console.error('explainWhyForCard error:', e);
    ensureChatPanel();
    appendChat('assistant', `[UI error] ${e.message}`);
  }
}


// One-time: handle clicks on any future ".why-btn" inside #placesList
(function attachWhyDelegation(){
  function bind() {
    const list = document.getElementById('placesList');
    if (!list) return false;
    list.addEventListener('click', (e) => {
      const btn = e.target.closest('.why-btn');
      if (!btn) return;
      e.stopPropagation();
      const card = btn.closest('.place-card');
      // Debug: confirm we got the right card
      console.log('[Why click] card:', card);
      explainWhyForCard(card);
    }, true);
    return true;
  }
  if (!bind()) {
    document.addEventListener('DOMContentLoaded', bind, { once: true });
  }
})();


/* ============================
   Inline chat for #prompt / #send
   ============================ */

let _inlineAbort = null;

// Find the active place card, or default to the first one
function getActiveExplainPayload() {
  // Prefer a selected/expanded card if you set that class in your UI
  const selected = document.querySelector('.place-card.selected') || document.querySelector('.place-card');
  if (!selected) return null;

  const raw = selected.dataset?.explain || '';
  try {
    return JSON.parse(raw.replace(/&quot;/g, '"'));
  } catch (e) {
    console.warn('Failed to parse data-explain on active card:', e, raw);
    return null;
  }
}

// Ensure a container exists under the prompt row to show messages
function ensureInlineChatBox() {
  let box = document.getElementById('inlineChat');
  if (box) return box;

  const row = document.querySelector('.row'); // your snippet's wrapper
  box = document.createElement('div');
  box.id = 'inlineChat';
  box.style.cssText = `
    margin-top: 8px; padding: 10px; border: 1px solid #e5e7eb;
    border-radius: 8px; background: #fff; max-height: 40vh; overflow-y: auto;
    font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif;
  `;
  if (row && row.parentNode) {
    row.parentNode.insertBefore(box, row.nextSibling);
  } else {
    document.body.appendChild(box);
  }
  return box;
}

function appendInline(role, text) {
  const box = ensureInlineChatBox();
  const bubble = document.createElement('div');
  bubble.style.cssText = `
    max-width: 95%; white-space: pre-wrap; line-height:1.4; margin: 6px 0;
    padding: 8px 10px; border-radius:10px; box-shadow:0 1px 2px rgba(0,0,0,0.05);
    ${role === 'user'
      ? 'align-self:flex-end;background:#1a73e8;color:#fff;'
      : 'align-self:flex-start;background:#f1f5f9;color:#111827;'}
  `;
  bubble.textContent = text || '';
  box.appendChild(bubble);
  box.scrollTop = box.scrollHeight;
  return bubble;
}

function streamInlineChat(message, clientMeta) {
  const box = ensureInlineChatBox();

  // cancel any in-flight stream
  if (_inlineAbort) _inlineAbort.abort();
  _inlineAbort = new AbortController();

  appendInline('user', message);
  const assistantBubble = appendInline('assistant', '');

  fetch('/api/chat/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message, clientMeta }),
    signal: _inlineAbort.signal
  }).then(async (res) => {
    const ctype = res.headers.get('content-type') || '';
    if (!res.ok) {
      const txt = await res.text().catch(()=>'');
      assistantBubble.textContent = `HTTP ${res.status} ${res.statusText}\n${txt}`;
      return;
    }
    if (!res.body || !ctype.includes('event-stream')) {
      const txt = await res.text().catch(()=>'');
      assistantBubble.textContent = txt || '[No stream body]';
      return;
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let done = false;

    const appendFromPayload = (p) => {
      const piece = p?.content ?? p?.delta ?? p?.token ?? p?.text ?? p?.message ?? '';
      if (piece) assistantBubble.textContent += piece;
    };

    while (!done) {
      const { value, done: streamDone } = await reader.read();
      done = streamDone;
      buffer += value ? decoder.decode(value, { stream: true }) : '';

      let idx;
      while ((idx = buffer.indexOf('\n\n')) !== -1) {
        const frame = buffer.slice(0, idx).trim();
        buffer = buffer.slice(idx + 2);
        if (!frame) continue;

        let ev = 'message';
        const dataLines = [];
        for (const line of frame.split('\n')) {
          if (line.startsWith('event:')) ev = line.slice(6).trim();
          else if (line.startsWith('data:')) dataLines.push(line.slice(5).trim());
        }
        const dataRaw = dataLines.join('\n');
        if (!dataRaw) continue;

        try {
          const payload = JSON.parse(dataRaw);
          if (ev === 'error') {
            assistantBubble.textContent += `\n\n[Error] ${payload.message || JSON.stringify(payload)}`;
          } else if (ev === 'delta' || ev === 'start' || ev === 'done') {
            appendFromPayload(payload);
          } else {
            // any other event with content-like fields
            appendFromPayload(payload);
          }
        } catch {
          if (dataRaw !== '[DONE]') assistantBubble.textContent += dataRaw;
        }
      }
    }
  }).catch(err => {
    assistantBubble.textContent += `\n\n[Network error] ${err.message}`;
  });
}

// Hook up #send and Enter on #prompt
(function wireInlinePrompt() {
  function handleSend() {
  const input = document.getElementById('prompt');
  if (!input) return;
  const text = input.value.trim();
  if (!text) return;

  // 1) Parse constraints from user text
  const constraints = parseConstraints(text);
  const hasConstraints = Object.keys(constraints).length > 0;

  // 2) If constraints present, refine the *current* results client-side
  if (hasConstraints && Array.isArray(places) && places.length) {
    const refined = refinePlacesWithConstraints(places, constraints);

    // Re-render the list to reflect new priority
    displayAIRecommendations(refined, null);
    addMarkersToMap(refined);
    appendInline('assistant', formatRefineSummary(constraints));

    // Also stream a grounded sentence for the new top item (optional but nice)
    const top = refined[0];
    if (top) {
      const explain = normalizePlaceForExplain(ensureDerivedFields({ ...top }));
      const msg = `Considering the user's follow-up "${text}", explain briefly why “${explain.name}” remains a strong match using only rating, reviews, distance, and price if present. Omit unknowns gracefully.`;
      streamInlineChat(msg, { resultExplanation: explain });
      window.__lastExplainPayload = explain; // keep for further follow-ups
    }

    input.value = '';
    return;
  }

  // 3) No recognizable constraints → fall back to pure chat refine on the currently selected card
  let explain = window.__lastExplainPayload || getActiveExplainPayload();
  if (!explain) {
    appendInline('assistant', 'Please select a place (or click “Why?”) first, then add your preferences.');
    return;
  }

  const contextualMsg =
    `User follow-up: "${text}". Please refine the explanation for “${explain.name}” ` +
    `using the provided metrics (rating, reviews, distance, price) only if present. ` +
    `Omit missing metrics gracefully. Keep it short and user-facing.`;

  streamInlineChat(contextualMsg, { resultExplanation: explain });
  input.value = '';
}

  function attach() {
    const sendBtn = document.getElementById('send');
    const promptInput = document.getElementById('prompt');
    if (sendBtn) sendBtn.addEventListener('click', handleSend);
    if (promptInput) {
      promptInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
          e.preventDefault();
          handleSend();
        }
      });
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', attach, { once: true });
  } else {
    attach();
  }
})();

