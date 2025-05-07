# app/fetch_api.py
# --- THIS IS THE COMPLETE FILE ---

import httpx
import asyncio
import traceback
import csv # Needed for parsing FIRMS CSV potentially
import io # Needed for reading CSV string
from datetime import datetime, timezone, timedelta
from app import db # Import db instance
from app.models import DisasterReport # Import model
# Import invalidate function carefully
# It's defined globally in __init__.py, so direct import should be okay
from app import invalidate_disaster_api_cache
# For logging errors
from flask import current_app
from sqlalchemy.exc import SQLAlchemyError # For DB errors
from sqlalchemy import select #for parsing

# --- Async Fetcher for USGS Earthquakes ---
async def fetch_usgs_earthquakes_async(client: httpx.AsyncClient):
    """
    Fetch earthquake data from USGS API asynchronously and prepare for DB save.
    Returns a list of new DisasterReport objects (not yet committed).
    """
    url = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/4.5_week.geojson"
    current_app.logger.info("Fetching USGS data...")
    new_reports = []
    try:
        response = await client.get(url, timeout=30.0) # Use longer timeout
        response.raise_for_status() # Check for HTTP 4xx/5xx errors
        data = response.json()
        current_app.logger.debug(f"USGS data received: {len(data.get('features', []))} features.")

        for feature in data.get('features', []):
            props = feature.get('properties', {})
            geom = feature.get('geometry', {})
            coords = geom.get('coordinates')
            api_event_id = feature.get('id')

            # Validation of essential fields from API response
            if not api_event_id:
                 current_app.logger.warning(f"Skipping USGS record due to missing 'id'")
                 continue
            if not props:
                 current_app.logger.warning(f"Skipping USGS record {api_event_id} due to missing 'properties'")
                 continue
            if not geom or not coords or len(coords) < 3:
                current_app.logger.warning(f"Skipping USGS record {api_event_id} due to missing/invalid 'geometry'")
                continue
            if props.get('mag') is None: # mag can be 0, check for None
                 current_app.logger.warning(f"Skipping USGS record {api_event_id} due to missing 'mag'")
                 continue
            if props.get('time') is None:
                 current_app.logger.warning(f"Skipping USGS record {api_event_id} due to missing 'time'")
                 continue


            # Deduplication check against database
            try:
                exists = db.session.query(DisasterReport.id).filter_by(
                    source="USGS",
                    source_event_id=api_event_id
                ).limit(1).scalar() is not None
                if exists:
                    continue # Skip if already exists
            except Exception as db_err:
                 current_app.logger.error(f"DB error checking existence for USGS {api_event_id}: {db_err}")
                 continue # Skip if we can't check


            # Process timestamp
            try:
                timestamp_ms = props['time']
                timestamp_dt = datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)
            except (TypeError, ValueError, OverflowError) as ts_err:
                 current_app.logger.warning(f"Skipping USGS record {api_event_id} due to invalid timestamp '{props.get('time')}': {ts_err}")
                 continue

            # Process magnitude and severity
            magnitude = None
            severity = None
            try:
                magnitude = float(props['mag'])
                if magnitude >= 7: severity = 5
                elif magnitude >= 6: severity = 4
                elif magnitude >= 5: severity = 3
                elif magnitude >= 4: severity = 2
                else: severity = 1 # Assuming magnitude can be less than 4.0 based on endpoint? Adjust if needed.
            except (ValueError, TypeError) as mag_err:
                current_app.logger.warning(f"Skipping USGS record {api_event_id} due to invalid magnitude '{props.get('mag')}': {mag_err}")
                continue

            # Create model instance
            try:
                report = DisasterReport(
                    source_event_id=api_event_id,
                    title=props.get('title', f"Magnitude {magnitude:.1f} Earthquake"), # Use title if available
                    description=f"Location: {props.get('place', 'N/A')}. Depth: {coords[2]:.2f}km",
                    disaster_type="earthquake", # <<< TYPE
                    latitude=coords[1],
                    longitude=coords[0],
                    depth_km=coords[2],
                    magnitude=magnitude,
                    timestamp=timestamp_dt,
                    severity=severity,
                    verified=True, # Trust USGS data
                    source="USGS", # <<< SOURCE
                    status='api_verified' # Set status for API-sourced reports
                )
                new_reports.append(report)
            except Exception as model_err:
                 current_app.logger.error(f"Error creating DisasterReport object for USGS {api_event_id}: {model_err}")
                 continue # Skip this report if model creation fails


        current_app.logger.info(f"Prepared {len(new_reports)} new USGS reports for DB.")
        return new_reports

    except httpx.HTTPStatusError as e:
        current_app.logger.error(f"HTTP error fetching USGS data: {e.response.status_code} - {e.request.url}")
    except httpx.RequestError as e:
        current_app.logger.error(f"Network error fetching USGS data: {e}")
    except Exception as e:
        current_app.logger.error(f"Unexpected error processing USGS data: {e}", exc_info=True)

    return [] # Return empty list on any top-level error


