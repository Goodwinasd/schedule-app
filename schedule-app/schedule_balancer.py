"""
Curriculum and schedule balancing module.
"""
import math


def weekly_pairs(total_hours, weeks_in_semester=18):
    """Calculate recommended weekly pairs (1 pair = 2 academic hours)."""
    return math.ceil(total_hours / (weeks_in_semester * 2))


def validate_weekly_load(lessons_by_date):
    """
    Validate a group's schedule for a week.
    lessons_by_date: dict of {date: [lesson, ...]} for Mon-Sat.

    Returns dict with:
      - total_pairs: int
      - total_hours: int (pairs * 2)
      - violations: list of strings
      - status: 'ok' | 'warning' | 'overload'
    """
    violations = []
    total_pairs = sum(len(v) for v in lessons_by_date.values())
    total_hours = total_pairs * 2

    if total_pairs > 18:
        violations.append(f"Превышение нагрузки: {total_pairs} пар (>18) — {total_hours} часов (>36)")

    day_counts = {}
    for date, lessons in lessons_by_date.items():
        cnt = len(lessons)
        day_counts[date] = cnt
        if cnt > 4:
            violations.append(f"{date}: {cnt} пар (>4)")
        elif cnt < 2 and total_pairs > 12:
            violations.append(f"{date}: {cnt} пар (<2) при высокой общей нагрузке")

    status = 'ok'
    if total_pairs > 18 or any(c > 4 for c in day_counts.values()):
        status = 'overload'
    elif any(c < 2 for c in day_counts.values()) and total_pairs > 12:
        status = 'warning'

    return {
        'total_pairs': total_pairs,
        'total_hours': total_hours,
        'day_counts': day_counts,
        'violations': violations,
        'status': status,
    }
