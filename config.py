"""
Configuration settings for the Disaster Aggregator application.
"""

import os
from datetime import timedelta
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class BaseConfig:
    """Base configuration settings."""
    
    # Flask configuration
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-key-change-in-production')
    
    # SQLAlchemy configuration
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Session configuration
    PERMANENT_SESSION_LIFETIME = timedelta(days=7)
    
    # API configuration
    USGS_API_KEY = os.environ.get('USGS_API_KEY')
    GDACS_API_KEY = os.environ.get('GDACS_API_KEY')
    GOOGLE_MAPS_API_KEY = os.environ.get('GOOGLE_MAPS_API_KEY')
    
    # Email configuration
    MAIL_SERVER = os.environ.get('MAIL_SERVER')
    MAIL_PORT = int(os.environ.get('MAIL_PORT', 587))
    MAIL_USE_TLS = os.environ.get('MAIL_USE_TLS', 'True').lower() == 'true'
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')
    MAIL_DEFAULT_SENDER = os.environ.get('MAIL_DEFAULT_SENDER')
    
    # SMS configuration
    TWILIO_ACCOUNT_SID = os.environ.get('TWILIO_ACCOUNT_SID')
    TWILIO_AUTH_TOKEN = os.environ.get('TWILIO_AUTH_TOKEN')
    TWILIO_PHONE_NUMBER = os.environ.get('TWILIO_PHONE_NUMBER')
    
    # Logging configuration
    LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO')
    LOG_FILE = os.environ.get('LOG_FILE', 'logs/app.log')
    
    # Scraper configuration
    SCRAPE_INTERVAL = int(os.environ.get('SCRAPE_INTERVAL', 3600))  # in seconds
    
    # API rate limiting
    RATELIMIT_DEFAULT = "100/hour"
    RATELIMIT_STORAGE_URL = "memory://"
    
    # Cache configuration
    CACHE_TYPE = "SimpleCache"
    CACHE_DEFAULT_TIMEOUT = 300  # 5 minutes
    
    # Alert configuration
    VERIFICATION_THRESHOLD = 3  # Number of reports needed to verify a disaster
    MAX_ALERT_RADIUS_KM = 100  # Maximum radius for alerts in km


class DevelopmentConfig(BaseConfig):
    """Development configuration settings."""
    
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL', 'sqlite:///database.db')
    
    # Development-specific settings
    TESTING = False
    WTF_CSRF_ENABLED = True
    

class TestingConfig(BaseConfig):
    """Testing configuration settings."""
    
    DEBUG = True
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    WTF_CSRF_ENABLED = False
    PRESERVE_CONTEXT_ON_EXCEPTION = False
    

class ProductionConfig(BaseConfig):
    """Production configuration settings."""
    
    DEBUG = False
    TESTING = False
    
    # Use PostgreSQL in production
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL')
    
    # Ensure security in production
    WTF_CSRF_ENABLED = True
    SSL_REDIRECT = True
    
    # Optimize for production
    SQLALCHEMY_POOL_SIZE = 10
    SQLALCHEMY_MAX_OVERFLOW = 20
    SQLALCHEMY_POOL_TIMEOUT = 30
    SQLALCHEMY_POOL_RECYCLE = 1800
    
    # Production mail settings
    MAIL_USE_TLS = True
    
    # Aggressive cache settings for production
    CACHE_DEFAULT_TIMEOUT = 600  # 10 minutes
    
    # Logging (more restrictive in production)
    LOG_LEVEL = "ERROR"
    
    # Enforce HTTPS
    SESSION_COOKIE_SECURE = True
    REMEMBER_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True


# Dictionary to map environment names to config classes
config = {
    'development': DevelopmentConfig,
    'testing': TestingConfig,
    'production': ProductionConfig,
    
    # Default to dev config
    'default': DevelopmentConfig
}

def get_config(config_name):
    """Helper function to get configuration by name."""
    return config.get(config_name, config['default'])