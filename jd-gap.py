#!/usr/bin/env python3
"""Lists what a job posting asks for that a CV variant does not say.

Usage: pbpaste | ./jd-gap.py --profile <you> --variant A
       ./jd-gap.py --profile <you> --variant B posting.txt
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import unicodedata
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))

# Equivalent spellings -> one canonical term, in both languages. Meant to grow:
# add a line whenever a posting says something the CV says in other words.
ALIASES = {
    "kubernetes": ["k8s"],
    "infrastructure as code": ["iac", "infra as code"],
    "load testing": ["tests de charge", "tests de performance", "test de charge", "performance testing",
                     "load tests", "tests de montee en charge"],
    "observability": ["observabilite"],
    "monitoring": ["supervision"],
    "incident management": ["gestion des incidents", "gestion d'incidents", "gestion d'incident",
                            "incident response", "incidents de production"],
    "on-call": ["astreinte", "astreintes", "on call"],
    "ci/cd": ["integration continue", "deploiement continu", "cicd", "ci-cd", "ci", "cd"],
    "test automation": ["tests automatises", "automatisation des tests", "automated testing",
                        "automatisation de tests", "test automatise"],
    "test strategy": ["strategie de test", "strategie de tests", "strategie qualite"],
    "test plan": ["plan de test", "plan de tests", "plans de test"],
    "post-mortem": ["postmortem", "rca", "root cause analysis", "analyse de cause racine"],
    "aws": ["amazon web services"],
    "gcp": ["google cloud", "google cloud platform"],
    "azure": ["microsoft azure"],
    "e2e testing": ["e2e", "end-to-end", "tests de bout en bout", "end to end", "tests end-to-end"],
    "api testing": ["tests d'api", "tests api", "test d'api", "tests d'apis"],
    "regression testing": ["tests de non-regression", "tests de regression", "non-regression", "regression"],
    "high availability": ["haute disponibilite"],
    "disaster recovery": ["plan de reprise d'activite", "pra"],
    "capacity planning": ["planification de capacite"],
    "finops": ["optimisation des couts"],
    "security": ["securite"],
    "security testing": ["tests de securite"],
    "mobile testing": ["tests mobiles", "tests mobile"],
    "quality kpis": ["kpi qualite", "kpis qualite", "indicateurs qualite", "quality kpi"],
    "code review": ["revue de code", "revues de code", "code reviews"],
    "mentoring": ["mentorat", "mentorer", "encadrer", "mentored"],
    "networking": ["reseau", "reseaux"],
    "containers": ["conteneurs", "conteneurisation", "containerization"],
    "bdd": ["behavior driven development"],
    "english": ["anglais"],
    "french": ["francais"],
    "reliability": ["fiabilite"],
    "pci dss": ["pci-dss"],
    "go": ["golang"],
    "postgresql": ["postgres"],
    "elk": ["elastic stack"],
}

TOOLS = {
    "kubernetes", "docker", "helm", "argocd", "flux", "terraform", "pulumi", "ansible", "packer", "vault",
    "consul", "istio", "linkerd", "nginx", "envoy", "aws", "gcp", "azure", "gke", "eks", "aks", "openstack",
    "lambda", "sqs", "s3", "aurora", "iam", "ci/cd", "gitlab ci", "github actions", "jenkins", "circleci",
    "azure devops", "gitlab", "github", "git", "prometheus", "grafana", "loki", "tempo", "jaeger",
    "opentelemetry", "datadog", "new relic", "dynatrace", "splunk", "elk", "elasticsearch", "kibana",
    "sentry", "pagerduty", "opsgenie", "incident.io", "checkly", "python", "go", "bash", "java", "kotlin",
    "typescript", "javascript", "node.js", "c++", "c#", ".net", "php", "ruby", "rust", "scala", "sql",
    "postgresql", "mysql", "mongodb", "redis", "kafka", "rabbitmq", "linux", "playwright", "cypress",
    "selenium", "pytest", "k6", "jmeter", "gatling", "locust", "postman", "jira", "xray", "testrail",
    "gherkin", "cucumber", "appium", "rest", "graphql", "grpc", "tsuga", "argo", "keda", "cloudflare",
}

SKILLS = {
    "infrastructure as code", "observability", "monitoring", "incident management", "on-call",
    "test automation", "test strategy", "test plan", "post-mortem", "e2e testing", "api testing",
    "regression testing", "high availability", "disaster recovery", "capacity planning", "finops",
    "security", "security testing", "mobile testing", "quality kpis", "code review", "mentoring",
    "networking", "containers", "bdd", "tdd", "english", "french", "load testing", "slo", "sli", "sla",
    "error budget", "service mesh", "chaos engineering", "load balancing", "gitops", "devops", "sre", "agile", "scrum",
    "shift-left", "risk-based testing", "quality gates", "release management", "microservices", "cloud",
    "automation", "scripting", "multi-cloud", "dns", "tcp/ip", "reliability", "pci dss", "qa", "sdet",
}

# Multi-word terms kept as one unit even without an alias.
PHRASES = {t for t in TOOLS | SKILLS if " " in t}

MUST = re.compile(r"\b(requis|requise|indispensable|obligatoire|imperatif|maitrise|maitriser|must|required|"
                  r"mandatory|requirements|\d+\+? ans d.experience|\d+\+? years)\b")
NICE = re.compile(r"\b(un plus|est un plus|apprecie|appreciee|apprecies|appreciees|nice to have|bonus|atout|"
                  r"idealement|souhaite|souhaitee|preferred|a plus|petit plus)\b")

STOPWORDS = set("""
a au aux avec ce ces cet cette d dans de des du elle en et eux il ils je la le les leur leurs lui ma mais me
meme mes moi mon ne nos notre ou par pas pour qu que qui sa se ses son sur ta te tes toi ton tu un une vos
votre y l n s c j m t est sont etre avoir a ont sera seront serait ainsi aussi tout tous toute toutes tres
plus moins comme sans sous chez entre vers afin dont si ni car or donc puis deja encore autre autres chaque
plusieurs certains quelques
the and or of to in on for with by at from as an be is are was were will would can could should this that
these those it its our your their we you they he she his her them us not no but if than then so such into
about over under via per all any each other more most some own same also only both well very
""".split())

GENERIC = set("""
equipe equipes team teams projet projets project projects nous vous mission missions poste entreprise
entreprises company companies societe client clients produit produits product products service services
environnement environnements cadre sein ensemble travail work role profil profile candidat candidate
experience experiences connaissance connaissances competence competences skill skills an ans annee annees
year years niveau bonne bonnes bon bons fort forte solide excellente excellent capacite sens esprit gout
envie rejoindre join offre avantages teletravail remote salaire cdi cdd h/f f/h paris lyon france jour
jours semaine personnes personne utilisateurs users minimum professionnel courant notions notion
concevoir mettre place assurer participer contribuer accompagner garantir ameliorer developper maintenir
piloter definir travailler faire construire structurer suivre rediger integrer operer animer outiller
automatiser cherchons recherche recherchons recherche pourquoi dont tant lead hands-on vraie vrai culture
budget formation rtt mutuelle carte prise charge partiel bienveillante scale-up startup fintech saas b2b
b2c pme eti rh ce h f po pm minimum maitrise requis indispensable apprecie appreciees appreciee plus atout bonus
nice have must required preferred petit seraient serait idealement souhaite secteur norme taille
production qualite quality engineers engineer ingenieur developpement development outils tools
plateforme platform infrastructure clusters cluster millions milliers synthetic sample invented job posting
real offer
""".split())

# Tokens that are only a term when written this way (Go the language, REST the API style).
CASE_SENSITIVE = {"go": "Go", "rest": "REST"}

# "Go/No Go" is a release decision, not the Go language.
NO_GO = re.compile(r"\bGo\s*/\s*No[ -]?Go\b", re.IGNORECASE)

TOKEN = re.compile(r"(?:(?<![a-z0-9])\.)?[a-z0-9][a-z0-9+#./'-]*[a-z0-9+#]|[a-z0-9]", re.I)
SEGMENT_BREAK = re.compile(r"[,;:!?()\[\]|\u2022]+|\.(?=\s|$)|\s[-\u2013\u2014/]\s")
BULLET = re.compile(r"^\s*[-*\u2022\u2013]\s*")


def fold(text):
    """Strips accents and unifies apostrophes and dashes, keeping case."""
    text = text.replace("\u2019", "'").replace("\u2018", "'").replace("\u2013", "-").replace("\u00a0", " ")
    text = unicodedata.normalize("NFKD", text)
    return "".join(c for c in text if not unicodedata.combining(c))


def key(term):
    """Matching key: lowercase, light plural strip per word."""
    return " ".join(w[:-1] if len(w) > 3 and w.endswith("s") and not w.endswith("ss") else w
                    for w in term.lower().split())


def split_token(tok):
    """Splits elisions (l'equipe) and unknown slash or dot compounds (Helm/ArgoCD)."""
    parts = []
    for p in tok.split("'"):
        for piece in [p] if is_term(p) else p.split("/"):
            if "." in piece.strip(".") and not is_term(piece):
                parts.extend(x for x in piece.split(".") if x)
            elif piece:
                parts.append(piece)
    return parts


def is_term(tok):
    low = tok.lower()
    return low in TOOLS or low in SKILLS or low in LOOKUP


def build_lookup():
    lookup = {}
    for canon, variants in ALIASES.items():
        for v in variants + [canon]:
            lookup[key(" ".join(tokenize_plain(v)))] = canon
    for p in PHRASES:
        lookup.setdefault(key(" ".join(tokenize_plain(p))), p)
    return lookup


def tokenize_plain(text):
    return [t.lower() for m in TOKEN.finditer(fold(text)) for t in m.group(0).split("'") if t]


LOOKUP = build_lookup()
KNOWN = TOOLS | SKILLS | set(LOOKUP.values())
MAX_PHRASE = max(len(k.split()) for k in LOOKUP)


def units(segment, starts_sentence):
    """Turns one text segment into a list of (canonical term, surface form, looks like a tool)."""
    toks = []
    for m in TOKEN.finditer(segment):
        before = segment[:m.start()].rstrip()
        at_start = (starts_sentence and not before) or before.endswith((".", "!", "?", ":", "-"))
        for p in split_token(m.group(0)):
            toks.append((p, at_start))
            at_start = False
    out, i = [], 0
    while i < len(toks):
        for n in range(min(MAX_PHRASE, len(toks) - i), 0, -1):
            words = [t.lower() for t, _ in toks[i:i + n]]
            canon = LOOKUP.get(key(" ".join(words)))
            if canon is None or (n == 1 and words[0] in CASE_SENSITIVE and toks[i][0] != CASE_SENSITIVE[words[0]]):
                continue
            surface = " ".join(t for t, _ in toks[i:i + n])
            out.append((canon, surface, 2))
            i += n
            break
        else:
            tok, at_start = toks[i]
            low = tok.lower()
            if low in CASE_SENSITIVE and tok != CASE_SENSITIVE[low]:
                low = ""
            out.append((low, tok, looks_like_tool(tok, at_start)))
            i += 1
    return out


def looks_like_tool(tok, at_start):
    """2: tech-shaped (C++, k8s, GitLab, AWS), 1: only capitalized mid-sentence (Ansible, or a company name), 0: no."""
    if any(c in tok for c in "+#./") or any(c.isdigit() for c in tok):
        return 2
    if (len(tok) >= 2 and tok.isupper()) or any(c.isupper() for c in tok[1:]):
        return 2
    return 1 if not at_start and tok[:1].isupper() else 0


def is_noise(term):
    return (not term or term in STOPWORDS or term in GENERIC or len(term) < 2
            or not any(c.isalpha() for c in term))


def segments(text):
    """Yields (segment, starts a line) for each line, split at punctuation."""
    for line in text.splitlines():
        body = BULLET.sub("", line)
        for j, seg in enumerate(SEGMENT_BREAK.split(body)):
            if seg.strip():
                yield seg, j == 0


def line_modes(text):
    """Maps each line to 'must', 'nice' or '' from its own markers or its section header."""
    modes, section = [], ""
    for line in text.splitlines():
        low = line.lower()
        own = "must" if MUST.search(low) else "nice" if NICE.search(low) else ""
        is_header = line.strip() and not BULLET.match(line) and (len(low.split()) <= 6 or low.rstrip().endswith(":"))
        if is_header:
            section = own
        modes.append(own or section)
    return modes


def extract(text):
    """Returns posting terms {canonical: stats}, n-gram counts and the line modes each n-gram appeared in."""
    text = NO_GO.sub("go-no-go", fold(text))
    terms = {}
    grams = Counter()
    gram_lines = {}
    for line, mode in zip(text.splitlines(), line_modes(text)):
        for seg, first in segments(line):
            us = units(seg, first)
            for canon, surface, tool in us:
                if is_noise(canon):
                    continue
                t = terms.setdefault(canon, {"count": 0, "surface": Counter(), "tool": 0, "known": canon in KNOWN,
                                             "must": False, "nice": False})
                t["count"] += 1
                t["surface"][surface] += 1
                t["tool"] = max(t["tool"], tool)
                t["must"] = t["must"] or mode == "must"
                t["nice"] = t["nice"] or mode == "nice"
            words = [c for c, _, _ in us]
            for n in (2, 3):
                for i in range(len(words) - n + 1):
                    g = words[i:i + n]
                    if is_noise(g[0]) or is_noise(g[-1]) or any(not w for w in g):
                        continue
                    phrase = " ".join(g)
                    grams[phrase] += 1
                    gram_lines.setdefault(phrase, set()).add(mode)
    return terms, grams, gram_lines


def cv_keys(cv):
    """Every matching key of 1 to 3 units the CV text contains."""
    strings = []

    def walk(node):
        if isinstance(node, str):
            strings.append(NO_GO.sub("go-no-go", fold(node)))
        elif isinstance(node, list):
            for x in node:
                walk(x)
        elif isinstance(node, dict):
            for k, x in node.items():
                if k not in ("contact", "name", "label"):
                    walk(x)

    walk(cv)
    keys = set()
    for s in strings:
        for seg, first in segments(fold(s)):
            words = [c for c, _, _ in units(seg, first) if c]
            for n in (1, 2, 3):
                for i in range(len(words) - n + 1):
                    keys.add(key(" ".join(words[i:i + n])))
    return keys


def load_cv(profile, variant):
    """Returns (variant id, variant) from profiles/<profile>/content.js; no variant means the first one."""
    node = shutil.which("node")
    if not node:
        sys.exit("jd-gap: node not found in PATH, it is needed to read content.js (brew install node)")
    res = subprocess.run([node, os.path.join(HERE, "read-profile.js"), profile], capture_output=True, text=True)
    if res.returncode != 0:
        sys.exit("jd-gap: " + res.stderr.strip())
    cvs = json.loads(res.stdout)["variants"]
    variant = variant or next(iter(cvs))
    if variant not in cvs:
        sys.exit("jd-gap: variant %s not in profile %s (has %s)" % (variant, profile, ", ".join(cvs)))
    return variant, cvs[variant]


def analyse(text, cv):
    terms, grams, gram_lines = extract(text)
    have = cv_keys(cv)
    # Multi-word phrases count when repeated in the posting or written the same way in the CV.
    for phrase, count in grams.items():
        if phrase in terms or not (count >= 2 or key(phrase) in have):
            continue
        modes = gram_lines[phrase]
        terms[phrase] = {"count": count, "surface": Counter({phrase: count}), "tool": 0, "known": True,
                         "must": "must" in modes, "nice": "nice" in modes}
        for w in phrase.split():
            if w in terms and not terms[w]["known"]:
                terms[w]["count"] -= count
    kept = {}
    for canon, t in terms.items():
        if t["count"] <= 0:
            continue
        # Unknown lowercase words are only terms when the posting repeats them.
        if not t["known"] and not t["tool"] and t["count"] < 2:
            continue
        if canon in SKILLS:
            t["kind"] = "skills"
        elif canon in TOOLS or t["tool"] == 2:
            t["kind"] = "tools"
        else:
            t["kind"] = "skills" if not t["tool"] else "other"
        t["matched"] = key(canon) in have
        kept[canon] = t
    return kept


def label(canon, t):
    surface = t["surface"].most_common(1)[0][0]
    return surface if surface.lower() == canon else canon


def rank(t):
    return (0 if t["must"] else 2 if t["nice"] and not t["must"] else 1, -t["count"])


def report(terms, variant, headline):
    matched = {c: t for c, t in terms.items() if t["matched"]}
    missing = {c: t for c, t in terms.items() if not t["matched"]}
    scored = [t for t in terms.values() if t["kind"] != "other"]
    hits = sum(1 for t in scored if t["matched"])
    score = round(100.0 * hits / len(scored)) if scored else 0
    print("jd-gap: posting vs CV %s (%s)" % (variant, headline))
    print("Match score: %d%% (%d of %d tool and skill terms in the CV)" % (score, hits, len(scored)))
    print()
    print("Matched (%d)" % len(matched))
    for kind in ("tools", "skills", "other"):
        names = [label(c, t) for c, t in sorted(matched.items(), key=lambda x: rank(x[1])) if t["kind"] == kind]
        if names:
            print("  %-7s %s" % (kind + ":", ", ".join(names)))
    print()
    print("Missing (%d), must-have first, then by count in the posting" % len(missing))
    for kind in ("tools", "skills"):
        rows = sorted(((c, t) for c, t in missing.items() if t["kind"] == kind), key=lambda x: rank(x[1]))
        if not rows:
            continue
        print("  %s:" % kind)
        for c, t in rows:
            tag = "must" if t["must"] else "nice" if t["nice"] else ""
            print(("    %-24s x%-2d %s" % (label(c, t), t["count"], tag)).rstrip())
    other = [label(c, t) for c, t in missing.items() if t["kind"] == "other"]
    if other:
        print("  other names, not scored (a tool, or a company or place?): %s" % ", ".join(other))
    print()
    print("Add a missing term to content.js only if it is true.")


def default_profile():
    """First profile directory not starting with _, else the _template example."""
    root = os.path.join(os.path.dirname(os.path.abspath(__file__)), "profiles")
    ids = sorted(d for d in os.listdir(root) if not d.startswith("_") and os.path.isdir(os.path.join(root, d)))
    return ids[0] if ids else "_template"


def main():
    parser = argparse.ArgumentParser(description="Lists what a job posting asks for that a CV variant does not say.")
    parser.add_argument("--profile", default=default_profile(),
                        help="profile id, a directory under profiles/ (default: the first one not starting with _)")
    parser.add_argument("--variant", help="variant id in the profile (default: its first variant)")
    parser.add_argument("posting", nargs="?", help="posting text file (default: stdin)")
    args = parser.parse_args()
    if args.posting:
        with open(args.posting, encoding="utf-8") as f:
            text = f.read()
    elif sys.stdin.isatty():
        parser.error("no posting: pass a file or pipe the text in (pbpaste | ./jd-gap.py --profile <you> --variant A)")
    else:
        text = sys.stdin.read()
    variant, cv = load_cv(args.profile, args.variant)
    report(analyse(text, cv), variant, cv.get("headline", ""))


if __name__ == "__main__":
    main()
