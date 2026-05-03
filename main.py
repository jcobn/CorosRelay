import logging
logging.basicConfig(level=logging.INFO, format="%(name)s: %(message)s")

from fastapi import FastAPI, Request, Form, HTTPException, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
import os
from datetime import datetime, timedelta
from typing import Optional

import coros_client as coros

# ------------------------------------------------------------------
# App init
# ------------------------------------------------------------------
app = FastAPI(title="CorosRelay")
# Use a stable secret key so sessions survive server restarts.
# In production, set COROS_SESSION_SECRET in your environment.
SESSION_SECRET = os.environ.get("COROS_SESSION_SECRET", "corosrelay-dev-secret-key-change-me")
app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET, max_age=86400 * 7)
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# Pre-compute next 14 days for template dropdowns
_next_14 = []
_now = datetime.now()
for i in range(14):
    d = _now + timedelta(days=i)
    _next_14.append({"ymd": d.strftime("%Y%m%d"), "label": d.strftime("%a %d %b")})
app.state.next_14_days = _next_14

# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------
def _today() -> str:
    return datetime.now().strftime("%Y%m%d")

def _week_bounds(offset: int = 0) -> tuple[str, str]:
    """Return (monday, sunday) for week offset from current week."""
    now = datetime.now()
    # Find Monday of current week
    monday = now - timedelta(days=now.weekday()) + timedelta(weeks=offset)
    sunday = monday + timedelta(days=6)
    return monday.strftime("%Y%m%d"), sunday.strftime("%Y%m%d")

def _fmt_day(yyyymmdd: str) -> str:
    d = datetime.strptime(yyyymmdd, "%Y%m%d")
    return d.strftime("%a %d %b")

def _sport_emoji(sport_type: Optional[int]) -> str:
    mapping = {
        1: "🏃",   # Run
        2: "🚴",   # Indoor cycling
        3: "🏊",   # Swim
        4: "🏋️",   # Strength
        5: "🎿",   # Ski
        6: "🏂",   # Snowboard
        7: "⛷️",   # Cross-country ski
        8: "🏄",   # Surf / windsurf
        9: "🚣",   # Row
        10: "🧗",  # Climb
        11: "🚶",  # Walk
        12: "🧘",  # Yoga
        13: "⛸️",  # Skate
        14: "🏈",  # Football
        15: "🏀",  # Basketball
        16: "🎾",  # Tennis
        17: "🤺",  # Fencing
        18: "🏓",  # Table tennis
        19: "🏸",  # Badminton
        20: "⚽",  # Soccer
        21: "🥊",  # Boxing
        22: "🤸",  # Gymnastics
        23: "🛹",  # Skateboard
        24: "🚵",  # MTB
        25: "🚲",  # Bike
        26: "🛶",  # Kayak
        27: "🪂",  # Parachute
        28: "🏇",  # Horse
        29: "🚙",  # Drive
        30: "🏍️",  # Motorcycle
        200: "🚴", # Road bike
        201: "🚴", # Indoor cycling alt
    }
    return mapping.get(sport_type or 0, "🏋️")

async def _get_auth(request: Request) -> coros.AuthState:
    """Reconstruct AuthState from session or raise."""
    token = request.session.get("coros_token")
    uid = request.session.get("coros_user_id")
    region = request.session.get("coros_region", "eu")
    ts = request.session.get("coros_ts")
    if not token or not uid:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return coros.AuthState(
        access_token=token,
        user_id=uid,
        region=region,
        timestamp_ms=ts or 0,
    )

# ------------------------------------------------------------------
# Routes
# ------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    if request.session.get("coros_token"):
        return RedirectResponse(url="/dashboard")
    return RedirectResponse(url="/login")

