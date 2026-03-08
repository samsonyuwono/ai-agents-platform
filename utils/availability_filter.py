"""Availability slot filtering and matching for reservation sniping."""

import re
from datetime import datetime
from typing import Dict, List, Optional


def parse_time(time_str: str) -> Optional[datetime]:
    """Parse a time string like '7:00 PM' into a datetime (date part is today).

    Args:
        time_str: Time in "H:MM AM/PM" or "HH:MM AM/PM" format

    Returns:
        datetime with today's date and parsed time, or None if unparseable
    """
    time_str = time_str.strip()
    for fmt in ("%I:%M %p", "%I:%M%p"):
        try:
            return datetime.strptime(time_str, fmt)
        except ValueError:
            continue
    return None


def _time_distance_minutes(t1: datetime, t2: datetime) -> int:
    """Absolute distance in minutes between two times (ignoring date)."""
    delta = abs((t1.hour * 60 + t1.minute) - (t2.hour * 60 + t2.minute))
    return delta


def filter_slots_by_time(
    slots: List[Dict],
    preferred_times: List[str],
    window_minutes: int = 60
) -> List[Dict]:
    """Filter and sort slots by closeness to preferred times.

    Args:
        slots: List of slot dicts, each must have a 'time' key (e.g., "7:00 PM")
        preferred_times: List of preferred time strings (e.g., ["7:00 PM", "7:30 PM"])
        window_minutes: Maximum acceptable distance in minutes from any preferred time

    Returns:
        Filtered slots sorted by distance to nearest preferred time (closest first)
    """
    if not slots:
        return []

    if not preferred_times:
        return list(slots)

    parsed_prefs = [parse_time(t) for t in preferred_times]
    parsed_prefs = [t for t in parsed_prefs if t is not None]

    if not parsed_prefs:
        return list(slots)

    scored = []
    for slot in slots:
        slot_time = parse_time(slot.get('time', ''))
        if slot_time is None:
            continue

        min_dist = min(_time_distance_minutes(slot_time, p) for p in parsed_prefs)
        if min_dist <= window_minutes:
            scored.append((min_dist, slot))

    scored.sort(key=lambda x: x[0])
    return [slot for _, slot in scored]


def pick_best_slot(
    slots: List[Dict],
    preferred_times: List[str],
    window_minutes: int = 60
) -> Optional[Dict]:
    """Pick the best available slot: preferred time first, then closest.

    Args:
        slots: List of slot dicts with 'time' key
        preferred_times: Preferred time strings
        window_minutes: Max acceptable distance in minutes

    Returns:
        Best matching slot dict, or None if no slots available
    """
    if not slots:
        return None

    if not preferred_times:
        return slots[0]

    filtered = filter_slots_by_time(slots, preferred_times, window_minutes)
    if filtered:
        return filtered[0]

    # No slots within window — return the closest overall
    parsed_prefs = [parse_time(t) for t in preferred_times]
    parsed_prefs = [t for t in parsed_prefs if t is not None]

    if not parsed_prefs:
        return slots[0]

    best = None
    best_dist = float('inf')
    for slot in slots:
        slot_time = parse_time(slot.get('time', ''))
        if slot_time is None:
            continue
        dist = min(_time_distance_minutes(slot_time, p) for p in parsed_prefs)
        if dist < best_dist:
            best_dist = dist
            best = slot

    return best or slots[0]
