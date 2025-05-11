# app/routes.py - Replace the entire get_disasters function AGAIN (v3)

# --- Ensure these imports are at the top of routes.py ---
from flask import (Blueprint, render_template, request, flash,
                   redirect, url_for, jsonify, abort, current_app)
from flask_login import login_required, current_user, login_user, logout_user
from . import db, limiter, cache, invalidate_disaster_api_cache
from .models import DisasterReport, Disaster, User
from .utils import sanitize_input, admin_required, find_or_create_disaster_event
from urllib.parse import urlparse, urljoin
from sqlalchemy import func, select, desc, extract
from sqlalchemy.orm import aliased
from datetime import datetime, timezone
import logging
# -------------------------------------------------------

# Keep main_bp definition
main_bp = Blueprint('main', __name__)

# Keep other routes (index, etc.)
# --- Homepage / Dashboard (Public) ---
@main_bp.route('/')
@main_bp.route('/index')
# Login NOT required
def index():
    # Data is fetched by frontend JS via /api/disasters
    return render_template('index.html', title='Live Dashboard')

# --- API Endpoint (RE-VERIFIED v3 - Top N per Type with Explicit Join) ---
@main_bp.route('/api/disasters')
@cache.memoize(timeout=180)
@limiter.limit("100 per hour")
def get_disasters():
    """
    API endpoint to get the latest N (e.g., 100) verified disaster reports
    for EACH disaster type. Uses explicit join to avoid Cartesian warning.
    """
    current_app.api_logger.info(f"API Request: {request.method} {request.path} from {request.remote_addr} with args {request.args}")
    N = 100 # Number of latest reports per type to fetch

    try:
        current_app.logger.debug(f"Querying database for top {N} verified reports per type...")

        # --- START SQLAlchemy Window Function Query ---

        # 1. Define the window function
        row_number_window = func.row_number().over(
            partition_by=DisasterReport.disaster_type,
            order_by=desc(DisasterReport.timestamp)
        ).label('row_num')

        # 2. Create a subquery selecting the ID and the row number
        #    selecting FROM DisasterReport itself (no alias needed here yet)
        subq = select(
                   DisasterReport.id, # Select the primary key directly
                   row_number_window  # Select the calculated row number
               )\
               .filter(DisasterReport.verified == True)\
               .subquery('ranked_reports') # Name the subquery

        # 3. Select the full DisasterReport object, joining ON the subquery's ID
        #    and filtering by the subquery's row number.
        query = select(DisasterReport)\
                .join(subq, DisasterReport.id == subq.c.id)\
                .filter(subq.c.row_num <= N)\
                .order_by(DisasterReport.disaster_type, desc(DisasterReport.timestamp))

        # --- Log the generated SQL for debugging ---
        try:
            compiled_sql = str(query.compile(db.session.bind, compile_kwargs={"literal_binds": False})) # Use session bind for dialect
            current_app.logger.debug(f"Generated SQL Query v3:\n{compiled_sql}")
        except Exception as sql_log_err:
            current_app.logger.warning(f"Could not compile/log SQL query: {sql_log_err}")
        # --- End SQL logging ---

        # Execute the query
        results = db.session.execute(query).scalars().all()

        # --- END SQLAlchemy Window Function Query ---

        report_count = len(results)
        current_app.logger.info(f"Found {report_count} reports (Top {N} per type).")

        # Convert to list of dictionaries
        disasters_data = [r.to_dict() for r in results]
        current_app.logger.debug(f"Returning {len(disasters_data)} reports in API response.")
        return jsonify(disasters_data)

    except Exception as e:
        current_app.logger.error(f"Error querying top N reports per type: {e}", exc_info=True)
        return jsonify(error="Error retrieving disaster data", message=str(e)), 500

# --- Keep remaining routes ---
# ... (report, verify, process_verification, history, login, is_safe_url, logout, register) ...
    

