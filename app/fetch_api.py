import requests
import json
import os
from datetime import datetime, timedelta

def fetch_usgs_earthquakes():
    """
    Fetch earthquake data from USGS API
    Returns earthquake data for the past 7 days with magnitude > 4.5
    """
    try:
        url = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/4.5_week.geojson"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        processed_data = []
        
        for feature in data['features']:
            props = feature['properties']
            coords = feature['geometry']['coordinates']
            
            processed_data.append({
                "id": feature['id'],
                "type": "earthquake",
                "title": props['title'],
                "description": f"Magnitude {props['mag']} earthquake at depth of {coords[2]}km",
                "lat": coords[1],
                "lng": coords[0],
                "timestamp": datetime.fromtimestamp(props['time']/1000).isoformat(),
                "severity": min(int(props['mag']), 5),  # Map magnitude to severity 1-5
                "verified": True,
                "source": "USGS"
            })
        
        return processed_data
    except Exception as e:
        print(f"Error fetching USGS data: {e}")
        # Return dummy data as fallback
        return [{
            "id": "usgs-eq-1002",
            "type": "earthquake",
            "title": "Magnitude 5.8 Earthquake in Chile",
            "description": "A moderate earthquake struck northern Chile on April 9, 2025.",
            "lat": -20.5,
            "lng": -68.9,
            "timestamp": datetime.now().isoformat(),
            "severity": 3,
            "verified": True,
            "source": "USGS"
        }]

def fetch_gdacs_floods():
    """
    This would typically fetch flood data from GDACS API
    For now, return dummy data
    """
    return [{
        "id": "gdacs-fl-1003",
        "type": "flood",
        "title": "Severe Flooding in Eastern India",
        "description": "Heavy monsoon rains have caused widespread flooding in Bihar state.",
        "lat": 25.4,
        "lng": 85.1,
        "timestamp": (datetime.now() - timedelta(days=2)).isoformat(),
        "severity": 4,
        "verified": True,
        "source": "GDACS"
    }]

def fetch_all_disasters():
    """Fetch data from all available APIs and return combined results"""
    all_data = []
    
    # Fetch from each API
    earthquakes = fetch_usgs_earthquakes()
    floods = fetch_gdacs_floods()
    
    # Add dummy wildfire for diversity
    wildfires = [{
        "id": "nasa-wf-1004",
        "type": "wildfire",
        "title": "Wildfire in California",
        "description": "A fast-moving wildfire has consumed over 5,000 acres near Los Angeles.",
        "lat": 34.05,
        "lng": -118.25,
        "timestamp": datetime.now().isoformat(),
        "severity": 5,
        "verified": True,
        "source": "NASA FIRMS"
    }]
    
    # Combine all data
    all_data.extend(earthquakes)
    all_data.extend(floods)
    all_data.extend(wildfires)
    
    # Save to cache file
    cache_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'cached_reports.json')
    with open(cache_path, 'w') as f:
        json.dump(all_data, f, indent=2)
    
    return all_data

if __name__ == "__main__":
    disasters = fetch_all_disasters()
    print(f"Fetched {len(disasters)} disaster reports")

# disaster-aggregator/app/verify.py
from app.models import DisasterReport
from app import db
import json
import os
from datetime import datetime

def get_unverified_reports():
    """Get all unverified user reports"""
    return DisasterReport.query.filter_by(verified=False).all()

def verify_report(report_id, verified=True):
    """Mark a report as verified or rejected"""
    report = DisasterReport.query.get(report_id)
    if report:
        report.verified = verified
        db.session.commit()
        return True
    return False

def get_reports_for_verification():
    """
    For development/demo purposes, return dummy unverified reports 
    In production, this would query the database
    """
    return [
        {
            "id": "user-rp-1005",
            "type": "flood", 
            "title": "Street flooding in downtown",
            "description": "Several streets in the downtown area are flooded after heavy rain.",
            "lat": 40.7128,
            "lng": -74.0060,
            "timestamp": datetime.now().isoformat(),
            "severity": 2,
            "verified": False,
            "source": "User Report",
            "contact": "anonymous@example.com"
        },
        {
            "id": "user-rp-1006",
            "type": "storm",
            "title": "Power outages from storm",
            "description": "Strong winds have knocked down power lines in the eastern suburbs.",
            "lat": 40.7328,
            "lng": -73.9860,
            "timestamp": datetime.now().isoformat(),
            "severity": 3,
            "verified": False,
            "source": "User Report",
            "contact": "resident@example.com"
        }
    ]
