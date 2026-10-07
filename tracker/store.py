"""Storage of the application tracker: one JSON document, atomic writes, rotating backups, a revision check.

The document is {schemaVersion, columns: [{id, name, kind, hint}], cards: [...], updatedAt}. updatedAt is the
revision: a save must carry the updatedAt it was loaded with, and gets a new one back.
The columns are fixed: DEFAULT_COLUMNS is the one list, put on every document read or saved (normalize), so a
new name there reaches existing boards. A card points at a column id. kind "start" marks where an application
enters the board, kind "closed" the column whose cards carry an outcome; every other column is "".
A card is {id, column, company, role, profile, variant, cvKind, cvNote, inbound, url, nextDate, posting,
closedReason, touchedOn, comments: [{at, text}], history: [{column, date}]}; only id, column, company and
history are required.
"""
import contextlib
import datetime
import json
import os
import re
import shutil
import tempfile
import threading

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DATA = os.path.join(HERE, "data", "applications.json")
SCHEMA_VERSION = 3
KEEP_BACKUPS = 30
MAX_CARDS = 5000
# The fixed list plus the old columns that still hold cards.
MAX_COLUMNS = 40
MAX_ERRORS = 10

# The one list of stages: every board shows these, in this order.
DEFAULT_COLUMNS = [
    {"id": "applied", "name": "Applied", "kind": "start", "hint": "Application sent, or a recruiter reached out"},
    {"id": "hr", "name": "HR screen", "kind": "", "hint": "Phone or video call with HR or a recruiter"},
    {"id": "manager", "name": "Hiring manager", "kind": "", "hint": "Engineering manager, manager or a team member"},
    {"id": "technical", "name": "Technical", "kind": "", "hint": "Live coding, debugging, system design"},
    {"id": "case", "name": "Case study", "kind": "",
     "hint": "Take-home: received, submitted, presented; set its deadline as the next step date"},
    {"id": "final", "name": "Final", "kind": "", "hint": "Culture fit, team meet, founders, CEO or N+2"},
    {"id": "offer", "name": "References & offer", "kind": "", "hint": "Reference or background check, offer, negotiation"},
    {"id": "closed", "name": "Closed", "kind": "closed", "hint": "Accepted, rejected, withdrew, ghosted or declined offer"},
]
# Column ids of earlier default lists -> current ids.
OLD_COLUMNS = {"screen": "hr", "interviews": "technical", "team": "manager"}
COLUMN_KINDS = ("", "start", "closed")

# Same keys as tracker/static/store.js; "" means not set.
CLOSED_REASONS = ("", "rejected", "withdrew", "ghosted", "declined", "accepted")
# "other": a CV from outside profiles/ (adapted by hand, or another kind of role), described in cvNote.
CV_KINDS = ("", "other")
ENUM_FIELDS = {"closedReason": CLOSED_REASONS, "cvKind": CV_KINDS}

# Free-text card fields and their maximum length.
TEXT_FIELDS = {"company": 200, "role": 200, "url": 2000, "profile": 64, "variant": 64, "cvNote": 200,
               "posting": 100000}
DATE_FIELDS = ("nextDate", "touchedOn")
CARD_KEYS = {"id", "column", "history", "comments", "inbound", *TEXT_FIELDS, *DATE_FIELDS, *ENUM_FIELDS}
# Fields of earlier versions: folded into one comment by normalize (labels in the order they are written).
LEGACY_TEXT = {"notes": "Notes", "nextStep": "Next step", "nextTime": "Interview time", "location": "Location",
               "salary": "Salary", "contact": "Contact", "source": "Source"}
LEGACY_DROPPED = ("initiator", "appliedOn")
MAX_HINT = 200
MAX_COMMENTS = 500
MAX_COMMENT = 5000

ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
DATETIME = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2}(\.\d{1,6})?)?(Z|[+-]\d{2}:\d{2})?$")


class Invalid(ValueError):
    """The document does not have the tracker shape."""


