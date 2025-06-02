# app/fetch_api.py
import httpx
import asyncio
import traceback # Keep for potential manual use if needed, though logger handles exc_info
import csv
import io
from datetime import datetime, timezone, timedelta  
from app import db
from app.models import DisasterReport
from app import invalidate_disaster_api_cache
from flask import current_app # For accessing app-bound loggers
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import select
from shapely.geometry import shape
from .utils import find_or_create_disaster_event


# --- Async Fetcher for USGS Earthquakes ---
async def fetch_usgs_earthquakes_async(client: httpx.AsyncClient):
    """
    Fetch earthquake data from USGS API asynchronously and prepare for DB save.
    Returns a list of new DisasterReport objects (not yet committed).
    """
    url = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/4.5_week.geojson"
    # Use fetch_logger for detailed fetch process
    current_app.fetch_logger.info("Fetching USGS data...")
    new_reports = []
    try:
        response = await client.get(url, timeout=30.0)
        response.raise_for_status()
        data = response.json()
        current_app.fetch_logger.debug(f"USGS data received: {len(data.get('features', []))} features.")

        for feature in data.get('features', []):
            props = feature.get('properties', {})
            geom = feature.get('geometry', {})
            coords = geom.get('coordinates')
            api_event_id = feature.get('id')

            # Validation messages go to fetch_logger as warnings (operational detail)
            if not api_event_id:
                 current_app.fetch_logger.warning(f"Skipping USGS record due to missing 'id'")
                 continue
            if not props:
                 current_app.fetch_logger.warning(f"Skipping USGS record {api_event_id} due to missing 'properties'")
                 continue
            if not geom or not coords or len(coords) < 3:
                current_app.fetch_logger.warning(f"Skipping USGS record {api_event_id} due to missing/invalid 'geometry'")
                continue
            if props.get('mag') is None:
                 current_app.fetch_logger.warning(f"Skipping USGS record {api_event_id} due to missing 'mag'")
                 continue
            if props.get('time') is None:
                 current_app.fetch_logger.warning(f"Skipping USGS record {api_event_id} due to missing 'time'")
                 continue

            try:
                exists = db.session.query(DisasterReport.id).filter_by(
                    source="USGS",
                    source_event_id=api_event_id
                ).limit(1).scalar() is not None
                if exists:
                    current_app.fetch_logger.debug(f"USGS record {api_event_id} already exists, skipping.")
                    continue
            except Exception as db_err:
                 # DB errors during fetch sub-operations are significant
                 current_app.fetch_logger.error(f"DB error checking existence for USGS {api_event_id}: {db_err}")
                 current_app.error_logger.error(f"Fetch_API (USGS): DB error checking existence for {api_event_id}", exc_info=True) # Also to main errors
                 continue

            try:
                timestamp_ms = props['time']
                timestamp_dt = datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)
            except (TypeError, ValueError, OverflowError) as ts_err:
                 current_app.fetch_logger.warning(f"Skipping USGS record {api_event_id} due to invalid timestamp '{props.get('time')}': {ts_err}")
                 continue

            magnitude = None
            severity = None
            try:
                magnitude = float(props['mag'])
                if magnitude >= 7: severity = 5
                elif magnitude >= 6: severity = 4
                elif magnitude >= 5: severity = 3
                elif magnitude >= 4: severity = 2
                else: severity = 1
            except (ValueError, TypeError) as mag_err:
                current_app.fetch_logger.warning(f"Skipping USGS record {api_event_id} due to invalid magnitude '{props.get('mag')}': {mag_err}")
                continue
            
            try:
                report = DisasterReport(
                    source_event_id=api_event_id,
                    title=props.get('title', f"Magnitude {magnitude:.1f} Earthquake"),
                    description=f"Location: {props.get('place', 'N/A')}. Depth: {coords[2]:.2f}km",
                    disaster_type="earthquake",
                    latitude=coords[1],
                    longitude=coords[0],
                    depth_km=coords[2],
                    magnitude=magnitude,
                    timestamp=timestamp_dt,
                    severity=severity,
                    verified=True,
                    source="USGS",
                    status='api_verified' # From Step 3 of previous instructions
                )
                new_reports.append(report)
            except Exception as model_err:
                 current_app.fetch_logger.error(f"Error creating DisasterReport object for USGS {api_event_id}: {model_err}")
                 current_app.error_logger.error(f"Fetch_API (USGS): Model creation error for {api_event_id}", exc_info=True) # Also to main errors
                 continue

        current_app.fetch_logger.info(f"Prepared {len(new_reports)} new USGS reports for DB.")
        return new_reports

    # Top-level exceptions for the whole fetcher are critical
    except httpx.HTTPStatusError as e:
        current_app.fetch_logger.error(f"HTTP error fetching USGS data: {e.response.status_code} - {e.request.url}")
        current_app.error_logger.error(f"Fetch_API (USGS): HTTPStatusError {e.response.status_code}", exc_info=True)
    except httpx.RequestError as e:
        current_app.fetch_logger.error(f"Network error fetching USGS data: {e}")
        current_app.error_logger.error(f"Fetch_API (USGS): RequestError", exc_info=True)
    except Exception as e:
        current_app.fetch_logger.error(f"Unexpected error processing USGS data: {e}", exc_info=True) # exc_info True for fetch_logger too here
        current_app.error_logger.error(f"Fetch_API (USGS): Unexpected error", exc_info=True)
    return []


