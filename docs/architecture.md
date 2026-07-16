# Architecture

## Android

The Android client uses a single `app` module with MVVM:

```text
Compose Screen
-> ViewModel
-> Repository
-> Retrofit ApiService
-> FastAPI
```

Dependencies are assembled with `AiTravelApplication` and `AppContainer`. This keeps the first stage easy to read and test without introducing Hilt before the app needs it.

Main packages:

- `data/model`: DTOs shared by Retrofit and repositories
- `data/remote`: Retrofit service and client creation
- `data/repository`: app-facing data interfaces and implementations
- `di`: lightweight dependency container
- `navigation`: single NavHost and bottom tabs
- `ui/home`: health-check screen and state
- `ui/itinerary`, `ui/discover`, `ui/profile`: first-level placeholders
- `ui/theme`: travel-themed Material color scheme

`BuildConfig.API_BASE_URL` controls the backend address. Debug uses the emulator host alias `http://10.0.2.2:8000/`. Release uses a non-routable placeholder and keeps cleartext HTTP disabled.

## Backend

The backend uses a small FastAPI layout:

```text
app/main.py
app/api/
app/core/
app/schemas/
app/services/
tests/
```

Settings are centralized in `core/config.py`. Local CORS origins exist for browser-based development tools; native Android calls do not rely on browser CORS.

## Future Boundaries

- Login: add auth APIs, token storage, and guarded screens.
- AI planning: keep model providers behind a backend service boundary.
- Maps: keep map SDK keys outside source control and wrap location/map calls.
- Guide import: parse and normalize imported content server-side.
- Membership and orders: isolate payment and order state from itinerary editing.
- Booking: treat third-party travel APIs as adapters, not direct UI dependencies.

