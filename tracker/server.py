#!/usr/bin/env python3
"""Serves the job-application tracker on 127.0.0.1: the board from tracker/static/ and a small JSON API.

Usage: python3 tracker/server.py [--port 8765] [--data <file or folder>] [--open]
       python3 tracker/server.py --export-csv applications.csv   (writes the board as CSV, then exits)
       TRACKER_DATA="$HOME/Google Drive/tracker" python3 tracker/server.py
API:   GET  /api/state     -> {document, dataPath, backupDir}
       PUT  /api/state     <- the document with the updatedAt it was loaded with; 409 when it changed since
       GET  /api/variants  -> {variants: [{profile, variant, label}], errors}, from node read-profile.js
       POST /api/gap       <- {profile, variant, posting}; runs jd-gap.py with the posting on stdin
"""
import argparse
import errno
import json
import os
import re
import shutil
import subprocess
import sys
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlsplit

import export
import store

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
STATIC = os.path.realpath(os.path.join(HERE, "static"))
HOST = "127.0.0.1"
DEFAULT_PORT = 8765
MAX_BODY = 32 * 1024 * 1024
MAX_POSTING = 100000
GAP_TIMEOUT = 30
PROFILE_TIMEOUT = 10
SAFE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")

TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json",
    ".svg": "image/svg+xml",
}
CSP = ("default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; "
       "base-uri 'none'; form-action 'self'; frame-ancestors 'none'")


def list_variants(root=ROOT):
    """Returns ([{"profile", "variant", "label"}], [error]) for every profiles/<id>/ not starting with _.

    label is the variant's label, else its headline, else its id; with several profiles it ends with " (<profile>)".
    """
    node = shutil.which("node")
    if not node:
        return [], ["node not found in PATH, the CV variants cannot be read"]
    base = os.path.join(root, "profiles")
    profiles, errors = [], []
    for pid in sorted(os.listdir(base)) if os.path.isdir(base) else []:
        if pid.startswith("_") or not SAFE.match(pid) or not os.path.isdir(os.path.join(base, pid)):
            continue
        try:
            res = subprocess.run([node, os.path.join(root, "read-profile.js"), pid],
                                 capture_output=True, text=True, timeout=PROFILE_TIMEOUT)
        except subprocess.TimeoutExpired:
            errors.append(f"{pid}: read-profile.js timed out")
            continue
        if res.returncode != 0:
            errors.append(res.stderr.strip() or f"{pid}: read-profile.js failed")
            continue
        try:
            variants = json.loads(res.stdout)["variants"]
        except (ValueError, KeyError, TypeError):
            errors.append(f"{pid}: read-profile.js did not print a profile")
            continue
        profiles.append((pid, variants))
    suffix = len(profiles) > 1
    out = [{"profile": pid, "variant": vid,
            "label": str(v.get("label") or v.get("headline") or vid) + (f" ({pid})" if suffix else "")}
           for pid, variants in profiles for vid, v in variants.items()]
    return out, errors


def run_gap(root, profile, variant, posting):
    """Runs jd-gap.py for one known profile and variant; returns (HTTP status, response body)."""
    if not isinstance(posting, str) or not posting.strip():
        return HTTPStatus.BAD_REQUEST, {"error": "paste the posting text first"}
    if len(posting) > MAX_POSTING:
        return HTTPStatus.BAD_REQUEST, {"error": f"the posting is longer than {MAX_POSTING} characters"}
    variants, _errors = list_variants(root)
    if not isinstance(profile, str) or profile not in {v["profile"] for v in variants}:
        return HTTPStatus.BAD_REQUEST, {"error": f"unknown profile {profile!r}"}
    if not isinstance(variant, str) or (profile, variant) not in {(v["profile"], v["variant"]) for v in variants}:
        return HTTPStatus.BAD_REQUEST, {"error": f"unknown variant {variant!r} for profile {profile}"}
    cmd = [sys.executable, os.path.join(root, "jd-gap.py"), "--profile", profile, "--variant", variant]
    try:
        res = subprocess.run(cmd, input=posting, capture_output=True, text=True, timeout=GAP_TIMEOUT, cwd=root)
    except subprocess.TimeoutExpired:
        return HTTPStatus.GATEWAY_TIMEOUT, {"error": f"jd-gap.py took longer than {GAP_TIMEOUT} s"}
    if res.returncode != 0:
        return HTTPStatus.BAD_GATEWAY, {"error": res.stderr.strip() or "jd-gap.py failed"}
    return HTTPStatus.OK, {"output": res.stdout}


