// static/js/map.js

// --- Add Basic CSS for the marker pin ---
const markerPinStyle = document.createElement('style');
markerPinStyle.innerHTML = `
  .marker-pin {
    border-radius: 50%;
    border: 2px solid white; /* Match border in createDisasterMarker */
    box-shadow: 0 0 3px rgba(0,0,0,0.5); /* Add shadow for visibility */
    display: block; /* Ensure it's treated as a block */
  }
  .disaster-marker { /* Ensure the outer container doesn't hide it */
      overflow: visible;
  }
  /* Ensure map container has explicit size */
  #disaster-map {
      height: 500px; /* Or use 100% if container has fixed height */
      width: 100%;
  }
`;
document.head.appendChild(markerPinStyle);
// --- End Basic CSS ---

// --- Fix Leaflet Default Icon Path ---
// Necessary when using Leaflet via CDN to find default icon images
delete L.Icon.Default.prototype._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.3/images/marker-icon-2x.png',
  iconUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.3/images/marker-icon.png',
  shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.3/images/marker-shadow.png',
});
console.log("Leaflet default icon path configured.");
// --- END FIX ---

// --- Global Variables ---
let disasterMap; // Initialize as undefined, will hold the Leaflet map instance
let markerLayer = L.layerGroup(); // Layer group to manage markers efficiently
let disasters = []; // Store raw data fetched from API
let currentFilteredDisasters = []; // Store data currently displayed after filtering

// --- Map Initialization Function ---
function initMap() {
    console.log("Attempting to initialize map...");
    const mapContainer = document.getElementById('disaster-map');
    if (!mapContainer) {
        console.error("Map container 'disaster-map' not found during init.");
        return false; // Indicate initialization failure
    }
    // Check if container has rendered size (basic check)
    if (mapContainer.offsetHeight === 0 || mapContainer.offsetWidth === 0) {
         console.warn("Map container has zero height or width during init. Check CSS. Retrying might be needed.");
         // Returning true here allows the retry logic in DOMContentLoaded to proceed,
         // hoping invalidateSize will fix it later. Could return false if preferred.
    }
     // Prevent re-initialization if map already exists
    if (disasterMap instanceof L.Map) {
        console.warn("Map is already initialized. Skipping re-initialization.");
        return true;
    }

    try {
        // Create the Leaflet map instance
        disasterMap = L.map(mapContainer, {
            center: [20, 0], // Initial geographical center
            zoom: 2,         // Initial zoom level
            minZoom: 2,      // Minimum zoom level allowed
            maxZoom: 18,     // Maximum zoom level allowed
            maxBounds: [[-85.05112878, -180.0], [85.05112878, 180.0]], // Limit panning
            maxBoundsViscosity: 1.0, // Make bounds solid
            worldCopyJump: false     // Prevent map repeating horizontally
        });

        // Add the OpenStreetMap tile layer
        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
            noWrap: true,      // Prevent tiles repeating horizontally
            minZoom: 2,
            maxZoom: 18,
            bounds: [[-90, -180],[90, 180]] // Constrain tile loading
        }).addTo(disasterMap);

        // Add the marker layer group (markers will be added here later)
        markerLayer.addTo(disasterMap);
        // Add the scale control to the map
        L.control.scale().addTo(disasterMap);

        console.log("Map initialized successfully with zoom constraints.");

        // Attach listeners for custom zoom buttons (if they exist on the page)
        attachZoomListeners();

        // Call invalidateSize shortly after initialization as good practice
        // This helps if the container size wasn't fully ready initially
        setTimeout(() => {
            if (disasterMap) {
                 console.log("Running invalidateSize() shortly after init.");
                 disasterMap.invalidateSize(); // Force map to recalculate its size
            }
        }, 50); // 50ms delay

        return true; // Indicate successful initialization

    } catch(e) {
        console.error("Critical error during L.map() or L.tileLayer() initialization:", e);
        // Clean up if partial init happened before error
        if (disasterMap) {
             try { disasterMap.remove(); } catch (removeErr) { console.error("Error removing partially initialized map:", removeErr); }
             disasterMap = undefined; // Reset global variable
        }
        return false; // Indicate initialization failure
    }
} // End initMap

