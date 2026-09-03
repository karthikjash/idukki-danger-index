# Idukki Monsoon Danger Index — API Reference

## Overview

The Idukki Monsoon Danger Index API is a RESTful service built with FastAPI that provides programmatic access to:
- Real-time Danger Indices for all inner-Idukki localities
- Historical incident data
- Interactive maps (HTML)
- Summary statistics

**Base URL (local):** `http://localhost:8000`

---

## Quick Start

### Start the API Server

```bash
cd /home/homie/Projects/SSR_system
python3 api/server.py
```

Server runs at `http://localhost:8000` with automatic startup on port 8000.

### Interactive API Documentation

- **Swagger UI:** `http://localhost:8000/docs` (try endpoints here)
- **ReDoc:** `http://localhost:8000/redoc` (alternative docs)

---

## Endpoints

### 1. Root / Info

**Endpoint:**
```
GET /
```

**Response:** HTML page with API info and quick links

**Example:**
```bash
curl http://localhost:8000/
```

---

### 2. Health Check

**Endpoint:**
```
GET /health
```

**Response:**
```json
{
  "status": "healthy",
  "last_update": "2026-09-01T21:57:00",
  "localities_computed": 7,
  "incidents_loaded": 5
}
```

**Example:**
```bash
curl http://localhost:8000/health | jq
```

---

### 3. List All Localities

**Endpoint:**
```
GET /localities
```

**Response:**
```json
{
  "localities": [
    "Adimali",
    "Idukki",
    "Kattappana",
    "Kumily",
    "Munnar",
    "Nedumkandam",
    "Peermedu"
  ],
  "count": 7
}
```

**Example:**
```bash
curl http://localhost:8000/localities | jq
```

---

### 4. Get All Danger Indices

**Endpoint:**
```
GET /index
```

**Response:**
```json
[
  {
    "locality": "Kumily",
    "tier": "High",
    "composite_score": 0.67,
    "sub_scores": {
      "environmental_severity": 0.58,
      "structural_risk": 0.83,
      "human_threat_level": 0.60
    },
    "color": "#e74c3c",
    "description": "Current risk is HIGH. Very heavy rainfall and strong winds expected...",
    "timestamp": "2026-09-01T21:57:00.123456",
    "latitude": 9.655,
    "longitude": 76.775
  },
  ...
]
```

**Example:**
```bash
curl http://localhost:8000/index | jq
```

**Filter by tier (requires custom implementation):**
```bash
curl http://localhost:8000/index | jq '.[] | select(.tier == "Extreme")'
```

---

### 5. Get Single Locality Index

**Endpoint:**
```
GET /index/{locality}
```

**Parameters:**
- `locality` (path, required): Locality name (e.g., "Kumily", "Peermedu")

**Response:**
```json
{
  "locality": "Kumily",
  "tier": "High",
  "composite_score": 0.67,
  "sub_scores": {
    "environmental_severity": 0.58,
    "structural_risk": 0.83,
    "human_threat_level": 0.60
  },
  "color": "#e74c3c",
  "description": "Current risk is HIGH...",
  "timestamp": "2026-09-01T21:57:00.123456",
  "latitude": 9.655,
  "longitude": 76.775
}
```

**Example:**
```bash
# Get index for Kumily
curl http://localhost:8000/index/Kumily | jq

# Get only the tier
curl http://localhost:8000/index/Kumily | jq '.tier'

# Get composite score
curl http://localhost:8000/index/Kumily | jq '.composite_score'
```

**Error Response (locality not found):**
```json
{
  "detail": "Locality 'InvalidName' not found"
}
```

---

### 6. Get Historical Incidents

**Endpoint:**
```
GET /incidents
```

**Response:**
```json
[
  {
    "latitude": 9.655,
    "longitude": 76.775,
    "incident_type": "landslide",
    "year": 2018,
    "severity": "high",
    "location": "Near Kumily",
    "description": "Landslide during heavy monsoon"
  },
  {
    "latitude": 9.545,
    "longitude": 76.615,
    "incident_type": "flood",
    "year": 2019,
    "severity": "extreme",
    "location": "Peermedu Region",
    "description": "Flash floods in Peermedu panchayat"
  },
  ...
]
```

**Example:**
```bash
# Get all incidents
curl http://localhost:8000/incidents | jq

# Filter by incident type
curl http://localhost:8000/incidents | jq '.[] | select(.incident_type == "landslide")'

# Filter by severity
curl http://localhost:8000/incidents | jq '.[] | select(.severity == "extreme")'

# Count by type
curl http://localhost:8000/incidents | jq 'group_by(.incident_type) | map({type: .[0].incident_type, count: length})'
```

---

### 7. Get Interactive Map

**Endpoint:**
```
GET /map
```

**Response:** HTML (Folium map)

**Example:**
```bash
# Download and open in browser
curl http://localhost:8000/map > /tmp/map.html
open /tmp/map.html

# Or in your browser:
# http://localhost:8000/map
```

**Features:**
- Colour-coded danger zones for each locality
- Toggleable historical incident layer
- Interactive legend
- Zoom and pan controls

---

### 8. Get Summary Statistics

**Endpoint:**
```
GET /summary
```

