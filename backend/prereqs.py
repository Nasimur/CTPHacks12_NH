"""Extract prerequisite edges for every course. Sources, highest priority first:

  0. CUNYfirst requirement groups (official; via the catalog API)   "PREQ: CSCI 313 AND MATH 231 with min grade of C"
  1. the current catalog's requisite text (customFields.Mmgow)        "Prereq.: C- or above in MATH 141 or 151."
  2. course descriptions                                              "builds on the work of English 110"
A regex parser handles the common forms with no API key. With GEMINI_API_KEY set, Gemini re-parses every
requirement group (and remaining prereq-less descriptions); its answer wins.
Ends with an audit of courses whose text names another course but got no prerequisite.

The 2020-21 Undergraduate Bulletin PDF used to sit between 1 and 2. It was dropped: it supplied only 36 of
1,986 prereq sources (CUNYfirst supplies 1,937), it was the sole reason this project needed `pdftotext`,
and being five years stale it contradicted the live catalog -- it claimed ACCT 100 requires BALA 100 (the
catalog says "BALA Minors Only", not a course) and that MATH 317 requires MATH 201 (the catalog says any
math course 200 or above), both false constraints enforced against students. Courses the live catalog is
silent about now fall through to `verified()` in server.py, which flags 200+ courses with no known
prerequisite for an advisor to confirm -- an honest "we don't know" beats a stale guess.

Usage:  python backend/prereqs.py   -> frontend/public/data/prereqs.json         {courseId: [[prereqId,...] (OR-group), ...]}
                                       frontend/public/data/coreqs.json          [courseId...]  may be taken the same term
                                       frontend/public/data/prereq_source.json   {courseId: "cunyfirst"|"catalog"|"description"|"gemini"}
Stdlib only.
"""
import json, os, re, sys, urllib.error, urllib.request
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "frontend" / "public" / "data"
MODEL = "gemini-3.6-flash"
BATCH = 60
PROMPT = """Each line below is "<id> | <course requisite text>" from a college catalog.
Extract the prerequisite and corequisite COURSES for each line.
Return ONLY JSON: {"<id>": {"pre": [["CSCI 313"], ["MATH 231"]], "co": [["MATH 152", "MATH 142"]]}}
- Outer list = AND; inner list = OR alternatives. "MATH 151 or 141" -> [["MATH 151", "MATH 141"]].
- "PRE:"/"PREQ:"/"PREREQ:" = pre; "CO:"/"COREQ:" = co; "PRE/CO:" = co (may be taken concurrently).
- Expand shorthand: "CSCI 211, 212, and 220" means CSCI 211, CSCI 212, CSCI 220 (same subject); "LCD 101/ANTH 108" means either.
- Codes look like "MATH 151" (subject, space, number, optional letter suffix).
- Ignore grades, GPA, standing, credits, "permission of instructor/department" and other non-course conditions.
- Omit lines with no course codes.

"""
CODE = re.compile(r"\b([A-Z]{2,5})? ?(\d{2,4}[A-Z]?)\b")
LABEL = re.compile(r"(PRE\s*/\s*CO(?:REQ)?|PREREQ|PREQ|PRE|Prereq\.?|COREQ|CO)\s*:", re.I)
ALIAS = {"english": "ENGL", "mathematics": "MATH", "math": "MATH", "computer science": "CSCI", "physics": "PHYS",
         "chemistry": "CHEM", "biology": "BIOL", "economics": "ECON", "psychology": "PSYCH", "spanish": "SPAN", "french": "FREN"}
CUE = re.compile(r"(?:builds? on|continuation of|sequel to|follows|requires?|prerequisites?:?|completion of|after taking)\b(.{0,80})", re.I)


def parse_clause(clause, subject):
    """'CSCI 220 and MATH 141 or 151' -> [['CSCI 220'], ['MATH 141', 'MATH 151']]"""
    clause = re.split(r"\.\s+(?=[A-Z][a-z])|;\s*(?=[A-Z][a-z])", clause, maxsplit=1)[0]   # stop at the next prose sentence
    clause = re.sub(r"\s*&\s*", " and ", clause)
    clause = re.sub(r"(?<=\d)\s*/\s*(?=[A-Z]{2,5} \d)", " or ", clause)                    # "LCD 101/ANTH 108"
    clause = re.sub(r"\bAND\b", "and", clause); clause = re.sub(r"\bOR\b", "or", clause)
    groups = []
    for part in re.split(r"\band\b|;", clause):
        codes = []
        for subj, num in CODE.findall(part):
            if subj:
                subject = subj
            elif not subject or "credit" in part.lower():
                continue
            codes.append(f"{subject} {num}")
        if codes:
            groups += [codes] if " or " in part else [[c] for c in codes]
    return groups


def parse_reqgroup(text, subject):
    """CUNYfirst text -> (pre_groups, co_groups). Segments are introduced by labels like 'PRE:', 'PRE/CO:', 'COREQ:'."""
    pre, co = [], []
    parts = LABEL.split(text)
    if len(parts) == 1:                                          # no label at all: treat as prerequisite prose
        return parse_clause(text, subject), []
    for label, body in zip(parts[1::2], parts[2::2]):
        groups = parse_clause(body, subject)
        (co if re.search(r"co", label, re.I) else pre).extend(groups)
    return pre, co


