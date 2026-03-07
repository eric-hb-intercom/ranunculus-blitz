/**
 * Ranunculus Blitz Tracker — Alpine.js stores & SSE connection
 */

// ── Global helpers ─────────────────────────────────────────────────────
window.fmt = (n) => (typeof n === 'number' ? n.toLocaleString() : n);

document.addEventListener('alpine:init', () => {

    // ── Overview store ──────────────────────────────────────────────────
    Alpine.store('overview', {
        total: 0,
        resolved: 0,
        pct: 0,
        elapsed: 0,
        status: 'setup',
        species: [],
        _timer: null,

        async refresh() {
            try {
                const resp = await fetch('/api/overview');
                const data = await resp.json();
                this.total = data.total_observations;
                this.resolved = data.resolved_count;
                this.pct = data.pct_complete;
                this.elapsed = data.elapsed_seconds;
                this.status = data.blitz_status;
                this.species = data.species || [];
            } catch (e) {
                console.error('Failed to refresh overview:', e);
            }
        },

        get timerDisplay() {
            const h = Math.floor(this.elapsed / 3600);
            const m = Math.floor((this.elapsed % 3600) / 60);
            const s = this.elapsed % 60;
            return `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
        },

        startLocalTimer() {
            if (this._timer) return;
            this._timer = setInterval(() => {
                if (this.status === 'live') {
                    this.elapsed++;
                }
            }, 1000);
        },

        stopLocalTimer() {
            if (this._timer) {
                clearInterval(this._timer);
                this._timer = null;
            }
        }
    });

    // ── Events store ────────────────────────────────────────────────────
    Alpine.store('events', {
        items: [],
        lastId: 0,

        async refresh() {
            try {
                const resp = await fetch(`/api/events?since=${this.lastId}&limit=50`);
                const data = await resp.json();
                if (data.length > 0) {
                    // Merge new events, prioritize participant events over system events
                    const allEvents = [...data, ...this.items];
                    // Separate participant events and quality_change system events
                    const participant = allEvents.filter(e => e.event_type !== 'quality_change');
                    const quality = allEvents.filter(e => e.event_type === 'quality_change');
                    // Keep most participant events, limit quality_change to 5
                    this.items = [...participant, ...quality.slice(0, 5)]
                        .sort((a, b) => b.event_id - a.event_id)
                        .slice(0, 100);
                    this.lastId = Math.max(this.lastId, ...data.map(e => e.event_id));
                }
            } catch (e) {
                console.error('Failed to refresh events:', e);
            }
        },

        eventIcon(type) {
            const icons = {
                identification: '🔍',
                comment: '💬',
                taxon_move: '🔄',
                annotation_added: '🏷️',
                quality_change: '⭐'
            };
            return icons[type] || '📌';
        },

        eventClass(type) {
            const classes = {
                identification: 'id',
                comment: 'comment',
                taxon_move: 'move',
                annotation_added: 'annotation',
                quality_change: 'quality'
            };
            return classes[type] || 'id';
        },

        eventText(event) {
            const actor = event.actor_name || event.actor_login || 'Someone';
            const detail = event.detail || {};
            const species = event.species_group || '';
            const speciesLabel = species ? `a <em>${species}</em>` : 'an observation';
            switch (event.event_type) {
                case 'identification':
                    return `${actor} identified ${speciesLabel} as <em>${detail.taxon_name || '?'}</em>`;
                case 'comment':
                    const body = (detail.body || '').substring(0, 60);
                    return `${actor} commented on ${speciesLabel}: "${body}${body.length >= 60 ? '...' : ''}"`;
                case 'taxon_move':
                    return `${actor} moved ${speciesLabel} to <em>${detail.to_taxon_name || '?'}</em>`;
                case 'annotation_added':
                    return `${actor} annotated ${speciesLabel}: ${detail.value || '?'}`;
                case 'quality_change':
                    const grade = detail.to === 'research' ? 'Research Grade' : detail.to || '?';
                    return `${speciesLabel} reached <strong>${grade}</strong>`;
                default:
                    return `${actor} contributed to ${speciesLabel}`;
            }
        },

        timeAgo(iso) {
            const diff = (Date.now() - new Date(iso).getTime()) / 1000;
            if (diff < 60) return 'just now';
            if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
            return `${Math.floor(diff / 3600)}h ago`;
        }
    });

    // ── Teams store ─────────────────────────────────────────────────────
    Alpine.store('teams', {
        items: [],

        async refresh() {
            try {
                const resp = await fetch('/api/teams');
                this.items = await resp.json();
            } catch (e) {
                console.error('Failed to refresh teams:', e);
            }
        },

        get maxTotal() {
            return Math.max(1, ...this.items.map(t => t.total));
        }
    });

    // ── Participants store ──────────────────────────────────────────────
    Alpine.store('participants', {
        items: [],

        async refresh() {
            try {
                const resp = await fetch('/api/participants');
                this.items = await resp.json();
            } catch (e) {
                console.error('Failed to refresh participants:', e);
            }
        }
    });

    // ── Map filter store (so legend clicks work even if map.js hasn't loaded) ──
    Alpine.store('mapFilter', {
        active: null,

        toggle(filter) {
            this.active = (this.active === filter) ? null : filter;
            // Delegate actual map work to map.js if it's loaded
            if (window._applyMapFilter) {
                window._applyMapFilter(this.active);
            }
            // Update legend highlight via DOM (works regardless of map.js)
            document.querySelectorAll('[data-map-filter]').forEach(el => {
                const f = el.dataset.mapFilter;
                if (this.active === null) {
                    el.classList.remove('legend-active', 'legend-dimmed');
                } else if (f === this.active) {
                    el.classList.add('legend-active');
                    el.classList.remove('legend-dimmed');
                } else {
                    el.classList.remove('legend-active');
                    el.classList.add('legend-dimmed');
                }
            });
        }
    });

    // ── SSE connection ──────────────────────────────────────────────────
    Alpine.store('sse', {
        connected: false,
        _refreshTimer: null,
        _pendingNewEvents: 0,

        connect() {
            const evtSource = new EventSource('/api/stream');

            evtSource.onopen = () => {
                this.connected = true;
                console.log('SSE connected');
            };

            evtSource.onmessage = (e) => {
                try {
                    const data = JSON.parse(e.data);
                    // Track whether any SSE message in this window has new events
                    this._pendingNewEvents += (data.new_events_count || 0);

                    // Debounce: collapse multiple SSE messages within 2s into one refresh
                    if (this._refreshTimer) clearTimeout(this._refreshTimer);
                    this._refreshTimer = setTimeout(() => {
                        this._doRefresh(this._pendingNewEvents > 0);
                        this._pendingNewEvents = 0;
                        this._refreshTimer = null;
                    }, 2000);
                } catch (err) {
                    console.error('SSE message error:', err);
                }
            };

            evtSource.onerror = () => {
                this.connected = false;
                console.warn('SSE disconnected, will reconnect...');
            };
        },

        _doRefresh(hasNewEvents) {
            Alpine.store('overview').refresh();
            Alpine.store('events').refresh();
            Alpine.store('teams').refresh();
            Alpine.store('participants').refresh();

            // Only refresh map when there are actual new events
            if (hasNewEvents && window.refreshMapMarkers) {
                window.refreshMapMarkers();
            }
        }
    });
});

// ── Initialize on page load ─────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    // Wait for Alpine to be ready
    setTimeout(() => {
        Alpine.store('overview').refresh();
        Alpine.store('overview').startLocalTimer();
        Alpine.store('events').refresh();
        Alpine.store('teams').refresh();
        Alpine.store('participants').refresh();
        Alpine.store('sse').connect();
    }, 100);
});
