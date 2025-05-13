#!/usr/bin/env python3
"""
Entry point for the Disaster Aggregator application.
Run this file to start the application server.
"""

import os
from app import create_app

# Determine environment based on environment variable or default to development
# Use FLASK_CONFIG for consistency with create_app, fallback to FLASK_ENV or default
env = os.environ.get('FLASK_CONFIG') or os.environ.get('FLASK_ENV', 'development')

# Create application instance with appropriate configuration
app = create_app(env)


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
    app.run(host=host, port=port, debug=use_debug, use_reloader=False)