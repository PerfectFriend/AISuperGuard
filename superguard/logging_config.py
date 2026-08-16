"""
SuperGuard Alarm - Structured Logging Configuration

Provides consistent JSON-structured logging across all modules.
Uses Python's logging module with JSON formatter for machine-readable logs.
"""
import os
import sys
import json
import logging
import logging.handlers
from datetime import datetime
from typing import Optional, Dict, Any


class JSONFormatter(logging.Formatter):
    """JSON log formatter with consistent fields."""
    
    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        
        # Add extra fields if present
        if hasattr(record, "extra_fields"):
            log_data.update(record.extra_fields)
        
        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)
        
        return json.dumps(log_data, ensure_ascii=False)


def setup_logging(
    log_level: str = "INFO",
    log_file: Optional[str] = None,
    max_bytes: int = 10 * 1024 * 1024,  # 10MB
    backup_count: int = 5,
    json_format: bool = True,
) -> logging.Logger:
    """Setup application-wide logging.
    
    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Optional path to log file (rotating)
        max_bytes: Max size of log file before rotation
        backup_count: Number of rotated files to keep
        json_format: Use JSON format (True) or human-readable (False)
    
    Returns:
        Root logger instance
    """
    level = getattr(logging, log_level.upper(), logging.INFO)
    
    # Root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    
    # Clear existing handlers
    root_logger.handlers.clear()
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    
    if json_format:
        console_handler.setFormatter(JSONFormatter())
    else:
        console_handler.setFormatter(
            logging.Formatter(
                "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S"
            )
        )
    root_logger.addHandler(console_handler)
    
    # File handler (rotating)
    if log_file:
        os.makedirs(os.path.dirname(log_file), exist_ok=True)
        file_handler = logging.handlers.RotatingFileHandler(
            log_file,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8"
        )
        file_handler.setLevel(level)
        
        if json_format:
            file_handler.setFormatter(JSONFormatter())
        else:
            file_handler.setFormatter(
                logging.Formatter(
                    "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
                    datefmt="%Y-%m-%d %H:%M:%S"
                )
            )
        root_logger.addHandler(file_handler)
    
    # Suppress noisy loggers
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("requests").setLevel(logging.WARNING)
    logging.getLogger("telethon").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    
    return root_logger


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance for a module.
    
    Args:
        name: Module name (usually __name__)
    
    Returns:
        Logger instance
    """
    return logging.getLogger(name)


class LogContext:
    """Context manager for adding structured fields to logs."""
    
    def __init__(self, logger: logging.Logger, **extra_fields):
        self.logger = logger
        self.extra_fields = extra_fields
        self.old_factory = None
    
    def __enter__(self):
        # Wrap the logger to add extra fields
        original_make_record = self.logger.makeRecord
        
        def make_record(*args, **kwargs):
            record = original_make_record(*args, **kwargs)
            record.extra_fields = self.extra_fields
            return record
        
        self.logger.makeRecord = make_record
        return self.logger
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.logger.makeRecord = self.old_factory


def log_call(logger: logging.Logger, level: int = logging.DEBUG):
    """Decorator to log function calls with args and return value.
    
    Args:
        logger: Logger instance
        level: Log level for call logging
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            logger.log(level, f"Calling {func.__name__}", extra={
                "extra_fields": {"function": func.__name__, "args": str(args)[:200], "kwargs": str(kwargs)[:200]}
            })
            try:
                result = func(*args, **kwargs)
                logger.log(level, f"Completed {func.__name__}", extra={
                    "extra_fields": {"function": func.__name__, "result": str(result)[:200]}
                })
                return result
            except Exception as e:
                logger.exception(f"Failed {func.__name__}: {e}")
                raise
        return wrapper
    return decorator


# Initialize default logging on import
if not logging.getLogger().handlers:
    setup_logging(
        log_level=os.environ.get("SG_LOG_LEVEL", "INFO"),
        log_file=os.environ.get("SG_LOG_FILE"),
        json_format=os.environ.get("SG_LOG_JSON", "true").lower() == "true"
    )