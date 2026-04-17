from __future__ import annotations

import logging
import os


def configure_logging() -> None:
    """
    Central logging configuration.

    Intentionally conservative: console logs, predictable format, env-driven level.
    """
    level_name = (os.getenv("LOG_LEVEL") or "INFO").upper().strip()
    level = getattr(logging, level_name, logging.INFO)

    root = logging.getLogger()
    if root.handlers:
        # Avoid double-configuring when imported by tests or reloaded.
        root.setLevel(level)
        return

    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