# --- Fetcher for NASA FIRMS Wildfires ---
async def fetch_nasa_firms_wildfires_async(client: httpx.AsyncClient):
    """ Fetches wildfire hotspot data from NASA FIRMS API and saves to DB. """
    current_app.fetch_logger.info("Fetching NASA FIRMS data...")
    new_reports = []
    api_key = current_app.config.get('NASA_FIRMS_API_KEY')
    if not api_key:
        current_app.fetch_logger.warning("NASA_FIRMS_API_KEY not configured. Skipping wildfire fetch.")
        # This isn't a critical error for the app, just for this fetcher
        return []

    SATELLITE_SOURCE = "VIIRS_SNPP_NRT"
    AREA = "world"
    DAY_RANGE = "1"
    COLUMN_NAMES_TO_FIND = {
        'lat': 'latitude', 'lon': 'longitude', 'date': 'acq_date',
        'time': 'acq_time', 'conf': 'confidence', 'bright': 'bright_ti5', 'frp': 'frp'
    }
    source = "NASA_FIRMS"
    MIN_CONFIDENCE_THRESHOLD_PERCENT = 75

    url = f"https://firms.modaps.eosdis.nasa.gov/api/area/csv/{api_key}/{SATELLITE_SOURCE}/{AREA}/{DAY_RANGE}"
    current_app.fetch_logger.debug(f"Requesting FIRMS URL")

    try:
        response = await client.get(url, timeout=90.0)
        # Specific API error handling goes to fetch_logger.error but also general error_logger
        if response.status_code in [401, 403]:
             current_app.fetch_logger.error(f"FIRMS API Error {response.status_code}: Invalid/unauthorized MAP_KEY.")
             current_app.error_logger.error(f"Fetch_API (FIRMS): API Key Error {response.status_code}")
             return []
        elif response.status_code == 400:
             current_app.fetch_logger.error(f"FIRMS API Error 400: Bad Request. Check URL. Response: {response.text[:200]}")
             current_app.error_logger.error(f"Fetch_API (FIRMS): API Bad Request 400. URL: {url}")
             return []
        elif response.status_code == 429: # Rate limit exceeded
             current_app.fetch_logger.warning(f"FIRMS API Error 429: Rate limit exceeded. Try later.")
             # Not necessarily a critical app error, so maybe only fetch_logger
             return []
        response.raise_for_status()

        csv_data = response.text
        lines = csv_data.strip().split('\n')
        if len(lines) <= 1:
             current_app.fetch_logger.info("No active fires found in FIRMS response.")
             return []
        current_app.fetch_logger.debug(f"FIRMS CSV received ({len(lines)} lines). Parsing...")

        csvfile = io.StringIO(csv_data)
        reader = csv.reader(csvfile)
        header = next(reader)
        col_indices = {}
        try:
            for key, name in COLUMN_NAMES_TO_FIND.items():
                col_indices[key] = header.index(name)
        except ValueError as e:
            current_app.fetch_logger.error(f"FIRMS CSV header mismatch: Cannot find column '{e}'. Header: {header}")
            current_app.error_logger.error(f"Fetch_API (FIRMS): CSV Header Mismatch. Expected '{e}', Got: {header}")
            return []
        
        existing_firms_ids = set()
        try:
            two_days_ago = datetime.now(timezone.utc) - timedelta(days=2)
            stmt = select(DisasterReport.source_event_id).filter(
                DisasterReport.source == source,
                DisasterReport.timestamp >= two_days_ago
            )
            result = db.session.execute(stmt).scalars().all()
            existing_firms_ids = set(result)
            current_app.fetch_logger.debug(f"Fetched {len(existing_firms_ids)} existing recent FIRMS IDs for deduplication.")
        except Exception as db_err:
            current_app.fetch_logger.error(f"DB error fetching existing FIRMS IDs: {db_err}. Proceeding with fallback.")
            current_app.error_logger.error(f"Fetch_API (FIRMS): DB error fetching existing IDs", exc_info=True)
            existing_firms_ids = None

        processed_ids_in_batch = set()
        for row_num, row in enumerate(reader):
            if not row: continue
            max_index = max(col_indices.values())
            if len(row) <= max_index:
                 current_app.fetch_logger.warning(f"Skipping FIRMS row {row_num+1}: Insufficient columns. Data: {row}")
                 continue

            try:
                lat_str = row[col_indices['lat']]
                lon_str = row[col_indices['lon']]
                date_str = row[col_indices['date']]
                time_str = row[col_indices['time']].zfill(4)
                confidence_raw = row[col_indices['conf']]
                brightness_str = row[col_indices['bright']]

                lat = float(lat_str)
                lon = float(lon_str)
                
                source_event_id = f"firms_{SATELLITE_SOURCE}_{lat:.4f}_{lon:.4f}_{date_str}_{time_str}"
                
                if source_event_id in processed_ids_in_batch:
                    current_app.fetch_logger.debug(f"FIRMS {source_event_id} skipped, already in this batch.")
                    continue
                processed_ids_in_batch.add(source_event_id)

                found_in_recent_set = False
                if existing_firms_ids is not None:
                     if source_event_id in existing_firms_ids:
                         found_in_recent_set = True
                
                if found_in_recent_set:
                    current_app.fetch_logger.debug(f"FIRMS {source_event_id} skipped, found in recent set.")
                    continue
                else:
                    try:
                        exists_in_db = db.session.query(DisasterReport.id).filter_by(
                            source=source, source_event_id=source_event_id
                        ).limit(1).scalar() is not None
                        if exists_in_db:
                            current_app.fetch_logger.debug(f"FIRMS {source_event_id} skipped, found in full DB check.")
                            continue
                    except Exception as db_err_fallback:
                         current_app.fetch_logger.error(f"DB error checking existence (fallback) for FIRMS {source_event_id}: {db_err_fallback}")
                         current_app.error_logger.error(f"Fetch_API (FIRMS): DB error in fallback deduplication for {source_event_id}", exc_info=True)
                         continue
                
                dt_str = f"{date_str} {time_str}"
                timestamp_dt = datetime.strptime(dt_str, "%Y-%m-%d %H%M").replace(tzinfo=timezone.utc)
                
                severity = 1
                confidence_str_display = str(confidence_raw)
                confidence_val = None
                should_skip_confidence = False
                try:
                    confidence_val = int(confidence_raw)
                    confidence_str_display = f"{confidence_val}%"
                    if confidence_val >= 90: severity = 4
                    elif confidence_val >= 75: severity = 3
                    elif confidence_val >= 50: severity = 2
                    if confidence_val < MIN_CONFIDENCE_THRESHOLD_PERCENT:
                        should_skip_confidence = True
                except ValueError:
                    confidence_str_lc = str(confidence_raw).lower()
                    confidence_str_display = confidence_str_lc # Use lowercased for display if not int
                    if confidence_str_lc == 'high': severity = 3
                    elif confidence_str_lc == 'nominal': severity = 2
                    if confidence_str_lc == 'low':
                         should_skip_confidence = True
                
                if should_skip_confidence:
                    current_app.fetch_logger.debug(f"Skipping FIRMS {source_event_id} due to low confidence: {confidence_raw}")
                    continue
                
                try:
                    brightness_k = float(brightness_str)
                    if brightness_k > 360: severity = max(severity, 5)
                    elif brightness_k > 340: severity = max(severity, 4)
                except (ValueError, TypeError): pass

                title = f"Wildfire Detection ({confidence_str_display} confidence)"
                description = f"Satellite hotspot detected near [{lat:.3f}, {lon:.3f}]. Brightness: {brightness_str}K."

                report = DisasterReport(
                    source_event_id=source_event_id, title=title, description=description,
                    disaster_type="wildfire", latitude=lat, longitude=lon,
                    timestamp=timestamp_dt, severity=severity, verified=True, source=source,
                    status='api_verified' # From Step 3 of previous instructions
                )
                new_reports.append(report)

            except (ValueError, IndexError, TypeError) as parse_err:
                 # These are expected row-level parsing issues
                 current_app.fetch_logger.warning(f"Skipping FIRMS row {row_num+1} due to parsing error: {parse_err}. Row: {row[:5]}")
            except Exception as row_err:
                 # Unexpected error processing a row, log to both
                 current_app.fetch_logger.error(f"Unexpected error processing FIRMS row {row_num+1}: {row_err}. Row: {row[:5]}", exc_info=True)
                 current_app.error_logger.error(f"Fetch_API (FIRMS): Unexpected error processing row {row_num+1}", exc_info=True)

        current_app.fetch_logger.info(f"Prepared {len(new_reports)} new NASA FIRMS reports.")
        return new_reports

    # Top-level exceptions for the whole fetcher are critical
    except httpx.HTTPStatusError as e:
        current_app.fetch_logger.error(f"HTTP error fetching FIRMS: {e.response.status_code}")
        current_app.error_logger.error(f"Fetch_API (FIRMS): HTTPStatusError {e.response.status_code}", exc_info=True)
    except httpx.RequestError as e:
        current_app.fetch_logger.error(f"Network error fetching FIRMS: {e}")
        current_app.error_logger.error(f"Fetch_API (FIRMS): RequestError", exc_info=True)
    except Exception as e:
        current_app.fetch_logger.error(f"Unexpected error processing FIRMS: {e}", exc_info=True)
        current_app.error_logger.error(f"Fetch_API (FIRMS): Unexpected error", exc_info=True)
    return []

