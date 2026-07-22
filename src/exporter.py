from __future__ import annotations

import csv
from .config import ROOT
from .db import connect, utcnow


def export_results() -> None:
    out=ROOT/"output";out.mkdir(exist_ok=True);(out/"email_drafts").mkdir(exist_ok=True)
    with connect() as db:
        rows=db.execute("""SELECT f.name,s.name school,d.name department,f.title,f.email,f.profile_url,f.research_text,
          f.admissions_status,f.admissions_evidence,f.evidence_url,f.evidence_checked_at,f.verification_source,
          f.verification_confidence,f.match_score,f.match_reasons,f.contact_status
          FROM faculty f LEFT JOIN schools s ON s.id=f.school_id LEFT JOIN departments d ON d.id=f.department_id
          ORDER BY f.match_score DESC,s.rank,f.name""").fetchall()
        run=db.execute("SELECT * FROM runs ORDER BY id DESC LIMIT 1").fetchone()
    fields=list(rows[0].keys()) if rows else ["name","school","department","match_score"]
    with (out/"faculty_rankings.csv").open("w",encoding="utf-8-sig",newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(dict(r) for r in rows)
    summary=["# Faculty discovery report","",f"Generated: {utcnow()}",f"Faculty records: {len(rows)}",""]
    if run: summary += [f"Pages fetched: {run['pages_ok']}",f"Failures: {run['pages_failed']}",f"Changed pages: {run['changed_pages']}",f"Model calls: {run['model_calls']}",f"Estimated model cost: ${run['estimated_cost']:.4f}"]
    (out/"weekly_report.md").write_text("\n".join(summary),encoding="utf-8")
