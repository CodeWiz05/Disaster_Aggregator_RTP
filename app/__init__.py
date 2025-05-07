# app/__init__.py
import os
from flask import Flask, render_template, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_cors import CORS
from flask_login import LoginManager
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_caching import Cache
# Import the config dictionary directly
from config import config as app_configs
# --- ADD Import for MetaData ---
from sqlalchemy import MetaData, func, select
from sqlalchemy.orm import aliased

# --- Import click HERE, before it's used by the CLI command ---
# We put it in a try-except in case it's not installed, though it's a Flask dependency
try:
    import click
except ImportError:
    click = None # Set to None if not found, commands using it might fail later

# --- ADD Naming Convention ---
# Define standard naming conventions for indexes, constraints, etc.
# See: https://flask-sqlalchemy.palletsprojects.com/en/3.0.x/config/#using-custom-metadata-and-naming-conventions
convention = {
    "ix": 'ix_%(column_0_label)s',
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s"
}

# Initialize extensions globally
# --- MODIFY SQLAlchemy initialization to use the convention ---
db = SQLAlchemy(metadata=MetaData(naming_convention=convention))
migrate = Migrate()
cors = CORS()
login = LoginManager()
cache = Cache()
limiter = Limiter(
    key_func=get_remote_address,
)

# --- Login Manager Configuration ---
# *** IMPORTANT: Adjust 'main.login' if your login route is in a different blueprint or has a different name ***
login.login_view = 'main.login'
login.login_message = 'Please log in to access this page.'
login.login_message_category = 'info'

# --- Limiter Key Function (optional override for user-specific limits) ---
def get_user_id_or_ip():
    from flask_login import current_user # Local import to avoid circular dependency
    if current_user.is_authenticated:
        return str(current_user.id)
    else:
        return get_remote_address

# --- Utility Function for Cache Invalidation (Defined globally here) ---
# --- Utility Function for Cache Invalidation (REVISED AGAIN) ---
def invalidate_disaster_api_cache():
    """Clears the cache used by the main /api/disasters endpoint."""
    # --- Use current_app to access cache within context ---
    from flask import current_app
    cache_obj = current_app.extensions.get('cache') # Get cache instance from app extensions
    if cache_obj:
        try:
            # Assuming the view function was registered as 'main.get_disasters'
            # Check your blueprint registration if this name is different
            view_func_name = 'main.get_disasters'
            # Use delete_memoized_verbatim if available (newer Flask-Caching)
            if hasattr(cache_obj, 'delete_memoized_verbatim'):
                 cache_obj.delete_memoized_verbatim(view_func_name)
                 print(f"Cache cleared for '{view_func_name}' using delete_memoized_verbatim.")
            # Fallback for older versions or if above fails (might not work with blueprints)
            elif hasattr(cache_obj, 'delete_memoized'):
                  # This might still fail with blueprints, but worth trying
                  try:
                      from .routes import get_disasters # Try local import as last resort
                      cache_obj.delete_memoized(get_disasters)
                      print(f"Cache cleared for '{view_func_name}' using delete_memoized(func_ref).")
                  except Exception:
                      print(f"Could not clear cache using delete_memoized(func_ref). Manual clearing might be needed.")

            # --- Optionally clear by path (less specific if using @cache.memoize) ---
            # cache_obj.delete('/api/disasters')
            # print("Attempted cache clear for path /api/disasters")

        except Exception as e:
            current_app.logger.error(f"Error clearing cache: {e}", exc_info=True)
    else:
        print("Error clearing cache: Cache object not found in app extensions.")


