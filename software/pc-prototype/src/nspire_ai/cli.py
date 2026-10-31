"""Minimal command-line smoke-test entry point."""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime
from typing import TextIO

from nspire_ai.config import Settings
from nspire_ai.conversations import ConversationEngine, create_conversation_engine
from nspire_ai.errors import ConversationNotFoundError, ConversationProviderError, NspireAIError, ProviderError
from nspire_ai.logging_config import configure_logging
from nspire_ai.providers.registry import create_provider


def main() -> int:
    parser = argparse.ArgumentParser(description="NSPIRE AI PC prototype")
    parser.add_argument("prompt", nargs="?", default="Hello from NSPIRE AI")
    parser.add_argument("--stream", action="store_true", help="Stream response text as it arrives")
    parser.add_argument(
        "--chat", nargs="?", const="", metavar="ID",
        help="Start an interactive saved chat, or resume one by its ID",
    )
    args = parser.parse_args()

    partial_output = False
    try:
        settings = Settings.from_env()
        configure_logging(settings.log_level)
        if args.chat is not None:
            with create_conversation_engine(settings) as engine:
                return run_interactive(engine, conversation_id=args.chat or None)
        provider = create_provider(settings)
        if args.stream:
            stream = getattr(provider, "stream", None)
            source = None
            iterator = None
            if callable(stream):
                try:
                    source = stream(args.prompt)
                    iterator = iter(source)
                except ProviderError as exc:
                    _close_stream_resources(iterator, source)
                    raise ConversationProviderError("The configured provider could not start the stream.", code=exc.code) from None
                except Exception:
                    _close_stream_resources(iterator, source)
                    raise ConversationProviderError("The configured provider could not start the stream.") from None
                except BaseException:
                    _close_stream_resources(iterator, source)
                    raise
            else:
                try:
                    response = provider.generate(args.prompt)
                except ProviderError as exc:
                    raise ConversationProviderError("The configured provider could not process the message.", code=exc.code) from None
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
                    except ProviderError as exc:
                        raise ConversationProviderError("The configured provider could not complete the stream.", code=exc.code) from None
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
                    partial_output = partial_output or bool(chunk.strip())
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
        if partial_output:
            sys.stdout.write("\n[Incomplete response; this turn was not saved.]\n")
        logging.getLogger(__name__).error("Streaming interrupted.")
        return 130
    except NspireAIError as exc:
        if partial_output:
            sys.stdout.write("\n[Incomplete response; this turn was not saved.]\n")
        logging.getLogger(__name__).error("%s", exc)
        return 2


