"""
Simplified COROS Training Hub API client for CorosRelay.
Reverse-engineered endpoints; no official API exists.
"""
import hashlib
import json
import time
from typing import Optional
from dataclasses import dataclass

import httpx

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36"
)

ENDPOINTS = {
    "login": "/account/login",
    "schedule_sum": "/training/schedule/querysum",
    "schedule": "/training/schedule/query",
    "schedule_update": "/training/schedule/update",
    "workout_list": "/training/program/query",
    "workout_add": "/training/program/add",
    "workout_delete": "/training/program/delete",
    "exercises": "/training/exercise/query",
}

BASE_URLS = {
    "eu": "https://teameuapi.coros.com",
    "us": "https://teamapi.coros.com",
    "asia": "https://teamcnapi.coros.com",
    "cn": "https://teamcnapi.coros.com",
}


@dataclass
class AuthState:
    access_token: str
    user_id: str
    region: str
    timestamp_ms: int


class CorosError(Exception):
    pass


def _check(body: dict, context: str) -> None:
    if body.get("result") != "0000":
        msg = body.get("message", "unknown error")
        raise CorosError(f"{context}: {msg}")


def _base(region: str) -> str:
    return BASE_URLS.get(region.lower(), BASE_URLS["eu"])


async def login(email: str, password: str, region: str = "eu") -> AuthState:
    import logging
    logger = logging.getLogger("coros")
    
    email = email.strip().lower()
    password_md5 = hashlib.md5(password.encode("utf-8")).hexdigest()
    payload = {
        "account": email,
        "accountType": 2,
        "pwd": password_md5,
    }
    headers = {"User-Agent": USER_AGENT, "Content-Type": "application/json"}
    
    # Try requested region first, then fall back to others
    regions_to_try = [region.lower()] + [r for r in ["eu", "us", "asia", "cn"] if r != region.lower()]
    
    for attempt_region in regions_to_try:
        base = _base(attempt_region)
        url = f"{base}{ENDPOINTS['login']}"
        
        logger.info(f"[COROS LOGIN] POST {url}")
        
        async with httpx.AsyncClient() as client:
            r = await client.post(url, json=payload, headers=headers, timeout=30)
        
        try:
            data = r.json()
        except Exception:
            logger.error(f"[COROS LOGIN] non-JSON response from {attempt_region}: {r.text[:500]}")
            continue
        
        result = data.get("result")
        msg = data.get("message", "unknown error")
        logger.info(f"[COROS LOGIN] region={attempt_region} result={result} msg={msg}")
        
        if result == "0000":
            token = data["data"]["accessToken"]
            user_id = str(data["data"]["userId"])
            return AuthState(
                access_token=token,
                user_id=user_id,
                region=attempt_region,
                timestamp_ms=int(time.time() * 1000),
            )
    
    # All regions failed
    raise CorosError(f"login: {msg} (tried {', '.join(regions_to_try)})")


def _headers(auth: AuthState) -> dict:
    return {
        "User-Agent": USER_AGENT,
        "accesstoken": auth.access_token,
        "yfheader": json.dumps({"timestamp": int(time.time() * 1000), "language": "en"}),
    }


def _user_headers(auth: AuthState) -> dict:
    h = _headers(auth)
    h["yfheader"] = json.dumps({
        "timestamp": int(time.time() * 1000),
        "language": "en",
        "userId": auth.user_id,
    })
    return h


async def fetch_schedule(auth: AuthState, start_day: str, end_day: str) -> list[dict]:
    """List planned workouts from the COROS training calendar."""
    params = {
        "startDay": start_day,
        "endDay": end_day,
        "userId": auth.user_id,
    }
    url = f"{_base(auth.region)}{ENDPOINTS['schedule']}"
    async with httpx.AsyncClient() as client:
        r = await client.get(url, headers=_headers(auth), params=params)
    body = r.json()
    _check(body, "schedule fetch")
    return body.get("data", {}).get("list", [])


async def schedule_workout(auth: AuthState, workout_id: str, happen_day: str, sort_no: int = 1) -> None:
    payload = {
        "happenDay": happen_day,
        "planProgramId": workout_id,
        "sortNo": sort_no,
        "userId": auth.user_id,
    }
    url = f"{_base(auth.region)}{ENDPOINTS['schedule_update']}"
    async with httpx.AsyncClient() as client:
        r = await client.post(url, headers=_user_headers(auth), json=payload)
    body = r.json()
    _check(body, "schedule workout")


