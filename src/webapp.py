from __future__ import annotations

import json
import os
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from .config import ROOT
from .db import connect
from .parser import is_valid_faculty_output


class Handler(SimpleHTTPRequestHandler):
    def _json(self, value) -> None:
        body = json.dumps(value, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/schools":
            with connect() as db:
                rows = db.execute(
                    """SELECT f.name,f.title,f.research_text,s.name school
                       FROM faculty f JOIN schools s ON s.id=f.school_id"""
                ).fetchall()
            schools = sorted({
                row["school"] for row in rows
                if is_valid_faculty_output(dict(row))
            })
            return self._json(schools)

        if parsed.path == "/api/faculty":
            query = parse_qs(parsed.query)
            school = (query.get("school") or [""])[0].strip()
            status = (query.get("status") or [""])[0].strip()
            sql = """SELECT f.*,s.name school,s.rank school_rank,s.website school_website,
                     d.name department,d.url department_url
                     FROM faculty f
                     JOIN schools s ON s.id=f.school_id
                     JOIN departments d ON d.id=f.department_id WHERE 1=1"""
            params = []
            if school:
                sql += " AND s.name=?"
                params.append(school)
            if status:
                sql += " AND f.admissions_status=?"
                params.append(status)
            sql += " ORDER BY f.match_score DESC,s.rank IS NULL,s.rank,f.name"
            with connect() as db:
                rows = db.execute(sql, params).fetchall()
            records = [
                dict(row) for row in rows
                if is_valid_faculty_output(dict(row))
            ]
            return self._json(records)

        if parsed.path == "/":
            self.path = "/web/index.html"
        return super().do_GET()


def serve() -> None:
    os.chdir(ROOT)
    ThreadingHTTPServer(
        ("0.0.0.0", int(os.getenv("PORT", "8765"))), Handler
    ).serve_forever()
