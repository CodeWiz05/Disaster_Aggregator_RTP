// Initialize the map
let disasterMap;
let markers = [];
let disasters = [];

function initMap() {
    // Create map centered on world view
    disasterMap = L.map('disaster-map').setView([20, 0], 2);
    
    // Add OpenStreetMap tile layer
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
    }).addTo(disasterMap);
    
    // Add scale
    L.control.scale().addTo(disasterMap);
}

function loadDisasterData() {
    // Clear existing markers
    clearMarkers();
    
    // Get filter values
    const typeFilter = document.getElementById('filter-type').value;
    const severityFilter = parseInt(document.getElementById('filter-severity').value);
    const daysFilter = parseInt(document.getElementById('filter-days').value);
    
    // Fetch data from API
    fetch('/api/disasters')
        .then(response => response.json())
        .then(data => {
            disasters = data;
            
            // Apply filters
            let filteredData = data;
            
            if (typeFilter !== 'all') {
                filteredData = filteredData.filter(d => d.type === typeFilter);
            }
            
            if (severityFilter > 1) {
                filteredData = filteredData.filter(d => d.severity >= severityFilter);
            }
            
            if (daysFilter) {
                const cutoffDate = new Date();
                cutoffDate.setDate(cutoffDate.getDate() - daysFilter);
                filteredData = filteredData.filter(d => new Date(d.timestamp) >= cutoffDate);
            }
            
            // Add markers to map
            addMarkersToMap(filteredData);
            
            // Update table
            updateDisasterTable(filteredData);
        })
        .catch(error => {
            console.error('Error fetching disaster data:', error);
            
            // Load backup data in case of error
            const backupData = getBackupData();
            addMarkersToMap(backupData);
            updateDisasterTable(backupData);
        });
}

function clearMarkers() {
    markers.forEach(marker => disasterMap.removeLayer(marker));
    markers = [];
}

function addMarkersToMap(disasters) {
    disasters.forEach(disaster => {
        // Create marker
        const marker = createDisasterMarker(disaster);
        
        // Add to map and store in array
        marker.addTo(disasterMap);
        markers.push(marker);
    });
    
    // If no disasters match filters, show message
    if (disasters.length === 0) {
        alert('No disasters match your current filters. Try adjusting the criteria.');
    }
}

function createDisasterMarker(disaster) {
    // Define icon colors by type
    const iconColors = {
        earthquake: 'red',
        flood: 'blue',
        wildfire: 'orange',
        storm: 'purple',
        landslide: 'brown',
        other: 'gray'
    };
    
    // Create icon
    const color = iconColors[disaster.type] || 'gray';
    const icon = L.divIcon({
        className: `disaster-marker ${disaster.type}-marker`,
        html: `<div style="background-color: ${color}; width: 12px; height: 12px; border-radius: 50%; border: 2px solid white;"></div>`,
        iconSize: [16, 16],
        iconAnchor: [8, 8]
    });
    
    // Create and return marker with popup
    const marker = L.marker([disaster.lat, disaster.lng], { icon: icon });
    
    // Add popup with disaster info
    marker.bindPopup(`
        <div class="disaster-popup">
            <h3>${disaster.title}</h3>
            <p><strong>Type:</strong> ${disaster.type}</p>
            <p><strong>Severity:</strong> ${disaster.severity} out of 5</p>
            <p><strong>Time:</strong> ${new Date(disaster.timestamp).toLocaleString()}</p>
            <p>${disaster.description}</p>
            <p><strong>Source:</strong> ${disaster.source}</p>
        </div>
    `);
    
    return marker;
}

function updateDisasterTable(disasters) {
    const tbody = document.getElementById('disaster-rows');
    tbody.innerHTML = '';
    
    if (disasters.length === 0) {
        const row = document.createElement('tr');
        row.innerHTML = '<td colspan="6">No disasters match your current filters</td>';
        tbody.appendChild(row);
        return;
    }
    
    // Sort by time (most recent first)
    disasters.sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp));
    
    // Add rows to table
    disasters.forEach(disaster => {
        const row = document.createElement('tr');
        row.classList.add(disaster.type);
        row.classList.add(`severity-${disaster.severity}`);
        
        row.innerHTML = `
            <td>${disaster.title}</td>
            <td>${disaster.type}</td>
            <td>${disaster.severity}</td>
            <td>${new Date(disaster.timestamp).toLocaleString()}</td>
            <td>${disaster.location}</td>
            <td>
                <button class="btn btn-info view-details" data-id="${disaster.id}">Details</button>
                <button class="btn btn-warning subscribe" data-id="${disaster.id}">Alert Me</button>
            </td>
        `;
        
        tbody.appendChild(row);
    });
    
    // Add event listeners to detail buttons
    document.querySelectorAll('.view-details').forEach(button => {
        button.addEventListener('click', () => {
            const id = button.getAttribute('data-id');
            const disaster = disasters.find(d => d.id === id);
            
            if (disaster) {
                showDisasterDetails(disaster);
            }
        });
    });
    
    // Add event listeners to subscribe buttons
    document.querySelectorAll('.subscribe').forEach(button => {
        button.addEventListener('click', () => {
            const id = button.getAttribute('data-id');
            showSubscribeForm(id);
        });
    });
}