class Conflict(Exception):
    """The document changed since the client loaded it."""


class StoreError(Exception):
    """The data file on disk cannot be used."""


def data_path(arg=None, env=None):
    """--data, else TRACKER_DATA, else tracker/data/applications.json; ~ is expanded, a directory gets applications.json."""
    raw = os.path.expanduser(arg or env or DEFAULT_DATA)
    if os.path.isdir(raw) or raw.endswith(("/", os.sep)):
        raw = os.path.join(raw, "applications.json")
    return os.path.abspath(raw)


def default_document():
    return {"schemaVersion": SCHEMA_VERSION, "columns": [dict(c) for c in DEFAULT_COLUMNS], "cards": [],
            "updatedAt": None}


def _upgrade_card(card, rename):
    """Maps old column ids, drops step labels, folds the fields of earlier versions into first comments."""
    card = dict(card, column=rename(card.get("column")))
    if isinstance(card.get("history"), list):
        card["history"] = [{"column": rename(h.get("column")), "date": h.get("date")} if isinstance(h, dict) else h
                           for h in card["history"]]
    if card.get("initiator") == "inbound":
        card["inbound"] = True
    lines = [f"{label}: {str(card[k]).strip()}" for k, label in LEGACY_TEXT.items()
             if card.get(k) not in (None, "") and str(card[k]).strip()]
    for k in [*LEGACY_TEXT, *LEGACY_DROPPED]:
        card.pop(k, None)
    if lines:
        history = card.get("history") if isinstance(card.get("history"), list) else []
        first = history[0].get("date") if history and isinstance(history[0], dict) else None
        day = first if isinstance(first, str) and DATE.match(first) else datetime.date.today().isoformat()
        comments = card.get("comments") if isinstance(card.get("comments"), list) else []
        card["comments"] = [{"at": f"{day}T12:00:00Z", "text": text} for text in _chunks(lines)] + comments
    return card


def _chunks(lines):
    """Joins lines into texts of at most MAX_COMMENT characters; a longer line is split, nothing is cut."""
    texts, current = [], ""
    for line in lines:
        for i in range(0, len(line), MAX_COMMENT):
            piece = line[i:i + MAX_COMMENT]
            if current and len(current) + 1 + len(piece) > MAX_COMMENT:
                texts.append(current)
                current = ""
            current = f"{current}\n{piece}" if current else piece
    return texts + [current] if current else texts


def normalize(doc):
    """Brings a document of any earlier version to the current one; no card and no text is dropped.

    The columns become DEFAULT_COLUMNS; a card in a column that is no longer a default keeps it, as an extra
    column before the closed one. A document of an unknown version passes as it is, and validate refuses it.
    """
    if not (isinstance(doc, dict) and doc.get("schemaVersion") in range(1, SCHEMA_VERSION + 1)
            and isinstance(doc.get("columns"), list) and isinstance(doc.get("cards"), list)
            and all(isinstance(c, dict) for c in doc["columns"] + doc["cards"])):
        return doc

    def rename(cid):
        return OLD_COLUMNS.get(cid, cid)

    cards = [_upgrade_card(card, rename) for card in doc["cards"]]
    stored = {rename(c.get("id")): c.get("name") for c in doc["columns"]}
    columns = [dict(c) for c in DEFAULT_COLUMNS]
    for cid in dict.fromkeys(c["column"] for c in cards):
        if isinstance(cid, str) and ID.match(cid) and cid not in {c["id"] for c in columns}:
            name = stored.get(cid) if isinstance(stored.get(cid), str) and stored.get(cid).strip() else cid
            columns.insert(-1, {"id": cid, "name": name[:60], "kind": ""})
    return dict(doc, schemaVersion=SCHEMA_VERSION, columns=columns, cards=cards)


def _check_date(value, where, errors):
    if value != "" and not (isinstance(value, str) and DATE.match(value)):
        errors.append(f"{where} must be a YYYY-MM-DD date or empty")


