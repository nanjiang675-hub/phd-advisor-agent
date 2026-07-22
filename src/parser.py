from __future__ import annotations

import html
import json
import re
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

TITLE_WORDS = ("professor", "faculty", "lecturer", "research scientist")
PROFILE_HINTS = ("faculty", "people", "profile", "person", "directory", "bio")
ADMISSION_POSITIVE = (
    r"(?:actively\s+)?recruiting.{0,80}(?:ph\.?d|doctoral)",
    r"looking for.{0,80}(?:ph\.?d|doctoral) students",
    r"accepting.{0,80}(?:ph\.?d|doctoral) students",
    r"open positions?.{0,80}(?:ph\.?d|doctoral)",
)
ADMISSION_NEGATIVE = (r"not (?:currently )?(?:taking|accepting|recruiting)", r"no longer (?:taking|accepting)")


class PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[tuple[str,str]] = []
        self.text: list[str] = []
        self.title: list[str] = []
        self.h1: list[str] = []
        self._href = ""
        self._in_title = self._in_h1 = False
        self._jsonld = self._script_type = ""

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "a": self._href = a.get("href", "")
        if tag == "title": self._in_title = True
        if tag == "h1": self._in_h1 = True
        if tag == "script": self._script_type = a.get("type", ""); self._jsonld = ""

    def handle_endtag(self, tag):
        if tag == "a": self._href = ""
        if tag == "title": self._in_title = False
        if tag == "h1": self._in_h1 = False
        if tag == "script" and self._script_type == "application/ld+json": self.text.append(self._jsonld)

    def handle_data(self, data):
        s = re.sub(r"\s+", " ", html.unescape(data)).strip()
        if not s: return
        self.text.append(s)
        if self._href: self.links.append((self._href,s))
        if self._in_title: self.title.append(s)
        if self._in_h1: self.h1.append(s)
        if self._script_type == "application/ld+json": self._jsonld += data


def parse(raw: str, base_url: str) -> dict:
    p = PageParser(); p.feed(raw)
    text = re.sub(r"\s+", " ", " ".join(p.text))
    links=[]; host=urlparse(base_url).netloc
    for href,label in p.links:
        url=urljoin(base_url,href).split("#")[0]
        if urlparse(url).scheme in ("http","https") and urlparse(url).netloc==host:
            links.append((url,label))
    return {"title":" ".join(p.title),"h1":" ".join(p.h1),"text":text,"links":links}


def profile_links(page: dict, limit: int = 200) -> list[str]:
    found=[]
    for url,label in page["links"]:
        low=f"{url} {label}".lower()
        looks_person = 2 <= len(label.split()) <= 6 and re.fullmatch(r"[A-Za-z .,'-]+", label or "")
        if looks_person and any(h in low for h in PROFILE_HINTS) and url not in found:
            found.append(url)
        if len(found)>=limit: break
    return found


def faculty_record(page: dict, url: str) -> dict | None:
    text=page["text"][:30000]
    heading=(page["h1"] or page["title"].split("|")[0]).strip()
    heading=re.sub(r"\s+[-|].*$", "", heading).strip()
    name_match=re.match(r"(?:Dr\.?|Professor)?\s*([A-Z][A-Za-z'’-]+(?:\s+[A-Z][A-Za-z'’-]+){1,3})", heading)
    if not name_match or not any(w in text.lower() for w in TITLE_WORDS): return None
    name=name_match.group(1)
    email_match=re.search(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", text)
    title_match=re.search(r"((?:Assistant|Associate|Full|Distinguished|Research)?\s*Professor[^.;|]{0,80})", text, re.I)
    evidence,status,confidence=admissions(text)
    return {"name":name,"title":title_match.group(1).strip() if title_match else "Professor",
            "email":email_match.group(0) if email_match else "","profile_url":url,
            "research_text":research_excerpt(text),"admissions_status":status,
            "admissions_evidence":evidence,"verification_confidence":confidence}


def admissions(text: str) -> tuple[str,str,float]:
    low=text.lower()
    for pat in ADMISSION_NEGATIVE:
        m=re.search(pat,low,re.I)
        if m: return snippet(text,m.start()),"not_recruiting",0.95
    for pat in ADMISSION_POSITIVE:
        m=re.search(pat,low,re.I|re.S)
        if m: return snippet(text,m.start()),"suspected_open",0.7
    return "","unknown",0.1


def snippet(text: str, pos: int, radius: int = 240) -> str:
    return text[max(0,pos-radius):min(len(text),pos+radius)].strip()


def research_excerpt(text: str) -> str:
    m=re.search(r"(?:research interests?|research areas?|my research)[:\s]",text,re.I)
    return text[m.start():m.start()+1200] if m else text[:1200]