# --- App Factory Function ---
def create_app(config_name=None):
    # (Keep app creation and config loading)
    app = Flask(__name__,
                static_folder='../static',
                template_folder='../templates')
    if config_name is None: ...
    if config_name not in app_configs: ...
    app.config.from_object(app_configs[config_name])
    print(f"Loaded config: {config_name}")

    # (Keep extension initializations: db, migrate, cors, login, cache, limiter)
    # --- MODIFY Migrate initialization to pass db.metadata ---
    db.init_app(app)
    migrate.init_app(app, db, render_as_batch=True) # Ensure render_as_batch is True for SQLite
    cors.init_app(app)
    login.init_app(app)
    cache.init_app(app)
    limiter.init_app(app)


    # (Keep Blueprint Registration)
    from .routes import main_bp
    app.register_blueprint(main_bp)


    # (Keep Error Handlers Registration)
    register_error_handlers(app)


    # (Keep Shell Context Processor)
    @app.shell_context_processor
    def make_shell_context(): 
        
        # Import models and db instance here so they are available in the shell
        from .models import User, DisasterReport, Disaster # Ensure these are correct model names
        # from . import db # db is already in the global scope of __init__.py
                            # but it's good practice to include it explicitly if needed
        
        return {
            'db': db,
            'User': User,
            'DisasterReport': DisasterReport,
            'Disaster': Disaster
            # Add any other models or utilities you want in the shell
        }


    # --- CLI Commands ---

    # --- Define fetch-data command (always available) ---
    @app.cli.command("fetch-data")
    def fetch_data_command():
        """Runs the async data fetchers."""
        import asyncio
        from .fetch_api import run_fetchers_async
        print("Starting data fetching...")
        with app.app_context():
            asyncio.run(run_fetchers_async())
        print("Data fetching finished.")

    # --- Register click-dependent commands together ---
    if click: # Single check if click is available

        # --- Define create-admin command ---
        @app.cli.command("create-admin")
        @click.argument("username")
        @click.argument("email")
        @click.argument("password")
        def create_admin(username, email, password):
            """Creates a new admin user."""
            # Imports needed specifically for this command
            from .models import User
            from . import db
            # Add current_app import if using logger inside
            from flask import current_app
            try:
                if User.query.filter((User.username == username) | (User.email == email)).first():
                    print(f"Error: User with username '{username}' or email '{email}' already exists.")
                    return
                admin = User(username=username, email=email, role='admin')
                admin.set_password(password)
                db.session.add(admin)
                db.session.commit()
                print(f"Admin user '{username}' created successfully.")
            except Exception as e:
                db.session.rollback()
                log_func = getattr(current_app, 'logger', None)
                if log_func:
                     log_func.error(f"Error creating admin user: {e}", exc_info=True)
                else:
                     print(f"Error creating admin user: {e}")
                print("Admin creation failed.")

        @app.cli.command("delete-unstable-firms-ids")
        @click.option('--dry-run', is_flag=True, help='Show count of reports to be deleted but do not delete.')
        @click.option('--yes', is_flag=True, help='Skip confirmation prompt.')
        def delete_unstable_firms_ids(dry_run, yes):
            """
            Deletes NASA_FIRMS reports whose source_event_id does not appear
            to match the stable format (firms_SAT_LAT_LON_DATE_TIME).
            USE WITH EXTREME CAUTION. BACKUP YOUR DB FIRST.
            """
            from .models import DisasterReport
            from sqlalchemy import delete
            import re # For regex matching

            print("Starting unstable FIRMS ID deletion check...")
            source_to_check = 'NASA_FIRMS'
        
            # Regex to identify the STABLE ID format.
            # It looks for: firms_ANYTHING_FLOAT_FLOAT_DATE_TIME
            # This is a basic regex; adjust SATELLITE_SOURCE part if needed.
            # Example: firms_VIIRS_SNPP_NRT_12.3456_-78.9012_2023-10-26_1430
            stable_id_pattern = re.compile(
                r"firms_[A-Z0-9_]+_-?\d{1,2}\.\d{4}_-?\d{1,3}\.\d{4}_\d{4}-\d{2}-\d{2}_\d{4}"
            )

            ids_to_delete = []
            try:
                with app.app_context():
                    # Fetch all NASA_FIRMS reports
                    all_firms_reports = db.session.query(DisasterReport.id, DisasterReport.source_event_id)\
                                            .filter(DisasterReport.source == source_to_check).all()

                    if not all_firms_reports:
                        print("No NASA_FIRMS reports found in the database.")
                        return

                    print(f"Checking {len(all_firms_reports)} FIRMS reports for unstable ID format...")

                    for report_id, source_event_id_val in all_firms_reports:
                        if not source_event_id_val or not stable_id_pattern.fullmatch(source_event_id_val):
                            ids_to_delete.append(report_id)
                            # if len(ids_to_delete) < 20: # Log first few to be deleted
                            #     print(f"  Marking for deletion (unstable ID): {report_id} - {source_event_id_val}")


                    count = len(ids_to_delete)

                    if count == 0:
                        print("No FIRMS reports with unstable ID format found to delete.")
                        return

                    print(f"Found {count} FIRMS reports with unstable ID format to delete.")
                    if dry_run:
                        print("Sample IDs to be deleted:", ids_to_delete[:20])
                        print("Dry run finished. No changes made.")
                        return

                    if not yes:
                        click.confirm(f'Proceed with deleting {count} unstable-ID FIRMS reports?', abort=True)

                    print(f"Deleting {count} unstable-ID FIRMS reports...")
                    if ids_to_delete:
                        chunk_size = 500
                        deleted_count_total = 0
                        for i in range(0, len(ids_to_delete), chunk_size):
                            chunk = ids_to_delete[i:i + chunk_size]
                            stmt_delete = delete(DisasterReport)\
                                        .where(DisasterReport.id.in_(chunk))\
                                        .execution_options(synchronize_session=False)
                            result = db.session.execute(stmt_delete)
                            deleted_count_total += result.rowcount
                        db.session.commit()
                        print(f"Successfully deleted {deleted_count_total} reports.")
                    else:
                        print("No reports to delete.")
            except Exception as e:
                db.session.rollback()
                from flask import current_app
                current_app.logger.error(f"Error deleting unstable FIRMS IDs: {e}", exc_info=True)
                print(f"An error occurred: {e}")

        # --- Define clean-firms-duplicates command (INSIDE the same 'if click:') ---
        @app.cli.command("clean-firms-duplicates")
        @click.option('--dry-run', is_flag=True, help='Show duplicates but do not delete.')
        @click.option('--yes', is_flag=True, help='Skip confirmation prompt (use with caution!).')
        def clean_firms_duplicates(dry_run, yes):
            """Finds and optionally removes duplicate NASA_FIRMS reports based on source_event_id."""
            from .models import DisasterReport # Import model inside command
            # Import necessary SQLAlchemy components for this command
            from sqlalchemy import delete, func, select

            print("Starting FIRMS duplicate check...")
            source_to_check = 'NASA_FIRMS'

            try:
                with app.app_context(): # Ensure we are in app context for DB session

                    # 1. Define the window function
                    row_number_window = func.row_number().over(
                        partition_by=(DisasterReport.source, DisasterReport.source_event_id),
                        order_by=DisasterReport.id.asc() # Keep the one with the lowest ID
                    ).label('row_num')

                    # 2. Create a subquery
                    subq = select(
                               DisasterReport.id,
                               row_number_window
                           )\
                           .where(DisasterReport.source == source_to_check)\
                           .subquery('ranked_firms_reports')

                    # 3. Select the IDs of the reports to DELETE
                    stmt_select_ids_to_delete = select(subq.c.id).where(subq.c.row_num > 1)

                    # Execute the selection query to find IDs
                    duplicate_ids_result = db.session.execute(stmt_select_ids_to_delete).scalars().all()
                    duplicate_ids = list(duplicate_ids_result) # Convert to list
                    count = len(duplicate_ids)

                    # Handle the "No Duplicates Found" case first
                    if count == 0:
                        print("No duplicate FIRMS reports found based on source_event_id.")
                        return # Exit cleanly

                    # Code below only runs if count > 0
                    print(f"Found {count} duplicate FIRMS report entries to remove.")

                    # Handle the "Dry Run" case next
                    if dry_run:
                        # Optionally print some IDs for confirmation during dry run
                        print("Duplicate IDs (sample):", duplicate_ids[:20]) # Show first 20
                        print("Dry run finished. No changes made.")
                        return # Exit after showing info

                    # Code below only runs if count > 0 AND it's NOT a dry run

                    # Confirmation prompt (only if not dry run)
                    if not yes:
                        click.confirm(f'Proceed with deleting {count} duplicate report entries?', abort=True)

                    # Execute the DELETE operation
                    print(f"Deleting {count} duplicate FIRMS reports...")
                    # Use synchronize_session=False for potentially better performance on bulk deletes
                    stmt_delete = delete(DisasterReport)\
                                  .where(DisasterReport.id.in_(duplicate_ids))\
                                  .execution_options(synchronize_session=False)

                    result = db.session.execute(stmt_delete)
                    db.session.commit()
                    print(f"Successfully deleted {result.rowcount} duplicate reports.") # rowcount gives affected rows

            except Exception as e:
                from flask import current_app
                db.session.rollback() # Rollback on error
                print(f"An error occurred: {e}")
                # Log the error as well
                log_func = getattr(current_app, 'logger', None)
                if log_func: log_func.error(f"Error cleaning FIRMS duplicates: {e}", exc_info=True)
                print("Operation failed and was rolled back.")

    # --- The SINGLE 'else' block for when 'click' is NOT available ---
    else:
        # Optional: Log a general warning if click isn't available
        # Note: Using app.logger here might not work if called before app logging is fully configured.
        # A print statement might be more reliable at this stage if needed.
        # print("WARNING: Package 'click' not found. Skipping registration of click-dependent CLI commands.")
        pass # Or log using app.logger if configured early enough

    # --- End of CLI Commands Section ---

    return app # Keep returning app from factory
   