@app.get("/demo", response_class=HTMLResponse)
async def demo_dashboard(request: Request, week_offset: int = 0):
    """Demo view with synthetic data — no COROS login required."""
    start_day, end_day = _week_bounds(week_offset)
    monday = datetime.strptime(start_day, "%Y%m%d")

    # Synthetic workout library for dropdowns
    demo_workouts = [
        {"id": "w1", "name": "Z2 Easy Run 30min", "sport_type": 1},
        {"id": "w2", "name": "Z2 Easy Run 45min", "sport_type": 1},
        {"id": "w3", "name": "Z2 Easy Run 60min", "sport_type": 1},
        {"id": "w4", "name": "Tempo Run 40min", "sport_type": 1},
        {"id": "w5", "name": "Interval Run", "sport_type": 1},
        {"id": "w6", "name": "Z2 Indoor Bike 60min", "sport_type": 2},
        {"id": "w7", "name": "Sweet Spot 90min", "sport_type": 2},
        {"id": "w8", "name": "MTB Easy 90min", "sport_type": 24},
        {"id": "w9", "name": "MTB Hard 2h", "sport_type": 24},
        {"id": "w10", "name": "Strength Full Body", "sport_type": 4},
        {"id": "w11", "name": "Strength Upper", "sport_type": 4},
        {"id": "w12", "name": "Strength Lower", "sport_type": 4},
        {"id": "w13", "name": "Yoga / Mobility", "sport_type": 12},
    ]

    # Synthetic scheduled items — a realistic athlete week
    _items = []
    for i in range(7):
        d = monday + timedelta(days=i)
        ymd = d.strftime("%Y%m%d")
        # Hardcode some realistic training
        if i == 0:  # Monday
            _items.append({"happenDay": ymd, "name": "Z2 Easy Run 45min", "sportType": 1, "sportName": "Run", "estimatedTime": 2700, "id": "p1", "idInPlan": "ip1"})
            _items.append({"happenDay": ymd, "name": "Strength Upper", "sportType": 4, "sportName": "Strength", "estimatedTime": 1800, "id": "p2", "idInPlan": "ip2"})
        elif i == 1:  # Tuesday
            _items.append({"happenDay": ymd, "name": "Z2 Indoor Bike 60min", "sportType": 2, "sportName": "Indoor Cycling", "estimatedTime": 3600, "id": "p3", "idInPlan": "ip3"})
        elif i == 3:  # Thursday
            _items.append({"happenDay": ymd, "name": "Tempo Run 40min", "sportType": 1, "sportName": "Run", "estimatedTime": 2400, "id": "p4", "idInPlan": "ip4"})
        elif i == 5:  # Saturday
            _items.append({"happenDay": ymd, "name": "MTB Hard 2h", "sportType": 24, "sportName": "MTB", "estimatedTime": 7200, "id": "p5", "idInPlan": "ip5"})
        elif i == 6:  # Sunday
            _items.append({"happenDay": ymd, "name": "Yoga / Mobility", "sportType": 12, "sportName": "Yoga", "estimatedTime": 1800, "id": "p6", "idInPlan": "ip6"})

    days = []
    for i in range(7):
        d = monday + timedelta(days=i)
        ymd = d.strftime("%Y%m%d")
        day_items = [it for it in _items if it.get("happenDay") == ymd]
        days.append({
            "date": ymd,
            "label": d.strftime("%a %d"),
            "is_today": ymd == _today(),
            "workouts": day_items,
        })

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "days": days,
        "workouts": demo_workouts,
        "week_label": f"{monday.strftime('%d %b')} – {(monday + timedelta(days=6)).strftime('%d %b %Y')}",
        "week_offset": week_offset,
        "prev_week": week_offset - 1,
        "next_week": week_offset + 1,
        "sport_emoji": _sport_emoji,
        "fmt_day": _fmt_day,
    })

@app.get("/demo/templates", response_class=HTMLResponse)
async def demo_templates(request: Request):
    auth = None  # no auth needed
    tpls = [
        {"name": "Z2 Easy Run 30min", "sport_type": 1, "duration": 30, "intensity_type": 2, "low": 130, "high": 150},
        {"name": "Z2 Easy Run 45min", "sport_type": 1, "duration": 45, "intensity_type": 2, "low": 130, "high": 150},
        {"name": "Z2 Easy Run 60min", "sport_type": 1, "duration": 60, "intensity_type": 2, "low": 130, "high": 150},
        {"name": "Tempo Run 40min", "sport_type": 1, "duration": 40, "intensity_type": 2, "low": 160, "high": 175},
        {"name": "Interval Run", "sport_type": 1, "duration": 45, "intensity_type": 2, "low": 170, "high": 190},
        {"name": "Z2 Indoor Bike 60min", "sport_type": 2, "duration": 60, "intensity_type": 6, "low": 180, "high": 220},
        {"name": "Sweet Spot 90min", "sport_type": 2, "duration": 90, "intensity_type": 6, "low": 260, "high": 285},
        {"name": "MTB Easy 90min", "sport_type": 24, "duration": 90, "intensity_type": 2, "low": 130, "high": 150},
        {"name": "MTB Hard 2h", "sport_type": 24, "duration": 120, "intensity_type": 2, "low": 150, "high": 175},
        {"name": "Strength Full Body", "sport_type": 4, "duration": 45, "intensity_type": 5, "low": 0, "high": 0},
        {"name": "Strength Upper", "sport_type": 4, "duration": 30, "intensity_type": 5, "low": 0, "high": 0},
        {"name": "Strength Lower", "sport_type": 4, "duration": 30, "intensity_type": 5, "low": 0, "high": 0},
        {"name": "Yoga / Mobility", "sport_type": 12, "duration": 30, "intensity_type": 5, "low": 0, "high": 0},
    ]
    return templates.TemplateResponse("templates.html", {
        "request": request,
        "templates": tpls,
        "next_14_days": app.state.next_14_days,
        "sport_emoji": _sport_emoji,
    })

