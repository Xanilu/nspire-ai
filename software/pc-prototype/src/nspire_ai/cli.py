"""Minimal command-line smoke-test entry point."""

from __future__ import annotations

import argparse
import logging
import sys

from nspire_ai.config import Settings
from nspire_ai.errors import ConversationProviderError, NspireAIError
from nspire_ai.logging_config import configure_logging
from nspire_ai.providers.registry import create_provider


def main() -> int:
    parser = argparse.ArgumentParser(description="NSPIRE AI PC prototype")
    parser.add_argument("prompt", nargs="?", default="Hello from NSPIRE AI")
    parser.add_argument("--stream", action="store_true", help="Stream response text as it arrives")
    args = parser.parse_args()

    try:
        settings = Settings.from_env()
        configure_logging(settings.log_level)
        provider = create_provider(settings)
        if args.stream:
            stream = getattr(provider, "stream", None)
            source = None
            iterator = None
            if callable(stream):
                try:
                    source = stream(args.prompt)
                    iterator = iter(source)
                except Exception:
                    _close_stream_resources(iterator, source)
                    raise ConversationProviderError("The configured provider could not start the stream.") from None
                except BaseException:
                    _close_stream_resources(iterator, source)
                    raise
            else:
                try:
                    response = provider.generate(args.prompt)
                except Exception:
                    raise ConversationProviderError("The configured provider could not process the message.") from None
                if not hasattr(response, "text") or not isinstance(response.text, str) or not response.text.strip():
                    raise ConversationProviderError("The configured provider returned an invalid response.")
                if len(response.text) > settings.max_stream_chars:
                    raise ConversationProviderError("The configured provider response exceeds the output limit.")
                source = (response.text[offset:offset + settings.max_stream_chunk_chars]
                          for offset in range(0, len(response.text), settings.max_stream_chunk_chars))
                iterator = iter(source)
            total = 0
            has_content = False
            try:
                while True:
                    try:
                        chunk = next(iterator)
                    except StopIteration:
                        break
                    except Exception:
                        raise ConversationProviderError("The configured provider could not complete the stream.") from None
                    if not isinstance(chunk, str) or not chunk:
                        raise ConversationProviderError("The configured provider returned an invalid stream chunk.")
                    if len(chunk) > settings.max_stream_chunk_chars:
                        raise ConversationProviderError("The configured provider returned an invalid stream chunk.")
                    total += len(chunk)
                    if total > settings.max_stream_chars:
                        raise ConversationProviderError("The configured provider response exceeds the output limit.")
                    has_content = has_content or bool(chunk.strip())
                    sys.stdout.write(chunk)
                    sys.stdout.flush()
                if not has_content:
                    raise ConversationProviderError("The configured provider returned an empty response.")
            finally:
                _close_stream_resources(iterator, source)
            sys.stdout.write("\n")
        else:
            response = provider.generate(args.prompt)
            print(response.text)
        return 0
    except KeyboardInterrupt:
        logging.getLogger(__name__).error("Streaming interrupted.")
        return 130
    except NspireAIError as exc:
        logging.getLogger(__name__).error("%s", exc)
        return 2


def _close_stream_resources(iterator, source) -> None:
    """Close each distinct stream object once, including when iter() fails."""
    seen: set[int] = set()
    for resource in (iterator, source):
        if resource is None or id(resource) in seen:
            continue
        seen.add(id(resource))
        close = getattr(resource, "close", None)
        if callable(close):
            try:
                close()
            except Exception:
                pass


if __name__ == "__main__":
    raise SystemExit(main())
