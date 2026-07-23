from __future__ import annotations

import json
import re
import unicodedata
import urllib.parse
import urllib.request

from .db import connect


STOP_WORDS = {
    "university", "college", "institute", "technology", "of", "the", "at",
    "main", "campus", "new", "state", "and",
}

SCHOOL_ALIASES = {
    "Massachusetts Institute of Technology": ("MIT",),
    "University of California Los Angeles": ("UCLA",),
    "University of California Berkeley": ("UC Berkeley", "Cal Berkeley"),
    "University of California San Diego": ("UCSD",),
    "University of Illinois Urbana-Champaign": ("UIUC",),
    "Georgia Institute of Technology": ("Georgia Tech",),
    "Pennsylvania State University": ("Penn State",),
    "Virginia Tech": ("Virginia Polytechnic",),
    "William & Mary": ("William and Mary",),
}


def _normalise(value: str) -> str:
    value = unicodedata.normalize("NFKD", value or "")
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def _host(value: str) -> str:
    value = (value or "").strip()
    if not value:
        return ""
    if "://" not in value:
        value = "https://" + value
    host = (urllib.parse.urlparse(value).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def _same_site(url: str, official_host: str) -> bool:
    candidate = _host(url)
    return bool(candidate and official_host and (
        candidate == official_host or candidate.endswith("." + official_host)
    ))


def _identity_score(result: dict, school_name: str) -> int:
    corpus = _normalise(" ".join(str(result.get(k, "")) for k in ("title", "content", "url")))
    tokens = [
        token for token in _normalise(school_name).split()
        if token not in STOP_WORDS and len(token) > 2
    ]
    score = sum(1 for token in tokens if token in corpus)
    for alias in SCHOOL_ALIASES.get(school_name, ()):
        if _normalise(alias) in corpus:
            score += 3
    return score


def _identity_matches(result: dict, school_name: str) -> bool:
    corpus = _normalise(" ".join(str(result.get(k, "")) for k in ("title", "content", "url")))
    if any(_normalise(alias) in corpus for alias in SCHOOL_ALIASES.get(school_name, ())):
        return True
    tokens = [
        token for token in _normalise(school_name).split()
        if token not in STOP_WORDS and len(token) > 2
    ]
    if not tokens:
        return False
    matched = sum(1 for token in tokens if token in corpus)
    required = 1 if len(tokens) == 1 else max(2, (len(tokens) + 1) // 2)
    return matched >= required


def _search(endpoint: str, api_key: str, query: str) -> list[dict]:
    payload = json.dumps({
        "query": query,
        "search_depth": "basic",
        "max_results": 5,
        "include_answer": False,
        "include_raw_content": False,
    }).encode("utf-8")
    request = urllib.request.Request(
        endpoint,
        data=payload,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response).get("results", [])


def _discover_official_website(endpoint: str, api_key: str, school_name: str) -> str:
    results = _search(endpoint, api_key, f'"{school_name}" official university website')
    candidates = []
    for result in results:
        host = _host(result.get("url", ""))
        if not host.endswith(".edu"):
            continue
        score = _identity_score(result, school_name)
        if _identity_matches(result, school_name):
            candidates.append((score, len(host), result.get("url", "")))
    if not candidates:
        return ""
    return max(candidates, key=lambda item: (item[0], -item[1]))[2]


def _clean_wrong_school_records(school_id: int, official_host: str) -> None:
    """Remove records whose source is outside the verified official domain."""
    with connect() as db:
        faculty = db.execute(
            "SELECT id,profile_url FROM faculty WHERE school_id=?", (school_id,)
        ).fetchall()
        bad_faculty = [row["id"] for row in faculty if not _same_site(row["profile_url"], official_host)]
        for faculty_id in bad_faculty:
            db.execute("DELETE FROM review_queue WHERE faculty_id=?", (faculty_id,))
            db.execute("DELETE FROM faculty WHERE id=?", (faculty_id,))

        departments = db.execute(
            "SELECT id,url FROM departments WHERE school_id=?", (school_id,)
        ).fetchall()
        for department in departments:
            if _same_site(department["url"], official_host):
                continue
            pages = db.execute(
                "SELECT url FROM pages WHERE department_id=?", (department["id"],)
            ).fetchall()
            for page in pages:
                db.execute("DELETE FROM page_versions WHERE url=?", (page["url"],))
            db.execute("DELETE FROM pages WHERE department_id=?", (department["id"],))
            db.execute("DELETE FROM departments WHERE id=?", (department["id"],))


def discover_department_urls(cfg: dict) -> int:
    """Discover official CS/Statistics pages and enforce school-domain ownership."""
    api_key = cfg.get("search_api_key")
    endpoint = cfg.get("search_endpoint") or "https://api.tavily.com/search"
    if not api_key:
        print("SEARCH_API_KEY is not configured.", flush=True)
        return 0

    max_queries = max(1, int(cfg.get("max_search_queries_per_run", 10)))
    department_names = ("Computer Science", "Statistics")
    queries = added = 0

    with connect() as db:
        schools = db.execute(
            "SELECT * FROM schools WHERE active=1 ORDER BY rank IS NULL,rank,id"
        ).fetchall()

    for school in schools:
        if queries >= max_queries:
            break
        website = school["website"] or ""
        official_host = _host(website)

        if not official_host:
            try:
                website = _discover_official_website(endpoint, api_key, school["name"])
            except Exception as exc:
                print(f'Official-site search failed for {school["name"]}: {exc}', flush=True)
                queries += 1
                continue
            queries += 1
            official_host = _host(website)
            if not official_host:
                print(f'No verified .edu domain for {school["name"]}.', flush=True)
                continue
            with connect() as db:
                db.execute("UPDATE schools SET website=? WHERE id=?", (f"https://{official_host}", school["id"]))

        _clean_wrong_school_records(school["id"], official_host)

        with connect() as db:
            existing = {
                row["name"] for row in db.execute(
                    "SELECT name FROM departments WHERE school_id=?", (school["id"],)
                ).fetchall()
            }

        for department_name in department_names:
            if queries >= max_queries:
                break
            if department_name in existing:
                continue
            query = f'site:{official_host} "{department_name}" faculty directory'
            try:
                results = _search(endpoint, api_key, query)
            except Exception as exc:
                print(f'Department search failed for {school["name"]}: {exc}', flush=True)
                queries += 1
                continue
            queries += 1
            valid = [
                item for item in results
                if _same_site(item.get("url", ""), official_host)
                and _identity_matches(item, school["name"])
            ]
            if not valid:
                continue
            result_url = valid[0]["url"]
            with connect() as db:
                db.execute(
                    "INSERT OR IGNORE INTO departments(school_id,name,url) VALUES(?,?,?)",
                    (school["id"], department_name, result_url),
                )
                department = db.execute(
                    "SELECT id FROM departments WHERE school_id=? AND name=?",
                    (school["id"], department_name),
                ).fetchone()
                if department:
                    db.execute(
                        "INSERT OR IGNORE INTO pages(url,school_id,department_id,kind) VALUES(?,?,?,'directory')",
                        (result_url, school["id"], department["id"]),
                    )
                    added += 1

    print(f"Verified {added} department pages using {queries} searches.", flush=True)
    return added
