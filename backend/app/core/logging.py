"""Structured logging: JSON lines (or readable console lines) carrying the request id and run id of the work."""

import json
import logging
import sys
import uuid
from contextvars import ContextVar
from datetime import UTC, datetime

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)
run_id_var: ContextVar[str | None] = ContextVar("run_id", default=None)

# Attributes every LogRecord has; anything else was passed via `extra=` and is emitted as a field
_STANDARD = set(vars(logging.LogRecord("", 0, "", 0, "", (), None))) | {"message", "asctime", "request_id", "run_id"}


def new_run_id() -> str:
    """Start a run (one /query or /chat stream): its id is attached to every log line it produces."""
    run_id = uuid.uuid4().hex[:16]
    run_id_var.set(run_id)
    return run_id


_base_factory = logging.getLogRecordFactory()


def _record_factory(*args, **kwargs) -> logging.LogRecord:
    record = _base_factory(*args, **kwargs)
    record.request_id = request_id_var.get()
    record.run_id = run_id_var.get()
    return record


def install_context_ids() -> None:
    """Every LogRecord carries the current request_id and run_id, whichever handler formats it."""
    if logging.getLogRecordFactory() is not _record_factory:
        logging.setLogRecordFactory(_record_factory)


def _extras(record: logging.LogRecord) -> dict:
    return {k: v for k, v in vars(record).items() if k not in _STANDARD and not k.startswith("_")}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "request_id": getattr(record, "request_id", None),
            "run_id": getattr(record, "run_id", None),
            **_extras(record),
        }
        if record.exc_info:
            entry["exc"] = self.formatException(record.exc_info)
        return json.dumps(entry, default=str)


class ConsoleFormatter(logging.Formatter):
    def __init__(self):
        super().__init__("%(asctime)s %(levelname)s %(name)s %(message)s", datefmt="%H:%M:%S")

    def format(self, record: logging.LogRecord) -> str:
        line = super().format(record)
        ids = [f"{k}={getattr(record, k)}" for k in ("request_id", "run_id") if getattr(record, k, None)]
        extras = [f"{k}={v}" for k, v in _extras(record).items()]
        return " ".join([line, *ids, *extras])


def configure_logging(level: str = "INFO", fmt: str = "json") -> None:
    """Install one stdout handler on the root logger and route uvicorn's loggers through it.

    Idempotent. Replaces handlers that libraries install on the root logger (the MCP SDK adds a rich console
    handler), but keeps pytest's capture handlers.
    """
    install_context_ids()
    root = logging.getLogger()
    for h in [h for h in root.handlers if not type(h).__module__.startswith("_pytest")]:
        root.removeHandler(h)
    handler = logging.StreamHandler(sys.stdout)
    handler._arena = True  # type: ignore[attr-defined]
    handler.setFormatter(JsonFormatter() if fmt == "json" else ConsoleFormatter())
    root.addHandler(handler)
    root.setLevel(level.upper())

    for name in ("uvicorn", "uvicorn.error"):
        lg = logging.getLogger(name)
        lg.handlers.clear()
        lg.propagate = True
    # The request middleware writes one access line per request instead
    logging.getLogger("uvicorn.access").disabled = True
    for noisy in ("httpx", "httpcore", "neo4j", "chromadb", "alembic"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
