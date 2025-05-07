# app/logging_config.py
import logging
import logging.handlers
import os
from datetime import datetime # Not strictly needed here if filenames are static patterns

# --- Standard Log Formatter ---
LOG_FORMAT = '%(asctime)s %(levelname)s: %(name)s: %(message)s [in %(pathname)s:%(lineno)d]'
# A simpler format for some logs if desired:
# SIMPLE_LOG_FORMAT = '%(asctime)s %(levelname)s: %(name)s: %(message)s'

# --- Common Handler Setup Function ---
def create_timed_rotating_handler(log_dir, filename_pattern, level, formatter, backup_count=30):
    """Helper to create a TimedRotatingFileHandler."""
    handler = logging.handlers.TimedRotatingFileHandler(
        os.path.join(log_dir, filename_pattern),
        when="midnight",  # Rotate daily
        interval=1,
        backupCount=backup_count,
        encoding='utf-8'
    )
    handler.setFormatter(formatter)
    handler.setLevel(level)
    return handler

# --- Main Logging Setup Function ---
def setup_logging(app):
    # Disable default Flask handler if we are setting up our own for app.logger
    # app.logger.handlers.clear() # Or remove specific handlers

    log_dir = app.config.get('LOG_DIR', 'logs')
    print(f"Attempting to use/create log directory: {os.path.abspath(log_dir)}") # <-- ADD THIS
    if not os.path.exists(log_dir):
        try:
            os.makedirs(log_dir)
        except OSError as e:
            # Fallback to console if log dir creation fails
            print(f"Warning: Could not create log directory {log_dir}: {e}. Logging to console.")
            return


    # --- Basic Formatter ---
    formatter = logging.Formatter(LOG_FORMAT)

    # 1. Error Logger (errors_YYYY-MM-DD.log)
    error_logger = logging.getLogger('error_logger') # Custom name
    error_logger.setLevel(logging.ERROR)
    error_handler = create_timed_rotating_handler(log_dir, "errors.log", logging.ERROR, formatter, backup_count=90) # Keep errors longer
    error_logger.addHandler(error_handler)
    error_logger.propagate = False # Don't let errors also go to other general loggers unless intended
    app.error_logger = error_logger # Attach to app

    # 2. General App Activity Logger (app_activity_YYYY-MM-DD.log)
    # This will be the default Flask logger `app.logger`
    # Remove existing handlers added by run.py or Flask default to avoid duplicates
    for handler in list(app.logger.handlers): # Iterate over a copy
        app.logger.removeHandler(handler)
    
    app_activity_level_str = app.config.get('LOG_LEVEL', 'INFO').upper() # From config
    app_activity_level = getattr(logging, app_activity_level_str, logging.INFO)
    app.logger.setLevel(app_activity_level) # Set level for Flask's default logger
    
    app_activity_handler = create_timed_rotating_handler(log_dir, "app_activity.log", app_activity_level, formatter)
    app.logger.addHandler(app_activity_handler)
    # Add error handler to app.logger as well, so app.logger.error() also goes to errors.log
    app.logger.addHandler(error_handler) 
    # Note: app.logger.propagate is True by default, meaning messages also go to root logger.
    # If root logger has handlers (e.g., console), you might see duplicates.
    # Consider setting app.logger.propagate = False if you only want its specific handlers.

    # 3. User Actions Logger (user_actions_YYYY-MM-DD.log)
    user_logger = logging.getLogger('user_actions')
    user_logger.setLevel(logging.INFO)
    user_handler = create_timed_rotating_handler(log_dir, "user_actions.log", logging.INFO, formatter)
    user_logger.addHandler(user_handler)
    user_logger.propagate = False
    app.user_logger = user_logger

    # 4. Admin Actions Logger (admin_actions_YYYY-MM-DD.log)
    admin_logger = logging.getLogger('admin_actions')
    admin_logger.setLevel(logging.INFO)
    admin_handler = create_timed_rotating_handler(log_dir, "admin_actions.log", logging.INFO, formatter)
    admin_logger.addHandler(admin_handler)
    admin_logger.propagate = False
    app.admin_logger = admin_logger

    # 5. Data Fetching Logger (data_fetching_YYYY-MM-DD.log)
    fetch_logger = logging.getLogger('data_fetching')
    fetch_logger.setLevel(logging.DEBUG) # More verbose for fetching
    fetch_handler = create_timed_rotating_handler(log_dir, "data_fetching.log", logging.DEBUG, formatter, backup_count=14)
    fetch_logger.addHandler(fetch_handler)
    fetch_logger.propagate = False
    app.fetch_logger = fetch_logger

    # 6. API Requests Logger (api_requests_YYYY-MM-DD.log)
    api_logger = logging.getLogger('api_requests')
    api_logger.setLevel(logging.INFO)
    # Using a simpler format for API logs might be preferable
    api_formatter = logging.Formatter('%(asctime)s: %(message)s')
    api_handler = create_timed_rotating_handler(log_dir, "api_requests.log", logging.INFO, api_formatter)
    api_logger.addHandler(api_handler)
    api_logger.propagate = False
    app.api_logger = api_logger

    # --- Initial log message to confirm setup ---
    app.logger.info("Logging configured with daily rotation and multiple handlers.")
    if app.debug: # Only in debug mode, log all configured loggers
        for name, logger_obj in logging.Logger.manager.loggerDict.items():
            if isinstance(logger_obj, logging.Logger) and logger_obj.handlers:
                 app.logger.debug(f"Logger '{name}' configured with handlers: {logger_obj.handlers}")