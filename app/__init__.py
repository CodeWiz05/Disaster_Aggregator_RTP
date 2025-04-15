import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_cors import CORS

# Initialize extensions
db = SQLAlchemy()
migrate = Migrate()

def create_app(config_name=None):
    # Create and configure the app
    app = Flask(__name__, 
                static_folder='../static', 
                template_folder='../templates')
    
    # Load configuration
    if config_name is None:
        config_name = os.environ.get('FLASK_CONFIG', 'development')
    
    app.config.from_object(f'config.{config_name.capitalize()}Config')
    
    # Enable CORS
    CORS(app)
    
    # Initialize extensions with app
    db.init_app(app)
    migrate.init_app(app, db)
    
    # Register blueprints
    from app.routes import main_bp
    app.register_blueprint(main_bp)
    
    # Create database tables if they don't exist
    with app.app_context():
        db.create_all()
    
    # Setup error handlers
    register_error_handlers(app)
    
    return app

def register_error_handlers(app):
    @app.errorhandler(404)
    def page_not_found(e):
        from flask import render_template
        return render_template('error.html', 
                              error_code=404, 
                              error_message='Page not found'), 404

    @app.errorhandler(500)
    def internal_server_error(e):
        from flask import render_template
        return render_template('error.html', 
                              error_code=500, 
                              error_message='Internal server error'), 500