@app.get("/demo/workouts", response_class=HTMLResponse)
async def demo_workouts(request: Request):
    workouts = [
        {"id": "w1", "name": "Z2 Easy Run 30min", "sport_type": 1, "sport_name": "Run", "estimated_time_seconds": 1800, "exercise_count": 1},
        {"id": "w2", "name": "Tempo Run 40min", "sport_type": 1, "sport_name": "Run", "estimated_time_seconds": 2400, "exercise_count": 3},
        {"id": "w3", "name": "Sweet Spot 90min", "sport_type": 2, "sport_name": "Indoor Cycling", "estimated_time_seconds": 5400, "exercise_count": 5},
        {"id": "w4", "name": "Strength Upper", "sport_type": 4, "sport_name": "Strength", "estimated_time_seconds": 1800, "exercise_count": 8},
    ]
    return templates.TemplateResponse("workouts.html", {
        "request": request,
        "workouts": workouts,
        "sport_emoji": _sport_emoji,
    })

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request, "error": None})

@app.post("/login")
async def do_login(request: Request, email: str = Form(...), password: str = Form(...), region: str = Form("eu")):
    import logging
    logger = logging.getLogger("main")
    logger.info(f"[LOGIN ATTEMPT] email={email} region={region}")
    try:
        auth = await coros.login(email, password, region)
    except coros.CorosError as exc:
        logger.warning(f"[LOGIN FAILED] {exc}")
        return templates.TemplateResponse("login.html", {"request": request, "error": str(exc)})
    except Exception as exc:
        logger.error(f"[LOGIN ERROR] {type(exc).__name__}: {exc}")
        return templates.TemplateResponse("login.html", {"request": request, "error": f"Internal error: {exc}"})
    request.session["coros_token"] = auth.access_token
    request.session["coros_user_id"] = auth.user_id
    request.session["coros_region"] = auth.region
    request.session["coros_ts"] = auth.timestamp_ms
    logger.info(f"[LOGIN SUCCESS] user_id={auth.user_id}")
    return RedirectResponse(url="/dashboard", status_code=303)

@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login")

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, week_offset: int = 0):
    auth = await _get_auth(request)
    start_day, end_day = _week_bounds(week_offset)
    try:
        items = await coros.fetch_schedule(auth, start_day, end_day)
        workouts = await coros.fetch_workouts(auth)
    except coros.CorosError as exc:
        # Token might be expired — clear and redirect to login
        request.session.clear()
        return RedirectResponse(url="/login")

    # Build a calendar grid: Monday -> Sunday
    monday = datetime.strptime(start_day, "%Y%m%d")
    days = []
    for i in range(7):
        d = monday + timedelta(days=i)
        ymd = d.strftime("%Y%m%d")
        day_items = [it for it in items if it.get("happenDay") == ymd]
        days.append({
            "date": ymd,
            "label": d.strftime("%a %d"),
            "is_today": ymd == _today(),
            "workouts": day_items,
        })

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "days": days,
        "workouts": workouts,
        "week_label": f"{monday.strftime('%d %b')} – {(monday + timedelta(days=6)).strftime('%d %b %Y')}",
        "week_offset": week_offset,
        "prev_week": week_offset - 1,
        "next_week": week_offset + 1,
        "sport_emoji": _sport_emoji,
        "fmt_day": _fmt_day,
    })

@app.get("/workouts", response_class=HTMLResponse)
async def workouts_page(request: Request):
    auth = await _get_auth(request)
    try:
        workouts = await coros.fetch_workouts(auth)
    except coros.CorosError:
        request.session.clear()
        return RedirectResponse(url="/login")
    return templates.TemplateResponse("workouts.html", {
        "request": request,
        "workouts": workouts,
        "sport_emoji": _sport_emoji,
    })