# --- User Report Submission (Login Required) ---
@main_bp.route('/report', methods=['GET', 'POST'])
@login_required # Login IS required
def report():
    """Handles user submission of disaster reports."""
    # Keep track of form data to repopulate on error
    form_data = request.form if request.method == 'POST' else {}

    if request.method == 'POST':
        # Apply rate limiting specifically to POST for this user
        limit_key = f"report:{current_user.id}"
        # Use limiter.check() to see if limit would be exceeded, though limiter handles 429 response automatically
        if not limiter.check():
             # This block might not be reached if limiter directly aborts with 429
             # Depending on Flask-Limiter config, it might just return False here
             # flash("Rate limit exceeded. Please wait before submitting again.", "warning")
             # return render_template('report_form.html', title='Submit Report', form_data=form_data), 429
             pass # Assume limiter handles the 429 response

        try:
            # Sanitize and retrieve form data
            title = sanitize_input(request.form.get('title'))
            description = sanitize_input(request.form.get('description'))
            disaster_type = request.form.get('disaster_type')
            latitude_str = request.form.get('latitude')
            longitude_str = request.form.get('longitude')
            severity_str = request.form.get('severity')

            # Validation
            errors = []
            if not title: errors.append("Title is required.")
            if not disaster_type: errors.append("Disaster type is required.")

            latitude, longitude = None, None
            try:
                # Ensure lat/lon are provided before trying float conversion
                if not latitude_str: raise ValueError("Latitude is required.")
                latitude = float(latitude_str)
                if not longitude_str: raise ValueError("Longitude is required.")
                longitude = float(longitude_str)
                # Basic range check for lat/lon
                if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
                     raise ValueError("Latitude/Longitude out of valid range.")
            except (ValueError, TypeError) as ve:
                errors.append(f"Invalid location format or value: {ve}")

            severity = None
            if severity_str: # Severity might be optional
                try:
                    severity = int(severity_str)
                    if not 1 <= severity <= 5:
                        raise ValueError("Severity must be between 1 and 5.")
                except (ValueError, TypeError):
                    errors.append("Severity must be a whole number between 1 and 5.")
            # Uncomment below if severity is required
            # else: errors.append("Severity is required.")

            if errors:
                for error in errors: flash(error, 'danger')
                # Pass form data back to template
                return render_template('report_form.html', title='Submit Report', form_data=form_data), 400

            # Create and save the report
            new_report = DisasterReport(
                title=title,
                description=description,
                disaster_type=disaster_type,
                latitude=latitude,
                longitude=longitude,
                severity=severity,
                source='UserReport',
                verified=False, # User reports start unverified
                user_id=current_user.id, # Link to logged-in user
                status='pending' #Explicitly set, or rely on default
            )
            db.session.add(new_report)
            db.session.commit()
            # ... after report is saved ...
            current_app.user_logger.info(f"User '{current_user.username}' (ID: {current_user.id}) submitted report ID {new_report.id}, status '{new_report.status}'.")

            flash('Report submitted successfully! Awaiting verification.', 'success')
            return redirect(url_for('main.index'))

        except Exception as e:
            db.session.rollback() # Rollback on any error during processing
            current_app.error_logger.error(f"Error saving user report for user {current_user.id}: {e}", exc_info=True) # Use error_logger
            flash('An error occurred while submitting your report. Please try again.', 'danger')
            # Pass form data back
            return render_template('report_form.html', title='Submit Report', form_data=form_data), 500

    # GET request: Render the form page
    return render_template('report_form.html', title='Submit Report', form_data={})


# --- Admin Verification Panel (GET Request - Renders the page) ---
@main_bp.route('/verify')
@login_required
@admin_required
def verify():
    """Admin panel page - HTML is rendered, JS will fetch data."""
    # No need to pass reports here anymore, JS will fetch them.
    return render_template('verify_panel.html', title='Verify Reports')

