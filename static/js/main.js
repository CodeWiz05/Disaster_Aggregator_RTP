// Main JavaScript for Disaster Aggregator

document.addEventListener('DOMContentLoaded', function() {
    // Initialize tooltips and popovers if using them
    initializeTooltips();
    
    // Setup event handlers for UI interactions
    setupEventHandlers();
    
    // Check for notifications permission
    checkNotificationPermission();
});

function initializeTooltips() {
    // Initialize tooltips if needed
    const tooltipElements = document.querySelectorAll('[data-tooltip]');
    tooltipElements.forEach(el => {
        el.setAttribute('title', el.getAttribute('data-tooltip'));
        // Basic tooltip functionality could be enhanced later
    });
}

function setupEventHandlers() {
    // Mobile menu toggle
    const menuToggle = document.getElementById('mobile-menu-toggle');
    if (menuToggle) {
        menuToggle.addEventListener('click', function() {
            const nav = document.querySelector('nav ul');
            nav.classList.toggle('show');
        });
    }
    
    // Report form submission
    const reportForm = document.getElementById('disaster-report-form');
    if (reportForm) {
        reportForm.addEventListener('submit', function(e) {
            e.preventDefault();
            submitDisasterReport(this);
        });
    }
    
    // Subscription form for alerts
    const alertForm = document.getElementById('alert-subscription-form');
    if (alertForm) {
        alertForm.addEventListener('submit', function(e) {
            e.preventDefault();
            subscribeToAlerts(this);
        });
    }
    
    // Setup tab navigation if present
    setupTabNavigation();
}

function setupTabNavigation() {
    const tabLinks = document.querySelectorAll('.tab-link');
    if (tabLinks.length > 0) {
        tabLinks.forEach(link => {
            link.addEventListener('click', function(e) {
                e.preventDefault();
                
                // Get the tab to activate
                const tabId = this.getAttribute('data-tab');
                
                // Deactivate all tabs and links
                document.querySelectorAll('.tab-link').forEach(el => el.classList.remove('active'));
                document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
                
                // Activate selected tab and link
                this.classList.add('active');
                document.getElementById(tabId).classList.add('active');
            });
        });
        
        // Activate first tab by default
        tabLinks[0].click();
    }
}

function submitDisasterReport(form) {
    const formData = new FormData(form);
    
    // Add timestamp
    formData.append('timestamp', new Date().toISOString());
    
    // Submit the report
    fetch('/api/report', {
        method: 'POST',
        body: formData
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showNotification('Report Submitted', 'Thank you for your disaster report. It will be verified by our team.');
            form.reset();
        } else {
            showNotification('Error', data.message || 'There was an error submitting your report. Please try again.');
        }
    })
    .catch(error => {
        console.error('Error submitting report:', error);
        showNotification('Error', 'An unexpected error occurred. Please try again later.');
    });
}

function subscribeToAlerts(form) {
    const formData = new FormData(form);
    
    fetch('/api/subscribe', {
        method: 'POST',
        body: formData
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showNotification('Subscription Successful', 'You have been subscribed to disaster alerts.');
            form.reset();
        } else {
            showNotification('Error', data.message || 'There was an error processing your subscription. Please try again.');
        }
    })
    .catch(error => {
        console.error('Error subscribing:', error);
        showNotification('Error', 'An unexpected error occurred. Please try again later.');
    });
}

function showNotification(title, message) {
    // Create notification element
    const notification = document.createElement('div');
    notification.classList.add('notification');
    
    notification.innerHTML = `
        <div class="notification-content">
            <h3>${title}</h3>
            <p>${message}</p>
            <button class="close-notification">&times;</button>
        </div>
    `;
    
    // Add to DOM
    document.body.appendChild(notification);
    
    // Add close button functionality
    notification.querySelector('.close-notification').addEventListener('click', function() {
        document.body.removeChild(notification);
    });
    
    // Auto-remove after 5 seconds
    setTimeout(() => {
        if (document.body.contains(notification)) {
            document.body.removeChild(notification);
        }
    }, 5000);
}

function checkNotificationPermission() {
    if ('Notification' in window) {
        if (Notification.permission !== 'granted' && Notification.permission !== 'denied') {
            // Show option to enable browser notifications
            const notifBar = document.createElement('div');
            notifBar.classList.add('notification-permission-bar');
            notifBar.innerHTML = `
                <p>Enable notifications to receive disaster alerts?</p>
                <button id="enable-notifications" class="btn btn-primary">Enable</button>
                <button id="dismiss-notifications" class="btn btn-secondary">Dismiss</button>
            `;
            
            document.body.appendChild(notifBar);
            
            // Add event listeners
            document.getElementById('enable-notifications').addEventListener('click', function() {
                Notification.requestPermission().then(function(permission) {
                    if (permission === 'granted') {
                        showNotification('Notifications Enabled', 'You will now receive disaster alerts.');
                    }
                    document.body.removeChild(notifBar);
                });
            });
            
            document.getElementById('dismiss-notifications').addEventListener('click', function() {
                document.body.removeChild(notifBar);
            });
        }
    }
}