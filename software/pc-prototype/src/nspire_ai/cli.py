"""Minimal command-line smoke-test entry point."""

from __future__ import annotations

import argparse
import logging

from nspire_ai.config import Settings
from nspire_ai.errors import NspireAIError
from nspire_ai.logging_config import configure_logging
from nspire_ai.providers.registry import create_provider


def main() -> int:
    parser = argparse.ArgumentParser(description="NSPIRE AI PC prototype")
    parser.add_argument("prompt", nargs="?", default="Hello from NSPIRE AI")
    args = parser.parse_args()

    try:
        settings = Settings.from_env()
        configure_logging(settings.log_level)
        response = create_provider(settings).generate(args.prompt)
        print(response.text)
        return 0
    except NspireAIError as exc:
        logging.getLogger(__name__).error("%s", exc)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