def run_interactive(
    engine: ConversationEngine,
    *,
    conversation_id: str | None = None,
    input_fn=input,
    output: TextIO | None = None,
) -> int:
    """Run the guided terminal chat using the persistent conversation engine."""
    output = output or sys.stdout
    if conversation_id is None:
        output.write("Welcome to NSPIRE AI chat. Press Enter to start a new chat.\n")
        output.write("Type L to list saved chats, paste a chat ID to resume, or Q to quit.\n")
        while True:
            try:
                choice = input_fn("Start a new chat? [Enter=yes, L=list, Q=quit]: ").strip()
            except EOFError:
                output.write("Goodbye.\n")
                return 0
            except KeyboardInterrupt:
                output.write("\nChat interrupted. Your saved chats are unchanged.\n")
                return 130
            if not choice:
                try:
                    conversation_id = engine.create_conversation()
                except NspireAIError as exc:
                    output.write(f"Could not start a chat: {exc}\n")
                    return 2
                break
            command = choice.casefold()
            if command in {"q", "quit", "exit"}:
                output.write("Goodbye.\n")
                return 0
            if command in {"l", "list", "sessions", ":sessions"}:
                if not _print_sessions(engine, output):
                    continue
                output.write("Enter a chat ID to resume, or press Enter to start a new chat.\n")
                continue
            if command.startswith("resume "):
                candidate = choice[7:].strip()
            else:
                candidate = choice
            try:
                engine.get_history(candidate)
            except ConversationNotFoundError:
                output.write("That chat ID was not found. Type L to see saved chats, or press Enter for a new chat.\n")
                continue
            except NspireAIError as exc:
                output.write(f"Could not open that chat: {exc}\n")
                continue
            conversation_id = candidate
            break

    try:
        history = engine.get_history(conversation_id)
    except ConversationNotFoundError:
        output.write("That chat ID was not found. Start chat again and choose a saved chat from the list.\n")
        return 2
    except NspireAIError as exc:
        output.write(f"Could not open the chat: {exc}\n")
        return 2

    output.write(f"\nChat ID: {conversation_id}\n")
    if history:
        output.write(f"Resumed with {len(history) // 2} saved turn(s). Type :history to review them.\n")
    else:
        output.write("New chat started. Type a message and press Enter.\n")
    output.write("Actions: :help for tips, :history to review, :sessions to list chats, :quit to leave.\n")

    while True:
        try:
            content = input_fn("You: ")
        except EOFError:
            output.write("\nChat closed. Your completed turns are saved.\n")
            return 0
        except KeyboardInterrupt:
            output.write("\nChat interrupted. Your completed turns are saved.\n")
            return 130
        stripped = content.strip()
        command = stripped.casefold()
        if command in {":quit", ":q", "quit", "exit"}:
            output.write("Chat closed. Your completed turns are saved.\n")
            return 0
        if command in {":help", ":h", "help"}:
            output.write("Type a message and press Enter. Use :history to review this chat, :sessions to list saved chats, or :quit to leave.\n")
            continue
        if command in {":sessions", ":list"}:
            _print_sessions(engine, output)
            continue
        if command == ":history":
            try:
                history = engine.get_history(conversation_id)
            except NspireAIError as exc:
                output.write(f"Could not load history: {exc}\n")
                continue
            if not history:
                output.write("No completed turns yet.\n")
            else:
                for message in history:
                    label = "You" if message.role == "user" else "Assistant"
                    output.write(f"{label}: {message.content}\n")
            continue
        if not stripped:
            output.write("Enter a message, or type :help to see available actions.\n")
            continue
        try:
            output.write("Assistant: ")
            output.flush()
            wrote_chunk = False
            stream = engine.stream_message(conversation_id, stripped)
            try:
                for chunk in stream:
                    output.write(chunk)
                    output.flush()
                    wrote_chunk = wrote_chunk or bool(chunk.strip())
            finally:
                close = getattr(stream, "close", None)
                if callable(close):
                    close()
            output.write("\n")
        except KeyboardInterrupt:
            marker = "[Incomplete response.] " if wrote_chunk else ""
            output.write(f"\n{marker}Turn interrupted; it was not saved. Chat remains open. Type :quit to leave.\n")
        except ValueError as exc:
            output.write(f"\n{exc} Please try again.\n")
        except NspireAIError as exc:
            marker = "[Incomplete response; this turn was not saved.]\n" if wrote_chunk else ""
            output.write(f"\n{marker}Could not complete that turn: {exc}\nYour earlier history is still available; please try again.\n")


def _print_sessions(engine: ConversationEngine, output: TextIO) -> bool:
    try:
        sessions = engine.list_conversations()
    except NspireAIError as exc:
        output.write(f"Could not list saved chats: {exc}\n")
        return False
    if not sessions:
        output.write("No saved chats yet. Press Enter at the prompt to start one.\n")
        return False
    output.write("Saved chats (newest activity first):\n")
    for session in sessions:
        try:
            updated = datetime.fromisoformat(session.updated_at).astimezone().strftime("%Y-%m-%d %H:%M")
        except (TypeError, ValueError):
            updated = session.updated_at
        output.write(
            f"  {session.conversation_id}  |  {updated}  |  "
            f"{session.message_count} message(s), {session.message_count // 2} turn(s)\n"
        )
    return True


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