def _check_card(card, i, column_ids, seen, errors):
    where = f"cards[{i}]"
    if not isinstance(card, dict):
        errors.append(f"{where} must be an object")
        return
    unknown = sorted(set(card) - CARD_KEYS)
    if unknown:
        errors.append(f"{where} has unknown fields: {', '.join(unknown)}")
    cid = card.get("id")
    if not (isinstance(cid, str) and ID.match(cid)):
        errors.append(f"{where}.id must be 1 to 64 letters, digits, dash or underscore")
    elif cid in seen:
        errors.append(f"{where}.id {cid} is used twice")
    else:
        seen.add(cid)
    if card.get("column") not in column_ids:
        errors.append(f"{where}.column must be one of the column ids")
    if not (isinstance(card.get("company"), str) and card["company"].strip()):
        errors.append(f"{where}.company is required")
    for name, limit in TEXT_FIELDS.items():
        value = card.get(name, "")
        if not isinstance(value, str) or len(value) > limit:
            errors.append(f"{where}.{name} must be text of at most {limit} characters")
    for name in DATE_FIELDS:
        _check_date(card.get(name, ""), f"{where}.{name}", errors)
    if not isinstance(card.get("inbound", False), bool):
        errors.append(f"{where}.inbound must be true or false")
    for name, allowed in ENUM_FIELDS.items():
        if card.get(name, "") not in allowed:
            errors.append(f"{where}.{name} must be one of {', '.join(a for a in allowed if a)} or empty")
    comments = card.get("comments", [])
    if not (isinstance(comments, list) and len(comments) <= MAX_COMMENTS):
        errors.append(f"{where}.comments must be a list of at most {MAX_COMMENTS} comments")
    else:
        for j, comment in enumerate(comments):
            if not (isinstance(comment, dict) and set(comment) == {"at", "text"} and isinstance(comment["at"], str)
                    and DATETIME.match(comment["at"]) and isinstance(comment["text"], str)
                    and 0 < len(comment["text"].strip()) and len(comment["text"]) <= MAX_COMMENT):
                errors.append(f"{where}.comments[{j}] must be {{at: ISO date and time, text: 1 to {MAX_COMMENT} characters}}")
    history = card.get("history")
    if not (isinstance(history, list) and history):
        errors.append(f"{where}.history must list at least the first stage")
        return
    for j, step in enumerate(history):
        if not (isinstance(step, dict) and set(step) == {"column", "date"}
                and isinstance(step["column"], str) and ID.match(step["column"])):
            errors.append(f"{where}.history[{j}] must be {{column, date}}")
        else:
            _check_date(step["date"], f"{where}.history[{j}].date", errors)


def validate(doc):
    """Raises Invalid with the first problems found when doc is not a tracker document."""
    if not isinstance(doc, dict):
        raise Invalid("the document must be a JSON object")
    errors = []
    unknown = sorted(set(doc) - {"schemaVersion", "columns", "cards", "updatedAt"})
    if unknown:
        errors.append(f"unknown fields: {', '.join(unknown)}")
    if doc.get("schemaVersion") != SCHEMA_VERSION:
        errors.append(f"schemaVersion must be {SCHEMA_VERSION}")
    if not (doc.get("updatedAt") is None or isinstance(doc.get("updatedAt"), str)):
        errors.append("updatedAt must be text or null")
    columns = doc.get("columns")
    column_ids = set()
    if not (isinstance(columns, list) and 0 < len(columns) <= MAX_COLUMNS):
        errors.append(f"columns must list 1 to {MAX_COLUMNS} columns")
    else:
        kinds = []
        for i, col in enumerate(columns):
            if not (isinstance(col, dict) and {"id", "name", "kind"} <= set(col) <= {"id", "name", "kind", "hint"}
                    and isinstance(col["id"], str) and ID.match(col["id"]) and isinstance(col["name"], str)
                    and 0 < len(col["name"].strip()) <= 60 and col["kind"] in COLUMN_KINDS
                    and isinstance(col.get("hint", ""), str) and len(col.get("hint", "")) <= MAX_HINT):
                errors.append(f"columns[{i}] must be {{id, name, kind, hint}} with a name of 1 to 60 characters, "
                              f"a kind of start, closed or empty, and a hint of at most {MAX_HINT} characters")
            elif col["id"] in column_ids:
                errors.append(f"columns[{i}].id {col['id']} is used twice")
            else:
                column_ids.add(col["id"])
                kinds.append(col["kind"])
        for kind in ("start", "closed"):
            if kinds.count(kind) != 1:
                errors.append(f"columns must have exactly one column of kind {kind}")
    cards = doc.get("cards")
    if not (isinstance(cards, list) and len(cards) <= MAX_CARDS):
        errors.append(f"cards must be a list of at most {MAX_CARDS} cards")
    else:
        seen = set()
        for i, card in enumerate(cards):
            _check_card(card, i, column_ids, seen, errors)
            if len(errors) >= MAX_ERRORS:
                break
    if errors:
        raise Invalid("; ".join(errors[:MAX_ERRORS]))


