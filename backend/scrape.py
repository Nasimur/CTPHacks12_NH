"""Pull Queens College programs + courses from the Coursedog catalog API into static JSON.

Usage:  python backend/scrape.py            -> writes frontend/public/data/{programs,courses}.json
"""
import json, re, urllib.request
from pathlib import Path

SCHOOL = "qns01"
CATALOG = "RGWSZjseaUypaWsYUs4X"          # 2025-2026 Undergraduate Catalog
DATES = "2025-08-01,2026-08-01"
BASE = f"https://app.coursedog.com/api/v1/cm/{SCHOOL}"
HEADERS = {
    "content-type": "application/json",
    "x-requested-with": "catalog",
    "origin": "https://qc-undergraduate.catalog.cuny.edu",
    "referer": "https://qc-undergraduate.catalog.cuny.edu/",
}
OUT = Path(__file__).resolve().parent.parent / "frontend" / "public" / "data"


def search(kind, group, skip=0, limit=500):
    url = (f"{BASE}/{kind}/search/$filters?catalogId={CATALOG}&skip={skip}&limit={limit}"
           f"&effectiveDatesRange={DATES}&formatDependents=true")
    body = json.dumps({"condition": "and", "filters": [
        {"id": f"status-{group}", "name": "status", "inputType": "select", "group": group, "type": "is", "value": "Active"}]})
    req = urllib.request.Request(url, data=body.encode(), headers=HEADERS, method="POST")
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.load(r)


def fetch_all(kind, group):
    print(f"  {kind}: fetching...")
    first = search(kind, group)
    items, total = first["data"], first["listLength"]
    while len(items) < total:
        items += search(kind, group, skip=len(items))["data"]
        print(f"  {kind}: {len(items)}/{total}")
    return items


def strip_html(s, known={}):
    s = re.sub(r'<a [^>]*data-course-id="(\w+)"[^>]*>course</a>', lambda m: known.get(m.group(1), m.group(1)), s or "")
    return re.sub(r"<[^>]+>", "", s).replace("&nbsp;", " ").strip()


def flatten_rule(rule, known, sets):
    """Coursedog rule -> {kind, n, options:[[courseGroupId,...],...], set?} ; options = list of OR-groups, each ANDed.
    A rule may list courses directly or reference course sets (saved filters, e.g. "Computer Science Electives")."""
    val = rule.get("value")
    if not isinstance(val, dict) or val.get("condition") not in ("courses", "courseSets"):
        return None
    options, names = [], []
    for v in val.get("values", []):
        ids = v["value"] if isinstance(v, dict) else [v]
        if val["condition"] == "courseSets":                      # expand each set into one option per course
            for sid in ids:
                cset = sets.get(sid, {})
                names.append(cset.get("name", sid).strip())
                ids = [i for i in cset.get("dynamicCourseList", []) if i in known]
                options += [[i] for i in ids]
            continue
        ids = [i for i in ids if isinstance(i, str) and i in known]
        if ids:
            options.append(ids)
    if not options:
        return None
    # completedAllOf / minimumGrade over a course list = every option; completedAtLeastXOf carries `restriction`
    n = rule.get("restriction") or rule.get("credits") or len(options)
    out = {"kind": "credits" if rule["condition"] == "minimumCredits" else "count", "n": n, "options": options}
    if names:
        out["set"] = " / ".join(names)
    return out


def flatten_rules(rules, known, sets):
    out = []
    for r in rules or []:
        if r.get("subRules"):
            out += flatten_rules(r["subRules"], known, sets)
        else:
            f = flatten_rule(r, known, sets)
            if f:
                out.append(f)
    return out