# --- NEW API Endpoint: Get Unverified Reports ---
@main_bp.route('/api/unverified_reports')
@login_required
@admin_required
@limiter.limit("60 per minute") # Add rate limit if desired
def get_unverified_reports():
    """API endpoint to fetch unverified user-submitted reports."""
    current_app.logger.info(f"Admin '{current_user.username}' requested unverified reports.")
    try:
        reports_to_verify = DisasterReport.query.filter_by(
            source='UserReport',
            status='pending' # MODIFIED: Only fetch 'pending' status
            # Optional: Add filter for status != 'spam' or 'rejected' if using a status field
        ).order_by(DisasterReport.timestamp.asc()).all() # Show oldest first

        reports_data = [report.to_dict() for report in reports_to_verify]
        current_app.logger.debug(f"Found {len(reports_data)} unverified reports.")
        return jsonify(reports_data)

    except Exception as e:
        current_app.logger.error(f"Error fetching reports for verification API: {e}", exc_info=True)
        # Return a JSON error response for the API
        return jsonify(error="Failed to fetch reports", message=str(e)), 500


# --- Process Verification Action (POST Request - Updated slightly for clarity) ---
@main_bp.route('/verify/<int:report_id>', methods=['POST'])
@login_required
@admin_required
def process_verification(report_id):
    """Handles the POST request from the verification panel (Verify/Reject/Spam)."""
    report = db.session.get(DisasterReport, report_id)
    if not report:
        # Return JSON error for AJAX, or keep flash/redirect if JS handles it
        # flash(f'Report ID {report_id} not found.', 'error')
        # return redirect(url_for('main.verify'))
        return jsonify(success=False, message=f'Report ID {report_id} not found.'), 404

    if report.source != 'UserReport':
         # flash(f'Report ID {report_id} is not a user report...', 'warning')
         # return redirect(url_for('main.verify'))
        return jsonify(success=False, message=f'Report ID {report_id} is not a user report.'), 400

    action = request.form.get('action') # Still expecting form data from JS fetch
    if not action:
        return jsonify(success=False, message='Missing action parameter.'), 400

    needs_cache_invalidation = False
    action_performed_message = "" # Message for successful action

    try:
        original_verified_status = report.verified # Store original for cache check
        if action == 'verify':
            if not report.verified: needs_cache_invalidation = True
            report.verified = True
            report.status = 'verified_agg' # New status for user reports verified by admin
            disaster_event = find_or_create_disaster_event(report)
            if disaster_event:
                action_performed_message = f'Report {report_id} verified and linked/updated event {disaster_event.id}.'
            else:
                # Still verified, but linking failed - might be a warning level?
                action_performed_message = f'Report {report_id} verified, but failed to link to an aggregate event.'
                # Consider if this should be a 200 OK with warning or different status

        elif action == 'reject':
            if report.verified: needs_cache_invalidation = True
            report.verified = False
            report.status = 'rejected' # Mark as not verified (can be resubmitted/reconsidered?)
            # Optional: Unlink if previously linked (though unlikely for unverified)
            # if report.disaster_id: report.disaster_id = None
            db.session.add(report) # Ensure change is tracked
            action_performed_message = f'Report {report_id} marked as rejected.'

        elif action == 'spam':
            # Treat spam same as reject for now (mark unverified)
            # We might later add a specific 'status' field or delete spam
            if report.verified: needs_cache_invalidation = True
            report.verified = False
            report.status = 'spam'
            db.session.add(report)
            action_performed_message = f'Report {report_id} marked as spam.'
            # Optional: Consider deleting spam reports immediately
            # db.session.delete(report)
            # action_performed_message = f'Report {report_id} marked as spam and deleted.'
        else:
            return jsonify(success=False, message='Invalid verification action specified.'), 400

        # Check if the public 'verified' status changed
        if original_verified_status != report.verified:
            needs_cache_invalidation = True
        
        # Commit all changes for this action transactionally
        db.session.commit()
        current_app.admin_logger.info(f"Admin '{current_user.username}' (ID: {current_user.id}) performed action '{action}' on report {report_id}. Status set to '{report.status}'.")

        # Invalidate Cache only if verification status might have changed public data
        if needs_cache_invalidation:
            current_app.logger.info(f"Action '{action}' triggered cache invalidation for report {report_id}.")
            invalidate_disaster_api_cache()

        # Return JSON success for AJAX call
        return jsonify(success=True, message=action_performed_message)

    except Exception as e:
        db.session.rollback()
        current_app.error_logger.error(f"Error processing verification action '{action}' for report {report_id}: {e}", exc_info=True) # Use error_logger
        # Return JSON error for AJAX call
        return jsonify(success=False, message='An error occurred during verification processing.'), 500
    
