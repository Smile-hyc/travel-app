# Development Plan

## Phase 1: Foundation

Status: implemented in this scaffold.

- Android + FastAPI monorepo
- Four-tab Compose shell
- Health-check API
- Home Loading / Success / Error / Retry states
- Basic tests and documentation

## Phase 2: Login And Registration

- User registration and login APIs
- Token model and secure client storage
- Login, registration, and profile entry screens
- Basic authenticated request flow

## Phase 3: Itinerary Model

- Trip and day models
- Itinerary list and detail screens
- Create, edit, delete, and local validation

## Phase 4: AI Trip Planning

- Backend provider boundary
- Prompt templates and result schema
- Draft itinerary generation

## Phase 5: Guide Import

- Import entry point
- Server-side parsing
- Structured extraction into itinerary drafts

## Phase 6: Maps

- Map SDK integration
- Place search and route preview
- Key management outside source control

## Phase 7: Collaboration And Sharing

- Share links or invitation flow
- Read-only itinerary preview
- Basic permission model

## Phase 8: Membership

- Membership state
- Feature gates
- Account entitlement display

## Phase 9: Orders And Booking

- Booking provider adapters
- Order state model
- Payment boundary and callbacks

## Phase 10: Release Hardening

- Production config
- HTTPS and deployment
- CI/CD
- Crash and analytics hooks
- Signing and release build checks