def norm_program(p, known, sets):
    reqs = []
    for g in (p.get("requisites") or {}).get("requisitesSimple", []):
        if "Major" not in g["name"]:                              # Gen Ed / degree-level groups are handled as Pathways slots
            continue
        rules = flatten_rules(g.get("rules"), known, sets)
        if rules:
            reqs.append({"name": g["name"], "rules": rules, "notes": strip_html(g.get("notes"), known)[:400]})
    maps = [m for m in p.get("degreeMaps") or [] if m.get("isActive")]
    semesters = []
    if maps:
        for s in sorted(maps[0]["semesters"], key=lambda s: s["sequence"]):
            slots = []
            for r in s["requirements"]:
                vals = []
                for x in r.get("requirementSelect", []):
                    v = x.get("value")
                    vals += [i for i in (v if isinstance(v, list) else [v]) if isinstance(i, str)]
                ids = [i for i in vals if i in known]                       # drop inactive/graduate course ids
                wild = [v.replace("@", "x") for v in vals if "@" in v and v != "@ @"]   # e.g. "CSCI 3@@" -> "CSCI 3xx"
                slots.append({"courses": ids, "credits": (r.get("actualCredits") or {}).get("min", 3),
                              "label": r.get("name") or r.get("courseRequirementGroupFreeText") or " / ".join(wild)})
            semesters.append({"name": s["semester"], "slots": slots})
    return {
        "id": p["programGroupId"] or p["_id"],
        "name": p["catalogDisplayName"] or p["name"],
        "degree": p.get("degreeDesignation") or "Minor/Cert",
        "departments": p.get("departments") or [],
        "description": strip_html((p.get("customFields") or {}).get("pXTAW") or p.get("catalogDescription"))[:600],
        "requirements": reqs,
        "semesters": semesters,
    }


def norm_course(c):
    return {
        "id": c["courseGroupId"],
        "code": c["code"],
        "subject": c["subjectCode"],
        "name": c.get("longName") or c["name"],
        "credits": (c.get("credits") or {}).get("creditHours", {}).get("min", 0) or 0,
        "offered": c.get("courseTypicallyOffered") or "",
        "description": (c.get("description") or "")[:1200],
        "prereq_text": strip_html((c.get("customFields") or {}).get("Mmgow") or "")[:500],   # catalog's requisite prose
        "rg": c.get("requirementGroup") or "",                                                # CUNYfirst requirement group id

        "departments": c.get("departments") or [],
    }


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    print("courses...")
    courses = [norm_course(c) for c in fetch_all("courses", "course") if c.get("career") == "Undergraduate"]
    known = {c["id"]: c["code"] for c in courses}
    # CUNYfirst requirement groups = the official requisite text per course ("PREQ: CSCI 313 AND MATH 231 ...")
    ids = sorted({c["rg"] for c in courses if c["rg"]})
    groups = {}
    print(f"requirement groups: {len(ids)}")
    for i in range(0, len(ids), 40):
        req = urllib.request.Request(f"{BASE.replace('/cm', '')}/requirementGroups/{','.join(ids[i:i + 40])}?returnFields=code,descriptionLong", headers=HEADERS)
        with urllib.request.urlopen(req, timeout=120) as r:
            groups.update({k: v.get("descriptionLong") or "" for k, v in json.load(r)["data"].items()})
    (OUT / "reqgroups.json").write_text(json.dumps(groups, ensure_ascii=False), encoding="utf8")
    print(f"  fetched {len(groups)}")
    print("course sets...")
    req = urllib.request.Request(f"{BASE}/courseSets", headers=HEADERS)
    with urllib.request.urlopen(req, timeout=120) as r:
        sets = json.load(r)
    print("programs...")
    programs = [norm_program(p, known, sets) for p in fetch_all("programs", "program") if p.get("career") == "Undergraduate"]
    (OUT / "programs.json").write_text(json.dumps(programs, ensure_ascii=False), encoding="utf8")
    (OUT / "courses.json").write_text(json.dumps(courses, ensure_ascii=False), encoding="utf8")
    print(f"wrote {len(programs)} programs, {len(courses)} courses -> {OUT}")
