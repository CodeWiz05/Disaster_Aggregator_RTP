# Disaster Aggregator Platform

A comprehensive web platform for aggregating, visualizing, and reporting disaster events globally. This application integrates real-time disaster data from multiple sources, allows user-submitted reports, and provides notification capabilities.

## Features

- **Live Disaster Tracking**: View real-time disaster data on an interactive map and in tabular format
- **User Report Submission**: Submit first-hand disaster reports with location, type, severity, and media
- **Verification System**: Crowd-sourced verification of user-submitted reports
- **Multi-channel Alerts**: Receive notifications via email, SMS, and web notifications
- **Historical Data Analysis**: View and analyze past disaster events and trends
- **APIs Integration**: Data collection from USGS, GDACS, and other disaster monitoring services

## Tech Stack

- **Backend**: Flask (Python)
- **Frontend**: HTML, CSS, JavaScript
- **Database**: SQLite (Development), PostgreSQL (Production)
- **Mapping**: OpenStreetMap/Google Maps
- **Notifications**: Email service and Twilio for SMS

## Installation and Setup

### Prerequisites

- Python 3.8+
- Pip package manager
- Git

### Installation Steps

1. Clone the repository:
   ```
   git clone https://github.com/yourusername/disaster-aggregator.git
   cd disaster-aggregator
   ```

2. Create and activate a virtual environment:
   ```
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. Install dependencies:
   ```
   pip install -r requirements.txt
   ```

4. Set up environment variables:
   - Copy `.env.example` to `.env`
   - Update the variables in `.env` with your API keys and configuration

5. Initialize the database:
   ```
   flask db init
   flask db migrate -m "Initial migration"
   flask db upgrade
   ```

6. Run the application:
   ```
   python run.py
   ```

7. Access the application at `http://localhost:5000`

## Project Structure

```
disaster-aggregator/
├── app/                  # Application package
│   ├── __init__.py       # Application factory
│   ├── routes.py         # URL routes and views
│   ├── scraper.py        # Disaster data scraper
│   ├── fetch_api.py      # API integration client
│   ├── verify.py         # Report verification logic
│   ├── utils.py          # Utility functions
│   └── models.py         # Database models
├── templates/            # HTML templates
├── static/               # Static files (CSS, JS, images)
├── data/                 # Data files
├── migrations/           # Database migrations
├── requirements.txt      # Python dependencies
├── .env                  # Environment variables
├── config.py             # Configuration settings
├── run.py                # Application entry point
└── database.db           # SQLite database file
```

## API Documentation

The platform provides RESTful APIs to access disaster data:

- `GET /api/disasters`: List all disasters
- `GET /api/disasters/{id}`: Get details of a specific disaster
- `POST /api/reports`: Submit a new disaster report
- `GET /api/reports/verified`: Get verified user reports

See full API documentation in the `/docs` endpoint when running the application.

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add some amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Acknowledgments

- Data sources: USGS, GDACS, ReliefWeb
- OpenStreetMap/Google Maps for mapping capabilities
- Twilio for SMS alert functionality