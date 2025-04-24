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
from sqlalchemy import MetaData

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
    def make_shell_context(): ...


    # --- CLI Commands ---
    # Define fetch-data command
    @app.cli.command("fetch-data")
    def fetch_data_command():
        """Runs the async data fetchers."""
        import asyncio
        from .fetch_api import run_fetchers_async
        print("Starting data fetching...")
        with app.app_context():
            asyncio.run(run_fetchers_async())
        print("Data fetching finished.")

    # Define create-admin command *only if click was imported successfully*
    if click:
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
                # Use logger if available, otherwise print
                log_func = getattr(current_app, 'logger', None)
                if log_func:
                     log_func.error(f"Error creating admin user: {e}", exc_info=True)
                else:
                     print(f"Error creating admin user: {e}")
                print("Admin creation failed.")
    else:
        # Optional: Log a warning if click isn't available and command can't be registered
        app.logger.warning("Package 'click' not found. Skipping registration of 'create-admin' command.")


    return app


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