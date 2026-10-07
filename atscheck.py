"""Stamps the PDF metadata of each built variant of a profile and checks the text an ATS extracts from it.

Usage: python3 atscheck.py <profile> [variant ...]   (default: every variant of the profile)
Reads out/<profile>/<fileStem>-<v>.pdf, writes snapshots/<profile>/<fileStem>-<v>.txt.
"""
import difflib
import json
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
BAD_CHARS = re.compile("[\ufb00-\ufb06\ue000-\uf8ff]")
DIFF_LINES = 10



def run(*cmd):
    try:
        return subprocess.run(cmd, capture_output=True, check=True).stdout.decode("utf-8")
    except FileNotFoundError:
        raise SystemExit(f"{cmd[0]} not found: install node and poppler (pdftotext, pdfinfo)")
    except subprocess.CalledProcessError as e:
        raise SystemExit(e.stderr.decode("utf-8").strip() or f"{cmd[0]} failed")


def ascii_safe(s):
    return s.encode("ascii", "backslashreplace").decode("ascii")


def load_profile(profile_id):
    return json.loads(run("node", os.path.join(ROOT, "read-profile.js"), profile_id))


def split_terms(value):
    """'GCP (GKE, Artifact Registry), Helm' -> ['GCP', 'GKE', 'Artifact Registry', 'Helm']"""
    terms = []
    for item in re.split(r",(?![^()]*\))", value):
        m = re.fullmatch(r"(.*?)\s*\((.*)\)", item.strip())
        if m:
            terms.append(m.group(1))
            terms += m.group(2).split(",")
        else:
            terms.append(item)
    return [t.strip() for t in terms if t.strip()]


def must_have_terms(cv):
    terms = [cv["headline"], *cv["tagline"]]
    for _, value in cv["skills"]:
        terms += split_terms(value)
    return list(dict.fromkeys(terms))


def keywords(cv):
    firsts = [split_terms(value)[0] for label, value in cv["skills"] if label != "Languages"]
    seen, out = set(), []
    for k in [*cv["tagline"], *firsts]:
        if k.lower() not in seen:
            seen.add(k.lower())
            out.append(k)
    return ", ".join(out)


def pdf_string(s):
    if s.isascii():
        return "(" + s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)") + ")"
    return "<FEFF" + s.encode("utf-16-be").hex().upper() + ">"


def stamp_info(pdf, fields):
    """Adds fields to the Info dict through a PDF incremental update; the bytes Chrome wrote stay untouched."""
    data = open(pdf, "rb").read()
    if data.count(b"%%EOF") != 1:
        return "already stamped"
    m = re.search(rb"trailer\s*<<(.*?)>>\s*startxref\s*(\d+)\s*%%EOF\s*$", data, re.S)
    if not m:
        raise SystemExit(f"{pdf}: no classic xref trailer, cannot stamp metadata")
    trailer, prev = m.group(1).decode("latin-1"), int(m.group(2))
    size = re.search(r"/Size (\d+)", trailer).group(1)
    root = re.search(r"/Root (\d+ \d+ R)", trailer).group(1)
    num, gen = re.search(r"/Info (\d+) (\d+) R", trailer).groups()
    info = re.search(rb"(?<!\d)%s %s obj\s*<<(.*?)>>\s*endobj" % (num.encode(), gen.encode()), data, re.S)
    body = info.group(1).decode("latin-1")
    body += "".join(f"\n/{k} {pdf_string(v)}" for k, v in fields.items() if f"/{k} " not in body)
    if not data.endswith(b"\n"):
        data += b"\n"
    obj = f"{num} {gen} obj\n<<{body}>>\nendobj\n".encode("latin-1")
    xref_at = len(data) + len(obj)
    tail = (
        f"xref\n{num} 1\n{len(data):010d} {int(gen):05d} n \n"
        f"trailer\n<</Size {size}\n/Root {root}\n/Info {num} {gen} R\n/Prev {prev}>>\n"
        f"startxref\n{xref_at}\n%%EOF\n"
    )
    open(pdf, "wb").write(data + obj + tail.encode("latin-1"))
    return "stamped"