function showDisasterDetails(disaster) {
    // Create modal to show details
    const modal = document.createElement('div');
    modal.classList.add('disaster-modal');
    
    modal.innerHTML = `
        <div class="disaster-modal-content">
            <span class="close">&times;</span>
            <h2>${disaster.title}</h2>
            <div class="disaster-details">
                <p><strong>Type:</strong> ${disaster.type}</p>
                <p><strong>Severity:</strong> ${disaster.severity} out of 5</p>
                <p><strong>Time:</strong> ${new Date(disaster.timestamp).toLocaleString()}</p>
                <p><strong>Location:</strong> ${disaster.location}</p>
                <p><strong>Coordinates:</strong> ${disaster.lat}, ${disaster.lng}</p>
                <p><strong>Description:</strong> ${disaster.description}</p>
                <p><strong>Source:</strong> ${disaster.source}</p>
                <p><strong>Status:</strong> ${disaster.status || 'Active'}</p>
                <div class="disaster-actions">
                    <button class="btn btn-primary" onclick="zoomToDisaster(${disaster.lat}, ${disaster.lng})">Show on Map</button>
                    <button class="btn btn-warning" onclick="showSubscribeForm('${disaster.id}')">Set Alert</button>
                </div>
            </div>
        </div>
    `;
    
    document.body.appendChild(modal);
    
    // Add close functionality
    modal.querySelector('.close').addEventListener('click', () => {
        document.body.removeChild(modal);
    });
}

function zoomToDisaster(lat, lng) {
    disasterMap.setView([lat, lng], 8);
    
    // Close any open modals
    const modals = document.querySelectorAll('.disaster-modal');
    modals.forEach(modal => document.body.removeChild(modal));
}

function showSubscribeForm(disasterId) {
    // Create modal for subscription
    const modal = document.createElement('div');
    modal.classList.add('subscribe-modal');
    
    modal.innerHTML = `
        <div class="subscribe-modal-content">
            <span class="close">&times;</span>
            <h2>Subscribe to Alerts</h2>
            <form id="subscribe-form">
                <input type="hidden" name="disaster_id" value="${disasterId}">
                <div class="form-group">
                    <label for="email">Email:</label>
                    <input type="email" id="email" name="email" placeholder="Your email address">
                </div>
                <div class="form-group">
                    <label for="phone">Phone (for SMS):</label>
                    <input type="tel" id="phone" name="phone" placeholder="Your phone number (optional)">
                </div>
                <div class="form-group">
                    <label>Alert Methods:</label>
                    <div class="checkbox-group">
                        <input type="checkbox" id="alert-email" name="alert_methods" value="email" checked>
                        <label for="alert-email">Email</label>
                        
                        <input type="checkbox" id="alert-sms" name="alert_methods" value="sms">
                        <label for="alert-sms">SMS</label>
                        
                        <input type="checkbox" id="alert-web" name="alert_methods" value="web" checked>
                        <label for="alert-web">Web Notification</label>
                    </div>
                </div>
                <button type="submit" class="btn btn-primary">Subscribe</button>
            </form>
        </div>
    `;
    
    document.body.appendChild(modal);
    
    // Add close functionality
    modal.querySelector('.close').addEventListener('click', () => {
        document.body.removeChild(modal);
    });
    
    // Add form submission handler
    modal.querySelector('#subscribe-form').addEventListener('submit', event => {
        event.preventDefault();
        
        const formData = new FormData(event.target);
        
        // Submit subscription
        fetch('/api/subscribe', {
            method: 'POST',
            body: formData
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                alert('You have successfully subscribed to alerts for this disaster.');
                document.body.removeChild(modal);
            } else {
                alert('Error: ' + data.message);
            }
        })
        .catch(error => {
            console.error('Error subscribing:', error);
            alert('An error occurred while processing your subscription. Please try again.');
        });
    });
}

function getBackupData() {
    // Return backup data in case API fails
    return [
        {
            id: 'eq-001',
            title: 'Example Earthquake',
            type: 'earthquake',
            severity: 4,
            timestamp: new Date().toISOString(),
            lat: 34.052235,
            lng: -118.243683,
            location: 'Los Angeles, USA',
            description: 'This is an example earthquake used when the API is unavailable.',
            source: 'Local Backup',
            status: 'Active'
        },
        {
            id: 'fl-001',
            title: 'Example Flood',
            type: 'flood',
            severity: 3,
            timestamp: new Date().toISOString(),
            lat: 29.760427,
            lng: -95.369803,
            location: 'Houston, USA',
            description: 'This is an example flood used when the API is unavailable.',
            source: 'Local Backup',
            status: 'Active'
        }
    ];
}

// Initialize map when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    initMap();
    
    // Load initial data
    loadDisasterData();
    
    // Add event listeners to filter controls
    document.getElementById('filter-type').addEventListener('change', loadDisasterData);
    document.getElementById('filter-severity').addEventListener('change', loadDisasterData);
    document.getElementById('filter-days').addEventListener('change', loadDisasterData);
    
    // Refresh data every 5 minutes
    setInterval(loadDisasterData, 5 * 60 * 1000);
});