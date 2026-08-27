"""Refresh cached Rate My Professors summaries for CUNY Queens College.

Rate My Professors does not publish a supported API.  This uses the same unofficial
GraphQL endpoint as the wrappers linked in the project discussion and deliberately
stores only aggregate professor data (not review text).

    python backend/rmp.py

The planner never calls RMP during a student request.  Run this manually when class
sections are refreshed; a failed refresh leaves the last good snapshot untouched.
"""
import base64
import json
import re
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

SCHOOL_LEGACY_ID = 231
SCHOOL_ID = base64.b64encode(f"School-{SCHOOL_LEGACY_ID}".encode()).decode()
ENDPOINT = "https://www.ratemyprofessors.com/graphql"
OUT = Path(__file__).resolve().parent.parent / "frontend" / "public" / "data" / "rmp.json"
PRIOR_REVIEWS = 20

QUERY = """query QueensCollegeTeachers($query: TeacherSearchQuery!, $after: String) {
  newSearch {
    teachers(query: $query, first: 100, after: $after) {
      pageInfo { hasNextPage endCursor }
      edges { node {
        legacyId firstName lastName department avgRating avgDifficulty
        numRatings wouldTakeAgainPercent
      } }
    }
  }
}"""


def normalize_name(value):
    """Loose join key shared with CUNYfirst instructor names."""
    return re.sub(r"[^a-z0-9]", "", value.casefold())


def confidence_score(rating, count, prior_mean, prior_reviews=PRIOR_REVIEWS):
    """Bayesian mean: sparse perfect ratings cannot outrank established evidence."""
    count = max(0, int(count or 0))
    return (float(rating or 0) * count + prior_mean * prior_reviews) / (count + prior_reviews)


def fetch_all():
    teachers, cursor = [], None
    while True:
        payload = json.dumps({
            "query": QUERY,
            # Empty text means "all professors at this school" to RMP's search resolver.
            "variables": {"query": {"text": "", "schoolID": SCHOOL_ID}, "after": cursor},
        }).encode()
        request = urllib.request.Request(ENDPOINT, data=payload, headers={
            "Authorization": "Basic dGVzdDp0ZXN0",
            "Content-Type": "application/json",
            "User-Agent": "QC-Degree-Planner/1.0",
        })
        with urllib.request.urlopen(request, timeout=30) as response:
            body = json.load(response)
        if body.get("errors"):
            raise RuntimeError(body["errors"][0].get("message", "RMP GraphQL error"))
        page = body["data"]["newSearch"]["teachers"]
        teachers.extend(edge["node"] for edge in page["edges"])
        if not page["pageInfo"]["hasNextPage"]:
            return teachers
        cursor = page["pageInfo"]["endCursor"]


def build_snapshot(teachers):
    rated = [t for t in teachers if int(t.get("numRatings") or 0) > 0]
    total = sum(int(t["numRatings"]) for t in rated)
    school_mean = sum(float(t["avgRating"]) * int(t["numRatings"]) for t in rated) / total if total else 3.5
    by_name = {}
    for teacher in teachers:
        name = f'{teacher.get("firstName", "")} {teacher.get("lastName", "")}'.strip()
        count = int(teacher.get("numRatings") or 0)
        item = {
            "name": name,
            "rating": float(teacher.get("avgRating") or 0),
            "difficulty": float(teacher.get("avgDifficulty") or 0),
            "reviews": count,
            "wouldTakeAgain": teacher.get("wouldTakeAgainPercent"),
            "department": teacher.get("department") or "",
            "legacyId": teacher.get("legacyId"),
            "score": round(confidence_score(teacher.get("avgRating"), count, school_mean), 3),
        }
        key = normalize_name(name)
        # Duplicate RMP profiles happen; keep the profile with the larger evidence base.
        if key and (key not in by_name or count > by_name[key]["reviews"]):
            by_name[key] = item
    return {
        "school": "CUNY Queens College",
        "schoolLegacyId": SCHOOL_LEGACY_ID,
        "updated": datetime.now(timezone.utc).isoformat(),
        "prior": {"mean": round(school_mean, 3), "reviews": PRIOR_REVIEWS},
        "professors": by_name,
    }


if __name__ == "__main__":
    fetched = fetch_all()
    if not fetched:
        raise RuntimeError("RMP returned no Queens College professors; keeping the previous snapshot")
    snapshot = build_snapshot(fetched)
    OUT.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf8")
    print(f'wrote {len(snapshot["professors"])} Queens College professors -> {OUT}')
