from app import db
from datetime import datetime
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), index=True, unique=True)
    email = db.Column(db.String(120), index=True, unique=True)
    password_hash = db.Column(db.String(128))
    reports = db.relationship('DisasterReport', backref='author', lazy='dynamic')
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
        
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    def __repr__(self):
        return f'<User {self.username}>'

class DisasterReport(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    disaster_type = db.Column(db.String(64), index=True)
    title = db.Column(db.String(140))
    description = db.Column(db.Text)
    latitude = db.Column(db.Float)
    longitude = db.Column(db.Float)
    timestamp = db.Column(db.DateTime, index=True, default=datetime.utcnow)
    severity = db.Column(db.Integer)  # 1-5 scale
    verified = db.Column(db.Boolean, default=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    
    def __repr__(self):
        return f'<Report {self.title}>'
    
    def to_dict(self):
        return {
            'id': self.id,
            'type': self.disaster_type,
            'title': self.title,
            'description': self.description,
            'lat': self.latitude,
            'lng': self.longitude,
            'timestamp': self.timestamp.isoformat(),
            'severity': self.severity,
            'verified': self.verified
        }