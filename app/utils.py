import json
import os
from datetime import datetime, timedelta
import re

def get_all_disasters(include_unverified=False):
    """Get all disaster data from cache or database"""
    # Load data from cache file
    cache_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'cached_reports.json')
    
    if os.path.exists(cache_path):
        with open(cache_path, 'r') as f:
            disasters = json.load(f)
    else:
        disasters = []
    
    # Filter out unverified reports if needed
    if not include_unverified:
        disasters = [d for d in disasters if d.get('verified', False)]
    
    return disasters

def filter_disasters(disasters, disaster_type=None, days=None, severity=None):
    """Filter disasters by type, recency, and/or severity"""
    filtered = disasters
    
    if disaster_type:
        filtered = [d for d in filtered if d.get('type') == disaster_type]
    
    if days:
        cutoff = datetime.now() - timedelta(days=days)
        filtered = [d for d in filtered if datetime.fromisoformat(d.get('timestamp')) > cutoff]
    
    if severity:
        filtered = [d for d in filtered if d.get('severity', 0) >= severity]
    
    return filtered

def sanitize_input(text):
    """Basic input sanitization to prevent XSS"""
    if text is None:
        return ""
    # Remove potentially dangerous HTML/JS
    text = re.sub(r'<[^>]*>', '', text)
    return text

def generate_alert_message(disaster):
    """Generate alert message based on disaster type and severity"""
    severity_words = {
        1: "Minor",
        2: "Moderate",
        3: "Significant", 
        4: "Severe",
        5: "Extreme"
    }
    
    severity = severity_words.get(disaster.get('severity', 1), "Reported")
    
    return f"{severity} {disaster.get('type', 'disaster')} reported: {disaster.get('title')}. Stay safe!"
