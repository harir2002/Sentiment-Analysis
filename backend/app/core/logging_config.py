import json
import logging
import sys


class JsonLogFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(level: str = "INFO", access_log: bool = True, log_format: str = "text") -> None:
    """Configure backend logs. Use log_format=json for production log aggregation."""
    log_level = getattr(logging, level.upper(), logging.INFO)

    root = logging.getLogger()
    if not root.handlers:
        handler = logging.StreamHandler(sys.stdout)
        if log_format.lower() == "json":
            handler.setFormatter(JsonLogFormatter())
        else:
            handler.setFormatter(
                logging.Formatter("%(asctime)s %(levelname)s %(name)s — %(message)s")
            )
        root.addHandler(handler)
    root.setLevel(log_level)

    for name in (
        "sqlalchemy.engine",
        "sqlalchemy.engine.Engine",
        "sqlalchemy.pool",
        "sqlalchemy.orm",
        "httpx",
        "httpcore",
        "watchfiles",
    ):
        logging.getLogger(name).setLevel(logging.WARNING)

    if not access_log:
        logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
