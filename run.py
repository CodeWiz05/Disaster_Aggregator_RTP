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
env = os.environ.get('FLASK_ENV', 'development')

# Create application instance with appropriate configuration
app = create_app(env)

# Configure logging
if not os.path.exists('logs'):
    os.mkdir('logs')

file_handler = RotatingFileHandler(
    app.config['LOG_FILE'],
    maxBytes=10240,
    backupCount=10
)

file_handler.setFormatter(logging.Formatter(
    '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
))

file_handler.setLevel(logging.INFO)
app.logger.addHandler(file_handler)

app.logger.setLevel(logging.INFO)
app.logger.info('Disaster Aggregator startup')


if __name__ == '__main__':
    # Run the application
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)