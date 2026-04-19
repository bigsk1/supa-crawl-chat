"""
Application logging: rotating files under log/, console mirror, env-driven level.

Environment:
  APP_LOG_DIR   — directory for log files (default: log)
  LOG_LEVEL     — root level: DEBUG, INFO, WARNING, ERROR (default: INFO)
  LOG_FILE      — filename inside APP_LOG_DIR (default: app.log)

  AUDIT_LOG_ENABLED — if false/off, no separate audit file (default: true)
  AUDIT_LOG_FILE    — filename inside APP_LOG_DIR (default: audit.log)
  AUDIT_LOG_MAX_BYTES / AUDIT_LOG_BACKUP_COUNT — rotation for the audit file

Rotation (pick one):

  • Size-based (default): LOG_MAX_BYTES + LOG_BACKUP_COUNT — no time limit, caps total disk
    by file size (e.g. 10 MiB × 6 files ≈ 60 MiB).

  • Time-based (good for Docker, no cron): LOG_RETENTION_DAYS > 0 — uses daily rollover at
    midnight UTC; keeps that many rotated files (~that many days of history).

Optional crawl job files under log/crawl/: prune files older than CRAWL_LOG_MAX_AGE_DAYS
(no cron; runs once when logging is configured).
"""

from __future__ import annotations

import datetime
import logging
import os
import sys
import time
from logging.handlers import RotatingFileHandler, TimedRotatingFileHandler
from pathlib import Path

_CONFIGURED = False

_DEFAULT_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
_AUDIT_LOGGER_NAME = "supa_audit"


def _configure_audit_file_logger(base: Path, fmt: logging.Formatter) -> None:
    """Separate rotating file for operator actions (deletes, etc.); not mixed with noisy httpx lines."""
    raw = os.getenv("AUDIT_LOG_ENABLED", "true").strip().lower()
    if raw in ("0", "false", "no", "off"):
        return
    audit = logging.getLogger(_AUDIT_LOGGER_NAME)
    if audit.handlers:
        return
    fname = (os.getenv("AUDIT_LOG_FILE") or "audit.log").strip() or "audit.log"
    audit_path = base / fname
    try:
        fh = RotatingFileHandler(
            audit_path,
            maxBytes=int(os.getenv("AUDIT_LOG_MAX_BYTES", str(5 * 1024 * 1024))),
            backupCount=int(os.getenv("AUDIT_LOG_BACKUP_COUNT", "5")),
            encoding="utf-8",
        )
        fh.setFormatter(fmt)
        fh.setLevel(logging.INFO)
        audit.setLevel(logging.INFO)
        audit.addHandler(fh)
        audit.propagate = False
    except OSError as exc:
        sys.stderr.write(f"[app_logging] Cannot open audit log {audit_path}: {exc}\n")
_DATEFMT = "%Y-%m-%d %H:%M:%S"


def configure_logging(
    *,
    log_dir: str | Path | None = None,
    log_file: str | None = None,
    level: int | str | None = None,
    force: bool = False,
) -> logging.Logger:
    """
    Configure root logging once: rotating file under log/ + stderr stream.

    Returns the root logger. Safe to call multiple times (no duplicate handlers
    unless force=True).
    """
    global _CONFIGURED
    if _CONFIGURED and not force:
        return logging.getLogger()

    root = logging.getLogger()
    level_val = _resolve_level(level)
    root.setLevel(level_val)

    fmt = logging.Formatter(_DEFAULT_FORMAT, datefmt=_DATEFMT)

    base = Path(log_dir or os.getenv("APP_LOG_DIR", "log")).resolve()
    try:
        base.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        sys.stderr.write(f"[app_logging] Cannot create {base}: {exc}; using stderr only.\n")
        if not root.handlers:
            logging.basicConfig(level=level_val, format=_DEFAULT_FORMAT, datefmt=_DATEFMT)
        _CONFIGURED = True
        return root

    fname = log_file or os.getenv("LOG_FILE", "app.log")
    log_path = base / fname

    # Avoid duplicate file handlers pointing at the same path
    def _has_file_handler() -> bool:
        for h in root.handlers:
            if isinstance(h, (RotatingFileHandler, TimedRotatingFileHandler)):
                p = getattr(h, "baseFilename", None)
                if p and Path(p).resolve() == log_path.resolve():
                    return True
        return False

    if not _has_file_handler():
        try:
            retention_days = int(os.getenv("LOG_RETENTION_DAYS", "0") or "0")
            if retention_days > 0:
                # Daily files; backupCount = number of rolled files to retain (~days of history)
                fh = TimedRotatingFileHandler(
                    log_path,
                    when="midnight",
                    interval=1,
                    backupCount=min(366, max(1, retention_days)),
                    encoding="utf-8",
                    utc=True,
                )
            else:
                fh = RotatingFileHandler(
                    log_path,
                    maxBytes=int(os.getenv("LOG_MAX_BYTES", str(10 * 1024 * 1024))),
                    backupCount=int(os.getenv("LOG_BACKUP_COUNT", "5")),
                    encoding="utf-8",
                )
            fh.setFormatter(fmt)
            fh.setLevel(level_val)
            root.addHandler(fh)
        except OSError as exc:
            sys.stderr.write(f"[app_logging] Cannot open log file {log_path}: {exc}\n")

    pruned = _prune_old_crawl_logs(base)
    if pruned:
        logging.getLogger(__name__).info(
            "Pruned %s crawl log file(s) older than CRAWL_LOG_MAX_AGE_DAYS",
            pruned,
        )

    # One stderr handler for container/docker visibility
    if not any(
        isinstance(h, logging.StreamHandler) and getattr(h, "stream", None) is sys.stderr
        for h in root.handlers
    ):
        sh = logging.StreamHandler(sys.stderr)
        sh.setFormatter(fmt)
        sh.setLevel(level_val)
        root.addHandler(sh)

    _configure_audit_file_logger(base, fmt)

    _CONFIGURED = True
    logging.captureWarnings(True)
    _quiet_noisy_third_party_loggers()
    return root


