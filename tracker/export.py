"""CSV export of the board, one row per card: python3 tracker/server.py --export-csv applications.csv"""
import csv
import datetime

HEADER = ["Company", "Role", "Stage", "Outcome", "Stage reached", "Added on", "In stage since", "Days in stage",
          "Recruiter reached out", "CV sent", "Next step date", "Job link", "Comments", "Last comment", "History"]
OUTCOMES = {"accepted": "Accepted", "rejected": "Rejected", "withdrew": "Withdrew", "ghosted": "Ghosted",
            "declined": "Offer declined"}


def _cell(value):
    """A leading = + - @ is prefixed with ' so a spreadsheet does not run the cell as a formula."""
    text = str(value)
    return "'" + text if text[:1] in ("=", "+", "-", "@", "\t", "\r") else text


def cv_name(card, labels):
    """The CV sent as the tracker shows it; labels maps (profile, variant) to the label of GET /api/variants."""
    if card.get("cvKind") == "other":
        return "Other" + (f": {card['cvNote']}" if card.get("cvNote") else "")
    key = (card.get("profile", ""), card.get("variant", ""))
    return labels.get(key, " / ".join(key)) if all(key) else ""


def rows(doc, labels, today=None):
    today = today or datetime.date.today()
    names = {c["id"]: c["name"] for c in doc["columns"]}
    closed = next(c["id"] for c in doc["columns"] if c["kind"] == "closed")
    for card in doc["cards"]:
        history = card["history"]
        since = history[-1]["date"]
        reached = [h["column"] for h in history if h["column"] != closed]
        comments = sorted(card.get("comments", []), key=lambda c: c["at"])
        last = comments[-1] if comments else None
        yield [card["company"], card.get("role", ""), names.get(card["column"], card["column"]),
               OUTCOMES.get(card.get("closedReason", ""), ""),
               names.get(reached[-1], reached[-1]) if card["column"] == closed and reached else "",
               history[0]["date"], since, (today - datetime.date.fromisoformat(since)).days,
               "yes" if card.get("inbound") else "no", cv_name(card, labels), card.get("nextDate", ""),
               card.get("url", ""), len(comments), f"{last['at'][:10]} {last['text']}" if last else "",
               "; ".join(f"{h['date']} {names.get(h['column'], h['column'])}" for h in history)]


def write_csv(doc, labels, path):
    """Writes UTF-8 with a byte order mark, which spreadsheet apps need to read it as UTF-8; returns the row count."""
    count = 0
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        out = csv.writer(f)
        out.writerow(HEADER)
        for row in rows(doc, labels):
            out.writerow([_cell(v) for v in row])
            count += 1
    return count