def pdf_info(pdf):
    return dict(line.split(":", 1) for line in run("pdfinfo", pdf).splitlines() if ":" in line)


def snapshot_diff(rel, text):
    """Summary of the snapshot change versus the version committed at HEAD."""
    try:
        old = subprocess.run(["git", "-C", ROOT, "show", f"HEAD:{rel}"], capture_output=True)
    except FileNotFoundError:
        return ["new snapshot (git not found)"]
    if old.returncode != 0:
        return ["new snapshot, not committed yet"]
    diff = [
        line for line in difflib.unified_diff(old.stdout.decode("utf-8").splitlines(), text.splitlines(), lineterm="", n=0)
        if line[:1] in "+-" and line[:3] not in ("+++", "---")
    ]
    if not diff:
        return ["unchanged vs HEAD"]
    added = sum(1 for line in diff if line[0] == "+")
    out = [f"changed vs HEAD: +{added} -{len(diff) - added} lines"]
    out += ["  " + ascii_safe(line) for line in diff[:DIFF_LINES]]
    if len(diff) > DIFF_LINES:
        out.append(f"  ... {len(diff) - DIFF_LINES} more")
    return out


def check(profile_id, stem, variant, cv):
    pdf = os.path.join(ROOT, "out", profile_id, f"{stem}-{variant}.pdf")
    if not os.path.exists(pdf):
        return [f"{pdf} not found"]
    author = cv["name"].title()
    title = f"{author} - {cv['headline']} CV"
    stamped = stamp_info(pdf, {"Author": author, "Subject": cv["headline"], "Keywords": keywords(cv)})
    print(f"{variant}: metadata {stamped}")

    errors = []
    info = {k.strip(): v.strip() for k, v in pdf_info(pdf).items()}
    if info.get("Pages") != "1":
        errors.append(f"{info.get('Pages')} pages, expected 1")
    if info.get("Title") != title:
        errors.append(f"PDF title is {ascii(info.get('Title', ''))}, expected {title!r}")
    if info.get("Tagged") != "yes":
        errors.append("PDF is not tagged")

    text = run("pdftotext", "-raw", "-enc", "UTF-8", pdf, "-")
    rel = f"snapshots/{profile_id}/{stem}-{variant}.txt"
    os.makedirs(os.path.join(ROOT, "snapshots", profile_id), exist_ok=True)
    with open(os.path.join(ROOT, rel), "w", encoding="utf-8", newline="") as f:
        f.write(text)
    for line in snapshot_diff(rel, text):
        print(f"{variant}: {line}")
    return errors + text_errors(text, cv)


def text_errors(text, cv):
    errors = []
    bad = sorted({f"U+{ord(c):04X}" for c in BAD_CHARS.findall(text)})
    if bad:
        errors.append("ligature or private-use characters: " + ", ".join(bad))
    email = cv["contact"]["email"]
    if email not in text:
        errors.append(f"email {ascii(email)} not found intact")
    if "OVERFLOW" in text:
        errors.append("OVERFLOW banner is in the text")
    flat = re.sub(r"\s+", " ", re.sub(r"-[ \t]*\n\s*", "-", text))
    for term in must_have_terms(cv):
        needle = re.sub(r"\s+", " ", term)
        if not re.search(r"(?<!\w)" + re.escape(needle) + r"(?!\w)", flat):
            errors.append(f"must-have term missing: {ascii(term)}")
    return errors


def main(profile_id, variants):
    profile = load_profile(profile_id)
    cvs = profile["variants"]
    unknown = [v for v in variants if v not in cvs]
    if unknown:
        raise SystemExit(f"variant {', '.join(unknown)} not in profile {profile_id} (has {', '.join(cvs)})")
    failed = False
    for v in variants or list(cvs):
        errors = check(profile_id, profile["fileStem"], v, cvs[v])
        for e in errors:
            print(f"FAIL {v}: {e}")
        failed = failed or bool(errors)
        if not errors:
            print(f"{v}: ATS check passed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit("usage: python3 atscheck.py <profile> [variant ...]")
    main(sys.argv[1], sys.argv[2:])