# --- Error Handler Registration Function ---
def register_error_handlers(app):
    @app.errorhandler(403)
    def forbidden(e):
        if request.accept_mimetypes.accept_json and not request.accept_mimetypes.accept_html:
            return jsonify(error="Forbidden", message="You don't have permission to access this resource."), 403
        return render_template('error.html', error_code=403, error_message='Forbidden - Access Denied'), 403

    @app.errorhandler(404)
    def page_not_found(e):
        if request.accept_mimetypes.accept_json and not request.accept_mimetypes.accept_html:
             return jsonify(error="Not Found", message="The requested resource was not found."), 404
        return render_template('error.html', error_code=404, error_message='Page Not Found'), 404

    @app.errorhandler(429) # Rate limit exceeded
    def rate_limit_handler(e):
        # Correct way to get description from limiter error
        error_desc = getattr(e, 'description', 'Rate limit exceeded')
        if request.accept_mimetypes.accept_json and not request.accept_mimetypes.accept_html:
            return jsonify(error="Rate Limit Exceeded", message=error_desc), 429
        return render_template('error.html', error_code=429, error_message=f"Too many requests: {error_desc}"), 429

    @app.errorhandler(500)
    def internal_server_error(e):
        # Log the exception e?
        app.logger.error(f"Internal Server Error: {e}", exc_info=True) # Log the full traceback
        db.session.rollback() # Rollback session on internal errors
        if request.accept_mimetypes.accept_json and not request.accept_mimetypes.accept_html:
             return jsonify(error="Internal Server Error", message="An unexpected error occurred."), 500
        # Pass generic message to user, specific details are logged
        return render_template('error.html', error_code=500, error_message='Internal Server Error'), 500