from __future__ import annotations

import hashlib
import json
import re
import time
import urllib.error
import urllib.request
import urllib.robotparser
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

from .config import ROOT, settings
from .db import connect, init_db, utcnow
from .parser import faculty_record, parse, profile_links
from .verifier import verify_with_model
from .search import _host, _same_site, discover_department_urls

_robots: dict[str, urllib.robotparser.RobotFileParser] = {}
_robots_lock = threading.Lock()
_host_last_access: dict[str, float] = {}


def fetch(url: str, cfg: dict) -> tuple[int,str,str]:
    parsed=urlparse(url); robots_url=f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    with _robots_lock:
        rp=_robots.get(robots_url)
        if rp is None:
            rp=urllib.robotparser.RobotFileParser();rp.set_url(robots_url)
            try: rp.read()
            except Exception: rp.parse([])
            _robots[robots_url]=rp
        if not rp.can_fetch(cfg["user_agent"],url): raise PermissionError("robots.txt disallows this URL")
        delay=float(cfg.get("minimum_host_delay_seconds",1.0));wait=delay-(time.monotonic()-_host_last_access.get(parsed.netloc,0))
        if wait>0: time.sleep(wait)
        _host_last_access[parsed.netloc]=time.monotonic()
    req=urllib.request.Request(url,headers={"User-Agent":cfg["user_agent"],"Accept":"text/html"})
    with urllib.request.urlopen(req,timeout=cfg["request_timeout_seconds"]) as res:
        kind=res.headers.get("Content-Type","")
        if "html" not in kind: raise ValueError(f"unsupported content type: {kind}")
        return res.status,res.geturl(),res.read(int(cfg.get("max_page_bytes",3000000))).decode(res.headers.get_content_charset() or "utf-8","replace")


def canonical(name: str, school_id: int) -> str:
    clean=re.sub(r"[^a-z]","",name.lower())
    return f"{school_id}:{clean}"


def score(record: dict, profile: str, cfg: dict) -> tuple[float,str]:
    corpus=(record.get("research_text","")+" "+record.get("admissions_evidence","")).lower()
    terms=[t for t in cfg["research_terms"] if t.lower() in corpus]
    value=min(60,len(terms)*12)
    if record.get("admissions_status")=="confirmed_open": value+=25
    elif record.get("admissions_status")=="suspected_open": value+=15
    if record.get("email"): value+=5
    if record.get("profile_url"): value+=10
    return min(100,value),"; ".join(terms) or "manual review needed"


