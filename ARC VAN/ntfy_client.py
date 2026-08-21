"""
ntfy_client.py
==============
Small helper for publishing push notifications to ntfy.sh.

The ARC Van 045/048 app uses two ntfy topics so the driver and students
can receive real-time alerts on their phones:

* STUDENTS_TOPIC  -> every student subscribes to this. Driver button presses
                     (location updates, departure times, availability) land here.
* DRIVER_TOPIC    -> only the driver subscribes to this. Student button presses
                     ("I'm heading to the van", sign-ups, ride requests) land here.

Both topics are published server-side. Anyone who wants alerts simply opens
the ntfy app (or https://ntfy.sh/<topic> in a browser) and subscribes.

Configuration can be overridden via environment variables so a self-hosted
ntfy server can be used instead of the public one:

    NTFY_SERVER          default https://ntfy.sh
    NTFY_STUDENTS_TOPIC  default arc-van-045048-students-x7q
    NTFY_DRIVER_TOPIC    default arc-van-045048-driver-k3m
    NTFY_TOKEN           optional access token if the topics are protected
"""

import os
import urllib.request
import urllib.error
import json
import threading

NTFY_SERVER = os.getenv("NTFY_SERVER", "https://ntfy.sh").rstrip("/")
STUDENTS_TOPIC = os.getenv("NTFY_STUDENTS_TOPIC", "arc-van-045048-students-x7q")
DRIVER_TOPIC = os.getenv("NTFY_DRIVER_TOPIC", "arc-van-045048-driver-k3m")
NTFY_TOKEN = os.getenv("NTFY_TOKEN", "")

# Emoji map for friendly notifications (ntfy supports emoji shortcodes in Title).
_EMOJI = {
    "driver": "bus",          # driver -> students updates
    "student": "wave",        # student -> driver signals
    "departure": "alarm_clock",
    "location": "round_pushpin",
    "full": "no_entry",
    "norides": "construction",
    "heading": "runner",
    "signup": "bell",
    "ride": "tickets",
    "info": "information_source",
}


def _publish(topic: str, title: str, message: str, tags: str = "information_source",
             priority: str = "default", click: str | None = None) -> bool:
    """
    POST a notification to an ntfy topic.

    Uses only the standard library (urllib) so no extra dependency is required
    in the hot path; we fall back to `requests` only if present (kept optional).
    Runs in a background thread so the FastAPI request is never blocked.
    """
    url = f"{NTFY_SERVER}/{topic}"
    headers = {
        "Title": title,
        "Tags": tags,
        "Priority": priority,
        "Content-Type": "text/plain; charset=utf-8",
    }
    if NTFY_TOKEN:
        headers["Authorization"] = f"Bearer {NTFY_TOKEN}"
    if click:
        headers["Click"] = click

    def _do_post():
        try:
            data = message.encode("utf-8")
            req = urllib.request.Request(url, data=data, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=5) as resp:
                return resp.status == 200
        except urllib.error.HTTPError as e:
            print(f"[ntfy] HTTP {e.code} posting to {topic}: {e.reason}")
            return False
        except Exception as e:  # network down, DNS, etc.
            print(f"[ntfy] failed posting to {topic}: {e}")
            return False

    # Fire-and-forget so API responses stay fast even if ntfy is slow/unreachable.
    threading.Thread(target=_do_post, daemon=True).start()
    return True


def notify_students(title: str, message: str, emoji: str = "driver",
                    priority: str = "default", click: str | None = None) -> bool:
    """Driver -> students. Used by all driver broadcast buttons."""
    return _publish(STUDENTS_TOPIC, title, message, tags=_EMOJI.get(emoji, "bus"),
                    priority=priority, click=click)


def notify_driver(title: str, message: str, emoji: str = "student",
                  priority: str = "default", click: str | None = None) -> bool:
    """Student -> driver. Used by heading-to-van, signup, and ride-request buttons."""
    return _publish(DRIVER_TOPIC, title, message, tags=_EMOJI.get(emoji, "wave"),
                    priority=priority, click=click)


def students_topic() -> str:
    return STUDENTS_TOPIC


def driver_topic() -> str:
    return DRIVER_TOPIC


def students_subscribe_url() -> str:
    return f"{NTFY_SERVER}/{STUDENTS_TOPIC}"


def driver_subscribe_url() -> str:
    return f"{NTFY_SERVER}/{DRIVER_TOPIC}"
