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
let markerLayer = L.markerClusterGroup({chunkedLoading:true, maxClusterRadius: 80, spiderfyOnMaxZoom: true, showCoverageOnHover: true, zoomToBoundsOnClick: true}); // Layer group to manage markers efficiently
let disasters = []; // Store raw data fetched from API
let currentFilteredDisasters = []; // Store data currently displayed after filtering

// ... (Keep CSS Injection, Icon Path Fix, Global Vars) ...
let currentMapTheme = 'light'; // Track current map theme
let activeTileLayer = null; // Track the current tile layer

// --- REVISED initMap Function for Horizontal Wrapping ---
function initMap() {
    console.log("Initializing map (Focus on Wrapping)...");
    const mapContainer = document.getElementById('disaster-map');
    if (!mapContainer) { console.error("Map container not found."); return false; }
    if (disasterMap instanceof L.Map) { console.warn("Map already initialized."); return true; }

    try {
        disasterMap = L.map(mapContainer, {
            center: [20, 0],
            zoom: 2,
            minZoom: 2,   // Keep a reasonable minZoom
            maxZoom: 18,
            // --- Use Leaflet defaults for wrapping ---
            worldCopyJump: true, // This is the default and enables wrapping jump
            // --- REMOVE maxBounds ---
            maxBounds: [
                [-85.05112878, -360.0], // Allow panning far left (multiple wraps)
                [85.05112878, 360.0]   // Allow panning far right (multiple wraps)
            ],
            // maxBoundsViscosity: 1.0,
        });

        // --- Set Initial Theme/Tile Layer ---
        const initialTheme = document.documentElement.getAttribute('data-theme') || 'light';
        setMapTheme(initialTheme); // Call this to add the *first* layer

        markerLayer.addTo(disasterMap); // Add cluster group
        L.control.scale().addTo(disasterMap); // Add scale
        console.log("Map initialized with default wrapping.");

        attachZoomListeners(); // Attach custom zoom button listeners

        // InvalidateSize still useful after initial layout
        setTimeout(() => { if (disasterMap) { disasterMap.invalidateSize(); } }, 100);

        return true; // Success

    } catch(e) {
        console.error("Error during map initialization:", e);
        if (disasterMap) { try { disasterMap.remove(); } catch (removeErr) {} disasterMap = undefined; }
        return false;
    }
} // End initMap


// --- Set Map Theme Function (Simplified Tile Options) ---
function setMapTheme(theme) {
    console.log(`Setting map theme to: ${theme}`);
    if (!disasterMap && theme) {
         // If map doesn't exist yet, just store the theme for initMap
         console.log("Map not ready, storing theme for later.");
         currentMapTheme = theme;
         return;
    }
    if (!disasterMap) {
        console.error("Cannot set theme, map object does not exist.");
        return;
    }
     // Only proceed if theme actually changes or no layer exists yet
     if (currentMapTheme === theme && activeTileLayer) {
         console.log("Theme already set.");
         return;
     }

    let newTileUrl = 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png';
    let newAttribution = '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors';
    if (theme === 'dark') {
        newTileUrl = 'https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png';
        newAttribution = '© OSM contributors © CARTO';
    }

    // Remove the old layer *before* adding the new one
    if (activeTileLayer) {
        console.log("Removing previous tile layer.");
        disasterMap.removeLayer(activeTileLayer);
        activeTileLayer = null; // Clear the reference
    }

    // Add the new tile layer with options suitable for wrapping
    console.log("Adding new tile layer:", newTileUrl);
    activeTileLayer = L.tileLayer(newTileUrl, {
        attribution: newAttribution,
        // --- Ensure NO noWrap or bounds for seamless wrapping ---
        minZoom: 2,
        maxZoom: 18
    }).addTo(disasterMap);

    currentMapTheme = theme; // Update the currently active theme
    console.log("Map theme updated.");

} // End setMapTheme


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

             // Apply Filtering
             const cutoff = (daysFilter > 0) ? calculateCutoffDate(daysFilter) : null;
             // --- START DATE DEBUG LOGGING ---
             console.log("Cutoff Date for filtering:", cutoff ? cutoff.toISOString() : "None");
             let reportsChecked = 0;
             let reportsKeptByTime = 0;
             // --- END DATE DEBUG LOGGING ---
             currentFilteredDisasters = disasters.filter(d => {
                let keep = true;
                reportsChecked++; // Increment for every report checked

                // Type filter
                if (typeFilter !== 'all' && d.type !== typeFilter) { keep = false; }
                // Severity filter
                if (keep && severityFilter > 1) { if (typeof d.severity !== 'number' || d.severity < severityFilter) { keep = false; } }
                // Days filter
                if (keep && cutoff) {
                    let reportDate = null;
                    let isValidDate = false;
                    try {
                        reportDate = new Date(d.timestamp); // Try parsing
                        isValidDate = !isNaN(reportDate.getTime()); // Check if valid date object
                        if (!isValidDate) {
                            throw new Error("Parsed Date is Invalid");
                        }
                        // --- Compare Dates ---
                        if (!(reportDate >= cutoff)) {
                             keep = false;
                        } else {
                             reportsKeptByTime++; // Count if kept by time filter
                        }
                        // --- Log comparison for the first few ---
                        if(reportsChecked <= 10) { // Log first 10 checks
                             console.log(`  Report ID ${d.id}, Time: ${d.timestamp}, Parsed: ${reportDate.toISOString()}, Keep (Time)? ${reportDate >= cutoff}`);
                        }
                    } catch (e) {
                        console.warn(`Invalid timestamp for ID ${d.id}: "${d.timestamp}". Excluding. Error: ${e.message}`);
                        keep = false;
                    }
                } else if (keep && !cutoff) {
                     reportsKeptByTime++; // Keep if no time filter applied
                }
                return keep;
            });

            // --- Log final time filter count ---
            console.log(`Total reports checked: ${reportsChecked}. Reports kept after time filter (or no time filter): ${reportsKeptByTime}`);
            console.log(`Final filtered count (all filters): ${currentFilteredDisasters.length}`);
            // --- End final log ---


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
     let markersToCluster = [];
     dataToAdd.forEach(disaster => { // Loop through the filtered data
        // console.log(`Processing disaster ID ${disaster.id || 'N/A'} for marker.`); // Uncomment for deep debug
        const marker = createDisasterMarker(disaster); // Create marker object
        if (marker) { // If marker was created successfully
            try {
                markersToCluster.push(marker); // Add it to the layer group
                markersAddedCount++;
            } catch(e) {
                // Log error if adding to layer fails
                console.error(`Error adding marker for ID ${disaster.id || 'N/A'} to layer group:`, e);
            }
        } else { // If createDisasterMarker returned null
             console.warn(`Marker creation failed for disaster ID ${disaster.id || 'N/A'}, not adding to map.`);
        }
     }); // End forEach
     
     if (markersToCluster.length > 0) {
        console.log(`Adding ${markersToCluster.length} markers to MarkerClusterGroup...`);
        markerLayer.addLayers(markersToCluster); // More efficient bulk add
        console.log(`Successfully added ${markersAddedCount} markers to the cluster group.`);
     } else {
         console.log("No valid markers created to add to the cluster group.");
     }
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