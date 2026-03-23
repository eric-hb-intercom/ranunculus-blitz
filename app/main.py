"""FastAPI application — Ranunculus ID Blitz Tracker."""

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .config import load_settings
from .database import set_db_path, init_db, get_db
from .inat.client import close_client
from .routers import admin, events, map, observations, overview, participants, stream, teams
from .workers.snapshot import run_snapshot

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

settings = load_settings()

APP_DIR = Path(__file__).parent
templates = Jinja2Templates(directory=str(APP_DIR / "templates"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown lifecycle."""
    # Initialize database
    set_db_path(settings.db_path)
    await init_db()

    # Seed teams and participants from config
    await _seed_teams_and_participants()

    # Configure admin router
    admin.configure(settings, stream.broadcast)

    # Auto-snapshot if configured
    if settings.auto_snapshot:
        logger.info("Auto-snapshot enabled, running snapshot...")
        try:
            await run_snapshot(settings.species, settings.place_id)
        except Exception as e:
            logger.error(f"Auto-snapshot failed: {e}", exc_info=True)

    yield

    # Cleanup
    from .workers import poller
    await poller.stop_poller()
    await close_client()


app = FastAPI(title="Ranunculus Blitz Tracker", lifespan=lifespan)

# Mount static files
app.mount("/static", StaticFiles(directory=str(APP_DIR / "static")), name="static")

# Register API routers
app.include_router(overview.router)
app.include_router(participants.router)
app.include_router(observations.router)
app.include_router(events.router)
app.include_router(map.router)
app.include_router(teams.router)
app.include_router(admin.router)
app.include_router(stream.router)


# ── Page routes ──────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    return templates.TemplateResponse(request, "dashboard.html")


@app.get("/map", response_class=HTMLResponse)
async def fullscreen_map(request: Request):
    return templates.TemplateResponse(request, "map.html")


@app.get("/teams", response_class=HTMLResponse)
async def teams_page(request: Request):
    return templates.TemplateResponse(request, "teams.html")


@app.get("/observations", response_class=HTMLResponse)
async def observations_page(request: Request):
    return templates.TemplateResponse(request, "observations.html")


@app.get("/wrapup", response_class=HTMLResponse)
async def wrapup_page(request: Request):
    return templates.TemplateResponse(request, "wrapup.html")


@app.get("/admin", response_class=HTMLResponse)
async def admin_page(request: Request):
    return templates.TemplateResponse(request, "admin.html")


# ── Helpers ──────────────────────────────────────────────────────────────────

async def _seed_teams_and_participants():
    """Populate teams and participants from env config."""
    if not settings.teams:
        return

    db = await get_db()
    try:
        for team_cfg in settings.teams:
            # Upsert team
            cursor = await db.execute(
                "SELECT team_id FROM teams WHERE name = ?", (team_cfg.name,)
            )
            row = await cursor.fetchone()
            if row:
                team_id = row[0]
                await db.execute(
                    "UPDATE teams SET color = ? WHERE team_id = ?",
                    (team_cfg.color, team_id),
                )
            else:
                cursor = await db.execute(
                    "INSERT INTO teams (name, color) VALUES (?, ?)",
                    (team_cfg.name, team_cfg.color),
                )
                team_id = cursor.lastrowid

            # Add members as participants (with placeholder user_id)
            for login in team_cfg.members:
                await db.execute(
                    """INSERT OR IGNORE INTO participants (user_id, login, team_id)
                       VALUES (
                           (SELECT COALESCE(MAX(user_id), 0) + 1 FROM participants),
                           ?, ?
                       )""",
                    (login.lower(), team_id),
                )
                # Update team assignment if participant already exists
                await db.execute(
                    "UPDATE participants SET team_id = ? WHERE login = ?",
                    (team_id, login.lower()),
                )

        await db.commit()
        logger.info(f"Seeded {len(settings.teams)} teams with participants")
    finally:
        await db.close()