**Response:**
```json
{
  "total_localities": 7,
  "tier_breakdown": {
    "Low": 0,
    "Moderate": 0,
    "High": 4,
    "Extreme": 3
  },
  "average_danger_score": 0.72,
  "last_computed": "2026-09-01T21:57:00.123456",
  "status": "OK"
}
```

**Example:**
```bash
curl http://localhost:8000/summary | jq

# Get only extreme count
curl http://localhost:8000/summary | jq '.tier_breakdown.Extreme'

# Get average score
curl http://localhost:8000/summary | jq '.average_danger_score'
```

---

## Common Use Cases

### 1. Government Alert System Integration

**Trigger SMS warnings when tier ≥ High:**

```bash
#!/bin/bash
# Check for high-risk areas every 30 minutes

ENDPOINT="http://localhost:8000/index"

while true; do
  EXTREME_COUNT=$(curl -s $ENDPOINT | jq '[.[] | select(.tier == "Extreme")] | length')
  
  if [ "$EXTREME_COUNT" -gt 0 ]; then
    # Trigger SMS alert
    echo "EXTREME risk in $EXTREME_COUNT localities"
    # send_sms_alert "EXTREME MONSOON RISK in Inner Idukki. Call 1077 for help."
  fi
  
  sleep 1800  # 30 minutes
done
```

### 2. Dashboard Display

**Fetch and display all current tiers:**

```bash
curl http://localhost:8000/index | jq '.[] | "\(.locality): \(.tier)"'
```

Output:
```
"Kumily: High"
"Peermedu: Extreme"
"Idukki: High"
...
```

### 3. Emergency Operations

**Find all locations at Extreme risk:**

```bash
curl http://localhost:8000/index | jq '.[] | select(.tier == "Extreme") | {locality, description}'
```

### 4. Data Export

**Export all data to CSV:**

```bash
curl http://localhost:8000/index | jq -r '.[] | [.locality, .tier, .composite_score, .environmental_severity] | @csv' > danger_index.csv
```

### 5. Monitor Specific Locality

**Watch one locality:**

```bash
watch -n 300 'curl -s http://localhost:8000/index/Kumily | jq ".tier, .composite_score"'
```

---

## Response Codes

| Code | Meaning |
|------|---------|
| 200 | Success |
| 404 | Locality not found |
| 500 | Server error (data computation failed) |

---

## Data Format Details

### Danger Tier Values
- `"Low"` — Safe
- `"Moderate"` — Caution
- `"High"` — Danger
- `"Extreme"` — Severe danger

### Incident Types
- `"landslide"` — Landslide event
- `"flood"` — Flooding event
- `"dam"` — Dam-related incident
- `"debris"` — Debris flow

### Severity Levels
- `"low"` — Minor impact
- `"moderate"` — Moderate impact
- `"high"` — Significant impact
- `"extreme"` — Catastrophic impact

### Sub-Score Ranges
All sub-scores and composite scores are normalized 0–1:
- `0.0–0.25` — Low
- `0.25–0.50` — Moderate
- `0.50–0.75` — High
- `0.75–1.0` — Extreme

---

## Authentication & Rate Limiting

**Current Implementation:**
- No authentication required (local use)
- No rate limiting (can be added for production)

**For production deployment**, add:
- API key authentication
- Rate limiting per IP/key
- HTTPS/TLS encryption

---

## Error Handling

**Invalid Locality:**
```bash
curl http://localhost:8000/index/InvalidName
```

Response (HTTP 404):
```json
{
  "detail": "Locality 'InvalidName' not found"
}
```

**Server Error:**
If data computation fails, endpoint returns HTTP 500 with error details.

---

## Deployment Notes

### Docker Deployment

```dockerfile
FROM python:3.9
WORKDIR /app
COPY . .
RUN pip install -r requirements.txt
CMD ["python3", "api/server.py"]
```

```bash
docker build -t idukki-api .
docker run -p 8000:8000 idukki-api
```

### Production Settings

Modify `api/server.py` before deployment:

```python
if __name__ == "__main__":
    uvicorn.run(
        app,
        host="0.0.0.0",      # Listen on all interfaces
        port=8000,
        workers=4,           # Multiple worker processes
        log_level="info",
        ssl_keyfile="/path/to/key.pem",
        ssl_certfile="/path/to/cert.pem"
    )
```

---

## Integration Examples

### Python

```python
import requests

# Get all indices
response = requests.get("http://localhost:8000/index")
indices = response.json()

for locality in indices:
    print(f"{locality['locality']}: {locality['tier']}")
```

### JavaScript/Node.js

```javascript
fetch('http://localhost:8000/index')
  .then(res => res.json())
  .then(data => {
    data.forEach(loc => {
      console.log(`${loc.locality}: ${loc.tier}`);
    });
  });
```

### Bash/curl

```bash
curl http://localhost:8000/index | jq '.[] | {locality: .locality, tier: .tier}'
```

---

## Support & Issues

- **API Docs (Interactive):** `http://localhost:8000/docs`
- **Code:** `/api/server.py`
- **Configuration:** See `index/calculator.py` for weighting and threshold tuning

---

**API Version:** 1.0  
**Last Updated:** September 2026  
**Framework:** FastAPI / Uvicorn