class Handler(BaseHTTPRequestHandler):
    server_version = "tracker"
    sys_version = ""

    def do_GET(self):
        if not self._allowed(write=False):
            return
        path = urlsplit(self.path).path
        if path == "/api/state":
            self._get_state()
        elif path == "/api/variants":
            variants, errors = list_variants(self.server.root)
            self._json(HTTPStatus.OK, {"variants": variants, "errors": errors})
        elif path.startswith("/api/"):
            self._json(HTTPStatus.NOT_FOUND, {"error": "no such API route"})
        else:
            self._static(path)

    def do_PUT(self):
        if not self._allowed(write=True):
            return
        if urlsplit(self.path).path != "/api/state":
            return self._json(HTTPStatus.NOT_FOUND, {"error": "no such API route"})
        doc = self._body()
        if doc is None:
            return
        try:
            saved = self.server.store.save(doc)
        except store.Invalid as e:
            return self._json(HTTPStatus.BAD_REQUEST, {"error": f"invalid document: {e}"})
        except store.Conflict as e:
            return self._json(HTTPStatus.CONFLICT, {"error": str(e)})
        except store.StoreError as e:
            return self._json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(e)})
        self._json(HTTPStatus.OK, {"document": saved})

    def do_POST(self):
        if not self._allowed(write=True):
            return
        if urlsplit(self.path).path != "/api/gap":
            return self._json(HTTPStatus.NOT_FOUND, {"error": "no such API route"})
        body = self._body()
        if body is None:
            return
        if not isinstance(body, dict):
            return self._json(HTTPStatus.BAD_REQUEST, {"error": "send {profile, variant, posting}"})
        status, payload = run_gap(self.server.root, body.get("profile"), body.get("variant"), body.get("posting"))
        self._json(status, payload)

    def log_message(self, fmt, *args):
        """Silent: no request log."""

    def _allowed(self, write):
        """Only this server's own host name; writes also need a JSON body from the same origin."""
        port = self.server.server_address[1]
        hosts = {f"{HOST}:{port}", f"localhost:{port}"}
        if self.headers.get("Host") not in hosts:
            self._json(HTTPStatus.FORBIDDEN, {"error": "wrong Host header"})
            return False
        origin = self.headers.get("Origin")
        if write and origin is not None and origin not in {f"http://{h}" for h in hosts}:
            self._json(HTTPStatus.FORBIDDEN, {"error": "cross-origin request"})
            return False
        if write and not (self.headers.get("Content-Type") or "").startswith("application/json"):
            self._json(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, {"error": "send application/json"})
            return False
        return True

    def _body(self):
        """The parsed JSON body, or None after sending the error."""
        length = self.headers.get("Content-Length")
        if length is None or not (length.isascii() and length.isdigit()):
            self._json(HTTPStatus.LENGTH_REQUIRED, {"error": "Content-Length is required"})
            return None
        if int(length) > MAX_BODY:
            self.close_connection = True
            self._json(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"error": f"the body is larger than {MAX_BODY} bytes"})
            return None
        try:
            return json.loads(self.rfile.read(int(length)).decode("utf-8"))
        except ValueError as e:
            self._json(HTTPStatus.BAD_REQUEST, {"error": f"the body is not JSON: {e}"})
            return None

    def _get_state(self):
        try:
            doc = self.server.store.load()
        except store.StoreError as e:
            return self._json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(e)})
        self._json(HTTPStatus.OK, {"document": doc, "dataPath": self.server.store.path,
                                   "backupDir": self.server.store.backup_dir})

    def _static(self, path):
        """Files under tracker/static/ only; / is index.html."""
        rel = unquote(path).lstrip("/") or "index.html"
        if "\0" in rel:
            return self._json(HTTPStatus.NOT_FOUND, {"error": "not found"})
        full = os.path.realpath(os.path.join(STATIC, rel))
        ext = os.path.splitext(full)[1]
        if os.path.commonpath([full, STATIC]) != STATIC or ext not in TYPES or not os.path.isfile(full):
            return self._json(HTTPStatus.NOT_FOUND, {"error": "not found"})
        with open(full, "rb") as f:
            data = f.read()
        headers = {"Content-Security-Policy": CSP} if ext == ".html" else {}
        self._send(HTTPStatus.OK, data, TYPES[ext], headers)

    def _json(self, status, payload):
        self._send(status, json.dumps(payload).encode("utf-8"), "application/json", {})

    def _send(self, status, data, ctype, headers):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        for name, value in headers.items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(data)


class TrackerServer(ThreadingHTTPServer):
    """Binds 127.0.0.1 only; port 0 picks a free port."""
    daemon_threads = True
    # Listen backlog: the browser opens one connection per ES module at once.
    request_queue_size = 64

    def __init__(self, port, data_store, root=ROOT):
        self.store = data_store
        self.root = root
        super().__init__((HOST, port), Handler)


def main():
    parser = argparse.ArgumentParser(description="Serves the job-application tracker on 127.0.0.1.")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"port (default: {DEFAULT_PORT}, 0: any free port)")
    parser.add_argument("--data", help="data file or folder (default: $TRACKER_DATA, else tracker/data/applications.json)")
    parser.add_argument("--open", action="store_true", help="open the board in the default browser (macOS)")
    parser.add_argument("--export-csv", metavar="FILE", help="write the board as CSV to FILE and exit")
    args = parser.parse_args()
    data = store.Store(store.data_path(args.data, os.environ.get("TRACKER_DATA")))
    try:
        doc = data.load()
    except store.StoreError as e:
        sys.exit(f"tracker: {e}")
    if args.export_csv:
        variants, _errors = list_variants()
        labels = {(v["profile"], v["variant"]): v["label"] for v in variants}
        count = export.write_csv(doc, labels, args.export_csv)
        print(f"tracker: {count} applications written to {args.export_csv}")
        return
    try:
        httpd = TrackerServer(args.port, data)
    except OSError as e:
        if e.errno != errno.EADDRINUSE:
            raise
        sys.exit(f"tracker: port {args.port} is busy: the tracker may already run, open http://{HOST}:{args.port}/ "
                 "or pass --port <another>")
    url = f"http://{HOST}:{httpd.server_address[1]}/"
    print(f"tracker: board   {url}", flush=True)
    print(f"tracker: data    {data.path}", flush=True)
    print(f"tracker: backups {data.backup_dir}", flush=True)
    print("tracker: Ctrl+C to stop", flush=True)
    if args.open and sys.platform == "darwin":
        subprocess.run(["open", url], check=False)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print()
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