NWS_USER_AGENT = "(DisasterTrack Aggregator, samaan.numair@gmail.com)"
# --- Placeholder Fetcher for NWS/NOAA Storm/Weather Alerts ---
async def fetch_nws_alerts_async(client: httpx.AsyncClient):
    """ Fetches active weather alerts from NWS/NOAA API. """
    current_app.fetch_logger.info("Fetching NWS alerts...")
    new_reports = []
    url = "https://api.weather.gov/alerts/active"
    headers = {'User-Agent': NWS_USER_AGENT, 'Accept': 'application/geo+json'} # Specify GeoJSON

    try:
        response = await client.get(url, headers=headers, timeout=45.0, follow_redirects=True)
        response.raise_for_status()
        data = response.json()
        current_app.fetch_logger.debug(f"NWS data received: {len(data.get('features', []))} items in collection.")

        if not data.get('features'):
            current_app.fetch_logger.info("No NWS alert features found in response.")
            return []

        for alert_feature in data['features']:
            props = alert_feature.get('properties', {})
            if not props:
                current_app.fetch_logger.warning("NWS: Skipping alert due to missing 'properties'.")
                continue

            # --- Filter by status and messageType ---
            alert_status = props.get('status')
            message_type = props.get('messageType')

            if alert_status != "Actual":
                current_app.fetch_logger.debug(f"NWS: Skipping alert with status '{alert_status}' (ID: {props.get('id')}).")
                continue
            if message_type not in ["Alert", "Update"]:
                current_app.fetch_logger.debug(f"NWS: Skipping alert with messageType '{message_type}' (ID: {props.get('id')}).")
                continue

            api_event_id = props.get('id')
            if not api_event_id:
                current_app.fetch_logger.warning("NWS: Skipping alert due to missing 'id' in properties.")
                continue

            # --- Deduplication ---
            try:
                exists = db.session.query(DisasterReport.id).filter_by(
                    source="NWS", source_event_id=api_event_id
                ).limit(1).scalar() is not None
                if exists:
                    current_app.fetch_logger.debug(f"NWS alert {api_event_id} already exists, skipping.")
                    continue
            except Exception as db_err:
                 current_app.fetch_logger.error(f"NWS: DB error checking existence for {api_event_id}: {db_err}")
                 current_app.error_logger.error(f"Fetch_API (NWS): DB error checking existence for {api_event_id}", exc_info=True)
                 continue
            
            event_type_str = props.get('event', "Unknown Weather Event").strip()
            nws_severity_str = props.get('severity', "Unknown").strip()
            
            title = props.get('headline') or event_type_str # Headline is often more descriptive
            description = props.get('description', "No specific description provided.")
            instruction = props.get('instruction')
            if instruction:
                description += f"\n\nInstructions: {instruction}"

            timestamp_str = props.get('onset')
            if not timestamp_str: # Check for null onset (like in KEEPALIVE)
                current_app.fetch_logger.warning(f"NWS: Missing 'onset' timestamp for alert {api_event_id}, skipping.")
                continue
            try:
                timestamp_dt = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
                if timestamp_dt.tzinfo is None:
                    timestamp_dt = timestamp_dt.replace(tzinfo=timezone.utc)
                else: # Ensure it's UTC
                    timestamp_dt = timestamp_dt.astimezone(timezone.utc)
            except ValueError:
                current_app.fetch_logger.warning(f"NWS: Invalid onset timestamp format for {api_event_id}: {timestamp_str}")
                continue

            severity = 1 
            if nws_severity_str:
                nws_sev_lower = nws_severity_str.lower()
                if nws_sev_lower == 'extreme': severity = 5
                elif nws_sev_lower == 'severe': severity = 4
                elif nws_sev_lower == 'moderate': severity = 3
                elif nws_sev_lower == 'minor': severity = 2
            
            disaster_type = "weather_alert" # More generic default
            event_lower = event_type_str.lower()
            # More specific type mapping
            if any(s in event_lower for s in ["tornado", "hurricane", "tropical storm", "severe thunderstorm", "wind advisory", "high wind", "special marine warning"]):
                disaster_type = "storm"
            elif any(s in event_lower for s in ["flood", "flash flood", "coastal flood", "flood advisory"]):
                disaster_type = "flood"
            elif any(s in event_lower for s in ["winter storm", "blizzard", "ice storm", "heavy snow", "lake effect snow"]):
                disaster_type = "winter_storm"
            elif "fire weather" in event_lower or "red flag" in event_lower:
                disaster_type = "fire_weather"
            elif "earthquake" in event_lower: disaster_type = "earthquake"
            elif "tsunami" in event_lower: disaster_type = "tsunami"
            elif "volcano" in event_lower: disaster_type = "volcano"
            # Add more specific mappings as you observe event types

            latitude, longitude = None, None
            alert_geometry_data = alert_feature.get('geometry')

            if alert_geometry_data:
                try:
                    geom = shape(alert_geometry_data) # Create shapely geometry object
                    if geom.is_valid:
                        centroid = geom.centroid
                        latitude = centroid.y
                        longitude = centroid.x
                        current_app.fetch_logger.debug(f"NWS: Calculated centroid ({latitude:.4f}, {longitude:.4f}) for {api_event_id}")
                    else:
                        current_app.fetch_logger.warning(f"NWS: Invalid geometry for {api_event_id}, cannot calculate centroid.")
                except Exception as shape_err:
                    current_app.fetch_logger.warning(f"NWS: Error processing geometry for {api_event_id} with Shapely: {shape_err}")
            
            if latitude is None or longitude is None:
                area_description = props.get('areaDesc', "Area description not available.")
                current_app.fetch_logger.warning(f"NWS: Skipping alert {api_event_id} ({title}). No representative lat/lon. Area: {area_description.split(';')[0]}")
                continue

            try:
                report = DisasterReport(
                    source_event_id=api_event_id,
                    title=title,
                    description=description,
                    disaster_type=disaster_type,
                    latitude=latitude,
                    longitude=longitude,
                    timestamp=timestamp_dt,
                    severity=severity,
                    verified=True,
                    source="NWS",
                    status='api_verified'
                )
                new_reports.append(report)
            except Exception as model_err:
                 current_app.fetch_logger.error(f"NWS: Error creating DisasterReport for {api_event_id}: {model_err}")
                 current_app.error_logger.error(f"Fetch_API (NWS): Model creation error for {api_event_id}", exc_info=True)
                 continue
        
        current_app.fetch_logger.info(f"Prepared {len(new_reports)} new NWS reports for DB.")
        return new_reports

    except httpx.HTTPStatusError as e:
        current_app.fetch_logger.error(f"NWS: HTTP error fetching alerts: {e.response.status_code} - {e.request.url}")
        current_app.error_logger.error(f"Fetch_API (NWS): HTTPStatusError {e.response.status_code}", exc_info=True)
    except httpx.RequestError as e:
        current_app.fetch_logger.error(f"NWS: Network error fetching alerts: {e}")
        current_app.error_logger.error(f"Fetch_API (NWS): RequestError", exc_info=True)
    except Exception as e: # Includes JSONDecodeError if response is not valid JSON
        current_app.fetch_logger.error(f"NWS: Unexpected error processing alerts: {e}", exc_info=True)
        current_app.error_logger.error(f"Fetch_API (NWS): Unexpected error", exc_info=True)
    return []