# --- NEW API Endpoint: Get Historical Reports (Filterable & Paginated) ---
@main_bp.route('/api/history/reports')
# @login_required # Decide if login is required for historical data
@limiter.limit("120 per minute") # Adjust rate limit as needed
def get_historical_reports():
    current_app.api_logger.info(f"API Request: {request.method} {request.path} from {request.remote_addr} with args {request.args}")

    try:
        # --- 1. Get and Validate Query Parameters ---
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 25, type=int)
        if per_page > 100: # Max per_page limit
            per_page = 100
        if page < 1:
            page = 1

        start_date_str = request.args.get('start_date')
        end_date_str = request.args.get('end_date')
        disaster_type = request.args.get('type', 'all')
        min_severity_str = request.args.get('min_severity')
        # year_str = request.args.get('year') # For later

        # --- 2. Build Base Query ---
        # We want reports that are considered public/finalized
        # Using verified=True is a good start.
        # Or specific statuses: query = DisasterReport.query.filter(DisasterReport.status.in_(['verified_agg', 'api_verified']))
        query = DisasterReport.query.filter(DisasterReport.verified == True)


        # --- 3. Apply Filters ---
        # Date Range Filter
        if start_date_str:
            try:
                start_date = datetime.strptime(start_date_str, '%Y-%m-%d').replace(hour=0, minute=0, second=0, microsecond=0)
                # Ensure timezone awareness if comparing with timezone-aware DB timestamps
                # If your DB stores naive UTC, make start_date naive UTC too.
                # If DB stores aware UTC, make start_date aware UTC.
                # Assuming DB timestamp is aware UTC (from DateTime(timezone=True)):
                start_date = start_date.replace(tzinfo=timezone.utc)
                query = query.filter(DisasterReport.timestamp >= start_date)
            except ValueError:
                return jsonify(error="Invalid start_date format. Use YYYY-MM-DD."), 400
        
        if end_date_str:
            try:
                end_date = datetime.strptime(end_date_str, '%Y-%m-%d').replace(hour=23, minute=59, second=59, microsecond=999999)
                # Timezone awareness, similar to start_date
                end_date = end_date.replace(tzinfo=timezone.utc)
                query = query.filter(DisasterReport.timestamp <= end_date)
            except ValueError:
                return jsonify(error="Invalid end_date format. Use YYYY-MM-DD."), 400

        # Disaster Type Filter
        if disaster_type and disaster_type.lower() != 'all':
            query = query.filter(DisasterReport.disaster_type == disaster_type.lower())

        # Minimum Severity Filter
        if min_severity_str:
            try:
                min_severity = int(min_severity_str)
                if 1 <= min_severity <= 5:
                    query = query.filter(DisasterReport.severity >= min_severity)
                else:
                    # Optional: return error for invalid severity range, or just ignore
                    pass # Ignoring invalid severity for now
            except ValueError:
                # Optional: return error for non-integer severity, or ignore
                pass # Ignoring invalid severity for now
        
        # Year Filter (Example for later)
        # if year_str and year_str.lower() != 'all':
        #     try:
        #         year = int(year_str)
        #         query = query.filter(extract('year', DisasterReport.timestamp) == year)
        #     except ValueError:
        #         pass # Ignore invalid year

        # --- 4. Order and Paginate ---
        query = query.order_by(DisasterReport.timestamp.desc())
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)
        
        reports_data = [report.to_dict() for report in pagination.items]

        # --- 5. Return JSON Response with Pagination Metadata ---
        response_data = {
            'reports': reports_data,
            'total_items': pagination.total,
            'total_pages': pagination.pages,
            'current_page': pagination.page,
            'per_page': pagination.per_page,
            'has_next': pagination.has_next,
            'has_prev': pagination.has_prev,
            'next_page_num': pagination.next_num,
            'prev_page_num': pagination.prev_num
        }
        current_app.api_logger.info(f"API Response: Status 200, {len(reports_data)} items (Page {pagination.page}/{pagination.pages}) for {request.path}")
        return jsonify(response_data)

    except Exception as e:
        current_app.error_logger.error(f"Error in /api/history/reports: {e}", exc_info=True)
        return jsonify(error="An internal error occurred", message=str(e)), 500

