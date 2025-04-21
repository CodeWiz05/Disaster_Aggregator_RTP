#!/usr/bin/env python3
"""
Entry point for the Disaster Aggregator application.
Run this file to start the application server.
"""

import os
from app import create_app
import logging
from logging.handlers import RotatingFileHandler

# Determine environment based on environment variable or default to development
# Use FLASK_CONFIG for consistency with create_app, fallback to FLASK_ENV or default
env = os.environ.get('FLASK_CONFIG') or os.environ.get('FLASK_ENV', 'development')

# Create application instance with appropriate configuration
app = create_app(env)

# Configure logging only if not in testing environment
if not app.config['TESTING']:
    log_dir = app.config.get('LOG_DIR', 'logs') # Get log dir from config or default
    log_file = app.config.get('LOG_FILE', os.path.join(log_dir, 'app.log')) # Get log file from config or default

    if not os.path.exists(log_dir):
        try:
            os.makedirs(log_dir)
        except OSError as e:
             app.logger.error(f"Could not create log directory {log_dir}: {e}")

    # Ensure log file path is absolute or relative to instance path maybe?
    # For simplicity, keeping it relative to project root as implied by original code.

    try:
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=10240,
            backupCount=10
        )

        file_handler.setFormatter(logging.Formatter(
            '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
        ))

        # Set level based on config
        log_level_str = app.config.get('LOG_LEVEL', 'INFO').upper()
        log_level = getattr(logging, log_level_str, logging.INFO)
        file_handler.setLevel(log_level)

        if not app.logger.handlers: # Avoid adding handler multiple times if run script is imported
            app.logger.addHandler(file_handler)
            app.logger.setLevel(log_level)
            app.logger.info('Disaster Aggregator startup')

    except Exception as e:
        app.logger.error(f"Failed to configure file logging: {e}")


if __name__ == '__main__':
    # Get host and port from environment or defaults
    host = os.environ.get('FLASK_RUN_HOST', '0.0.0.0')
    try:
        port = int(os.environ.get('FLASK_RUN_PORT', 5000))
    except ValueError:
        port = 5000

    # Use debug mode based on config
    use_debug = app.config.get('DEBUG', False)

    app.logger.info(f"Starting Disaster Aggregator on {host}:{port} in {env} mode (Debug: {use_debug})")
    # Use Flask's built-in server, disable reloader if debug is False for stability
    app.run(host=host, port=port, debug=use_debug, use_reloader=use_debug)