// --- Helper to attach zoom listeners ---
function attachZoomListeners() {
     const zoomInBtn = document.getElementById('zoom-in');
     const zoomOutBtn = document.getElementById('zoom-out');
     const resetViewBtn = document.getElementById('reset-view');
     // Ensure map object exists before adding listeners
     if (disasterMap) {
         if (zoomInBtn) zoomInBtn.addEventListener('click', () => disasterMap.zoomIn());
         if (zoomOutBtn) zoomOutBtn.addEventListener('click', () => disasterMap.zoomOut());
         if (resetViewBtn) resetViewBtn.addEventListener('click', () => disasterMap.setView([20, 0], 2));
     } else {
        console.warn("Cannot attach zoom listeners: map object not available.");
     }
}

// --- Data Loading and Filtering Function ---
function loadDisasterData() {
    // Ensure map is initialized before trying to load data for it
    if (!disasterMap) {
        console.warn("Map not ready, delaying data load slightly...");
        setTimeout(loadDisasterData, 300); // Retry loading after 300ms
        return;
    }

    console.log("Loading disaster data...");
    const loadingRow = document.querySelector('.loading-row');
    const loadingOverlay = document.querySelector('.loading-overlay');
    if(loadingRow) loadingRow.style.display = 'table-row';
    if(loadingOverlay) loadingOverlay.style.display = 'flex';

    // Get filter values from HTML elements
    const typeFilterElement = document.getElementById('filter-type');
    const severityFilterElement = document.getElementById('filter-severity');
    const daysFilterElement = document.getElementById('filter-days');
    const typeFilter = typeFilterElement ? typeFilterElement.value : 'all';
    const severityFilter = severityFilterElement ? parseInt(severityFilterElement.value, 10) || 1 : 1;
    const daysFilter = daysFilterElement ? parseInt(daysFilterElement.value, 10) || 7 : 7;
    console.log(`Filters - Type: ${typeFilter}, Severity >= ${severityFilter}, Days: ${daysFilter}`);

    // Fetch data from the backend API
    fetch('/api/disasters')
        .then(response => {
             if (!response.ok) {
                 // Try to get error message from response body
                return response.text().then(text => { throw new Error(`API Error: ${response.status} - ${text || response.statusText}`) });
            }
            return response.json(); // Parse response as JSON
        })
        .then(data => {
            // Hide loading indicators
             if(loadingRow) loadingRow.style.display = 'none';
             if(loadingOverlay) loadingOverlay.style.display = 'none';

            // Validate received data
            if (!Array.isArray(data)) {
                console.error('API response is not an array:', data);
                alert('Error: Received invalid data format from server.');
                disasters = []; // Reset internal data store
            } else {
                disasters = data; // Store fetched data globally
                console.log(`Fetched ${disasters.length} reports. First report:`, disasters.length > 0 ? JSON.stringify(disasters[0]) : 'N/A');
            }

            // Apply filtering based on current filter values
            const cutoff = (daysFilter > 0) ? calculateCutoffDate(daysFilter) : null;
            currentFilteredDisasters = disasters.filter(d => { // Start filter callback
                let keep = true;
                // Apply Type filter
                if (typeFilter !== 'all' && d.type !== typeFilter) {
                    keep = false;
                }
                // Apply Severity filter
                if (keep && severityFilter > 1) {
                    if (typeof d.severity !== 'number' || d.severity < severityFilter) {
                         keep = false;
                    }
                }
                // Apply Days filter
                if (keep && cutoff) {
                    try {
                        if (!d.timestamp || !(new Date(d.timestamp) >= cutoff)) {
                            keep = false;
                        }
                    } catch (e) {
                        console.warn(`Invalid timestamp for disaster ID ${d.id}: ${d.timestamp}. Excluding.`);
                        keep = false; // Exclude if timestamp is invalid
                    }
                }
                return keep;
            }); // End filter callback

            console.log(`Filtered down to ${currentFilteredDisasters.length} reports.`);
            console.log('First few filtered reports:', currentFilteredDisasters.slice(0, 5));

            // Update map with markers for filtered data
            addMarkersToMap(currentFilteredDisasters);

            // Update table and stats if those functions exist on the page
            if (typeof updateDisasterTable === 'function') {
                updateDisasterTable(currentFilteredDisasters);
            }
            if (typeof updateStatistics === 'function') {
                updateStatistics(currentFilteredDisasters);
            }

        }) // End second .then()
        .catch(error => {
            // Hide loading indicators
             if(loadingRow) loadingRow.style.display = 'none';
             if(loadingOverlay) loadingOverlay.style.display = 'none';
            console.error('Error fetching or processing disaster data:', error);
            alert(`Failed to load disaster data: ${error.message}. Please try refreshing the page.`);
        }); // End .catch()
} // End loadDisasterData

