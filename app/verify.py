"""
Verification module for disaster reports.
This module handles the verification of user-submitted disaster reports.
"""

import json
import logging
from datetime import datetime
from app.models import DisasterReport, Disaster
from app import db
from app.utils import send_notification, calculate_severity

# Setup logging
logger = logging.getLogger(__name__)

def verify_report(report_id):
    """
    Verify a user-submitted disaster report.
    
    Args:
        report_id (int): ID of the report to verify
        
    Returns:
        dict: Result of verification process
    """
    try:
        # Fetch the report from database
        report = DisasterReport.query.get(report_id)
        
        if not report:
            logger.error(f"Report ID {report_id} not found")
            return {
                'success': False, 
                'message': 'Report not found'
            }
        
        # Check if report is already verified
        if report.is_verified:
            logger.info(f"Report ID {report_id} already verified")
            return {
                'success': False, 
                'message': 'Report already verified'
            }
        
        # Perform verification checks
        verification_result = _run_verification_checks(report)
        
        if verification_result['verified']:
            # Update report status
            report.is_verified = True
            report.verified_at = datetime.utcnow()
            report.verified_by = verification_result['method']
            
            # Create a confirmed disaster entry if needed
            _create_or_update_disaster(report)
            
            # Commit changes
            db.session.commit()
            
            # Send notifications to subscribers
            send_notification(
                'disaster_verified', 
                {'disaster_id': report.disaster_id}
            )
            
            logger.info(f"Report ID {report_id} verified successfully")
            return {
                'success': True,
                'message': 'Report verified successfully',
                'method': verification_result['method']
            }
        else:
            logger.warning(f"Report ID {report_id} verification failed: {verification_result['reason']}")
            return {
                'success': False,
                'message': f"Verification failed: {verification_result['reason']}"
            }
            
    except Exception as e:
        logger.exception(f"Error verifying report ID {report_id}")
        db.session.rollback()
        return {
            'success': False,
            'message': f"Error during verification: {str(e)}"
        }

def _run_verification_checks(report):
    """Run a series of checks to verify a disaster report."""
    
    # Check 1: Cross-reference with known data sources
    external_match = _check_external_sources(report)
    if external_match['found']:
        return {
            'verified': True,
            'method': 'external_match',
            'details': external_match
        }
    
    # Check 2: Similar reports from multiple users
    multiple_reports = _check_multiple_reports(report)
    if multiple_reports['found']:
        return {
            'verified': True,
            'method': 'multiple_reports',
            'details': multiple_reports
        }
    
    # Check 3: Trusted submitter
    if report.user_id and _is_trusted_user(report.user_id):
        return {
            'verified': True,
            'method': 'trusted_user'
        }
    
    # No verification method passed
    return {
        'verified': False,
        'reason': 'Could not verify through any available method'
    }

def _check_external_sources(report):
    """Check if report matches data from official sources."""
    # In a real implementation, this would query APIs from USGS, weather services, etc.
    # For demo purposes, we'll use a simple simulation
    
    # Example implementation:
    try:
        # Get coordinates and disaster type
        lat, lng = report.latitude, report.longitude
        disaster_type = report.disaster_type
        
        # Define search radius (degrees)
        radius = 0.5  # Approximately 55km at equator
        
        # Time window (hours)
        time_window = 24
        
        # Check if we have any matching official data
        # This would be replaced with actual API calls
        
        # For demo: Simulate checking external sources
        return {
            'found': False,  # Would be True if found in official sources
            'source': None,
            'url': None
        }
        
    except Exception as e:
        logger.error(f"Error checking external sources: {str(e)}")
        return {'found': False}

def _check_multiple_reports(report):
    """Check if multiple users reported the same disaster."""
    try:
        # Define search radius (degrees)
        radius = 0.5  # Approximately 55km at equator
        
        # Time window (hours)
        time_window = 24
        
        # Find reports in the same area and time period
        similar_reports = DisasterReport.query.filter(
            DisasterReport.id != report.id,
            DisasterReport.disaster_type == report.disaster_type,
            DisasterReport.latitude.between(report.latitude - radius, report.latitude + radius),
            DisasterReport.longitude.between(report.longitude - radius, report.longitude + radius),
            DisasterReport.created_at >= report.created_at.replace(
                hour=report.created_at.hour-time_window),
            DisasterReport.is_spam == False
        ).all()
        
        # Check if we have enough similar reports
        threshold = 3  # Number of similar reports needed for verification
        
        if len(similar_reports) >= threshold:
            return {
                'found': True,
                'count': len(similar_reports),
                'reports': [r.id for r in similar_reports]
            }
        
        return {'found': False}
        
    except Exception as e:
        logger.error(f"Error checking multiple reports: {str(e)}")
        return {'found': False}

def _is_trusted_user(user_id):
    """Check if user is a trusted source."""
    # In a real implementation, check against a database of trusted sources
    # For demo purposes, we'll use a simple list
    
    # Example implementation
    trusted_users = [1, 2, 3]  # IDs of trusted users/organizations
    return user_id in trusted_users

def _create_or_update_disaster(report):
    """Create a new disaster entry or update existing one based on the report."""
    try:
        # Check if there's already a disaster in this area
        radius = 0.5  # Approximately 55km at equator
        
        existing_disaster = Disaster.query.filter(
            Disaster.type == report.disaster_type,
            Disaster.latitude.between(report.latitude - radius, report.latitude + radius),
            Disaster.longitude.between(report.longitude - radius, report.longitude + radius),
            Disaster.status != 'resolved'
        ).first()
        
        if existing_disaster:
            # Update existing disaster with new report info
            existing_disaster.report_count += 1
            existing_disaster.last_updated = datetime.utcnow()
            
            # Recalculate severity if needed
            if report.severity > existing_disaster.severity:
                existing_disaster.severity = report.severity
                
            # Link report to this disaster
            report.disaster_id = existing_disaster.id
            
        else:
            # Create new disaster
            new_disaster = Disaster(
                title=report.title,
                type=report.disaster_type,
                latitude=report.latitude,
                longitude=report.longitude,
                location=report.location,
                description=report.description,
                severity=report.severity,
                started_at=report.created_at,
                status='active',
                report_count=1
            )
            
            db.session.add(new_disaster)
            db.session.flush()  # Get ID before commit
            
            # Link report to this disaster
            report.disaster_id = new_disaster.id
            
    except Exception as e:
        logger.exception(f"Error creating/updating disaster from report: {str(e)}")
        raise

def mark_as_spam(report_id, reason=None):
    """Mark a report as spam or false."""
    try:
        report = DisasterReport.query.get(report_id)
        
        if not report:
            return {
                'success': False, 
                'message': 'Report not found'
            }
        
        report.is_spam = True
        report.spam_reason = reason
        db.session.commit()
        
        logger.info(f"Report ID {report_id} marked as spam")
        return {
            'success': True,
            'message': 'Report marked as spam'
        }
        
    except Exception as e:
        logger.exception(f"Error marking report as spam: {str(e)}")
        db.session.rollback()
        return {
            'success': False,
            'message': f"Error: {str(e)}"
        }