def _prune_old_crawl_logs(log_base: Path) -> int:
    """Remove log/crawl/*.log older than CRAWL_LOG_MAX_AGE_DAYS (mtime). Opt-in; no cron."""
    raw = os.getenv("CRAWL_LOG_MAX_AGE_DAYS", "").strip()
    if not raw:
        return 0
    try:
        max_age = int(raw)
    except ValueError:
        return 0
    if max_age <= 0:
        return 0
    crawl_dir = log_base / "crawl"
    if not crawl_dir.is_dir():
        return 0
    cutoff = time.time() - max_age * 86400
    removed = 0
    for path in crawl_dir.glob("*.log"):
        try:
            if path.stat().st_mtime < cutoff:
                path.unlink()
                removed += 1
        except OSError:
            continue
    return removed


def _quiet_noisy_third_party_loggers() -> None:
    """Uvicorn reload uses watchfiles; at INFO it floods app.log with 'change detected'."""
    for name in ("watchfiles", "watchfiles.main"):
        logging.getLogger(name).setLevel(logging.WARNING)


def crawl_session_log_path(job_id: int | None, site_id: int | None) -> Path:
    """
    Path for one crawl run: log/crawl/YYYYMMDD-HHMMSSZ-site{id}-job{id}.log (UTC).
    """
    base = Path(os.getenv("APP_LOG_DIR", "log")).resolve() / "crawl"
    base.mkdir(parents=True, exist_ok=True)
    ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d-%H%M%SZ")
    sid = site_id if site_id is not None else "unknown"
    jid = job_id if job_id is not None else "none"
    return base / f"{ts}-site{sid}-job{jid}.log"


def attach_crawl_job_logger(
    job_id: int | None, site_id: int | None
) -> tuple[logging.Logger, logging.Handler, Path]:
    """
    Per-job logger + file under log/crawl/. Handler removed when crawl finishes.
    Propagates to root so summaries also appear in app.log.
    """
    path = crawl_session_log_path(job_id, site_id)
    key = job_id if job_id is not None else id(path)
    log = logging.getLogger(f"crawl.job.{key}")
    log.handlers.clear()
    log.setLevel(logging.INFO)
    log.propagate = True
    fh = logging.FileHandler(path, encoding="utf-8")
    fh.setFormatter(logging.Formatter(_DEFAULT_FORMAT, datefmt=_DATEFMT))
    fh.setLevel(logging.INFO)
    log.addHandler(fh)
    return log, fh, path


def detach_crawl_job_logger(log: logging.Logger, fh: logging.Handler) -> None:
    log.removeHandler(fh)
    try:
        fh.close()
    except Exception:
        pass


def _resolve_level(level: int | str | None) -> int:
    if level is not None:
        if isinstance(level, int):
            return level
        return getattr(logging, str(level).upper(), logging.INFO)
    name = os.getenv("LOG_LEVEL", "INFO").upper()
    return getattr(logging, name, logging.INFO)


def get_logger(name: str) -> logging.Logger:
    """Named logger (propagates to root handlers after configure_logging())."""
    return logging.getLogger(name)


def get_audit_logger() -> logging.Logger:
    """Structured operator/audit lines (log/audit.log by default). Call after configure_logging()."""
    return logging.getLogger(_AUDIT_LOGGER_NAME)
