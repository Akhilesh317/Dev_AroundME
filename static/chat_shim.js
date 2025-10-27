/* chat_shim.js — add data-name & data-explain to your result cards */

(function(){
  function round3(x){ return Math.round((x + Number.EPSILON) * 1000) / 1000; }
  function mapVals(o,f){ const r={}; for(const k in o||{}) r[k]=f(o[k]); return r; }
  function haversineMeters(lat1,lon1,lat2,lon2){
    const R=6371000, toRad=x=>x*Math.PI/180;
    const dLat=toRad(lat2-lat1), dLon=toRad(lon2-lon1);
    const a=Math.sin(dLat/2)**2 + Math.cos(toRad(lat1))*Math.cos(toRad(lat2))*Math.sin(dLon/2)**2;
    return 2*R*Math.asin(Math.sqrt(a));
  }

  // --- Normalizers (Google / Yelp) → unified object u ---
  function normGoogle(p, weights){
    const id = p.place_id || p.id || p.reference || `g_${(p.name||'').slice(0,8)}_${Math.random().toString(36).slice(2,6)}`;
    const name = p.name || 'Unknown';
    const rating = Number(p.rating ?? 0);
    const reviews = Number(p.user_ratings_total ?? p.user_ratings_count ?? 0);
    const price_level = Number(p.price_level ?? -1); // -1 unknown
    let distance_m = Number(p._distance_m ?? p.distance_m ?? 0);

    // try compute distance if coords exist and you have user coords on window
    try {
      const lat = typeof p.geometry?.location?.lat === 'function' ? p.geometry.location.lat() : (p.geometry?.location?.lat ?? p.geometry?.location?.latitude);
      const lng = typeof p.geometry?.location?.lng === 'function' ? p.geometry.location.lng() : (p.geometry?.location?.lng ?? p.geometry?.location?.longitude);
      if (!distance_m && window.AM_user && typeof lat === 'number' && typeof lng === 'number') {
        distance_m = haversineMeters(window.AM_user.lat, window.AM_user.lng, lat, lng);
      }
    } catch {}

    const w = Object.assign({ rating: 0.45, distance: -0.25, price: 0.1, reviews: 0.2 }, weights||{});
    const contributions = {
      rating: w.rating * rating,
      distance: w.distance * (distance_m/1000),
      price: price_level >= 0 ? w.price * (3 - price_level) : 0,
      reviews: w.reviews * Math.log10(Math.max(reviews, 1)+1),
    };
    const score = Object.values(contributions).reduce((a,b)=>a+b,0);

    return {source:'google', id, name, rating, reviews, price_level, distance_m, score, contributions,
      raw:{ rating, reviews, price_level, distance_m }};
  }

  function normYelp(b, weights){
    const id = b.id || `y_${(b.name||'').slice(0,8)}_${Math.random().toString(36).slice(2,6)}`;
    const name = b.name || 'Unknown';
    const rating = Number(b.rating ?? 0);
    const reviews = Number(b.review_count ?? 0);
    const price_level = (b.price ? Math.min(b.price.length-1, 4) : -1); // "$"->0, "$$$$"->3/4
    const distance_m = Number(b.distance ?? b._distance_m ?? 0);

    const w = Object.assign({ rating: 0.45, distance: -0.25, price: 0.1, reviews: 0.2 }, weights||{});
    const contributions = {
      rating: w.rating * rating,
      distance: w.distance * (distance_m/1000),
      price: price_level >= 0 ? w.price * (3 - price_level) : 0,
      reviews: w.reviews * Math.log10(Math.max(reviews, 1)+1),
    };
    const score = Object.values(contributions).reduce((a,b)=>a+b,0);

    return {source:'yelp', id, name, rating, reviews, price_level, distance_m, score, contributions,
      raw:{ rating, reviews, price_level, distance_m }};
  }

  function toExplain(u){
    return {
      placeId: u.id,
      name: u.name,
      score: round3(u.score),
      contributions: mapVals(u.contributions, round3),
      raw: {
        rating: u.raw.rating,
        distance_m: Math.round(u.raw.distance_m||0),
        price_level: u.raw.price_level,
        reviews: u.raw.reviews
      }
    };
  }

  // --- Tag DOM cards with data-* so /chat can explain rankings
  /**
   * results: array of raw Google or Yelp objects (or mixed)
   * options:
   *   { cardSelector?: string, listSelector?: string, weights?: {...}, source?: 'google'|'yelp'|'auto' }
   * How it matches:
   *   - It takes cards under listSelector (default "#placesList .place-card" OR "#placesList > *")
   *   - It tries to match by name (card text vs result name); fallback pairs in order.
   */
  function AM_tagCardsFromResults(results, options){
    const opts = options||{};
    const list = document.querySelector('#placesList');
    if (!list) return;
    const cards = list.querySelectorAll(opts.cardSelector || '.place-card, :scope > *');

    const weights = opts.weights || {};
    const unified = (results||[]).map(r=>{
      if (opts.source === 'google' || r.place_id !== undefined || r.user_ratings_total !== undefined) return normGoogle(r, weights);
      if (opts.source === 'yelp' || r.review_count !== undefined || r.alias !== undefined) return normYelp(r, weights);
      return (r.place_id !== undefined) ? normGoogle(r, weights) : normYelp(r, weights);
    });

    // name → unified map for quick lookup
    const byName = new Map();
    unified.forEach(u => byName.set((u.name||'').toLowerCase(), u));

    let i = 0;
    cards.forEach(card=>{
      const nameAttr = card.getAttribute('data-name');
      const textName = (nameAttr || card.getAttribute('data-title') || card.textContent || '').trim();
      const key = textName.toLowerCase();
      let u = byName.get(key);

      if (!u && i < unified.length) { // fallback: pair by order
        u = unified[i++];
      }

      if (u) {
        card.dataset.id = u.id;
        card.dataset.name = u.name;
        card.dataset.score = String(round3(u.score));
        card.dataset.explain = JSON.stringify(toExplain(u));
      }

      // allow selection for follow-up
      card.addEventListener('click', ()=>{
        document.querySelectorAll('#placesList .place-card.selected, #placesList > *.selected').forEach(el=>el.classList.remove('selected'));
        card.classList.add('selected');
      });
    });

    if (window.AM_showFollowupCTA) window.AM_showFollowupCTA();
  }

  // expose globally so your existing code can call it
  window.AM_tagCardsFromResults = AM_tagCardsFromResults;
  window.AM_normGoogle = normGoogle;
  window.AM_normYelp = normYelp;
})();
