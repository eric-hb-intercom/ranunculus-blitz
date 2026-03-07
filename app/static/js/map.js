/**
 * Ranunculus Blitz Tracker — Leaflet map with individual CircleMarkers
 *
 * Uses Canvas renderer for performance with 14K+ markers.
 * Every observation is shown as its own dot — no clustering.
 * Legend items are clickable to filter by species or resolved status.
 */

let map = null;
let markerLayer = null;
let markers = {};  // obs_id -> circleMarker
let obsData = {};  // obs_id -> obs object (for popups)

// Active filter: null = show all, 'resolved' = resolved only, 'Ranunculus acris' = that species only
let activeFilter = null;

// Timestamp of last successful full or delta fetch, for delta updates
let lastMapRefresh = null;

// Canvas renderer — created lazily in initMap() so map.js loads even if Leaflet isn't ready yet
let canvasRenderer = null;

function initMap(elementId, options = {}) {
    if (!canvasRenderer) {
        canvasRenderer = L.canvas({ padding: 0.5 });
    }
    const defaults = {
        center: [54.5, -2.5],
        zoom: 6,
        minZoom: 5,
        maxZoom: 18,
    };
    const opts = { ...defaults, ...options };

    map = L.map(elementId, {
        center: opts.center,
        zoom: opts.zoom,
        minZoom: opts.minZoom,
        maxZoom: opts.maxZoom,
        preferCanvas: true,
    });

    // OpenStreetMap tiles — no API key needed
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
        maxZoom: 19,
    }).addTo(map);

    // Layer group for all markers
    markerLayer = L.layerGroup().addTo(map);

    // Load initial data
    refreshMapMarkers();
}


/**
 * Toggle map filter. Clicking the same filter again clears it (show all).
 * @param {string} filter - 'resolved' or a species_group name like 'Ranunculus acris'
 */
function toggleMapFilter(filter) {
    if (activeFilter === filter) {
        activeFilter = null;  // toggle off
    } else {
        activeFilter = filter;
    }
    applyFilter();
    updateLegendHighlight();
}

/**
 * Called by Alpine store to apply a filter value set from the UI.
 */
function _applyMapFilter(filter) {
    activeFilter = filter;
    applyFilter();
}

function applyFilter() {
    for (const [obsId, marker] of Object.entries(markers)) {
        const obs = obsData[obsId];
        if (!obs) continue;

        const visible = passesFilter(obs);
        if (visible) {
            if (!markerLayer.hasLayer(marker)) {
                markerLayer.addLayer(marker);
            }
        } else {
            if (markerLayer.hasLayer(marker)) {
                markerLayer.removeLayer(marker);
            }
        }
    }
}

function passesFilter(obs) {
    if (!activeFilter) return true;
    if (activeFilter === 'resolved') return obs.resolved;
    // Species filter — show unresolved of that species
    return obs.species_group === activeFilter && !obs.resolved;
}

function updateLegendHighlight() {
    // Update all legend items to show active state
    document.querySelectorAll('[data-map-filter]').forEach(el => {
        const filter = el.dataset.mapFilter;
        if (activeFilter === null) {
            el.classList.remove('legend-active', 'legend-dimmed');
        } else if (filter === activeFilter) {
            el.classList.add('legend-active');
            el.classList.remove('legend-dimmed');
        } else {
            el.classList.remove('legend-active');
            el.classList.add('legend-dimmed');
        }
    });
}


async function refreshMapMarkers() {
    try {
        // Delta updates: after first load, only fetch changed observations
        let url = '/api/map-data';
        const isDelta = lastMapRefresh !== null;
        if (isDelta) {
            url += `?since=${encodeURIComponent(lastMapRefresh)}`;
        }

        const resp = await fetch(url);
        const data = await resp.json();

        // Also fetch recent events for highlight effects
        const eventsResp = await fetch('/api/events?limit=20');
        const events = await eventsResp.json();

        const eventTypeByObs = {};
        for (const e of events) {
            if (!eventTypeByObs[e.obs_id]) {
                eventTypeByObs[e.obs_id] = e.event_type;
            }
        }

        // Track the latest updated_at for next delta
        let maxUpdatedAt = lastMapRefresh;
        for (const obs of data) {
            if (obs.updated_at && (!maxUpdatedAt || obs.updated_at > maxUpdatedAt)) {
                maxUpdatedAt = obs.updated_at;
            }
        }

        // Update or create markers
        const currentIds = isDelta ? null : new Set();  // Only track IDs on full load
        for (const obs of data) {
            if (currentIds) currentIds.add(obs.obs_id);
            obsData[obs.obs_id] = obs;

            const color = getMarkerColor(obs, eventTypeByObs[obs.obs_id]);
            const hasRecentEvent = !!eventTypeByObs[obs.obs_id];
            const radius = hasRecentEvent ? 5 : (obs.resolved ? 4 : 3);
            const weight = hasRecentEvent ? 2 : 1;
            const stroke = hasRecentEvent ? '#ffffff' : 'rgba(0,0,0,0.4)';

            if (markers[obs.obs_id]) {
                // Update existing marker
                markers[obs.obs_id].setStyle({
                    fillColor: color,
                    color: stroke,
                    radius: radius,
                    weight: weight,
                    fillOpacity: obs.resolved ? 0.9 : 0.8,
                });
            } else {
                // Create new circleMarker
                const marker = L.circleMarker([obs.lat, obs.lng], {
                    renderer: canvasRenderer,
                    radius: radius,
                    fillColor: color,
                    color: stroke,
                    weight: weight,
                    opacity: 1,
                    fillOpacity: obs.resolved ? 0.9 : 0.8,
                });

                marker.on('click', () => {
                    const o = obsData[obs.obs_id] || obs;
                    L.popup()
                        .setLatLng([o.lat, o.lng])
                        .setContent(createPopupContent(o))
                        .openOn(map);
                });

                markers[obs.obs_id] = marker;

                // Only add to layer if it passes the current filter
                if (passesFilter(obs)) {
                    markerLayer.addLayer(marker);
                }
            }
        }

        // Remove markers for obs no longer in data (only on full load)
        if (currentIds) {
            for (const [obsId, marker] of Object.entries(markers)) {
                if (!currentIds.has(parseInt(obsId))) {
                    markerLayer.removeLayer(marker);
                    delete markers[obsId];
                    delete obsData[obsId];
                }
            }
        }

        lastMapRefresh = maxUpdatedAt || new Date().toISOString();
    } catch (e) {
        console.error('Failed to refresh map markers:', e);
    }
}