# --- Fetcher for NASA FIRMS Wildfires ---
async def fetch_nasa_firms_wildfires_async(client: httpx.AsyncClient):
    """ Fetches wildfire hotspot data from NASA FIRMS API and saves to DB. """
    current_app.logger.info("Fetching NASA FIRMS data...")
    new_reports = []
    # Get API Key from Flask config
    api_key = current_app.config.get('NASA_FIRMS_API_KEY')
    if not api_key:
        current_app.logger.warning("NASA_FIRMS_API_KEY not configured. Skipping wildfire fetch.")
        return []

    # --- Configuration (Verify/Adjust these) ---
    SATELLITE_SOURCE = "VIIRS_SNPP_NRT" # Common choice, check FIRMS docs for others
    AREA = "world"
    DAY_RANGE = "1" # Last 24 hours
    # Define the EXACT column names expected in the CSV header
    # **VERIFY THESE AGAINST ACTUAL FIRMS OUTPUT FOR YOUR CHOSEN SOURCE**
    COLUMN_NAMES_TO_FIND = {
        'lat': 'latitude',
        'lon': 'longitude',
        'date': 'acq_date',
        'time': 'acq_time',
        'conf': 'confidence',
        'bright': 'bright_ti5', # Or 'bright_ti4' for MODIS, or 'brightness'
        'frp': 'frp'
    }
    source = "NASA_FIRMS" # Define source name
    # --- End Configuration ---

    url = f"https://firms.modaps.eosdis.nasa.gov/api/area/csv/{api_key}/{SATELLITE_SOURCE}/{AREA}/{DAY_RANGE}"
    current_app.logger.debug(f"Requesting FIRMS URL") # Avoid logging key if possible

    try:
        response = await client.get(url, timeout=90.0) # Increased timeout further
        if response.status_code in [401, 403]:
             current_app.logger.error(f"FIRMS API Error {response.status_code}: Invalid/unauthorized MAP_KEY.")
             return []
        elif response.status_code == 400:
             current_app.logger.error(f"FIRMS API Error 400: Bad Request. Check URL parameters. Response: {response.text[:200]}")
             return []
        elif response.status_code == 429: # Rate limit exceeded
             current_app.logger.warning(f"FIRMS API Error 429: Rate limit exceeded. Try later.")
             return []
        response.raise_for_status() # Check other errors

        csv_data = response.text
        lines = csv_data.strip().split('\n')
        if len(lines) <= 1:
             current_app.logger.info("No active fires found in FIRMS response.")
             return []
        current_app.logger.debug(f"FIRMS CSV received ({len(lines)} lines). Parsing...")

        csvfile = io.StringIO(csv_data)
        reader = csv.reader(csvfile)
        header = next(reader)

        # Create a mapping from our keys ('lat', 'lon', etc.) to column indices
        col_indices = {}
        try:
            for key, name in COLUMN_NAMES_TO_FIND.items():
                col_indices[key] = header.index(name)
        except ValueError as e:
            # Log the missing column name and the actual header for easier debugging
            current_app.logger.error(f"FIRMS CSV header mismatch: Cannot find column '{e}'. Header received: {header}")
            return [] # Stop if essential columns are missing
        
        # --- START Deduplication Optimization ---
        existing_firms_ids = set()
        try:
            # Define time window for checking existing IDs (e.g., last 2 days)
            # Avoids loading *all* historical IDs if the table is huge
            two_days_ago = datetime.now(timezone.utc) - timedelta(days=2)
            # Query ONLY the source_event_id column for recent FIRMS reports
            stmt = select(DisasterReport.source_event_id).filter(
                DisasterReport.source == source,
                DisasterReport.timestamp >= two_days_ago # Check only recent ones
            )
            result = db.session.execute(stmt).scalars().all()
            existing_firms_ids = set(result)
            current_app.logger.debug(f"Fetched {len(existing_firms_ids)} existing recent FIRMS IDs for deduplication.")
        except Exception as db_err:
            current_app.logger.error(f"DB error fetching existing FIRMS IDs: {db_err}. Proceeding without optimal deduplication.")
            # Continue without the set, will fall back to individual checks (slower)
            existing_firms_ids = None # Signal that the bulk check failed

        # --- END Deduplication Optimization ---

        processed_ids_in_batch = set() # To handle duplicates within the same fetched file

        for row_num, row in enumerate(reader):
            # Skip empty rows if any
            if not row: continue
            # Ensure row has enough columns based on the maximum index we need
            max_index = max(col_indices.values())
            if len(row) <= max_index:
                 current_app.logger.warning(f"Skipping FIRMS row {row_num+1}: Only {len(row)} columns, expected at least {max_index+1}. Data: {row}")
                 continue

            try:
                # Extract and Validate fields using the determined indices
                lat_str = row[col_indices['lat']]
                lon_str = row[col_indices['lon']]
                date_str = row[col_indices['date']]
                time_str = row[col_indices['time']].zfill(4) # Pad HHMM
                confidence_raw = row[col_indices['conf']]
                brightness_str = row[col_indices['bright']]
                timestamp_dt = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H%M").replace(tzinfo=timezone.utc)

                # Convert lat/lon immediately, handle potential errors here
                lat = float(lat_str)
                lon = float(lon_str)
                # --- End Step 1 ---

                # NEW STABLE ID GENERATION:
                # Ensure lat, lon, date_str, time_str, SATELLITE_SOURCE are defined before this line
                # Use 4 decimal places for lat/lon for reasonable precision (~11 meters)
                source_event_id = f"firms_{SATELLITE_SOURCE}_{lat:.4f}_{lon:.4f}_{date_str}_{time_str}"
                if source_event_id in processed_ids_in_batch: continue
                processed_ids_in_batch.add(source_event_id)

                # --- REVISED Deduplication Check ---
                # Check against the pre-fetched set if available
                if existing_firms_ids is not None:
                     if source_event_id in existing_firms_ids:
                         continue # Skip if found in the pre-fetched set
                else:
                    # Fallback: Query DB individually if pre-fetch failed
                    try:
                        exists = db.session.query(DisasterReport.id).filter_by(source=source, source_event_id=source_event_id).limit(1).scalar() is not None
                        if exists: continue
                    except Exception as db_err:
                         current_app.logger.error(f"DB error checking existence (fallback) for FIRMS {source_event_id}: {db_err}")
                         continue # Skip if check fails
                # --- END REVISED Check ---

                # Create timestamp (ensure it's UTC)
                dt_str = f"{date_str} {time_str}"
                timestamp_dt = datetime.strptime(dt_str, "%Y-%m-%d %H%M").replace(tzinfo=timezone.utc)

                # Check DB duplicate
                source = "NASA_FIRMS"
                try:
                     exists = db.session.query(DisasterReport.id).filter_by(source=source, source_event_id=source_event_id).limit(1).scalar() is not None
                     if exists: continue
                except Exception as db_err:
                     current_app.logger.error(f"DB error checking existence for FIRMS {source_event_id}: {db_err}")
                     continue

                # Map confidence/brightness to Severity (ADJUST MAPPING AS NEEDED)
                severity = 1 # Default
                confidence_str = str(confidence_raw) # Store original confidence string/value
                confidence_val = None
                try:
                    confidence_val = int(confidence_raw)
                    confidence_str = f"{confidence_val}%"
                    if confidence_val >= 90: severity = 4
                    elif confidence_val >= 75: severity = 3
                    elif confidence_val >= 50: severity = 2
                except ValueError:
                    confidence_str = str(confidence_raw).lower()
                    if confidence_str == 'high': severity = 3
                    elif confidence_str == 'nominal': severity = 2
                # Optional: Boost based on brightness
                 # --- START: Add Confidence Filter ---
                MIN_CONFIDENCE_THRESHOLD_PERCENT = 75 # Example: Only save if confidence >= 75%
                MIN_CONFIDENCE_THRESHOLD_TEXT = 'nominal' # Example: Only save if 'nominal' or 'high'

                # Check if confidence meets the threshold
                should_skip = False
                if confidence_val is not None: # If confidence was numeric
                    if confidence_val < MIN_CONFIDENCE_THRESHOLD_PERCENT:
                        should_skip = True
                elif confidence_str: # If confidence was text ('low', 'nominal', 'high')
                    if confidence_str == 'low': # Only skip if it's explicitly 'low'
                         should_skip = True
                     # Allow 'nominal' and 'high' based on MIN_CONFIDENCE_THRESHOLD_TEXT check below (optional)
                    # elif confidence_str != 'high' and confidence_str != 'nominal': # More strict: only allow high/nominal
                    #    should_skip = True

                if should_skip:
                    # Optional: Log skipped low-confidence points if needed (can be very noisy)
                    # current_app.logger.debug(f"Skipping FIRMS row {row_num+1} due to low confidence: {confidence_raw}")
                    continue # Skip to the next row
                # --- END: Add Confidence Filter ---

                 # Create title/description (Only runs if confidence filter passed)
                title = f"Wildfire Detection ({confidence_str} confidence)"
                description = f"Satellite hotspot detected near [{lat:.3f}, {lon:.3f}]. Brightness: {brightness_str}K."

                try:
                    brightness_k = float(brightness_str)
                    if brightness_k > 360: severity = max(severity, 5)
                    elif brightness_k > 340: severity = max(severity, 4)
                except (ValueError, TypeError): pass

                # Create title/description
                title = f"Wildfire Detection ({confidence_str} confidence)"
                description = f"Satellite hotspot detected near [{lat:.3f}, {lon:.3f}]. Brightness: {brightness_str}K."

                # Create Model Instance
                report = DisasterReport(
                    source_event_id=source_event_id, title=title, description=description,
                    disaster_type="wildfire", latitude=lat, longitude=lon,
                    timestamp=timestamp_dt, severity=severity, verified=True, source=source, status='api_verified' # Set status for API-sourced reports
                )
                new_reports.append(report)

            except (ValueError, IndexError, TypeError) as parse_err:
                 current_app.logger.warning(f"Skipping FIRMS row {row_num+1} due to parsing error: {parse_err}. Row data snippet: {row[:len(COLUMN_NAMES_TO_FIND)]}")
            except Exception as row_err:
                 current_app.logger.error(f"Unexpected error processing FIRMS row {row_num+1}: {row_err}. Row data snippet: {row[:len(COLUMN_NAMES_TO_FIND)]}", exc_info=True)

        current_app.logger.info(f"Prepared {len(new_reports)} new NASA FIRMS reports.")
        return new_reports

    except httpx.HTTPStatusError as e: current_app.logger.error(f"HTTP error fetching FIRMS: {e.response.status_code}")
    except httpx.RequestError as e: current_app.logger.error(f"Network error fetching FIRMS: {e}")
    except Exception as e: current_app.logger.error(f"Unexpected error processing FIRMS: {e}", exc_info=True)
    return []


