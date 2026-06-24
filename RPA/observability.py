import builtins
import json
import logging
import os
import socket
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

try:
    import requests
except Exception:
    requests = None


_ORIGINAL_PRINT = builtins.print
_CONFIGURED = False


class ContextLoggerAdapter(logging.LoggerAdapter):
    def process(self, msg, kwargs):
        extra = dict(self.extra)
        extra.update(kwargs.pop("extra", {}) or {})
        kwargs["extra"] = extra
        return msg, kwargs


def carregar_env_local():
    project_root = Path(__file__).resolve().parent.parent
    for env_path in (project_root / ".env", Path(__file__).resolve().parent / ".env"):
        if not env_path.exists():
            continue
        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


class LokiHandler(logging.Handler):
    def __init__(self, url, labels):
        super().__init__()
        self.url = url
        self.labels = labels
        self.timeout = float(os.getenv("LOKI_TIMEOUT_SECONDS", "2"))

    def emit(self, record):
        labels = dict(self.labels)
        for key in ("robot", "run_id", "status", "solicitacao", "attempt"):
            value = getattr(record, key, None)
            if value is not None:
                labels[key] = str(value)

        payload = {
            "streams": [
                {
                    "stream": labels,
                    "values": [[str(time.time_ns()), self.format(record)]],
                }
            ]
        }

        try:
            body = json.dumps(payload).encode("utf-8")
            if requests:
                requests.post(self.url, data=body, headers={"Content-Type": "application/json"}, timeout=self.timeout)
            else:
                request = Request(self.url, data=body, headers={"Content-Type": "application/json"}, method="POST")
                with urlopen(request, timeout=self.timeout):
                    pass
        except Exception:
            pass


def setup_logging(robot_name="onerequest", run_id=None):
    global _CONFIGURED
    carregar_env_local()

    logger = logging.getLogger("onerequest")
    logger.setLevel(os.getenv("LOG_LEVEL", "INFO").upper())
    logger.propagate = False

    if not _CONFIGURED:
        formatter = logging.Formatter("%(message)s")

        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

        console = logging.StreamHandler(sys.stdout)
        console.setFormatter(formatter)
        logger.addHandler(console)

        loki_url = os.getenv("LOKI_URL")
        if loki_url:
            labels = {
                "application": os.getenv("LOKI_APPLICATION", "onerequest-rpa"),
                "env": os.getenv("APP_ENV", "local"),
                "host": os.getenv("APP_HOST_IP") or socket.gethostbyname(socket.gethostname()),
            }
            loki = LokiHandler(loki_url, labels)
            loki.setFormatter(formatter)
            logger.addHandler(loki)

        _CONFIGURED = True

    if not run_id:
        run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    return ContextLoggerAdapter(logger, {"robot": robot_name, "run_id": run_id})


def install_print_logger(robot_name="onerequest", run_id=None):
    logger = setup_logging(robot_name=robot_name, run_id=run_id)

    def print_logger(*args, sep=" ", end="\n", file=None, flush=False):
        if file not in (None, sys.stdout):
            _ORIGINAL_PRINT(*args, sep=sep, end=end, file=file, flush=flush)
            return
        message = sep.join(str(arg) for arg in args)
        if end and end != "\n":
            message += end
        logger.info(message)
        if flush:
            for handler in logger.logger.handlers:
                handler.flush()

    builtins.print = print_logger
    return logger


def log_event(logger, message, **extra):
    logger.info(message, extra=extra)


def _label_value(value):
    return str(value).replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")


def push_robot_metrics(robot_name, status, *, duration_seconds=None, successes=None, failures=None):
    carregar_env_local()
    pushgateway_url = os.getenv("PUSHGATEWAY_URL")
    if not pushgateway_url:
        return

    labels = f'robot="{_label_value(robot_name)}",application="{_label_value(os.getenv("LOKI_APPLICATION", "onerequest-rpa"))}"'
    status_labels = f'{labels},status="{_label_value(status)}"'
    now = time.time()
    lines = [
        "# TYPE onerequest_robot_last_run_timestamp_seconds gauge",
        f"onerequest_robot_last_run_timestamp_seconds{{{status_labels}}} {now}",
        "# TYPE onerequest_robot_last_status gauge",
        f"onerequest_robot_last_status{{{status_labels}}} 1",
    ]

    if status == "success":
        lines.extend(
            [
                "# TYPE onerequest_robot_last_success_timestamp_seconds gauge",
                f"onerequest_robot_last_success_timestamp_seconds{{{labels}}} {now}",
            ]
        )

    if duration_seconds is not None:
        lines.extend(
            [
                "# TYPE onerequest_robot_last_duration_seconds gauge",
                f"onerequest_robot_last_duration_seconds{{{status_labels}}} {float(duration_seconds):.3f}",
            ]
        )

    if successes is not None:
        lines.extend(
            [
                "# TYPE onerequest_robot_last_successful_items gauge",
                f"onerequest_robot_last_successful_items{{{labels}}} {int(successes)}",
            ]
        )

    if failures is not None:
        lines.extend(
            [
                "# TYPE onerequest_robot_last_failed_items gauge",
                f"onerequest_robot_last_failed_items{{{labels}}} {int(failures)}",
            ]
        )

    body = ("\n".join(lines) + "\n").encode("utf-8")
    url = pushgateway_url.rstrip("/") + f"/metrics/job/onerequest/robot/{robot_name}"
    try:
        request = Request(url, data=body, headers={"Content-Type": "text/plain; version=0.0.4"}, method="PUT")
        with urlopen(request, timeout=float(os.getenv("PUSHGATEWAY_TIMEOUT_SECONDS", "2"))):
            pass
    except Exception:
        pass
