"""FastAPI application entry-point."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .routers import supply_chain, analysis, simulation

settings = get_settings()

app = FastAPI(
    title="Provenance API",
    version="0.1.0",
    description="Supply-chain intelligence backend for Hack Canada",
)

# CORS so the Vite dev server can reach us
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────
app.include_router(supply_chain.router, prefix="/api/supply-chain", tags=["supply-chain"])
app.include_router(analysis.router, prefix="/api/analysis", tags=["analysis"])
app.include_router(simulation.router, prefix="/api/simulation", tags=["simulation"])


@app.get("/api/health")
async def health_check():
    return {"status": "ok"}