@main_bp.route('/api/history/stats/by_type')
# @login_required # Optional
@limiter.limit("60 per minute")
def get_history_stats_by_type():
    current_app.api_logger.info(f"API Request: {request.method} {request.path} from {request.remote_addr} with args {request.args}")
    try:
        start_date_str = request.args.get('start_date')
        end_date_str = request.args.get('end_date')
        # disaster_type filter is NOT applied here, as we want counts for ALL types
        min_severity_str = request.args.get('min_severity')
        # Add year/region filters here if they become available

        query = DisasterReport.query.filter(DisasterReport.verified == True)

        if start_date_str:
            try:
                start_date = datetime.strptime(start_date_str, '%Y-%m-%d').replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=timezone.utc)
                query = query.filter(DisasterReport.timestamp >= start_date)
            except ValueError:
                return jsonify(error="Invalid start_date format. Use YYYY-MM-DD."), 400
        
        if end_date_str:
            try:
                end_date = datetime.strptime(end_date_str, '%Y-%m-%d').replace(hour=23, minute=59, second=59, microsecond=999999, tzinfo=timezone.utc)
                query = query.filter(DisasterReport.timestamp <= end_date)
            except ValueError:
                return jsonify(error="Invalid end_date format. Use YYYY-MM-DD."), 400

        if min_severity_str:
            try:
                min_severity = int(min_severity_str)
                if 1 <= min_severity <= 5:
                    query = query.filter(DisasterReport.severity >= min_severity)
            except ValueError:
                pass # Ignore invalid severity

        # Perform aggregation
        # Group by disaster_type and count occurrences
        results = query.with_entities(DisasterReport.disaster_type, func.count(DisasterReport.id))\
                       .group_by(DisasterReport.disaster_type)\
                       .order_by(func.count(DisasterReport.id).desc())\
                       .all()
        
        labels = [row[0] for row in results]
        data = [row[1] for row in results]

        return jsonify({'labels': labels, 'data': data})

    except Exception as e:
        current_app.error_logger.error(f"Error in /api/history/stats/by_type: {e}", exc_info=True)
        return jsonify(error="An internal error occurred", message=str(e)), 500

@main_bp.route('/api/history/stats/by_month')
# @login_required # Optional
@limiter.limit("60 per minute")
def get_history_stats_by_month():
    current_app.api_logger.info(f"API Request: {request.method} {request.path} from {request.remote_addr} with args {request.args}")
    try:
        start_date_str = request.args.get('start_date')
        end_date_str = request.args.get('end_date')
        disaster_type = request.args.get('type', 'all')
        min_severity_str = request.args.get('min_severity')
        target_year_str = request.args.get('year') # Specific year for monthly breakdown

        query = DisasterReport.query.filter(DisasterReport.verified == True)

        # Apply common filters
        if start_date_str:
            try:
                start_date = datetime.strptime(start_date_str, '%Y-%m-%d').replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=timezone.utc)
                query = query.filter(DisasterReport.timestamp >= start_date)
            except ValueError: return jsonify(error="Invalid start_date"), 400
        
        if end_date_str:
            try:
                end_date = datetime.strptime(end_date_str, '%Y-%m-%d').replace(hour=23, minute=59, second=59, microsecond=999999, tzinfo=timezone.utc)
                query = query.filter(DisasterReport.timestamp <= end_date)
            except ValueError: return jsonify(error="Invalid end_date"), 400

        if disaster_type and disaster_type.lower() != 'all':
            query = query.filter(DisasterReport.disaster_type == disaster_type.lower())

        if min_severity_str:
            try:
                min_severity = int(min_severity_str)
                if 1 <= min_severity <= 5: query = query.filter(DisasterReport.severity >= min_severity)
            except ValueError: pass

        if target_year_str and target_year_str.lower() != 'all':
            try:
                target_year = int(target_year_str)
                query = query.filter(extract('year', DisasterReport.timestamp) == target_year)
            except ValueError:
                return jsonify(error="Invalid year format."), 400
        # If no target_year, and no start/end date, this chart might not make sense or show all months ever.
        # For now, it will use the date range if provided, or filter by target_year.
        # If neither, it will group all data by month across all years.

        # Perform aggregation
        # Group by month and count occurrences
        # extract('month', ...) gives 1 for Jan, 2 for Feb, etc.
        results = query.with_entities(extract('month', DisasterReport.timestamp).label('month'), 
                                      func.count(DisasterReport.id).label('count'))\
                       .group_by('month')\
                       .order_by('month')\
                       .all()
        
        # Prepare data for Chart.js (ensure all 12 months are present, even if count is 0)
        month_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
        monthly_data = [0] * 12 # Initialize with zeros
        for row in results:
            month_index = int(row.month) - 1 # SQLAlchemy extract might return float/Decimal
            if 0 <= month_index < 12:
                monthly_data[month_index] = row.count
        
        return jsonify({'labels': month_names, 'data': monthly_data})

    except Exception as e:
        current_app.error_logger.error(f"Error in /api/history/stats/by_month: {e}", exc_info=True)
        return jsonify(error="An internal error occurred", message=str(e)), 500
    
