import os

import sentry_sdk
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routers import outfit_suggestions, suggestion_rails, wardrobe

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))

# SS-009: kept as a module constant (rather than the design doc's literal
# `f'stylesense-backend@{app.version}'`) because `app` is constructed below
# this sentry_sdk.init() call -- referencing it here would be a NameError.
# Same value as FastAPI(version=...) below, single source of truth.
APP_VERSION = "0.1.0"

sentry_dsn = os.getenv("SENTRY_DSN_BACKEND")
if sentry_dsn:
    sentry_sdk.init(
        dsn=sentry_dsn,
        traces_sample_rate=0.1,
        environment=os.getenv("ENVIRONMENT", "development"),
        release=f"stylesense-backend@{APP_VERSION}",
    )

app = FastAPI(title="StyleSense API", version=APP_VERSION)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(outfit_suggestions.router)
app.include_router(wardrobe.router)
app.include_router(suggestion_rails.router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "version": APP_VERSION}