def gemini(text):
    key = os.environ["GEMINI_API_KEY"]
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent?key={key}"
    body = {"contents": [{"parts": [{"text": text}]}],
            "generationConfig": {"responseMimeType": "application/json", "temperature": 0}}
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"content-type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            return json.loads(json.load(r)["candidates"][0]["content"]["parts"][0]["text"])
    except urllib.error.HTTPError as e:
        sys.exit(f"Gemini HTTP {e.code}: {e.read().decode()[:400]}")


def gemini_batches(items):
    """items: [(id, text)] -> yields (id, {"pre": [...], "co": [...]})."""
    for i in range(0, len(items), BATCH):
        yield from gemini(PROMPT + "\n".join(f"{k} | {t}" for k, t in items[i:i + BATCH])).items()
        print(f"  gemini {min(i + BATCH, len(items))}/{len(items)}")


def resolve(groups, by_code):
    out = [[by_code[p] for p in g if p in by_code] for g in groups if isinstance(g, list)]
    return [g for g in out if g]


if __name__ == "__main__":
    courses = json.loads((DATA / "courses.json").read_text(encoding="utf8"))
    reqgroups = json.loads((DATA / "reqgroups.json").read_text(encoding="utf8")) if (DATA / "reqgroups.json").exists() else {}
    by_code = {c["code"]: c["id"] for c in courses}
    use_gemini = bool(os.environ.get("GEMINI_API_KEY"))
    out, coreqs, source = {}, set(), {}

    def record(cid, pre, co, src):
        """pre/co are code groups; co groups are prerequisites that may be satisfied in the same term."""
        pre, co = resolve(pre, by_code), resolve(co, by_code)
        if pre or co:
            out[cid] = pre + co
            source[cid] = src
            if co:
                coreqs.add(cid)
            return True
        return False

    # ---- 2) descriptions (lowest priority; applied first, overwritten by better sources) -------------------
    from_desc = 0
    for c in courses:
        text = c["description"]
        for name, subj in ALIAS.items():                          # "English 110" -> "ENGL 110"
            text = re.sub(rf"\b{name}\s+(\d)", rf"{subj} \1", text, flags=re.I)
        m = CUE.search(text)
        if m and record(c["id"], parse_clause(m.group(1), None), [], "description"):
            from_desc += 1
    print(f"descriptions: {from_desc}")

    # ---- 1) current catalog requisite text ------------------------------------------------------------------
    n = 0
    for c in courses:
        m = re.search(r"(Prereq[^:]*):\s*(.*)", c.get("prereq_text") or "")
        if m:
            groups = parse_clause(m.group(2), c["subject"])
            n += record(c["id"], [] if "coreq" in m.group(1).lower() else groups, groups if "coreq" in m.group(1).lower() else [], "catalog")
    print(f"catalog text: {n}")

    # ---- 0) CUNYfirst requirement groups (official) -----------------------------------------------------------
    n = 0
    for c in courses:
        text = reqgroups.get(c.get("rg") or "")
        if text:
            pre, co = parse_reqgroup(text, c["subject"])
            if record(c["id"], pre, co, "cunyfirst"):
                n += 1
            elif c["id"] not in source:
                source[c["id"]] = "cunyfirst"                     # e.g. "Junior standing": verified, no course prereq
    print(f"cunyfirst requirement groups: {n} courses with course prereqs, {sum(1 for c in courses if c.get('rg'))} courses have a group")

    if use_gemini:                                                # Gemini re-reads the official text; its parse wins
        items = [(c["id"], reqgroups[c["rg"]]) for c in courses if reqgroups.get(c.get("rg") or "")]
        for cid, r in gemini_batches(items):
            if isinstance(r, dict) and cid in out or isinstance(r, dict):
                record(cid, r.get("pre") or [], r.get("co") or [], "gemini")
        todo = [(c["id"], c["description"][:400]) for c in courses if c["id"] not in source and re.search(r"\b\d{3}\b", c["description"])]
        for cid, r in gemini_batches(todo):
            if isinstance(r, dict):
                record(cid, r.get("pre") or [], r.get("co") or [], "gemini")

    # ---- audit ------------------------------------------------------------------------------------------------
    gaps = [c["code"] for c in courses if c["id"] not in source and re.search(r"\b[A-Z]{2,5} \d{3}\b", c["prereq_text"] + " " + c["description"])]
    print(f"audit: {len(gaps)} courses mention another course but have no prereq source, e.g. {gaps[:10]}")
    from collections import Counter
    print("sources:", dict(Counter(source.values())))

    (DATA / "prereqs.json").write_text(json.dumps(out), encoding="utf8")
    (DATA / "coreqs.json").write_text(json.dumps(sorted(coreqs)), encoding="utf8")
    (DATA / "prereq_source.json").write_text(json.dumps(source), encoding="utf8")
    print(f"wrote {len(out)} courses with prereqs -> {DATA / 'prereqs.json'}")
