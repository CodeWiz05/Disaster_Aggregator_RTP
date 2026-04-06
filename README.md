# 🌍 DisasterTrack — Real-Time Multi-Source Data Ingestion Platform

A production-style data pipeline designed to ingest, process, and serve real-time geospatial disaster data from multiple authoritative sources.

---

## 🚀 Overview

DisasterTrack is a **backend-first data engineering system** that aggregates disaster events from APIs such as:

- USGS (Earthquakes)
- NASA FIRMS (Wildfires)
- NOAA/NWS (Weather Alerts)

The platform focuses on **reliable ingestion, deduplication, and structured data transformation**, enabling downstream analytics, visualization, and alerting systems.

---

## 🧠 System Design

### Core Pipeline
External APIs → Async Fetchers → Validation & Deduplication → DB Storage → API Layer

### Key Characteristics

- **Asynchronous ingestion pipeline** using `httpx.AsyncClient`
- **Concurrent multi-source data fetching** via `asyncio.gather`
- **Near real-time processing** using time-window filtering
- **Fault-tolerant architecture** with retry & exponential backoff
- **Database-level deduplication constraints**
- **Structured transformation into normalized schema**

---

## ⚙️ Tech Stack

### Backend
- Python (Flask)
- PostgreSQL / SQLite
- SQLAlchemy ORM

### Data Engineering
- Async IO (`asyncio`, `httpx`)
- REST API ingestion
- Geospatial processing (Shapely)

### Infrastructure
- Docker (containerization-ready)
- GitHub Actions (CI/CD basics)

---

## 🔥 Key Engineering Highlights

### 1. Multi-Source Async Ingestion
- Concurrently ingests data from multiple APIs
- Reduces latency using parallel fetch execution

### 2. Fault-Tolerant Fetching
- Implemented retry mechanisms with exponential backoff
- Handles network failures and API instability gracefully

### 3. Deduplication Strategy
- Application-level deduplication using `source_event_id`
- Enforced **database-level uniqueness constraints**
- Prevents duplicate entries across streaming batches

### 4. Near Real-Time Processing
- Time-window filtering ensures only recent events are processed
- Simulates streaming-style ingestion behavior

### 5. Pipeline Observability
- Structured logging across ingestion stages
- Tracks:
  - ingestion counts
  - processing latency
  - throughput (records/sec)

### 6. Optimized Data Retrieval
- SQL window functions used to fetch **top-N events per category**
- Efficient query design for large datasets

---

## 📊 Data Flow

1. Fetch disaster data asynchronously from external APIs  
2. Validate schema and discard malformed records  
3. Apply deduplication (DB + in-memory checks)  
4. Transform into normalized `DisasterReport` schema  
5. Store in database with relational linkage  
6. Serve via optimized API endpoints  

---

## 📡 API Endpoints

### Get Latest Disaster Events
GET /api/disasters

Returns top-N recent events per disaster type using optimized SQL queries.

---

### Historical Data
GET /api/history/reports

Supports:
- date range filtering
- severity filtering
- pagination

---

### User Reports
POST /api/reports

Allows crowd-sourced disaster reporting with moderation workflow.

---

## 🏗️ Project Structure
app/
├── fetch_api.py # Async ingestion pipeline
├── models.py # Database schema
├── routes.py # API endpoints
├── verify.py # (Reserved for advanced verification logic)
├── utils.py # Helper utilities


---

## ⚠️ Notes on Design Choices

- The system prioritizes **data reliability over raw ingestion volume**
- Designed as a **pipeline-first architecture**, not UI-first
- Built to simulate **real-world data engineering workflows**

---

## 🚧 Future Improvements

- Streaming integration (Kafka / event-driven architecture)
- Distributed processing for large-scale ingestion
- ML-based anomaly detection on disaster patterns
- Real-time alerting system

---

## 💡 Why This Project

This project was built to explore:

- real-world data ingestion challenges  
- building reliable backend pipelines  
- handling noisy, inconsistent external data sources  
- designing scalable data systems  

---

## 📜 License

MIT License