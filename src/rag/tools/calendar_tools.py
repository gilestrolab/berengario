"""
Calendar tools for generating .ics calendar files.

Provides functions to create calendar events that can be sent as
email attachments.
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional
from icalendar import Calendar, Event as ICalEvent
from dateutil import parser as date_parser

from .base import Tool, ToolParameter, ParameterType, register_tool

logger = logging.getLogger(__name__)


def _create_calendar_event_impl(
    title: str,
    start_date: str,
    end_date: str,
    description: str = "",
    location: str = "",
    all_day: bool = False,
) -> Dict[str, Any]:
    """
    Internal implementation for creating a calendar event.

    Args:
        title: Event title/summary
        start_date: Start date/time in ISO format or natural language
        end_date: End date/time in ISO format or natural language
        description: Event description
        location: Event location
        all_day: Whether this is an all-day event

    Returns:
        Dict with 'content' (ics file as bytes), 'filename', 'content_type'
    """
    try:
        # Parse dates
        try:
            start_dt = date_parser.parse(start_date)
            end_dt = date_parser.parse(end_date)
        except Exception as e:
            logger.error(f"Failed to parse dates: {e}")
            raise ValueError(f"Invalid date format. Please use ISO format (YYYY-MM-DD) or clear date strings. Error: {e}")

        # Create calendar
        cal = Calendar()
        cal.add('prodid', '-//RAGInbox Calendar//EN')
        cal.add('version', '2.0')

        # Create event
        event = ICalEvent()
        event.add('summary', title)
        event.add('dtstart', start_dt.date() if all_day else start_dt)
        event.add('dtend', end_dt.date() if all_day else end_dt)

        if description:
            event.add('description', description)

        if location:
            event.add('location', location)

        # Add timestamp
        event.add('dtstamp', datetime.now())

        # Generate UID
        event.add('uid', f"{datetime.now().timestamp()}@raginbox")

        # Add event to calendar
        cal.add_component(event)

        # Generate .ics file content
        ics_content = cal.to_ical()

        # Create safe filename from title
        safe_title = "".join(c for c in title if c.isalnum() or c in (' ', '-', '_')).strip()
        safe_title = safe_title.replace(' ', '_')[:50]  # Limit length
        filename = f"{safe_title}.ics" if safe_title else "event.ics"

        logger.info(f"Created calendar event: {title}")

        return {
            'content': ics_content,
            'filename': filename,
            'content_type': 'text/calendar'
        }

    except Exception as e:
        logger.error(f"Failed to create calendar event: {e}", exc_info=True)
        raise


def create_calendar_event(
    title: str,
    start_date: str,
    end_date: str,
    description: str = "",
    location: str = "",
) -> Dict[str, Any]:
    """
    Create a calendar event and return as .ics file.

    Args:
        title: Event title
        start_date: Start date/time (ISO format or natural language)
        end_date: End date/time (ISO format or natural language)
        description: Optional event description
        location: Optional event location

    Returns:
        Dictionary with attachment data (content, filename, content_type)
    """
    return _create_calendar_event_impl(
        title=title,
        start_date=start_date,
        end_date=end_date,
        description=description,
        location=location,
        all_day=False,
    )


def create_calendar_from_data(
    events: List[Dict[str, str]],
    calendar_name: str = "Events",
) -> Dict[str, Any]:
    """
    Create a calendar with multiple events from structured data.

    Args:
        events: List of event dicts, each with 'title', 'start_date', 'end_date',
                and optionally 'description' and 'location'
        calendar_name: Name for the calendar file

    Returns:
        Dictionary with attachment data (content, filename, content_type)
    """
    try:
        # Create calendar
        cal = Calendar()
        cal.add('prodid', '-//RAGInbox Calendar//EN')
        cal.add('version', '2.0')
        cal.add('x-wr-calname', calendar_name)

        # Add each event
        for event_data in events:
            try:
                start_dt = date_parser.parse(event_data['start_date'])
                end_dt = date_parser.parse(event_data['end_date'])

                event = ICalEvent()
                event.add('summary', event_data['title'])
                event.add('dtstart', start_dt)
                event.add('dtend', end_dt)

                if 'description' in event_data:
                    event.add('description', event_data['description'])

                if 'location' in event_data:
                    event.add('location', event_data['location'])

                event.add('dtstamp', datetime.now())
                event.add('uid', f"{datetime.now().timestamp()}_{event_data['title']}@raginbox")

                cal.add_component(event)

            except Exception as e:
                logger.warning(f"Skipped event {event_data.get('title', 'unknown')}: {e}")
                continue

        # Generate .ics file content
        ics_content = cal.to_ical()

        # Create filename
        safe_name = "".join(c for c in calendar_name if c.isalnum() or c in (' ', '-', '_')).strip()
        safe_name = safe_name.replace(' ', '_')[:50]
        filename = f"{safe_name}.ics" if safe_name else "calendar.ics"

        logger.info(f"Created calendar with {len(events)} events")

        return {
            'content': ics_content,
            'filename': filename,
            'content_type': 'text/calendar'
        }

    except Exception as e:
        logger.error(f"Failed to create calendar from data: {e}", exc_info=True)
        raise


# Register tools
create_calendar_event_tool = Tool(
    name="create_calendar_event",
    description="Create a calendar event (.ics file) that can be imported into calendar applications. Use this when the user requests a calendar invite or wants to add an event to their calendar.",
    parameters=[
        ToolParameter(
            name="title",
            type=ParameterType.STRING,
            description="Title/summary of the event",
            required=True,
        ),
        ToolParameter(
            name="start_date",
            type=ParameterType.STRING,
            description="Start date and time in ISO format (YYYY-MM-DDTHH:MM:SS) or natural language like '2026-06-08 09:00'",
            required=True,
        ),
        ToolParameter(
            name="end_date",
            type=ParameterType.STRING,
            description="End date and time in ISO format (YYYY-MM-DDTHH:MM:SS) or natural language like '2026-06-17 17:00'",
            required=True,
        ),
        ToolParameter(
            name="description",
            type=ParameterType.STRING,
            description="Optional description or details about the event",
            required=False,
        ),
        ToolParameter(
            name="location",
            type=ParameterType.STRING,
            description="Optional location where the event takes place",
            required=False,
        ),
    ],
    function=create_calendar_event,
    returns_attachment=True,
)

create_calendar_from_data_tool = Tool(
    name="create_calendar_from_data",
    description="Create a calendar file with multiple events from structured data. Use this when you have a list of events to export.",
    parameters=[
        ToolParameter(
            name="events",
            type=ParameterType.ARRAY,
            description="List of events, each with title, start_date, end_date, and optionally description and location",
            required=True,
            items={"type": "object"},
        ),
        ToolParameter(
            name="calendar_name",
            type=ParameterType.STRING,
            description="Name for the calendar",
            required=False,
        ),
    ],
    function=create_calendar_from_data,
    returns_attachment=True,
)

# Register tools in global registry
register_tool(create_calendar_event_tool)
register_tool(create_calendar_from_data_tool)
