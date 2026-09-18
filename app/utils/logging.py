from __future__ import annotations

import logging
import os

from app import config

_SECRET_VALUES = [v for v in (config.GEMINI_API_KEY, config.GROQ_API_KEY) if v]


class RedactSecretsFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        for secret in _SECRET_VALUES:
            if secret in message:
                message = message.replace(secret, "***REDACTED***")
        record.msg = message
        record.args = ()
        return True


def get_logger(name: str) -> logging.Logger:
    """Return a configured logger. Safe to call repeatedly with the same
    name -- handlers are only attached once per logger."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
        )
        handler.addFilter(RedactSecretsFilter())
        logger.addHandler(handler)
        logger.setLevel(os.getenv("LOG_LEVEL", "INFO").upper())
        logger.propagate = False
    return logger
