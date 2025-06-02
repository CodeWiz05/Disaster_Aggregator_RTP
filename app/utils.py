# app/utils.py
import bleach # For HTML sanitization
from functools import wraps
from flask import abort, current_app # Added current_app for logging
from flask_login import current_user
from .models import Disaster, DisasterReport # Import models used by helpers
from . import db # Import db instance used by helpers
from datetime import datetime, timedelta, timezone # Import necessary datetime components
from sqlalchemy.exc import SQLAlchemyError # Import specific DB errors

# --- Sanitize Input Function ---
def sanitize_input(text):
    """Sanitizes user input to prevent XSS using bleach."""
    if text is None:
        return None
    try:
        # Define allowed tags and attributes
        allowed_tags = ['p', 'b', 'i', 'u', 'em', 'strong', 'a', 'br', 'ul', 'ol', 'li']
        allowed_attrs = {'a': ['href', 'title', 'target']} # Added target for links
        # Clean the text
        cleaned_text = bleach.clean(text, tags=allowed_tags, attributes=allowed_attrs, strip=True)
        return cleaned_text
    except Exception as e:
        current_app.logger.error(f"Error during input sanitization: {e}", exc_info=True)
        return text # Return original text on error? Or empty string?

# --- Alert Message Generator ---
def generate_alert_message(report: DisasterReport):
    """Generates a simple alert message from a DisasterReport object."""
    if not isinstance(report, DisasterReport):
         return "Invalid report object provided."

    ts = report.timestamp
    # Ensure timestamp is timezone-aware before formatting
    if ts and ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc) # Assume UTC if naive
    ts_str = ts.strftime('%Y-%m-%d %H:%M %Z') if ts else "N/A"

    return f"ALERT: {report.disaster_type.upper()} - {report.title or 'Untitled Event'} reported at {ts_str} near ({report.latitude:.2f}, {report.longitude:.2f}). Severity: {report.severity or 'N/A'}"

