from __future__ import annotations

import html
import re
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

TITLE_WORDS = ("professor", "faculty", "lecturer", "research scientist")
PROFILE_HINTS = ("faculty", "people", "profile", "person", "directory", "bio")
GENERIC_NAME_WORDS = {
    "about", "academic", "achievements", "administrative", "admissions",
    "advisory", "affiliated", "alumni", "board", "biology", "computer",
    "computational", "contact", "department", "directory", "emeriti", "events",
    "faculty", "graduate", "in", "memoriam", "news", "open", "openings", "our",
    "people", "positions", "primary", "research", "researchers", "resources",
    "science", "secondary", "staff", "student", "students", "undergraduate",
}


def is_person_name(value: str) -> bool:
    value = re.sub(
        r"^(?:Dr\.?|Professor)\s+", "", (value or "").strip(), flags=re.I
    )
    value = re.sub(r"\s+", " ", value).strip(" ,|-")
    if not re.fullmatch(r"[A-Za-z][A-Za-z .,'?\-]+", value):
        return False
    tokens = [t.strip(".,'?- ") for t in value.split() if t.strip(".,'?- ")]
    if not 2 <= len(tokens) <= 5:
        return False
    if any(t.lower() in GENERIC_NAME_WORDS for t in tokens):
        return False
    return sum(1 for t in tokens if len(t) == 1 or t[0].isupper()) >= 2
ADMISSION_POSITIVE = (
    r"(?:actively\s+)?recruiting.{0,80}(?:ph\.?d|doctoral)",
    r"looking for.{0,80}(?:ph\.?d|doctoral) students",
    r"accepting.{0,80}(?:ph\.?d|doctoral) students",
    r"open positions?.{0,80}(?:ph\.?d|doctoral)",
)
ADMISSION_NEGATIVE = (r"not (?:currently )?(?:taking|accepting|recruiting)", r"no longer (?:taking|accepting)")
IGNORED_TAGS = {"script", "style", "noscript", "template", "svg"}
NON_PERSON_HEADINGS = {
    "alumni news", "news", "events", "faculty", "people", "directory",
    "research", "academics", "admissions", "contact", "home",
}
NON_PROFILE_PATHS = ("/news", "/events", "/alumni", "/admissions")


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
        self._ignored_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in IGNORED_TAGS:
            self._ignored_depth += 1
            return
        if self._ignored_depth:
            return
        a = dict(attrs)
        if tag == "a": self._href = a.get("href", "")
        if tag == "title": self._in_title = True
        if tag == "h1": self._in_h1 = True

    def handle_endtag(self, tag):
        if tag in IGNORED_TAGS:
            self._ignored_depth = max(0, self._ignored_depth - 1)
            return
        if self._ignored_depth:
            return
        if tag == "a": self._href = ""
        if tag == "title": self._in_title = False
        if tag == "h1": self._in_h1 = False

    def handle_data(self, data):
        if self._ignored_depth:
            return
        s = re.sub(r"\s+", " ", html.unescape(data)).strip()
        if not s: return
        self.text.append(s)
        if self._href: self.links.append((self._href,s))
        if self._in_title: self.title.append(s)
        if self._in_h1: self.h1.append(s)


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
        looks_person = is_person_name(label)
        path = urlparse(url).path.lower()
        if any(part in path for part in NON_PROFILE_PATHS):
            continue
        if looks_person and any(h in low for h in PROFILE_HINTS) and url not in found:
            found.append(url)
        if len(found)>=limit: break
    return found


def faculty_record(page: dict, url: str) -> dict | None:
    if any(part in urlparse(url).path.lower() for part in NON_PROFILE_PATHS):
        return None
    text=page["text"][:30000]
    heading=(page["h1"] or page["title"].split("|")[0]).strip()
    heading=re.sub(r"\s+[-|].*$", "", heading).strip()
    if heading.lower() in NON_PERSON_HEADINGS:
        return None
    name_match=re.match(r"(?:Dr\.?|Professor)?\s*([A-Z][A-Za-z'’-]+(?:\s+[A-Z][A-Za-z'’-]+){1,3})", heading)
    if not name_match or not any(w in text.lower() for w in TITLE_WORDS): return None
    name=name_match.group(1)
    if not is_person_name(name):
        return None
    if any(
        word.lower() in {"news", "events", "alumni", "faculty", "directory"}
        for word in name.split()
    ):
        return None
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
    cleaned = re.sub(
        r"(?:Toggle|Chevron Up|Plus Minus|Skip to (?:main )?content)\s*",
        " ",
        text,
        flags=re.I,
    )
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    m = re.search(
        r"(?:research interests?|research areas?|my research|research focuses?)[:\s]",
        cleaned,
        re.I,
    )
    if not m:
        return ""
    excerpt = cleaned[m.start():m.start()+600]
    sentences = re.split(r"(?<=[.!?])\s+", excerpt)
    concise = " ".join(sentences[:4]).strip()
    return concise[:600].rstrip() + ("…" if len(concise) > 600 else "")