@main_bp.route('/api/history/stats/by_severity')
# @login_required # Optional
@limiter.limit("60 per minute")
def get_history_stats_by_severity():
    current_app.api_logger.info(f"API Request: {request.method} {request.path} from {request.remote_addr} with args {request.args}")
    try:
        start_date_str = request.args.get('start_date')
        end_date_str = request.args.get('end_date')
        disaster_type = request.args.get('type', 'all')
        # min_severity filter is NOT applied here, as we want distribution across ALL severities
        # Add year/region filters here if they become available

        query = DisasterReport.query.filter(DisasterReport.verified == True)

        # Apply common filters
        if start_date_str:
            try:
                start_date = datetime.strptime(start_date_str, '%Y-%m-%d').replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=timezone.utc)
                query = query.filter(DisasterReport.timestamp >= start_date)
            except ValueError: return jsonify(error="Invalid start_date"), 400
        
        if end_date_str:
            try:
                end_date = datetime.strptime(end_date_str, '%Y-%m-%d').replace(hour=23, minute=59, second=59, microsecond=999999, tzinfo=timezone.utc)
                query = query.filter(DisasterReport.timestamp <= end_date)
            except ValueError: return jsonify(error="Invalid end_date"), 400

        if disaster_type and disaster_type.lower() != 'all':
            query = query.filter(DisasterReport.disaster_type == disaster_type.lower())

        # Perform aggregation
        # Group by severity and count occurrences
        results = query.with_entities(DisasterReport.severity, func.count(DisasterReport.id))\
                       .group_by(DisasterReport.severity)\
                       .order_by(DisasterReport.severity)\
                       .all()
        
        # Prepare data for Chart.js (ensure all severities 1-5 are present)
        severity_labels = [f"Severity {i}" for i in range(1, 6)]
        severity_data = [0] * 5 # Initialize with zeros
        for row in results:
            severity_val = row[0]
            count_val = row[1]
            if severity_val is not None and 1 <= severity_val <= 5:
                severity_data[severity_val - 1] = count_val
            elif severity_val is None: # Handle cases where severity might be NULL
                current_app.logger.warning("Found reports with NULL severity during aggregation for by_severity chart.")
                # Decide how to handle these - ignore, or add to a 'Severity Unknown' category
        
        return jsonify({'labels': severity_labels, 'data': severity_data})

    except Exception as e:
        current_app.error_logger.error(f"Error in /api/history/stats/by_severity: {e}", exc_info=True)
        return jsonify(error="An internal error occurred", message=str(e)), 500

# --- Historical Data Viewer (Public) ---
@main_bp.route('/history')
# Login NOT required
def history():
    """Displays historical verified disaster data."""
    try:
        # Show last 50 aggregated disaster events
        # Consider adding pagination here for larger datasets
        historical_events = Disaster.query.order_by(Disaster.start_time.desc()).limit(50).all()
        # Use the summary dict for cleaner display in template
        event_data = [event.to_summary_dict() for event in historical_events]
        return render_template('history.html', title='Historical Data', events=event_data)
    except Exception as e:
         current_app.logger.error(f"Error fetching history: {e}", exc_info=True)
         flash('Error loading historical data.', 'danger')
         return redirect(url_for('main.index'))


