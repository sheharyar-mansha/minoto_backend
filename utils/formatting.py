from datetime import date


def duration_label(minutes: int) -> str:
    if minutes < 60:
        return f"{minutes} min"
    h, m = divmod(minutes, 60)
    return f"{h}h {m}m" if m else f"{h}h"


def date_label(d: date) -> str:
    return d.strftime("%d %b %Y")
