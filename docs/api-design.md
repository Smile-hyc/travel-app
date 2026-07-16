# API Design

Base URL during Android emulator development:

```text
http://10.0.2.2:8000/
```

Local host URL:

```text
http://127.0.0.1:8000/
```

## Implemented

### GET /

Response:

```json
{
  "message": "Welcome to AI Travel API"
}
```

### GET /api/health

Response:

```json
{
  "code": 200,
  "message": "AI Travel backend is running",
  "status": "ok"
}
```

Android `HealthResponse` must stay aligned with these fields.

## Not Implemented

The following areas are planned but intentionally not built in phase one:

- Authentication and user profile APIs
- Itinerary CRUD APIs
- AI trip planning APIs
- Guide import APIs
- Map and location APIs
- Membership, order, booking, and payment APIs