async def remove_scheduled_workout(auth: AuthState, plan_id: str, id_in_plan: str) -> None:
    payload = {
        "happenDay": "",
        "id": plan_id,
        "idInPlan": id_in_plan,
        "userId": auth.user_id,
    }
    url = f"{_base(auth.region)}{ENDPOINTS['schedule_update']}"
    async with httpx.AsyncClient() as client:
        r = await client.post(url, headers=_user_headers(auth), json=payload)
    body = r.json()
    _check(body, "remove scheduled workout")


async def fetch_workouts(auth: AuthState) -> list[dict]:
    """List all saved workout programs."""
    payload = {
        "page": 1,
        "size": 100,
        "userId": auth.user_id,
    }
    url = f"{_base(auth.region)}{ENDPOINTS['workout_list']}"
    async with httpx.AsyncClient() as client:
        r = await client.post(url, headers=_user_headers(auth), json=payload)
    body = r.json()
    _check(body, "workout list")
    items = body.get("data", {}).get("list", [])
    out = []
    for w in items:
        out.append({
            "id": w.get("id"),
            "name": w.get("name"),
            "sport_type": w.get("sportType"),
            "sport_name": w.get("sportName"),
            "estimated_time_seconds": w.get("estimatedTime"),
            "exercise_count": w.get("exerciseCount"),
        })
    return out


async def delete_workout(auth: AuthState, workout_id: str) -> None:
    payload = [workout_id]
    url = f"{_base(auth.region)}{ENDPOINTS['workout_delete']}"
    async with httpx.AsyncClient() as client:
        r = await client.post(url, headers=_user_headers(auth), json=payload)
    body = r.json()
    _check(body, "delete workout")


async def fetch_exercises(auth: AuthState, sport_type: int = 4) -> list[dict]:
    """Fetch exercise catalogue (strength by default, sport_type=4)."""
    payload = {
        "sportType": sport_type,
        "userId": auth.user_id,
    }
    url = f"{_base(auth.region)}{ENDPOINTS['exercises']}"
    async with httpx.AsyncClient() as client:
        r = await client.post(url, headers=_user_headers(auth), json=payload)
    body = r.json()
    _check(body, "exercises fetch")
    return body.get("data", {}).get("list", [])


async def create_structured_workout(
    auth: AuthState,
    name: str,
    steps: list[dict],
    sport_type: int = 2,
    intensity_type: int = 6,
) -> str:
    """
    Create a new structured workout.
    steps: list of dicts with name, duration_minutes, intensity_low, intensity_high.
    """
    # COROS expects a payload with programs[] containing steps[]
    program_steps = []
    for s in steps:
        program_steps.append({
            "name": s["name"],
            "duration": int(s["duration_minutes"] * 60),
            "intensityType": intensity_type,
            "intensityValue": s.get("intensity_low", 0),
            "intensityDisplayUnit": 0,
            "intensityUpperValue": s.get("intensity_high", 0),
            "sportType": sport_type,
        })

    payload = {
        "name": name,
        "sportType": sport_type,
        "planType": 1,
        "duration": 0,
        "programList": [
            {
                "stepList": program_steps,
            }
        ],
        "userId": auth.user_id,
    }

    # Calculate first to get metrics
    calc_url = f"{_base(auth.region)}/training/program/calculate"
    async with httpx.AsyncClient() as client:
        r = await client.post(calc_url, headers=_user_headers(auth), json=payload)
    calc_body = r.json()
    _check(calc_body, "workout calculate")
    calc_data = calc_body.get("data", {})

    # Merge calculated metrics and add
    payload["totalSet"] = calc_data.get("totalSet", 0)
    payload["trainingLoad"] = calc_data.get("trainingLoad", 0)
    payload["estimatedTime"] = calc_data.get("estimatedTime", 0)

    add_url = f"{_base(auth.region)}{ENDPOINTS['workout_add']}"
    async with httpx.AsyncClient() as client:
        r = await client.post(add_url, headers=_user_headers(auth), json=payload)
    add_body = r.json()
    _check(add_body, "workout add")

    return str(add_body.get("data", {}).get("id", ""))
