from __future__ import annotations

import json
import os
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from .config import ROOT
from .db import connect


class Handler(SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith("/api/faculty"):
            with connect() as db:
                rows=db.execute("""SELECT f.*,s.name school,d.name department FROM faculty f LEFT JOIN schools s ON s.id=f.school_id LEFT JOIN departments d ON d.id=f.department_id ORDER BY match_score DESC""").fetchall()
            body=json.dumps([dict(r) for r in rows],ensure_ascii=False).encode()
            self.send_response(200);self.send_header("Content-Type","application/json; charset=utf-8");self.send_header("Content-Length",str(len(body)));self.end_headers();self.wfile.write(body);return
        if self.path=="/": self.path="/web/index.html"
        return super().do_GET()


def serve() -> None:
    os.chdir(ROOT)
    ThreadingHTTPServer(("0.0.0.0",int(os.getenv("PORT","8765"))),Handler).serve_forever()
