"""Structured JSON logging formatter.

Every log record is emitted as a single JSON object.  Log aggregators (Loki,
Datadog, etc.) can parse this without a custom grok pattern.

Context fields (agent_id, run_id, company_id) are attached via LoggerAdapter
at call sites — they show up here automatically if present on the log record.
"""

import json
import logging
import time


class StructuredFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        log_entry: dict = {
            "timestamp": time.strftime(
                "%Y-%m-%dT%H:%M:%SZ", time.gmtime(record.created)
            ),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "service": "agent-runtime",
        }

        # Optional context fields set by LoggerAdapter in the engine layer
        for field in ("agent_id", "run_id", "company_id", "trigger_id", "request_id"):
            value = getattr(record, field, None)
            if value is not None:
                log_entry[field] = value

        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_entry, default=str)
