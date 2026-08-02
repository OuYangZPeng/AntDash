"""AntDash (蚂蚁闪达) FastAPI application entrypoint."""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api import admin, auth, dispatch, geo, orders, proof, wallet, ws
from .config import get_settings
from .database import init_db
from .services.escalation import run_sweeper
from .services.notifications import get_hub


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    # Bind the running loop so sync endpoints can push to WebSocket clients.
    get_hub().bind_loop(asyncio.get_running_loop())
    # Background escalation/rescue sweeper for near-timeout unaccepted bundles.
    sweeper = asyncio.create_task(run_sweeper())
    yield
    sweeper.cancel()


settings = get_settings()
app = FastAPI(title=f"{settings.app_name} ({settings.app_name_cn})", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(orders.router)
app.include_router(dispatch.router)
app.include_router(proof.router)
app.include_router(wallet.router)
app.include_router(admin.router)
app.include_router(geo.router)
app.include_router(ws.router)


@app.get("/health")
def health():
    return {"status": "ok", "app": settings.app_name, "app_cn": settings.app_name_cn}
