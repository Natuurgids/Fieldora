"""Dependency-free iCalendar export and provider compose links."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import urlencode


@dataclass(frozen=True, slots=True)
class CalendarEvent:
    event_id: str
    title: str
    event_date: str
    description: str = ""
    location: str = ""


def _ics_text(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace("\n", "\\n")
        .replace(",", "\\,")
        .replace(";", "\\;")
    )


class CalendarInteropService:
    """Export portable calendars without granting a provider background access."""

    def export_ics(self, events: tuple[CalendarEvent, ...], destination: Path) -> Path:
        lines = (
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            "PRODID:-//Fieldora//Research Calendar//EN",
            "CALSCALE:GREGORIAN",
            "METHOD:PUBLISH",
        )
        content = list(lines)
        for event in events:
            day = date.fromisoformat(event.event_date)
            content.extend(
                (
                    "BEGIN:VEVENT",
                    f"UID:{_ics_text(event.event_id)}@fieldora.local",
                    f"DTSTART;VALUE=DATE:{day.strftime('%Y%m%d')}",
                    f"DTEND;VALUE=DATE:{(day + timedelta(days=1)).strftime('%Y%m%d')}",
                    f"SUMMARY:{_ics_text(event.title)}",
                    f"DESCRIPTION:{_ics_text(event.description)}",
                    f"LOCATION:{_ics_text(event.location)}",
                    "TRANSP:TRANSPARENT",
                    "END:VEVENT",
                )
            )
        content.append("END:VCALENDAR")
        destination.write_text("\r\n".join(content) + "\r\n", encoding="utf-8")
        return destination

    @staticmethod
    def google_create_url(event: CalendarEvent) -> str:
        day = date.fromisoformat(event.event_date)
        parameters = {
            "action": "TEMPLATE",
            "text": event.title,
            "dates": f"{day.strftime('%Y%m%d')}/{(day + timedelta(days=1)).strftime('%Y%m%d')}",
            "details": event.description,
            "location": event.location,
        }
        return "https://calendar.google.com/calendar/render?" + urlencode(parameters)

    @staticmethod
    def outlook_create_url(event: CalendarEvent) -> str:
        day = date.fromisoformat(event.event_date)
        parameters = {
            "path": "/calendar/action/compose",
            "rru": "addevent",
            "subject": event.title,
            "startdt": day.isoformat(),
            "enddt": (day + timedelta(days=1)).isoformat(),
            "body": event.description,
            "location": event.location,
            "allday": "true",
        }
        return "https://outlook.office.com/calendar/0/deeplink/compose?" + urlencode(parameters)