// --- Helper Function: Calculate Cutoff Date ---
function calculateCutoffDate(daysAgo) {
     const cutoff = new Date();
     cutoff.setDate(cutoff.getDate() - daysAgo);
     cutoff.setHours(0, 0, 0, 0); // Set to beginning of the day for consistency
     return cutoff;
}

// --- Marker Creation Function (Using Custom Colors/Intensity) ---
function createDisasterMarker(disaster) {
    // Define base colors for each disaster type
    const baseIconColors = {
        earthquake: '#e53935', // Base Red
        flood: '#1e88e5',      // Base Blue
        wildfire: '#fb8c00',   // Base Orange
        storm: '#8e24aa',      // Base Purple
        landslide: '#6d4c41',  // Base Brown
        other: '#757575'       // Base Gray
    };
    const type = disaster.type || 'other';
    const baseColor = baseIconColors[type] || baseIconColors.other;
    // Use severity from data, default to 1 if missing/invalid
    const severity = (typeof disaster.severity === 'number' && disaster.severity >= 1 && disaster.severity <= 5) ? disaster.severity : 1;

    // Helper function to adjust color intensity (darker for higher severity)
    function adjustColorIntensity(hexColor, severityLevel) {
        const sev = Math.max(1, Math.min(5, severityLevel)); // Clamp severity 1-5
        const darkenFactor = (sev - 1) * 0.15; // 0% for sev 1, up to 60% darker for sev 5
        if (typeof hexColor !== 'string') {
             console.error("adjustColorIntensity received non-string color:", hexColor);
             return '#757575'; // Default gray
        }
        let hex = hexColor.startsWith('#') ? hexColor.slice(1) : hexColor;
        if (hex.length === 3) { hex = hex[0]+hex[0]+hex[1]+hex[1]+hex[2]+hex[2]; }
        if (!/^[0-9a-fA-F]{6}$/.test(hex)) {
            console.error("adjustColorIntensity received invalid hex value:", hexColor);
            return '#757575';
        }
        try {
            const r = parseInt(hex.substring(0, 2), 16);
            const g = parseInt(hex.substring(2, 4), 16);
            const b = parseInt(hex.substring(4, 6), 16);
            const newR = Math.max(0, Math.min(255, Math.round(r * (1 - darkenFactor))));
            const newG = Math.max(0, Math.min(255, Math.round(g * (1 - darkenFactor))));
            const newB = Math.max(0, Math.min(255, Math.round(b * (1 - darkenFactor))));
            return `#${newR.toString(16).padStart(2, '0')}${newG.toString(16).padStart(2, '0')}${newB.toString(16).padStart(2, '0')}`;
        } catch(e) {
             console.error("Error during color intensity calculation:", e, "Input:", hexColor);
             return '#757575';
        }
     } // End adjustColorIntensity

    const adjustedColor = adjustColorIntensity(baseColor, severity);

    // Define marker appearance
    const pinSize = 16; // Diameter of the colored circle
    const borderSize = 2;
    const totalSize = pinSize + borderSize * 2;
    const iconHtml = `<div class="marker-pin" style="background-color: ${adjustedColor}; width: ${pinSize}px; height: ${pinSize}px;"></div>`;

    // Create the custom Leaflet DivIcon
    const icon = L.divIcon({
        className: `disaster-marker severity-${severity} type-${type}`, // Add CSS classes
        html: iconHtml,
        iconSize: [totalSize, totalSize], // Total size including border
        iconAnchor: [totalSize / 2, totalSize / 2] // Center the icon anchor
    });

    // Create the Leaflet marker object
    let marker;
    try {
       // Parse and validate coordinates
       const lat = parseFloat(disaster.lat);
       const lng = parseFloat(disaster.lng);
       if (isNaN(lat) || isNaN(lng)) {
            throw new Error(`Lat/Lng are not valid numbers: [${disaster.lat}, ${disaster.lng}]`);
       }
       // Create the marker with the custom icon and coordinates
       marker = L.marker([lat, lng], {
           icon: icon,
           title: `${disaster.title || 'Disaster Event'} (Severity: ${severity})` // Tooltip on hover
       });
    } catch (e) {
        console.error(`Error creating L.marker for disaster ID ${disaster.id || 'N/A'} with data ${JSON.stringify(disaster)}:`, e);
        return null; // Return null if marker creation fails
    }

    // --- Create Popup Content ---
    // Format timestamp nicely
    let formattedTime = 'Timestamp N/A';
    try {
       if (disaster.timestamp) {
           formattedTime = new Date(disaster.timestamp).toLocaleString(undefined, {
               dateStyle: 'medium', timeStyle: 'short'
           });
       }
    } catch (e) { console.warn(`Error formatting timestamp for ${disaster.id || 'N/A'}`); }

    // Build popup HTML safely using sanitization
    const popupContent = `
        <div class="map-popup">
            <h4>${sanitizeHtml(disaster.title || 'Disaster Event')}</h4>
            <p><strong>Type:</strong> ${sanitizeHtml(type)}</p>
            <p><strong>Severity:</strong> ${severity} / 5</p>
            <p><strong>Time:</strong> ${formattedTime}</p>
            ${disaster.description ? `<p><strong>Details:</strong> ${sanitizeHtml(disaster.description.substring(0, 150))}${disaster.description.length > 150 ? '...' : ''}</p>` : ''}
            <p><strong>Source:</strong> ${sanitizeHtml(disaster.source || 'N/A')}</p>
            <hr>
             <button class="btn btn-sm popup-details" data-id="${disaster.id || ''}">View Details</button>
        </div>
    `;
    marker.bindPopup(popupContent);

    // Add listener to the "View Details" button inside the popup
    marker.on('popupopen', function () {
        const detailButton = this.getPopup().getElement().querySelector('.popup-details');
        if (detailButton) {
            const handleDetailClick = function() {
                const disasterId = this.getAttribute('data-id');
                // Check if the viewDisasterDetails function is defined globally before calling
                if (disasterId && typeof viewDisasterDetails === 'function') {
                     viewDisasterDetails(disasterId); // Call the global function
                } else {
                     console.error("Cannot view details: Invalid ID or viewDisasterDetails function missing.");
                }
            };
            // Ensure listener isn't added multiple times if popup is re-opened
            detailButton.onclick = null; // Clear any previous inline handler
            detailButton.addEventListener('click', handleDetailClick, { once: true }); // Run only once per open
        }
    });

    return marker; // Return the created marker object
} // End createDisasterMarker

