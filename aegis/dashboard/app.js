/**
 * AegisAI Dashboard - Frontend JavaScript
 * Phase 4: Response & Productization Layer
 * 
 * Polls API endpoints and updates dashboard UI
 */

const API_BASE = '';  // Same origin
const POLL_INTERVAL = 2000;  // 2 seconds

// State
let isConnected = false;
let lastUpdate = null;

// DOM Elements
const statusBadge = document.getElementById('status-badge');
const statusText = statusBadge.querySelector('.status-text');
const activeTracks = document.getElementById('active-tracks');
const anomalies = document.getElementById('anomalies');
const maxRisk = document.getElementById('max-risk');
const fps = document.getElementById('fps');
const riskCard = document.getElementById('risk-card');
const riskTableBody = document.getElementById('risk-table-body');
const eventsList = document.getElementById('events-list');
const lastUpdateEl = document.getElementById('last-update');

/**
 * Fetch data from API endpoint
 */
async function fetchAPI(endpoint) {
    try {
        const response = await fetch(`${API_BASE}${endpoint}`);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        return await response.json();
    } catch (error) {
        console.error(`Failed to fetch ${endpoint}:`, error);
        throw error;
    }
}

/**
 * Update connection status
 */
function setConnectionStatus(connected) {
    isConnected = connected;
    statusBadge.classList.toggle('connected', connected);
    statusBadge.classList.toggle('error', !connected);
    statusText.textContent = connected ? 'Connected' : 'Disconnected';
}

/**
 * Update stats cards
 */
function updateStats(status, statistics) {
    // Active tracks
    activeTracks.textContent = status.active_tracks || 0;
    
    // Anomalies
    anomalies.textContent = status.total_anomalies || 0;
    
    // FPS
    fps.textContent = Math.round(status.current_fps || 0);
    
    // Max risk level
    const level = status.max_risk_level || 'LOW';
    maxRisk.textContent = level;
    
    // Update risk card color
    riskCard.className = 'stat-card risk-card ' + level.toLowerCase();
}

/**
 * Update risk table
 */
function updateRiskTable(tracks) {
    if (!tracks || tracks.length === 0) {
        riskTableBody.innerHTML = `
            <tr class="empty-row">
                <td colspan="5">No concerning tracks</td>
            </tr>
        `;
        return;
    }
    
    riskTableBody.innerHTML = tracks.map(track => `
        <tr>
            <td>#${track.track_id}</td>
            <td>${track.class_name}</td>
            <td><span class="risk-badge ${track.risk_level.toLowerCase()}">${track.risk_level}</span></td>
            <td>${(track.risk_score * 100).toFixed(0)}%</td>
            <td>${track.behaviors.slice(0, 2).join(', ') || '-'}</td>
        </tr>
    `).join('');
}

/**
 * Update events list
 */
function updateEvents(events) {
    if (!events || events.length === 0) {
        eventsList.innerHTML = '<div class="event-item empty">No events yet</div>';
        return;
    }
    
    eventsList.innerHTML = events.slice(-10).reverse().map(event => {
        const time = new Date(event.timestamp).toLocaleTimeString();
        return `
            <div class="event-item">
                <div class="event-time">${time}</div>
                <div class="event-message">
                    <span class="risk-badge ${event.risk_level.toLowerCase()}">${event.risk_level}</span>
                    Track #${event.track_id}: ${event.message}
                </div>
            </div>
        `;
    }).join('');
}

/**
 * Main update loop
 */
async function update() {
    try {
        // Fetch all data in parallel
        const [statusData, statsData, tracksData, eventsData] = await Promise.all([
            fetchAPI('/status'),
            fetchAPI('/statistics'),
            fetchAPI('/tracks/concerning'),
            fetchAPI('/events?limit=10')
        ]);
        
        // Update UI
        updateStats(statusData.system, statsData);
        updateRiskTable(tracksData.tracks);
        updateEvents(eventsData.events);
        
        // Update status
        setConnectionStatus(true);
        lastUpdate = new Date();
        lastUpdateEl.textContent = `Last update: ${lastUpdate.toLocaleTimeString()}`;
        
    } catch (error) {
        setConnectionStatus(false);
        console.error('Update failed:', error);
    }
}

/**
 * Initialize dashboard
 */
function init() {
    console.log('AegisAI Dashboard initializing...');
    
    // Initial update
    update();
    
    // Start polling
    setInterval(update, POLL_INTERVAL);
    
    console.log('Dashboard initialized');
}

// Start when DOM is ready
document.addEventListener('DOMContentLoaded', init);
