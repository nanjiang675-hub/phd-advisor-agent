from __future__ import annotations

import json
import urllib.request


def verify_with_model(record: dict, cfg: dict, spent: float) -> tuple[dict | None,float]:
    key=cfg.get("openai_api_key")
    max_calls=int(cfg.get("max_model_calls_per_run",20))
    budget=float(cfg.get("max_model_cost_usd_per_run",1.0))
    if not key or spent>=budget: return None,0.0
    payload={"model":cfg["openai_model"],"input":[{"role":"system","content":"Verify faculty recruiting evidence. Return only JSON with status (confirmed_open, not_recruiting, unknown), confidence 0-1, evidence_quote, reason. Do not infer beyond the supplied text."},{"role":"user","content":json.dumps(record,ensure_ascii=False)}],"max_output_tokens":250}
    req=urllib.request.Request("https://api.openai.com/v1/responses",data=json.dumps(payload).encode(),headers={"Authorization":f"Bearer {key}","Content-Type":"application/json"})
    with urllib.request.urlopen(req,timeout=45) as res: data=json.load(res)
    text="".join(x.get("text","") for item in data.get("output",[]) for x in item.get("content",[]) if x.get("type")=="output_text")
    result=json.loads(text.strip().removeprefix("```json").removesuffix("```").strip())
    tokens=data.get("usage",{}).get("total_tokens",0)
    estimate=tokens/1_000_000*float(cfg.get("estimated_usd_per_million_tokens",2.0))
    return result,estimate