def _now(previous):
    """A new revision, never equal to the previous one."""
    stamp = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="microseconds")
    return stamp if stamp != previous else stamp + "+1"


class Store:
    """The data file, its backups/ folder next to it, and a lock that makes check-then-write one step."""

    def __init__(self, path, keep=KEEP_BACKUPS):
        self.path = os.path.abspath(path)
        self.backup_dir = os.path.join(os.path.dirname(self.path), "backups")
        self.keep = keep
        self._lock = threading.Lock()
        os.makedirs(os.path.dirname(self.path), exist_ok=True)

    def load(self):
        """The saved document, or the default board when there is no file yet."""
        try:
            with open(self.path, encoding="utf-8") as f:
                doc = json.load(f)
        except FileNotFoundError:
            return default_document()
        except ValueError as e:
            raise StoreError(f"{self.path} is not valid JSON ({e}); restore a copy from {self.backup_dir}")
        doc = normalize(doc)
        try:
            validate(doc)
        except Invalid as e:
            raise StoreError(f"{self.path} is not a tracker document ({e}); restore a copy from {self.backup_dir}")
        return doc

    def save(self, doc):
        """Writes doc when its updatedAt is the saved one; returns it with its new updatedAt and the fixed columns."""
        doc = normalize(doc)
        validate(doc)
        with self._lock:
            current = self.load()
            if doc.get("updatedAt") != current.get("updatedAt"):
                raise Conflict("the board changed since it was loaded (another tab or device); reload it")
            saved = dict(doc, updatedAt=_now(current.get("updatedAt")))
            self._backup()
            self._write(saved)
        return saved

    def _backup(self):
        """Copies the current file to backups/<name>-<UTC time>.json and keeps the newest self.keep copies."""
        if not os.path.exists(self.path):
            return
        os.makedirs(self.backup_dir, exist_ok=True)
        stem = os.path.splitext(os.path.basename(self.path))[0]
        stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
        shutil.copy2(self.path, os.path.join(self.backup_dir, f"{stem}-{stamp}.json"))
        copies = sorted(n for n in os.listdir(self.backup_dir) if n.startswith(stem + "-") and n.endswith(".json"))
        for name in copies[:-self.keep] if self.keep else copies:
            os.remove(os.path.join(self.backup_dir, name))

    def _write(self, doc):
        """Writes to a temp file in the same folder, then renames it over the data file."""
        folder, name = os.path.split(self.path)
        fd, tmp = tempfile.mkstemp(prefix=f".{name}.", suffix=".tmp", dir=folder)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(doc, f, ensure_ascii=False, indent=1)
                f.write("\n")
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, self.path)
        except BaseException:
            with contextlib.suppress(FileNotFoundError):
                os.unlink(tmp)
            raise
