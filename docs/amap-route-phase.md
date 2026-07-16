# AMap Route Phase

This phase upgrades the travel plan detail page from a static overview to a real route-planning workflow.

## Data flow

```text
Explore real AMap POI
-> add to Android in-memory TravelPlan Day 1
-> PlanDetailViewModel
-> RemoteRouteRepository
-> FastAPI /api/routes/*
-> AMap Web route service
-> route polyline, distance, duration
-> Android AMap detail map
```

## Implemented boundaries

- Android stores selected POIs as `PlanItem` snapshots with AMap POI id, address, city metadata, and coordinates.
- FastAPI owns the AMap Web Service key and exposes route proxy endpoints.
- The detail page renders numbered markers, route polylines, day tabs, route mode switching, and optimization preview/apply.
- Optimization is deterministic: exact ordering for small groups, lightweight nearest-neighbor plus local improvement for larger day plans.

## Current limitations

- Travel plans are still in-memory and reset after app restart.
- Route quality depends on the configured AMap Web Service key and enabled route services.
- AI is intentionally not used for route ordering yet; it can later explain, personalize, or adjust the deterministic result.
- No real-time navigation, live location tracking, hotel/ticket/order, or social-content APIs are included in this phase.

## Manual verification

1. Start FastAPI with `backend/.env` containing `AMAP_WEB_SERVICE_KEY`.
2. Open the Android app and go to Explore.
3. Add at least two real POIs to the current plan.
4. Open the plan detail page.
5. Confirm numbered markers and route lines appear.
6. Switch walking/driving/cycling/transit and retry if the key lacks a specific route permission.
7. Add at least three places and test route optimization preview, apply, and cancel.
