from __future__ import annotations

import json
import urllib.parse
import urllib.request

from .db import connect


def _tavily_search(endpoint: str, api_key: str, query: str) -> list[dict]:
    payload = json.dumps(
        {
            "query": query,
            "search_depth": "basic",
            "max_results": 5,
            "include_answer": False,
            "include_raw_content": False,
        }
    ).encode("utf-8")

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
        data = json.load(response)

    return data.get("results", [])


def discover_department_urls(cfg: dict) -> int:
    """Use Tavily to discover missing CS and Statistics faculty pages."""
    api_key = cfg.get("search_api_key")
    endpoint = cfg.get("search_endpoint") or "https://api.tavily.com/search"

    if not api_key:
        print("SEARCH_API_KEY is not configured.", flush=True)
        return 0

    max_queries = max(2, int(cfg.get("max_search_queries_per_run", 10)))
    school_limit = max(1, max_queries // 2)

    with connect() as db:
        schools = db.execute(
            """
            SELECT s.*
            FROM schools s
            LEFT JOIN departments d ON d.school_id = s.id
            WHERE s.active = 1
            GROUP BY s.id
            HAVING COUNT(d.id) = 0
            LIMIT ?
            """,
            (school_limit,),
        ).fetchall()

    added = 0

    for school in schools:
        website = school["website"] or ""
        hostname = urllib.parse.urlparse(website).netloc

        if not hostname:
            hostname = website.replace("https://", "").replace("http://", "")
            hostname = hostname.split("/")[0]

        for department_name in ("Computer Science", "Statistics"):
            query = (
                f'"{school["name"]}" "{department_name}" '
                f"faculty directory machine learning"
            )

            if hostname:
                query += f" site:{hostname}"

            try:
                results = _tavily_search(endpoint, api_key, query)
            except Exception as exc:
                print(
                    f'Search failed for {school["name"]} '
                    f'{department_name}: {exc}',
                    flush=True,
                )
                continue

            result_url = next(
                (
                    item.get("url")
                    for item in results
                    if item.get("url")
                ),
                None,
            )

            if not result_url:
                continue

            with connect() as db:
                db.execute(
                    """
                    INSERT OR IGNORE INTO departments(school_id, name, url)
                    VALUES (?, ?, ?)
                    """,
                    (school["id"], department_name, result_url),
                )

                department = db.execute(
                    """
                    SELECT id
                    FROM departments
                    WHERE school_id = ? AND name = ?
                    """,
                    (school["id"], department_name),
                ).fetchone()

                if not department:
                    continue

                db.execute(
                    """
                    INSERT OR IGNORE INTO pages(
                        url, school_id, department_id, kind
                    )
                    VALUES (?, ?, ?, 'directory')
                    """,
                    (result_url, school["id"], department["id"]),
                )

            added += 1

    print(f"Discovered {added} department pages.", flush=True)
    return added