# --- RBAC Decorator ---
def admin_required(f):
    """Decorator to require admin privileges for a route."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            # This should typically be caught by @login_required first
            abort(401) # Unauthorized
        elif not hasattr(current_user, 'is_admin') or not current_user.is_admin:
             abort(403) # Forbidden
        return f(*args, **kwargs)
    return decorated_function

# --- Helper for Disaster Aggregation (Example) ---
def find_or_create_disaster_event(report: DisasterReport):
    """
    Attempts to find a matching existing Disaster event or creates a new one
    based on the verified report. Links the report to the disaster. Adds objects
    to the current session but does *not* commit. Returns the Disaster event object or None on failure.
    """
    # --- REVISED INITIAL CHECK ---
    allowed_statuses_for_aggregation = ['verified_agg', 'api_verified']
        
    if not isinstance(report, DisasterReport):
        current_app.logger.warning(f"find_or_create_disaster_event called with non-DisasterReport object.")
        return None

    if report.status not in allowed_statuses_for_aggregation:
        current_app.logger.warning(f"find_or_create_disaster_event called for report ID {report.id} with non-aggregatable status: '{report.status}'. Skipping.")
        return None
            
    # Although status should imply verified, an extra check doesn't hurt, 
    # or ensure your logic setting these statuses also sets verified=True.
    if not report.verified:
        current_app.logger.warning(f"find_or_create_disaster_event called for report ID {report.id} (status: {report.status}) but report.verified is False. Skipping.")
        return None
    # --- END REVISED CHECK ---

    time_window = timedelta(hours=12) # Time window for matching events
    lat_diff = 0.5 # Degrees latitude difference approx 55km
    lon_diff = 0.5 # Degrees longitude difference approx 55km (varies more with latitude)

    # Ensure report timestamp is timezone-aware
    report_ts = report.timestamp
    if report_ts and report_ts.tzinfo is None:
        report_ts = report_ts.replace(tzinfo=timezone.utc)

    if not report_ts:
        current_app.logger.error(f"Report {report.id} has invalid timestamp, cannot process for event aggregation.")
        return None

    potential_matches = []
    try:
        # Query potential matches more carefully
        potential_matches = Disaster.query.filter(
            Disaster.disaster_type == report.disaster_type,
            # Ensure timestamp comparisons use timezone-aware datetimes
            Disaster.last_updated >= (report_ts - time_window),
            Disaster.start_time <= (report_ts + time_window),
            # Bounding box filter (consider PostGIS for accuracy)
            Disaster.latitude.isnot(None), # Ensure existing events have coordinates
            Disaster.longitude.isnot(None),
            Disaster.latitude.between(report.latitude - lat_diff, report.latitude + lat_diff),
            Disaster.longitude.between(report.longitude - lon_diff, report.longitude + lon_diff)
        ).order_by(Disaster.last_updated.desc()).all()

    except SQLAlchemyError as db_err:
         current_app.logger.error(f"Database error querying for matching disasters: {db_err}", exc_info=True)
         return None # Cannot proceed if query fails
    except Exception as e:
         current_app.logger.error(f"Unexpected error querying for matching disasters: {e}", exc_info=True)
         return None


    # TODO: Implement more sophisticated matching (e.g., actual distance using geopy/PostGIS).

    disaster_event = None
    if potential_matches:
        # Simple: pick the most recently updated match
        # Add more checks here if needed (e.g., actual distance check)
        disaster_event = potential_matches[0]
        current_app.logger.info(f"Found matching disaster event {disaster_event.id} for report {report.id}")
    else:
        # Create a new Disaster event
        current_app.logger.info(f"Creating new disaster event for report {report.id}")
        try:
            disaster_event = Disaster(
                title=f"{report.disaster_type.capitalize()} Event near {report.latitude:.2f}, {report.longitude:.2f}", # Generic title
                disaster_type=report.disaster_type,
                status='active',
                start_time=report_ts, # Use timezone-aware timestamp
                last_updated=report_ts, # Use timezone-aware timestamp
                latitude=report.latitude,
                longitude=report.longitude,
                severity=report.severity,
                report_count=0 # Will be incremented below
            )
            db.session.add(disaster_event)
            # Need to flush to get the ID for the relationship if created here
            db.session.flush() # Flush might raise errors
        except SQLAlchemyError as db_err:
             current_app.logger.error(f"Database error creating or flushing new disaster event: {db_err}", exc_info=True)
             db.session.rollback() # Rollback the addition
             return None # Cannot proceed
        except Exception as e:
            current_app.logger.error(f"Unexpected error creating new disaster event: {e}", exc_info=True)
            db.session.rollback()
            return None

    # Link report and update disaster event if event creation/finding was successful
    if disaster_event and disaster_event.id: # Ensure event has an ID after flush
        try:
            report.disaster_id = disaster_event.id
            # Safely increment count
            disaster_event.report_count = (disaster_event.report_count or 0) + 1
            # Update last_updated and severity
            disaster_event.last_updated = max(disaster_event.last_updated or report_ts, report_ts)
            if report.severity is not None:
                 disaster_event.severity = max(disaster_event.severity or 0, report.severity)

            # Add objects again ensure updates are tracked by the session
            # (SQLAlchemy usually tracks changes on flushed/persistent objects,
            # but adding again doesn't hurt and ensures clarity)
            db.session.add(report)
            db.session.add(disaster_event)
            return disaster_event # Return the linked/created/updated disaster event

        except Exception as e:
             current_app.logger.error(f"Error linking report {report.id} to disaster {disaster_event.id}: {e}", exc_info=True)
             # Don't rollback here, let the calling route handle commit/rollback for the whole action
             return None # Indicate linking failed

    else:
        current_app.logger.warning(f"Could not link report {report.id}. Disaster event missing or has no ID after potential creation.")
        return None # Indicate failure