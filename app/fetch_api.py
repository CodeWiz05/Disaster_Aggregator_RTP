# app/fetch_api.py
import httpx
import asyncio
import traceback
from datetime import datetime, timezone, timedelta
from app import db # Import db instance
from app.models import DisasterReport # Import model
# Import invalidate function carefully
# It's defined globally in __init__.py, so direct import should be okay
from app import invalidate_disaster_api_cache
# For logging errors
from flask import current_app

# --- Async Fetcher for USGS ---
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
                    disaster_type="earthquake",
                    latitude=coords[1],
                    longitude=coords[0],
                    depth_km=coords[2],
                    magnitude=magnitude,
                    timestamp=timestamp_dt,
                    severity=severity,
                    verified=True, # Trust USGS data
                    source="USGS"
                )
                new_reports.append(report)
            except Exception as model_err:
                 current_app.logger.error(f"Error creating DisasterReport object for {api_event_id}: {model_err}")
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

# --- Placeholder for other async fetchers ---
async def fetch_gdacs_alerts_async(client: httpx.AsyncClient):
    current_app.logger.info("Fetching GDACS data... (Placeholder - Not Implemented)")
    await asyncio.sleep(0.1) # Simulate async work
    # Add real implementation here later
    return []

# --- Runner Function ---
async def run_fetchers_async():
    """Runs all async fetchers concurrently and commits results to DB."""
    current_app.logger.info("Starting async fetchers...")
    all_new_reports = []
    # Use a single client session for connection pooling and configuration
    # Consider setting headers like User-Agent if required by APIs
    async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
        fetcher_tasks = [
            fetch_usgs_earthquakes_async(client),
            fetch_gdacs_alerts_async(client),
            # Add other async fetcher calls here
        ]
        # return_exceptions=True allows tasks to fail without stopping others
        results = await asyncio.gather(*fetcher_tasks, return_exceptions=True)

    current_app.logger.info("Fetcher tasks completed. Processing results...")
    total_added_count = 0
    successful_commit = False

    # Process results from gather
    for i, result in enumerate(results):
        task_name = fetcher_tasks[i].__name__ # Get name of the async function
        if isinstance(result, Exception):
            # Log the specific exception and traceback for the failed task
            current_app.logger.error(f"Fetcher task '{task_name}' failed: {result}", exc_info=result)
        elif isinstance(result, list):
            valid_reports = [r for r in result if isinstance(r, DisasterReport)]
            if valid_reports:
                all_new_reports.extend(valid_reports)
                current_app.logger.debug(f"Fetcher task '{task_name}' provided {len(valid_reports)} valid reports.")
            else:
                 current_app.logger.info(f"Fetcher task '{task_name}' returned no valid reports.")
        else:
             current_app.logger.warning(f"Fetcher task '{task_name}' returned unexpected result type: {type(result)}")

    if not all_new_reports:
        current_app.logger.info("No new valid reports prepared by any fetcher.")
        return # Nothing to commit

    current_app.logger.info(f"Total valid reports prepared for DB: {len(all_new_reports)}. Attempting commit...")
    try:
        # Add all collected reports to the session
        db.session.add_all(all_new_reports)
        # Commit the session
        db.session.commit()
        total_added_count = len(all_new_reports)
        current_app.logger.info(f"Successfully committed {total_added_count} new reports to the database.")
        successful_commit = True
    except SQLAlchemyError as db_err: # Catch specific DB errors
        current_app.logger.error(f"!!! Database Commit Failed: {db_err} !!!", exc_info=True)
        db.session.rollback()
        current_app.logger.info("Database session rolled back.")
    except Exception as e: # Catch other potential errors during commit
        current_app.logger.error(f"!!! Unexpected Commit Failed: {e} !!!", exc_info=True)
        db.session.rollback()
        current_app.logger.info("Database session rolled back.")


    # --- Invalidate Cache AFTER successful commit ---
    if successful_commit and total_added_count > 0:
        current_app.logger.info("Triggering cache invalidation...")
        try:
            # Ensure this function exists and is accessible
            invalidate_disaster_api_cache()
        except NameError:
             current_app.logger.error("Cache invalidation function 'invalidate_disaster_api_cache' not found.")
        except Exception as cache_err:
            current_app.logger.error(f"Error during cache invalidation: {cache_err}", exc_info=True)

    current_app.logger.info("run_fetchers_async finished.")