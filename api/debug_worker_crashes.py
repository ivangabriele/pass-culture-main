"""List crashes of Gunicorn workers within a time windows, and try to
pinpoint causing HTTP requests.

Example:

    $ python debug_worker_crashes.py \
        --env production
        --timestamp-from 2024-02-07T15:56:00
        --timestamp-until 2024-02-07T15:57:59
    Found 1 crashes
    ----------
    Crash of PID 48291 on production-pcapi-native-v1-65d86cc5f6-4m6ff at 2024-02-07T15:56:10.109457+00:00
    Found 2 candidates for the crash:
    POST /native/v1/me/favorites at 2024-02-07T15:54:38.733539+00:00 (insert_id=dm00355b2jdpyo4w)
    POST /native/v1/me/favorites at 2024-02-07T15:54:38.688212+00:00 (insert_id=dndnthug7n35hnie)

Use ``--help`` for further details.


Context and how it works
========================

We see Gunicorn logs that look like this:

    Worker (pid:301) was sent SIGKILL! Perhaps out of memory?

That seems to indicate that an HTTP request uses too much memory,
which gets the worker killed. To pinpoint which request caused the
crash, we look for Gunicorn debugging logs (that indicate when a
request started to be processed) and our Flask application logs (that
indicate when a request has been processed by Flask) before the
crash. For each Gunicorn log, we try to find the corresponding Flask
log (same route and close timestamp). If we cannot find any Flask log,
it's because the processing did not end within the search time window,
possibly because the Gunicorn was killed during the processing. These
requests are thus our candidates to the cause of the crash.
"""

import argparse
import dataclasses
import datetime
import hashlib
import json
import re
import subprocess


# "[{timestamp}] [1] [ERROR] Worker (pid:204) was sent SIGKILL! Perhaps out of memory?"
CRASH_LOG_REGEXP = re.compile(".*? Worker \(pid:(\d+)\) was sent .*?")

GUNICORN_MESSAGES_TO_IGNORE = {
    "Closing connection",
    "Booting worker with pid",
    "Worker exiting",
    "Autorestarting worker after current request",
    "Ignoring connection epipe",
}


@dataclasses.dataclass
class Log:
    insert_id: str
    request: str
    timestamp: datetime.datetime

    def __hash__(self):
        unique = self.request + self.timestamp.isoformat()
        return int(hashlib.sha256(unique.encode()).hexdigest(), 16)

    def __str__(self):
        return f"{self.request} at {self.timestamp.isoformat()} (insert_id={self.insert_id})"


@dataclasses.dataclass
class Crash:
    pid: int
    pod: str
    timestamp: datetime.datetime

    @property
    def window(self) -> tuple[datetime.datetime, datetime.datetime]:
        return self.timestamp - datetime.timedelta(minutes=2), self.timestamp


def _run_gcloud_logging_query(namespace: str, timestamp_from: str, query: str) -> list[dict]:
    print(" ".join(["kubectl", "logs", "--namespace", namespace, "-l", query]))
    breakpoint()
    process = subprocess.run(
        [
            "kubectl",
            "logs",
            "--namespace",
            namespace,
            f"--since-time={timestamp_from}",
            "-l",
            query,
        ],
        capture_output=True,
    )
    if process.stderr:
        raise ValueError(f"`kubectl logs` returned an error: {process.stderr}")
    return json.loads(process.stdout)


def _ignore_gunicorn_log(log: dict) -> bool:
    for message_to_ignore in GUNICORN_MESSAGES_TO_IGNORE:
        if message_to_ignore in log["textPayload"]:
            return True
    return False


