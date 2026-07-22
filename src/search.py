from __future__ import annotations

import json
import urllib.parse
import urllib.request

from .db import connect


def discover_department_urls(cfg: dict) -> int:
    """Discover missing CS/Statistics directory pages through a configured Bing-compatible endpoint."""
    if not cfg.get("search_api_key") or not cfg.get("search_endpoint"):
        return 0
    with connect() as db:
        schools=db.execute("""SELECT s.* FROM schools s LEFT JOIN departments d ON d.school_id=s.id
          WHERE s.active=1 GROUP BY s.id HAVING COUNT(d.id)=0 LIMIT ?""",(cfg.get("max_search_queries_per_run",10),)).fetchall()
    added=0
    for school in schools:
        scope=f"site:{school['website']}" if school["website"] else f'"{school["name"]}"'
        for department in ("Computer Science faculty", "Statistics faculty"):
            query=f"{scope} {department}"
            url=cfg["search_endpoint"]+("&" if "?" in cfg["search_endpoint"] else "?")+urllib.parse.urlencode({"q":query,"count":5})
            req=urllib.request.Request(url,headers={"Ocp-Apim-Subscription-Key":cfg["search_api_key"]})
            with urllib.request.urlopen(req,timeout=20) as res: data=json.load(res)
            values=data.get("webPages",{}).get("value",[])
            if not values: continue
            result=values[0]["url"]
            with connect() as db:
                db.execute("INSERT OR IGNORE INTO departments(school_id,name,url) VALUES(?,?,?)",(school["id"],department.replace(" faculty",""),result))
                did=db.execute("SELECT id FROM departments WHERE url=?",(result,)).fetchone()[0]
                db.execute("INSERT OR IGNORE INTO pages(url,school_id,department_id,kind) VALUES(?,?,?,'directory')",(result,school["id"],did))
            added+=1
    return added