# --- Placeholder Fetcher for NWS/NOAA Storm/Weather Alerts ---
async def fetch_nws_alerts_async(client: httpx.AsyncClient):
    """ [PLACEHOLDER] Fetch active weather alerts from NWS/NOAA API. """
    current_app.logger.info("Fetching NWS alerts... (Placeholder - Not Implemented)")
    # TODO: Implement using https://api.weather.gov/alerts/active
    return []


# --- Placeholder for GDACS ---
async def fetch_gdacs_library_async(): # Renamed if using library attempt
    """ [PLACEHOLDER] Fetch various alerts from GDACS API/RSS or Library. """
    current_app.logger.info("Fetching GDACS data... (Placeholder - Not Implemented)")
    # TODO: Implement using RSS feeds or official API if available
    return []


# --- Main Runner Function (Includes ALL fetchers) ---
async def run_fetchers_async():
    """Runs all async fetchers concurrently and commits results to DB."""
    current_app.logger.info("Starting all async fetchers...")
    all_new_reports = []
    # Use a single client session for HTTP requests
    async with httpx.AsyncClient(follow_redirects=True, timeout=90.0) as client: # Shared client
        # List of coroutines to run
        fetcher_tasks = [
            fetch_usgs_earthquakes_async(client),
            fetch_nasa_firms_wildfires_async(client), # FIRMS fetcher included
            fetch_nws_alerts_async(client),           # NWS placeholder included
            fetch_gdacs_library_async(),              # GDACS placeholder included
        ]
        # Run them concurrently
        results = await asyncio.gather(*fetcher_tasks, return_exceptions=True)

    current_app.logger.info("Fetcher tasks completed. Processing results...")
    total_added_count = 0
    successful_commit = False

    # Process results
    for i, result in enumerate(results):
        try: task_name = fetcher_tasks[i].__name__
        except (IndexError, AttributeError): task_name = f"task_{i}"

        if isinstance(result, Exception):
            current_app.logger.error(f"Fetcher task '{task_name}' failed: {result}", exc_info=result)
        elif isinstance(result, list):
            valid_reports = [r for r in result if isinstance(r, DisasterReport)]
            if valid_reports:
                all_new_reports.extend(valid_reports)
                current_app.logger.debug(f"Fetcher task '{task_name}' added {len(valid_reports)} reports to process.")
            # else: current_app.logger.info(f"Fetcher task '{task_name}' returned no valid reports.") # Can be noisy
        else:
             current_app.logger.warning(f"Fetcher task '{task_name}' returned unexpected type: {type(result)}")

    if not all_new_reports:
        current_app.logger.info("No new valid reports prepared by any fetcher.")
        return # Nothing to commit

    current_app.logger.info(f"Total valid reports prepared for DB: {len(all_new_reports)}. Attempting commit...")
    try:
        db.session.add_all(all_new_reports)
        db.session.commit()
        total_added_count = len(all_new_reports)
        current_app.logger.info(f"Successfully committed {total_added_count} new reports.")
        successful_commit = True
    except SQLAlchemyError as db_err:
        current_app.logger.error(f"!!! Database Commit Failed: {db_err} !!!", exc_info=True)
        db.session.rollback()
        current_app.logger.info("Database session rolled back.")
    except Exception as e:
        current_app.logger.error(f"!!! Unexpected Commit Failed: {e} !!!", exc_info=True)
        db.session.rollback()
        current_app.logger.info("Database session rolled back.")

    # Invalidate Cache AFTER successful commit
    if successful_commit and total_added_count > 0:
        current_app.logger.info("Triggering cache invalidation...")
        try: invalidate_disaster_api_cache()
        except Exception as cache_err: current_app.logger.error(f"Error during cache invalidation: {cache_err}", exc_info=True)

    current_app.logger.info("run_fetchers_async finished.")