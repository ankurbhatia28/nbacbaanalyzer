"""
Which browser origins may call the API (CORS).

Kept apart from `api.main`, which builds the app on import and so needs the
artifacts and a key, so the rule can be tested on its own.
"""

from __future__ import annotations

import os

LOCAL_WEB_APP = "http://localhost:3000"


def allowed_origins(environment: str) -> list[str]:
    """
    Who may call this from a browser.

    Unset in development means the local web app, so `npm run dev` works with
    no extra configuration; unset anywhere else means no one, because a
    deployed API should name its web app rather than inherit a default.
    """
    configured = os.environ.get("NBACBA_ALLOWED_ORIGINS")
    if configured is None:
        return [LOCAL_WEB_APP] if environment == "development" else []
    return [o.strip() for o in configured.split(",") if o.strip()]
