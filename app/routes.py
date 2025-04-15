from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash
from app.models import DisasterReport
from app import db
import json
import os

main_bp = Blueprint('main', __name__)

@main_bp.route('/')
def index():
    """Homepage with map and disaster data"""
    return render_template('index.html', title='Disaster Tracker')

@main_bp.route('/report', methods=['GET', 'POST'])
def report():
    """Submit a disaster report"""
    if request.method == 'POST':
        # Handle form submission logic here
        flash('Report submitted successfully! Under review.', 'success')
        return redirect(url_for('main.index'))
    return render_template('report_form.html', title='Submit Report')

@main_bp.route('/verify')
def verify():
    """Admin panel for verifying user reports"""
    return render_template('verify_panel.html', title='Verify Reports')

@main_bp.route('/history')
def history():
    """Historical disaster data and analytics"""
    return render_template('history.html', title='Historical Data')

@main_bp.route('/api/disasters')
def get_disasters():
    """API endpoint to get disaster data for the map"""
    data_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'cached_reports.json')
    with open(data_file, 'r') as f:
        disasters = json.load(f)
    return jsonify(disasters)