function getMarkerColor(obs, recentEventType) {
    if (obs.resolved) return '#3a8a3f';  // Solid green

    switch (recentEventType) {
        case 'identification': return '#4caf50';  // Bright green
        case 'comment': return '#26a69a';          // Teal
        case 'taxon_move': return '#ff9800';       // Warm orange (distinct from gold)
        case 'annotation_added': return '#ff9800'; // Warm orange
        default:
            // Use species color, fallback to grey
            return obs.species_color || '#9e9e9e';
    }
}


function darken(hex, amount) {
    // Simple hex color darkener for border color
    const num = parseInt(hex.replace('#', ''), 16);
    const r = Math.max(0, (num >> 16) - Math.round(255 * amount));
    const g = Math.max(0, ((num >> 8) & 0x00FF) - Math.round(255 * amount));
    const b = Math.max(0, (num & 0x0000FF) - Math.round(255 * amount));
    return `#${(r << 16 | g << 8 | b).toString(16).padStart(6, '0')}`;
}


function createPopupContent(obs) {
    const img = obs.photo_url
        ? `<img class="popup-thumb" src="${obs.photo_url}" alt="Observation photo" loading="lazy">`
        : '';

    const speciesBadge = obs.species_group
        ? `<span class="popup-species" style="background:${obs.species_color || '#888'}">${obs.species_group}</span>`
        : '';

    // Build claim/release action section
    let claimHtml = '';
    const username = localStorage.getItem('blitz_username');

    if (!obs.resolved) {
        if (!obs.claimed_by) {
            if (username) {
                claimHtml = `
                    <div class="popup-actions">
                        <button class="btn btn-primary btn-sm" onclick="window.claimFromMap(${obs.obs_id})">Claim</button>
                    </div>`;
            } else {
                claimHtml = `
                    <div class="popup-actions">
                        <a href="/observations" class="popup-claim-link">Set username to claim</a>
                    </div>`;
            }
        } else if (obs.claimed_by === username) {
            claimHtml = `
                <div class="popup-actions">
                    <span class="popup-claimed popup-claimed-you">Claimed by you</span>
                    <button class="btn btn-secondary btn-sm" onclick="window.releaseFromMap(${obs.obs_id})">Release</button>
                </div>`;
        } else {
            claimHtml = `
                <div class="popup-actions">
                    <span class="popup-claimed">Claimed by <strong>${obs.claimed_by}</strong></span>
                </div>`;
        }
    }

    return `
        <div style="min-width:200px">
            ${img}
            <div class="popup-taxon">${obs.taxon_name || 'Unknown'}</div>
            ${speciesBadge}
            <div class="popup-meta">
                ${obs.observed_on ? `Observed: ${obs.observed_on}` : ''}
                ${obs.quality_grade ? `<br>Quality: ${obs.quality_grade.replace('_', ' ')}` : ''}
            </div>
            <a class="popup-link" href="https://www.inaturalist.org/observations/${obs.obs_id}" target="_blank">
                View on iNaturalist &rarr;
            </a>
            ${claimHtml}
        </div>
    `;
}


async function claimFromMap(obsId) {
    const username = localStorage.getItem('blitz_username');
    if (!username) return;

    try {
        const resp = await fetch(`/api/observations/${obsId}/claim`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ login: username }),
        });
        if (!resp.ok) throw new Error(await resp.text());

        // Update local data and re-open popup with fresh content
        if (obsData[obsId]) {
            obsData[obsId].claimed_by = username;
            const o = obsData[obsId];
            map.closePopup();
            L.popup()
                .setLatLng([o.lat, o.lng])
                .setContent(createPopupContent(o))
                .openOn(map);
        }
    } catch (e) {
        console.error('Failed to claim observation:', e);
    }
}


async function releaseFromMap(obsId) {
    const username = localStorage.getItem('blitz_username');
    if (!username) return;

    try {
        const resp = await fetch(`/api/observations/${obsId}/claim`, {
            method: 'DELETE',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ login: username }),
        });
        if (!resp.ok) throw new Error(await resp.text());

        if (obsData[obsId]) {
            obsData[obsId].claimed_by = null;
            const o = obsData[obsId];
            map.closePopup();
            L.popup()
                .setLatLng([o.lat, o.lng])
                .setContent(createPopupContent(o))
                .openOn(map);
        }
    } catch (e) {
        console.error('Failed to release observation:', e);
    }
}


// Expose globally for SSE refresh, legend filtering, map init, and popup actions
window.refreshMapMarkers = refreshMapMarkers;
window.initMap = initMap;
window.toggleMapFilter = toggleMapFilter;
window._applyMapFilter = _applyMapFilter;
window.claimFromMap = claimFromMap;
window.releaseFromMap = releaseFromMap;