def run_pipeline() -> None:
    init_db(load_inputs=True); cfg=settings(); started=utcnow(); discover_department_urls(cfg)
    with connect() as db:
        run_id=db.execute("INSERT INTO runs(started_at,status) VALUES(?,'running')",(started,)).lastrowid
        due=db.execute("""SELECT p.*,d.name department_name,s.name school_name,
          s.website school_website FROM pages p
          LEFT JOIN departments d ON d.id=p.department_id LEFT JOIN schools s ON s.id=p.school_id
          WHERE p.attempts<? AND (p.next_check_at IS NULL OR p.next_check_at<=?)
          ORDER BY CASE p.kind WHEN 'profile' THEN 1 ELSE 0 END,p.attempts LIMIT ?""",
          (cfg["max_attempts"],started,cfg["max_pages_per_run"])).fetchall()
    ok=failed=changed=found=model_calls=0; spent=0.0
    profile=(ROOT/"input"/"research_profile.md").read_text(encoding="utf-8").lower()
    workers=max(1,min(int(cfg.get("concurrency",4)),8))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        jobs={pool.submit(fetch,r["url"],cfg):r for r in due}
        for future in as_completed(jobs):
            row=jobs[future]
            try:
                status,final_url,raw=future.result(); page=parse(raw,final_url); digest=hashlib.sha256(page["text"].encode()).hexdigest()
                official_host = _host(row["school_website"] or "")
                if not official_host or not _same_site(final_url, official_host):
                    raise ValueError(
                        f"rejected cross-school page: {final_url} is not on {official_host or 'a verified domain'}"
                    )
                is_changed=bool(row["content_hash"] and row["content_hash"]!=digest); changed+=int(is_changed)
                next_at=(datetime.now(timezone.utc)+timedelta(days=cfg["recheck_days"])).isoformat(timespec="seconds")
                with connect() as db:
                    db.execute("INSERT OR IGNORE INTO page_versions(url,content_hash,title,text_content,captured_at) VALUES(?,?,?,?,?)",(row["url"],digest,page["title"],page["text"][:100000],utcnow()))
                    db.execute("""UPDATE pages SET status='ok',http_status=?,content_hash=?,title=?,text_content=?,
                      changed_at=CASE WHEN content_hash IS NOT NULL AND content_hash<>? THEN ? ELSE changed_at END,
                      fetched_at=?,next_check_at=?,attempts=0,error=NULL WHERE url=?""",(status,digest,page["title"],page["text"][:100000],digest,utcnow(),utcnow(),next_at,row["url"]))
                    if row["kind"]=="directory":
                        for link in profile_links(page,cfg.get("max_profiles_per_directory",200)):
                            if not _same_site(link, official_host):
                                continue
                            db.execute("INSERT OR IGNORE INTO pages(url,school_id,department_id,kind) VALUES(?,?,?,'profile')",(link,row["school_id"],row["department_id"]))
                    else:
                        rec=faculty_record(page,row["url"])
                        if rec:
                            result,cost=(None,0.0)
                            if rec["admissions_status"]=="suspected_open" and model_calls<cfg["max_model_calls_per_run"]:
                                try: result,cost=verify_with_model(rec,cfg,spent)
                                except Exception as exc: result=None
                            if result:
                                model_calls+=1;spent+=cost;rec["admissions_status"]=result.get("status","unknown");rec["admissions_evidence"]=result.get("evidence_quote",rec["admissions_evidence"]);rec["verification_confidence"]=result.get("confidence",0);source="model"
                            else: source="rules"
                            value,reasons=score(rec,profile,cfg); key=canonical(rec["name"],row["school_id"])
                            db.execute("""INSERT INTO faculty(canonical_key,name,school_id,department_id,title,email,profile_url,research_text,admissions_status,admissions_evidence,evidence_url,evidence_checked_at,verification_source,verification_confidence,match_score,match_reasons,updated_at)
                              VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(canonical_key) DO UPDATE SET title=excluded.title,email=COALESCE(NULLIF(excluded.email,''),faculty.email),profile_url=excluded.profile_url,research_text=excluded.research_text,admissions_status=excluded.admissions_status,admissions_evidence=excluded.admissions_evidence,evidence_url=excluded.evidence_url,evidence_checked_at=excluded.evidence_checked_at,verification_source=excluded.verification_source,verification_confidence=excluded.verification_confidence,match_score=excluded.match_score,match_reasons=excluded.match_reasons,updated_at=excluded.updated_at""",
                              (key,rec["name"],row["school_id"],row["department_id"],rec["title"],rec["email"],row["url"],rec["research_text"],rec["admissions_status"],rec["admissions_evidence"],row["url"],utcnow(),source,rec["verification_confidence"],value,reasons,utcnow()))
                            fid=db.execute("SELECT id FROM faculty WHERE canonical_key=?",(key,)).fetchone()[0]
                            if rec["admissions_status"] in ("suspected_open","unknown"):
                                db.execute("INSERT OR IGNORE INTO review_queue(faculty_id,reason,payload,created_at) VALUES(?,?,?,?)",(fid,"admissions_needs_review",json.dumps(rec,ensure_ascii=False),utcnow()))
                            found+=1
                ok+=1
            except Exception as exc:
                backoff=min(30,2**(row["attempts"]+1)); next_at=(datetime.now(timezone.utc)+timedelta(days=backoff)).isoformat(timespec="seconds")
                with connect() as db: db.execute("UPDATE pages SET status='failed',attempts=attempts+1,error=?,next_check_at=? WHERE url=?",(str(exc)[:1000],next_at,row["url"]))
                failed+=1
    with connect() as db: db.execute("UPDATE runs SET finished_at=?,status='completed',pages_ok=?,pages_failed=?,faculty_found=?,changed_pages=?,model_calls=?,estimated_cost=? WHERE id=?",(utcnow(),ok,failed,found,changed,model_calls,spent,run_id))
    print(json.dumps({"pages_ok":ok,"pages_failed":failed,"faculty_found":found,"changed_pages":changed,"model_calls":model_calls,"estimated_cost_usd":round(spent,4)}))
