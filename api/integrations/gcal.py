"""google calendar client.

reads from the shared google token (api/integrations/google_auth.py). same
shape as gmail.py: dataclasses + async wrappers around the sync client.

verbs:
- list_events(time_min?, time_max?, max=20)   -> list[Event]
- get_event(event_id)                          -> Event
- find_free(duration_min, time_min?, time_max?, work_hours?) -> list[FreeSlot]
- create_event(...)                            -> Event
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional

from api.integrations import google_auth
from api.observability.logging import log


@dataclass
class Event:
    event_id: str
    title: str
    start: str           # iso
    end: str             # iso
    location: str = ""
    description: str = ""
    attendees: list[str] = field(default_factory=list)
    organizer: str = ""
    hangout_link: str = ""
    all_day: bool = False
    status: str = "confirmed"


@dataclass
class FreeSlot:
    start: str           # iso
    end: str             # iso
    duration_min: int


def configured() -> bool:
    return google_auth.configured()


def _service():
    return google_auth.service("calendar", "v3")


async def _run(fn, *args, **kwargs):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, lambda: fn(*args, **kwargs))


# ----- list / get -----


async def list_events(
    time_min: Optional[datetime] = None,
    time_max: Optional[datetime] = None,
    max_results: int = 20,
    calendar_id: str = "primary",
) -> list[Event]:
    if not configured():
        return []
    svc = _service()
    tmin = (time_min or datetime.now(tz=timezone.utc)).isoformat()
    tmax = (time_max or (datetime.now(tz=timezone.utc) + timedelta(days=7))).isoformat()

    def _do():
        resp = (
            svc.events()
            .list(
                calendarId=calendar_id,
                timeMin=tmin,
                timeMax=tmax,
                maxResults=max_results,
                singleEvents=True,
                orderBy="startTime",
            )
            .execute()
        )
        return [_to_event(e) for e in resp.get("items", [])]

    return await _run(_do)


async def get_event(event_id: str, calendar_id: str = "primary") -> Event:
    svc = _service()

    def _do():
        e = svc.events().get(calendarId=calendar_id, eventId=event_id).execute()
        return _to_event(e)

    return await _run(_do)


# ----- find free -----


async def find_free(
    duration_min: int,
    time_min: Optional[datetime] = None,
    time_max: Optional[datetime] = None,
    work_hours: tuple[int, int] = (9, 18),  # 9am - 6pm local
    calendar_id: str = "primary",
    limit: int = 5,
) -> list[FreeSlot]:
    """find open slots of `duration_min` minutes within working hours."""
    svc = _service()
    tmin = (time_min or datetime.now(tz=timezone.utc)).astimezone()
    tmax = (time_max or (tmin + timedelta(days=5))).astimezone()

    def _do():
        # use freebusy api for a clean answer
        body = {
            "timeMin": tmin.isoformat(),
            "timeMax": tmax.isoformat(),
            "items": [{"id": calendar_id}],
        }
        resp = svc.freebusy().query(body=body).execute()
        busy = resp["calendars"][calendar_id].get("busy", [])
        busy_intervals = [
            (datetime.fromisoformat(b["start"].replace("Z", "+00:00")),
             datetime.fromisoformat(b["end"].replace("Z", "+00:00")))
            for b in busy
        ]

        # walk day-by-day, find gaps inside work hours
        slots: list[FreeSlot] = []
        day = tmin.replace(hour=work_hours[0], minute=0, second=0, microsecond=0)
        end_horizon = tmax
        delta = timedelta(minutes=duration_min)
        step = timedelta(minutes=15)

        while day < end_horizon and len(slots) < limit:
            work_start = day.replace(hour=work_hours[0], minute=0, second=0, microsecond=0)
            work_end = day.replace(hour=work_hours[1], minute=0, second=0, microsecond=0)
            cursor = max(work_start, tmin)
            while cursor + delta <= work_end and len(slots) < limit:
                slot_end = cursor + delta
                if not _overlaps_any(cursor, slot_end, busy_intervals):
                    slots.append(FreeSlot(
                        start=cursor.isoformat(),
                        end=slot_end.isoformat(),
                        duration_min=duration_min,
                    ))
                    cursor = slot_end  # don't return overlapping suggestions
                else:
                    cursor += step
            day += timedelta(days=1)
        return slots

    return await _run(_do)


def _overlaps_any(s: datetime, e: datetime, busy: list[tuple[datetime, datetime]]) -> bool:
    for bs, be in busy:
        if s < be and e > bs:
            return True
    return False


# ----- create -----


async def create_event(
    *,
    title: str,
    start: datetime,
    end: datetime,
    description: str = "",
    location: str = "",
    attendees: Optional[list[str]] = None,
    add_meet_link: bool = False,
    calendar_id: str = "primary",
) -> Event:
    svc = _service()

    def _do():
        body: dict = {
            "summary": title,
            "description": description,
            "location": location,
            "start": {"dateTime": start.isoformat()},
            "end": {"dateTime": end.isoformat()},
        }
        if attendees:
            body["attendees"] = [{"email": a} for a in attendees]
        if add_meet_link:
            body["conferenceData"] = {
                "createRequest": {
                    "requestId": f"ro-{int(start.timestamp())}",
                    "conferenceSolutionKey": {"type": "hangoutsMeet"},
                }
            }
        e = (
            svc.events()
            .insert(
                calendarId=calendar_id,
                body=body,
                conferenceDataVersion=1 if add_meet_link else 0,
                sendUpdates="all" if attendees else "none",
            )
            .execute()
        )
        return _to_event(e)

    return await _run(_do)


# ----- helpers -----


def _to_event(e: dict) -> Event:
    start = e.get("start", {})
    end = e.get("end", {})
    is_all_day = "date" in start
    attendees = [a.get("email", "") for a in e.get("attendees", []) if a.get("email")]
    return Event(
        event_id=e.get("id", ""),
        title=e.get("summary", "(no title)"),
        start=start.get("dateTime") or start.get("date", ""),
        end=end.get("dateTime") or end.get("date", ""),
        location=e.get("location", ""),
        description=e.get("description", ""),
        attendees=attendees,
        organizer=e.get("organizer", {}).get("email", ""),
        hangout_link=e.get("hangoutLink", ""),
        all_day=is_all_day,
        status=e.get("status", "confirmed"),
    )