# --- Login Route ---
@main_bp.route('/login', methods=['GET', 'POST'])
# Login NOT required (it's the login page itself)
def login():
     """Handles user login."""
     if current_user.is_authenticated:
         # If already logged in, redirect to index
         return redirect(url_for('main.index'))

     if request.method == 'POST':
         username = request.form.get('username')
         password = request.form.get('password')
         remember = request.form.get('remember_me') is not None

         # Basic validation
         if not username or not password:
              flash('Username and password are required.', 'danger')
              # Render form again, maybe pass username back?
              return render_template('login.html', title='Sign In', username=username), 400

         # Find user and check password
         user = User.query.filter_by(username=username).first()
         if user is None or not user.check_password(password):
             flash('Invalid username or password.', 'danger')
             # Render form again, maybe pass username back?
             return render_template('login.html', title='Sign In', username=username), 401 # Unauthorized

         # Log user in using Flask-Login
         login_user(user, remember=remember)
         current_app.logger.info(f"User '{username}' logged in successfully.")

         # Handle redirect after login (to intended page or index)
         next_page = request.args.get('next')
         # Use the is_safe_url check to prevent open redirect vulnerability
         if not next_page or not is_safe_url(next_page):
             next_page = url_for('main.index')
         flash('Login successful!', 'success')
         return redirect(next_page)

     # GET request: Show the login form
     return render_template('login.html', title='Sign In')


# --- Safe URL Check Function ---
def is_safe_url(target):
    """Checks if a redirect target URL is safe (same host)."""
    ref_url = urlparse(request.host_url)
    test_url = urlparse(urljoin(request.host_url, target))
    # Allow only http and https schemes and ensure the target domain is the same as host
    return test_url.scheme in ('http', 'https') and \
           ref_url.netloc == test_url.netloc


# --- Logout Route ---
@main_bp.route('/logout')
@login_required # User must be logged in to log out
def logout():
    """Logs the current user out."""
    username = current_user.username # Get username before logging out
    logout_user()
    current_app.logger.info(f"User '{username}' logged out.")
    flash('You have been successfully logged out.', 'info')
    return redirect(url_for('main.index'))


# --- Registration Route ---
@main_bp.route('/register', methods=['GET', 'POST'])
# Login NOT required
def register():
    """Handles new user registration."""
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))

    # Keep track of form data for repopulation
    form_data = request.form if request.method == 'POST' else {}

    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email') # Consider adding email validation (e.g., using email-validator)
        password = request.form.get('password')
        password2 = request.form.get('password2')

        # Validation
        errors = []
        if not username: errors.append('Username is required.')
        if not email: errors.append('Email is required.')
        if not password: errors.append('Password is required.')
        if password != password2: errors.append('Passwords do not match.')

        # Check uniqueness if basic validation passes
        if not errors:
            if User.query.filter_by(username=username).first():
                errors.append('Username already taken. Please choose another.')
            if User.query.filter_by(email=email).first():
                errors.append('Email address already registered. Please use a different email or log in.')

        if errors:
             for error in errors: flash(error, 'danger')
             return render_template('register.html', title='Register', form_data=form_data), 400
        else:
            # Create user if validation successful
            try:
                user = User(username=username, email=email)
                user.set_password(password)
                # Default role is 'user' as defined in the model
                db.session.add(user)
                db.session.commit()
                current_app.logger.info(f"New user registered: '{username}'")
                flash('Registration successful! Please log in.', 'success')
                return redirect(url_for('main.login'))
            except Exception as e:
                 db.session.rollback()
                 current_app.logger.error(f"Error during registration for {username}: {e}", exc_info=True)
                 flash('An error occurred during registration. Please try again later.', 'danger')
                 return render_template('register.html', title='Register', form_data=form_data), 500


    # GET request: Show registration form
    return render_template('register.html', title='Register', form_data={})