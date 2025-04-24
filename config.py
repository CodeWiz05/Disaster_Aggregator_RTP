"""
Configuration settings for the Disaster Aggregator application.
"""

import os
from datetime import timedelta
from dotenv import load_dotenv

# Determine the base directory of the project
basedir = os.path.abspath(os.path.dirname(__file__))
# Load environment variables from .env file in the project root
dotenv_path = os.path.join(basedir, '..', '.env') # Assuming config.py is inside project root
if not os.path.exists(dotenv_path):
     dotenv_path = os.path.join(basedir, '.env') # If config.py is in app folder

load_dotenv(dotenv_path=dotenv_path)


class BaseConfig:
    """Base configuration settings."""

    # Flask configuration
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-key-change-in-production')

    # SQLAlchemy configuration
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    # Define default database URI (can be overridden)
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL', 'sqlite:///' + os.path.join(basedir, '..', 'database.db'))

    # Session configuration
    PERMANENT_SESSION_LIFETIME = timedelta(days=7)

    # API configuration (placeholders)
    USGS_API_KEY = os.environ.get('USGS_API_KEY')
    GDACS_API_KEY = os.environ.get('GDACS_API_KEY')
    GOOGLE_MAPS_API_KEY = os.environ.get('GOOGLE_MAPS_API_KEY')
    NASA_FIRMS_API_KEY = os.environ.get('NASA_FIRMS_API_KEY')

    # Email configuration (using uppercase standard Flask-Mail keys)
    MAIL_SERVER = os.environ.get('MAIL_SERVER')
    MAIL_PORT = int(os.environ.get('MAIL_PORT', 587))
    MAIL_USE_TLS = os.environ.get('MAIL_USE_TLS', 'True').lower() in ['true', '1', 't', 'y']
    MAIL_USE_SSL = os.environ.get('MAIL_USE_SSL', 'False').lower() in ['true', '1', 't', 'y']
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')
    MAIL_DEFAULT_SENDER = os.environ.get('MAIL_DEFAULT_SENDER', MAIL_USERNAME) # Default to username if not set

    # SMS configuration (placeholders)
    TWILIO_ACCOUNT_SID = os.environ.get('TWILIO_ACCOUNT_SID')
    TWILIO_AUTH_TOKEN = os.environ.get('TWILIO_AUTH_TOKEN')
    TWILIO_PHONE_NUMBER = os.environ.get('TWILIO_PHONE_NUMBER')

    # Logging configuration
    LOG_DIR = os.path.join(basedir, '..', 'logs') # Log directory in project root
    LOG_FILE = os.path.join(LOG_DIR, 'app.log')
    LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO').upper()


    # Scraper configuration (Example)
    SCRAPE_INTERVAL = int(os.environ.get('SCRAPE_INTERVAL', '3600')) # Default 1 hour

    # API rate limiting (using uppercase standard Flask-Limiter keys)
    RATELIMIT_DEFAULT = os.environ.get('RATELIMIT_DEFAULT', "200 per day;50 per hour")
    # Default to memory, overridden in specific configs
    RATELIMIT_STORAGE_URL = os.environ.get('RATELIMIT_STORAGE_URL', "memory://")

    # Cache configuration (using uppercase standard Flask-Caching keys)
    # Default to SimpleCache, overridden in specific configs
    CACHE_TYPE = os.environ.get('CACHE_TYPE', "SimpleCache")
    CACHE_DEFAULT_TIMEOUT = int(os.environ.get('CACHE_DEFAULT_TIMEOUT', 300))  # 5 minutes
    CACHE_REDIS_URL = os.environ.get('CACHE_REDIS_URL') # For RedisCache

    # Alert configuration (Example placeholders)
    VERIFICATION_THRESHOLD = int(os.environ.get('VERIFICATION_THRESHOLD', 3))
    MAX_ALERT_RADIUS_KM = int(os.environ.get('MAX_ALERT_RADIUS_KM', 100))


class DevelopmentConfig(BaseConfig):
    """Development configuration settings."""
    DEBUG = True
    # Use SQLite database in development if DATABASE_URL is not set
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
        'sqlite:///' + os.path.join(basedir, '..', 'database.db')
    WTF_CSRF_ENABLED = True # Good to keep enabled even in dev


class TestingConfig(BaseConfig):
    """Testing configuration settings."""
    TESTING = True
    DEBUG = True # Often useful for debugging tests
    SQLALCHEMY_DATABASE_URI = os.environ.get('TEST_DATABASE_URL') or \
        'sqlite:///:memory:' # Use in-memory SQLite for tests
    WTF_CSRF_ENABLED = False # Disable CSRF for simpler testing
    PRESERVE_CONTEXT_ON_EXCEPTION = False
    # Use memory storage for limiter/cache during tests
    RATELIMIT_STORAGE_URL = "memory://"
    CACHE_TYPE = "NullCache" # Disable caching during tests usually


class ProductionConfig(BaseConfig):
    """Production configuration settings."""
    DEBUG = False
    TESTING = False

    # Require DATABASE_URL to be set in production
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL')
    if not SQLALCHEMY_DATABASE_URI:
        raise ValueError("No DATABASE_URL set for production")

    WTF_CSRF_ENABLED = True
    # Add other production security settings if needed (e.g., SSLify)
    # SESSION_COOKIE_SECURE = True
    # REMEMBER_COOKIE_SECURE = True
    # SESSION_COOKIE_HTTPONLY = True

    # Production should use Redis or similar for Caching/Rate Limiting
    RATELIMIT_STORAGE_URL = os.environ.get('RATELIMIT_STORAGE_URL', 'redis://localhost:6379/1')
    CACHE_TYPE = os.environ.get('CACHE_TYPE', 'RedisCache')
    CACHE_REDIS_URL = os.environ.get('CACHE_REDIS_URL', 'redis://localhost:6379/0')
    CACHE_DEFAULT_TIMEOUT = int(os.environ.get('CACHE_DEFAULT_TIMEOUT', 600)) # 10 minutes

    # More restrictive logging in production
    LOG_LEVEL = "WARNING"


# Dictionary to map environment names to config classes
config = {
    'development': DevelopmentConfig,
    'testing': TestingConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}