@app.post("/workouts/create")
async def create_workout_post(
    request: Request,
    name: str = Form(...),
    sport_type: int = Form(1),
    duration_minutes: int = Form(30),
    intensity_type: int = Form(2),  # 2=HR, 6=power
    intensity_low: int = Form(120),
    intensity_high: int = Form(150),
):
    auth = await _get_auth(request)
    steps = [
        {"name": name, "duration_minutes": duration_minutes, "intensity_low": intensity_low, "intensity_high": intensity_high}
    ]
    try:
        wid = await coros.create_structured_workout(auth, name, steps, sport_type, intensity_type)
    except coros.CorosError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return RedirectResponse(url="/workouts", status_code=303)


@app.post("/workouts/delete")
async def delete_workout_post(request: Request, workout_id: str = Form(...)):
    auth = await _get_auth(request)
    try:
        await coros.delete_workout(auth, workout_id)
    except coros.CorosError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return RedirectResponse(url="/workouts", status_code=303)


@app.post("/schedule")
async def schedule_post(
    request: Request,
    workout_id: str = Form(...),
    happen_day: str = Form(...),
):
    auth = await _get_auth(request)
    try:
        await coros.schedule_workout(auth, workout_id, happen_day)
    except coros.CorosError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return RedirectResponse(url="/dashboard", status_code=303)

@app.post("/unschedule")
async def unschedule_post(
    request: Request,
    plan_id: str = Form(...),
    id_in_plan: str = Form(...),
):
    auth = await _get_auth(request)
    try:
        await coros.remove_scheduled_workout(auth, plan_id, id_in_plan)
    except coros.CorosError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return RedirectResponse(url="/dashboard", status_code=303)

@app.get("/templates", response_class=HTMLResponse)
async def templates_page(request: Request):
    """Quick-create templates library."""
    auth = await _get_auth(request)
    # Pre-built templates
    tpls = [
        {"name": "Z2 Easy Run 30min", "sport_type": 1, "duration": 30, "intensity_type": 2, "low": 130, "high": 150},
        {"name": "Z2 Easy Run 45min", "sport_type": 1, "duration": 45, "intensity_type": 2, "low": 130, "high": 150},
        {"name": "Z2 Easy Run 60min", "sport_type": 1, "duration": 60, "intensity_type": 2, "low": 130, "high": 150},
        {"name": "Tempo Run 40min", "sport_type": 1, "duration": 40, "intensity_type": 2, "low": 160, "high": 175},
        {"name": "Interval Run", "sport_type": 1, "duration": 45, "intensity_type": 2, "low": 170, "high": 190},
        {"name": "Z2 Indoor Bike 60min", "sport_type": 2, "duration": 60, "intensity_type": 6, "low": 180, "high": 220},
        {"name": "Sweet Spot 90min", "sport_type": 2, "duration": 90, "intensity_type": 6, "low": 260, "high": 285},
        {"name": "MTB Easy 90min", "sport_type": 24, "duration": 90, "intensity_type": 2, "low": 130, "high": 150},
        {"name": "MTB Hard 2h", "sport_type": 24, "duration": 120, "intensity_type": 2, "low": 150, "high": 175},
        {"name": "Strength Full Body", "sport_type": 4, "duration": 45, "intensity_type": 5, "low": 0, "high": 0},
        {"name": "Strength Upper", "sport_type": 4, "duration": 30, "intensity_type": 5, "low": 0, "high": 0},
        {"name": "Strength Lower", "sport_type": 4, "duration": 30, "intensity_type": 5, "low": 0, "high": 0},
        {"name": "Yoga / Mobility", "sport_type": 12, "duration": 30, "intensity_type": 5, "low": 0, "high": 0},
    ]
    return templates.TemplateResponse("templates.html", {
        "request": request,
        "templates": tpls,
        "next_14_days": app.state.next_14_days,
        "sport_emoji": _sport_emoji,
    })

@app.post("/templates/create")
async def create_from_template(
    request: Request,
    name: str = Form(...),
    sport_type: int = Form(...),
    duration: int = Form(...),
    intensity_type: int = Form(...),
    low: int = Form(...),
    high: int = Form(...),
    happen_day: Optional[str] = Form(None),
):
    auth = await _get_auth(request)
    steps = [{"name": name, "duration_minutes": duration, "intensity_low": low, "intensity_high": high}]
    try:
        wid = await coros.create_structured_workout(auth, name, steps, sport_type, intensity_type)
        if happen_day:
            await coros.schedule_workout(auth, wid, happen_day)
    except coros.CorosError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if happen_day:
        return RedirectResponse(url="/dashboard", status_code=303)
    return RedirectResponse(url="/workouts", status_code=303)

# ------------------------------------------------------------------
# Run
# ------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