def get_request_logs(env: str, timestamp_from, query: str) -> list[Log]:
    logs = []
    for raw_log in _run_gcloud_logging_query(env, timestamp_from, query):
        if "jsonPayload" in raw_log:  # Flask logs
            method = raw_log["jsonPayload"]["extra"]["method"]
            path = raw_log["jsonPayload"]["extra"]["path"]
            request = f"{method} {path}"
            timestamp = datetime.datetime.fromisoformat(raw_log["timestamp"])
            # Get the timestamp when Flask _started_ to process the request
            timestamp -= datetime.timedelta(milliseconds=raw_log["jsonPayload"]["extra"]["duration"])
        else:  # Gunicorn logs
            if _ignore_gunicorn_log(raw_log):
                continue
            request = raw_log["textPayload"].split(" ", 5)[-1]
            timestamp = datetime.datetime.fromisoformat(raw_log["timestamp"])
        logs.append(Log(insert_id=raw_log["insertId"], timestamp=timestamp, request=request))
    return logs


def get_crashes(env: str, timestamp_from: str, query: str) -> list[Crash]:
    logs = []
    for raw_log in _run_gcloud_logging_query(env, timestamp_from, query):
        message = raw_log["textPayload"]
        pid = CRASH_LOG_REGEXP.match(message).group(1)
        pod = raw_log["resource"]["labels"]["pod_name"]
        logs.append(
            Crash(
                pid=pid,
                pod=pod,
                timestamp=datetime.datetime.fromisoformat(raw_log["timestamp"]),
            )
        )
    logs.sort(key=lambda log: log.timestamp)
    return logs


def build_worker_log_query(env: str, crash: Crash) -> str:
    timestamp_from, timestamp_until = crash.window
    return ",".join(
        (
            f'resource.labels.namespace_name="{env}"',
            f'resource.labels.pod_name="{crash.pod}"',
            f'timestamp>="{timestamp_from.isoformat()}"',
            f'timestamp<"{timestamp_until.isoformat()}"',
            f'"[{crash.pid}]"',
        )
    )


def build_flask_log_query(env: str, crash: Crash) -> str:
    timestamp_from, timestamp_until = crash.window
    return ",".join(
        (
            f'resource.labels.namespace_name="{env}"',
            f'resource.labels.pod_name="{crash.pod}"',
            f'timestamp>="{timestamp_from.isoformat()}"',
            f'timestamp<"{timestamp_until.isoformat()}"',
            '"HTTP request at"',
        )
    )


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--env",
        metavar="ENVIRONMENT",
        help='the environment, such as "staging" or "production"',
        required=True,
    )
    parser.add_argument(
        "--timestamp-from",
        metavar="YYYYMMDDTHH:MM:SS",
        help="an ISO-formatted timestamp, in UTC",
        required=True,
    )
    return parser.parse_args()


def analyze_logs(worker_logs, flask_logs):
    mappings = {}
    for worker_log in worker_logs:
        mappings[worker_log] = None
        for flask_log in flask_logs:
            if worker_log.request != flask_log.request:
                continue
            if abs(flask_log.timestamp - worker_log.timestamp) > datetime.timedelta(milliseconds=300):
                continue
            mappings[worker_log] = flask_log
            flask_logs.remove(flask_log)

    candidates = [worker_log for worker_log, flask_log in mappings.items() if not flask_log]
    print(f"Found {len(candidates)} candidates for the crash:")
    for candidate in candidates:
        print(candidate)


def main():
    args = parse_args()

    if args.env == "production":
        env = args.env
    else:
        env = args.env

    crashes = get_crashes(env, args.timestamp_from, "")
    print(f"Found {len(crashes)} crashes")
    for crash in crashes:
        print("-" * 10)
        print(f"Crash of PID {crash.pid} on {crash.pod} at {crash.timestamp.isoformat()}")
        try:
            worker_logs = get_request_logs(env, args.timestamp_from, build_worker_log_query(env, crash))
            flask_logs = get_request_logs(env, args.timestamp_from, build_flask_log_query(env, crash))
            if not worker_logs:
                print("No Gunicorn worker logs. Probably a bug in this tool!")
                continue
            if not flask_logs:
                print("No Flask logs. Probably a bug in this tool!")
                continue
            analyze_logs(worker_logs, flask_logs)
        except:
            __import__("pdb").set_trace()
            continue


main()
