"""Logging setup for the prototype."""

import logging


def configure_logging(level: str = "INFO") -> None:
    """Configure concise console logging once for the application."""
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