# --- Placeholder for GDACS ---
async def fetch_gdacs_library_async():
    """ [PLACEHOLDER] Fetch various alerts from GDACS API/RSS or Library. """
    # When implemented, use current_app.fetch_logger and current_app.error_logger similarly
    current_app.fetch_logger.info("Fetching GDACS data... (Placeholder - Not Implemented)")
    return []


# --- Main Runner Function (Includes ALL fetchers) ---
async def run_fetchers_async():
    """Runs all async fetchers concurrently and commits results to DB."""
    # Using fetch_logger for the overall process messages
    current_app.fetch_logger.info("Starting all async fetchers...")
    all_new_reports = []
    async with httpx.AsyncClient(follow_redirects=True, timeout=90.0) as client:
        fetcher_tasks = [
            fetch_usgs_earthquakes_async(client),
            fetch_nasa_firms_wildfires_async(client),
            fetch_nws_alerts_async(client),
            fetch_gdacs_library_async(),
        ]
        results = await asyncio.gather(*fetcher_tasks, return_exceptions=True)

    current_app.fetch_logger.info("Fetcher tasks completed. Processing results...")
    total_added_count = 0
    successful_commit = False

    for i, result in enumerate(results):
        try:
            # Get task name robustly
            task_name = fetcher_tasks[i].__name__ if hasattr(fetcher_tasks[i], '__name__') else f"task_{i}"
        except (IndexError, AttributeError):
            task_name = f"task_{i}"

        if isinstance(result, Exception):
            # Exceptions from gather are critical failures of a fetcher task
            current_app.fetch_logger.error(f"Fetcher task '{task_name}' failed: {result}", exc_info=result) # Log with full traceback to fetch_log
            current_app.error_logger.error(f"Run_Fetchers: Task '{task_name}' raised an exception", exc_info=result) # Also to main error log
        elif isinstance(result, list):
            valid_reports = [r for r in result if isinstance(r, DisasterReport)]
            if valid_reports:
                all_new_reports.extend(valid_reports)
                current_app.fetch_logger.debug(f"Fetcher task '{task_name}' added {len(valid_reports)} reports to process.")
        else:
             current_app.fetch_logger.warning(f"Fetcher task '{task_name}' returned unexpected type: {type(result)}")

    if not all_new_reports:
        current_app.fetch_logger.info("No new valid reports prepared by any fetcher.")
        return

    current_app.fetch_logger.info(f"Total valid reports prepared for DB: {len(all_new_reports)}. Attempting commit...")
    linked_disaster_events = [] # To keep track for logging
    try:
        db.session.add_all(all_new_reports)
        db.session.commit()
        total_added_count = len(all_new_reports)
        current_app.fetch_logger.info(f"Successfully committed {total_added_count} new reports.")
        successful_commit = True
        # --- NEW: Aggregate newly added API-verified reports ---
        if total_added_count > 0:
            current_app.fetch_logger.info(f"Aggregating {total_added_count} newly fetched reports into Disaster events...")
            aggregated_count = 0
            newly_created_disaster_events = 0
            for report_obj in all_new_reports: # Iterate over the Python objects we just added
                if report_obj.status == 'api_verified' and report_obj.id is not None: # Ensure it has an ID
                    # The report_obj is already in the session from the add_all and commit
                    # find_or_create_disaster_event will add/update Disaster and link report_obj
                    # It expects the report to be verified, which api_verified reports are.
                    disaster_event = find_or_create_disaster_event(report_obj)
                    if disaster_event:
                        aggregated_count += 1
                        if disaster_event not in linked_disaster_events: # Track unique disaster events affected
                            linked_disaster_events.append(disaster_event)
                            if disaster_event.id is None: # Check if it's a newly created one (before commit flushes)
                                # This check might be tricky before the final commit of disaster events
                                # A better way is to check if it was new inside find_or_create
                                pass 
                    else:
                        current_app.fetch_logger.warning(f"Failed to aggregate report ID {report_obj.id} into a Disaster event.")
            
            if linked_disaster_events: # If any Disaster events were created/updated
                db.session.commit() # Commit changes to Disaster events and DisasterReport.disaster_id links
                current_app.fetch_logger.info(f"Successfully aggregated {aggregated_count} reports. Affected/created {len(linked_disaster_events)} Disaster events.")
            else:
                current_app.fetch_logger.info("No new disaster events created or updated from this batch of reports.")
        # --- END NEW AGGREGATION ---
    except SQLAlchemyError as db_err:
        current_app.fetch_logger.error(f"!!! Database Commit Failed: {db_err} !!!", exc_info=True)
        current_app.error_logger.error(f"Run_Fetchers: Database Commit Failed (SQLAlchemyError)", exc_info=True) # Critical
        db.session.rollback()
        current_app.fetch_logger.info("Database session rolled back.")
    except Exception as e:
        current_app.fetch_logger.error(f"!!! Unexpected Commit Failed: {e} !!!", exc_info=True)
        current_app.error_logger.error(f"Run_Fetchers: Unexpected Commit Failed", exc_info=True) # Critical
        db.session.rollback()
        current_app.fetch_logger.info("Database session rolled back.")

    if successful_commit and total_added_count > 0:
        current_app.fetch_logger.info("Triggering cache invalidation...")
        try:
            invalidate_disaster_api_cache()
        except Exception as cache_err:
            current_app.fetch_logger.error(f"Error during cache invalidation: {cache_err}", exc_info=True)
            current_app.error_logger.warning(f"Run_Fetchers: Cache invalidation failed", exc_info=True) # Warning, not critical enough to stop all

    current_app.fetch_logger.info("run_fetchers_async finished.")