// --- Function to Add Markers to Map Layer ---
function addMarkersToMap(dataToAdd) {
     console.log(`Attempting to add ${dataToAdd.length} markers to map.`);
     markerLayer.clearLayers(); // Remove all markers from the layer group first

     if (!disasterMap) {
         console.error("Cannot add markers, map is not initialized.");
         return;
     }

     let markersAddedCount = 0;
     dataToAdd.forEach(disaster => { // Loop through the filtered data
        // console.log(`Processing disaster ID ${disaster.id || 'N/A'} for marker.`); // Uncomment for deep debug
        const marker = createDisasterMarker(disaster); // Create marker object
        if (marker) { // If marker was created successfully
            try {
                markerLayer.addLayer(marker); // Add it to the layer group
                markersAddedCount++;
            } catch(e) {
                // Log error if adding to layer fails
                console.error(`Error adding marker for ID ${disaster.id || 'N/A'} to layer group:`, e);
            }
        } else { // If createDisasterMarker returned null
             console.warn(`Marker creation failed for disaster ID ${disaster.id || 'N/A'}, not adding to map.`);
        }
     }); // End forEach

     console.log(`Successfully added ${markersAddedCount} markers to the map layer.`);
} // End addMarkersToMap

// --- Utility: Basic HTML Sanitizer (CORRECTED) ---
// Simple replacement function to prevent basic XSS in popups/tables
function sanitizeHtml(str) {
    if (typeof str !== 'string') return '';
    return str.replace(/&/g, '&') // Must be first
              .replace(/</g, '<')
              .replace(/>/g, '>')
              .replace(/"/g, '"')
              .replace(/'/g, '&#039'); // Corrected: Replace single quote with its HTML entity
}

// --- Placeholder Function: View Details ---
// This function is called from marker popups or potentially table buttons
// It needs access to the global 'disasters' array to find the data
function viewDisasterDetails(id) {
    console.log(`viewDisasterDetails called for ID: ${id}`);
    // Find the disaster data using the original fetched list
    const disaster = disasters.find(d => String(d.id) === String(id)); // Compare IDs as strings for safety

    if (disaster) {
         // Replace this alert with logic to show details in a modal or sidebar
         const details = `
             Disaster Details:\n------------------
             Title: ${disaster.title || 'N/A'}
             Type: ${disaster.type || 'N/A'}
             Severity: ${disaster.severity || 'N/A'} / 5
             Time: ${disaster.timestamp ? new Date(disaster.timestamp).toLocaleString() : 'N/A'}
             Location: [${disaster.lat}, ${disaster.lng}]
             Description: ${disaster.description || 'No description.'}
             Source: ${disaster.source || 'N/A'}
         `;
         alert(details);
    } else {
        console.error(`Details for disaster ID ${id} not found in fetched data.`);
        alert(`Details for disaster ID ${id} not found.`);
    }
}


// --- DOM Ready Initialization ---
// This block runs once the HTML is fully loaded and parsed
document.addEventListener('DOMContentLoaded', () => {
    console.log("DOM fully loaded and parsed");

    // Check if the map container element exists on the current page
    if (document.getElementById('disaster-map')) {
        // --- DELAY the map initialization slightly ---
        console.log("Delaying map initialization slightly...");
        setTimeout(() => {
            if (initMap()) { // Try to initialize the map; initMap returns true on success
                // If map initialization was successful, load the disaster data
                loadDisasterData();
            } else {
                // Handle case where initMap failed even after delay
                console.error("Map initialization failed even after delay.");
                alert("Could not initialize the map. Please check the console for errors or reload the page.");
            }
        }, 250); // Delay in milliseconds (e.g., 250ms = 1/4 second)

        // Attach listeners for non-map elements (filters, etc.) immediately
        // These don't depend on the map being fully ready, just the DOM
        const applyFiltersBtn = document.getElementById('apply-filters');
        const resetFiltersBtn = document.getElementById('reset-filters');

        if (applyFiltersBtn) {
             console.log("Attaching listener to Apply Filters button.");
             // When Apply is clicked, loadDisasterData will run (and it checks if map is ready)
             applyFiltersBtn.addEventListener('click', loadDisasterData);
        } else {
             console.warn("'apply-filters' button not found.");
        }

        if (resetFiltersBtn) {
             console.log("Attaching listener to Reset Filters button.");
             resetFiltersBtn.addEventListener('click', () => { // Start reset listener function
                // Reset filter dropdowns visually
                const typeFilter = document.getElementById('filter-type');
                const severityFilter = document.getElementById('filter-severity');
                const daysFilter = document.getElementById('filter-days');
                if (typeFilter) typeFilter.value = 'all';
                if (severityFilter) severityFilter.value = '1';
                if (daysFilter) daysFilter.value = '7'; // Reset to default
                // Trigger data load with default filters
                loadDisasterData(); // loadDisasterData will run checks
             }); // End reset listener function
        } else {
            console.warn("'reset-filters' button not found.");
        }

    } else {
        // Log if the map container isn't found (e.g., on login/history/report pages)
        console.log("Map container 'disaster-map' not found on this page. Skipping map-related initialization.");
    }

}); // End DOMContentLoaded listener