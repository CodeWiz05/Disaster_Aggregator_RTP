# app/models.py
from datetime import datetime, timezone
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin
from flask import current_app
from app import db, login # login is needed for the user_loader

# Optional: If using PostGIS for better location querying
# from geoalchemy2 import Geometry

class Disaster(db.Model):
    __tablename__ = 'disaster'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    disaster_type = db.Column(db.String(64), index=True, nullable=False)
    status = db.Column(db.String(32), index=True, default='active')
    start_time = db.Column(db.DateTime(timezone=True), index=True, nullable=False)
    last_updated = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    latitude = db.Column(db.Float, nullable=True)
    longitude = db.Column(db.Float, nullable=True)
    # location_geo = db.Column(Geometry(geometry_type='POINT', srid=4326), index=True) # PostGIS example
    severity = db.Column(db.Integer, index=True, nullable=True)
    report_count = db.Column(db.Integer, default=0)

    reports = db.relationship('DisasterReport', back_populates='disaster', lazy='dynamic', cascade="all, delete-orphan")

    def __repr__(self):
        return f'<Disaster {self.id}: {self.title} ({self.status})>'

    def to_summary_dict(self):
         return {
            'event_id': self.id,
            'title': self.title,
            'type': self.disaster_type,
            'status': self.status,
            'start_time': self.start_time.isoformat() if self.start_time else None,
            'last_updated': self.last_updated.isoformat() if self.last_updated else None,
            'lat': self.latitude,
            'lng': self.longitude,
            'severity': self.severity,
            'report_count': self.report_count
        }


class DisasterReport(db.Model):
    __tablename__ = 'disaster_report'
    id = db.Column(db.Integer, primary_key=True)
    source_event_id = db.Column(db.String(140), index=True, nullable=True)
    title = db.Column(db.String(200))
    description = db.Column(db.Text, nullable=True)
    disaster_type = db.Column(db.String(64), index=True, nullable=False)
    latitude = db.Column(db.Float, nullable=False)
    longitude = db.Column(db.Float, nullable=False)
    timestamp = db.Column(db.DateTime(timezone=True), index=True, nullable=False, default=lambda: datetime.now(timezone.utc))
    severity = db.Column(db.Integer, nullable=True)
    verified = db.Column(db.Boolean, default=False, index=True)
    source = db.Column(db.String(64), index=True, nullable=False) # e.g., USGS, GDACS, UserReport
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True, index=True)
    depth_km = db.Column(db.Float, nullable=True)
    magnitude = db.Column(db.Float, nullable=True)

    disaster_id = db.Column(db.Integer, db.ForeignKey('disaster.id'), nullable=True, index=True)

    # --- NEW STATUS FIELD ---
    # Possible values: 'pending', 'verified_agg', 'rejected', 'spam', 'api_verified' (for API sources)
    status = db.Column(db.String(32), default='pending', index=True, nullable=False)
    # -----------------------


    disaster = db.relationship('Disaster', back_populates='reports')
    author = db.relationship('User', back_populates='reports')

    def __repr__(self):
        # Use status field in repr for better clarity
        return f'<Report {self.id}: {self.title} ({self.source} - {self.status})>'

    def to_dict(self):
        ts_iso = None
        if self.timestamp:
            try:
                # Ensure the timestamp is treated as UTC and formatted correctly
                # If stored correctly as DateTime(timezone=True), it should have tzinfo
                if self.timestamp.tzinfo is None:
                     # If somehow timezone info was lost, assume UTC
                     ts_utc = self.timestamp.replace(tzinfo=timezone.utc)
                else:
                     # Convert to UTC just to be sure before formatting
                     ts_utc = self.timestamp.astimezone(timezone.utc)

                # Format as ISO 8601 with 'Z' for UTC
                ts_iso = ts_utc.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'
                # Or simpler if microseconds aren't critical and stored value IS UTC:
                # ts_iso = self.timestamp.strftime('%Y-%m-%dT%H:%M:%SZ')

            except Exception as e:
                 # Log error if formatting fails
                 current_app.logger.warning(f"Could not format timestamp for report {self.id}: {e}")
                 pass # Leave as None
        return {
            'id': self.id,
            'type': self.disaster_type,
            'title': self.title,
            'description': self.description,
            'lat': self.latitude,
            'lng': self.longitude,
            'timestamp': ts_iso,
            'severity': self.severity,
            'verified': self.verified,
            'source': self.source,
            'magnitude': self.magnitude,
            'depth_km': self.depth_km,
            'user_id': self.user_id,
            'disaster_event_id': self.disaster_id,
            'status': self.status # Add status to the dictionary
        }


class User(UserMixin, db.Model):
    __tablename__ = 'user'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), index=True, unique=True, nullable=False)
    email = db.Column(db.String(120), index=True, unique=True, nullable=False)
    password_hash = db.Column(db.String(256))
    role = db.Column(db.String(10), default='user', nullable=False) # 'user' or 'admin'

    reports = db.relationship('DisasterReport', back_populates='author', lazy='dynamic')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        # Handle cases where password_hash might be None initially
        if self.password_hash is None:
            return False
        return check_password_hash(self.password_hash, password)

    @property
    def is_admin(self):
        return self.role == 'admin'

    def __repr__(self):
        return f'<User {self.username} ({self.role})>'


# Flask-Login user loader callback
@login.user_loader
def load_user(id):
    # Use db.session.get for optimized primary key lookup
    try:
      user_id = int(id)
      return db.session.get(User, user_id)
    except (ValueError, TypeError):
      return None