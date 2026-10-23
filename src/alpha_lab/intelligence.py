"""Opt-in, bounded RSS/Atom event ingestion. Headlines do not create orders."""
from __future__ import annotations

import hashlib
import json
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse


def parse_feed(raw: bytes, source_url: str, retrieved_at: str) -> list[dict]:
    if len(raw) > 2_000_000:
        raise ValueError("FEED_TOO_LARGE")
    root = ET.fromstring(raw)
    events = []
    if root.tag.endswith("rss") or root.tag.endswith("RDF"):
        for item in root.findall(".//item"):
            title = item.findtext("title", "").strip()
            link = item.findtext("link", "").strip()
            published = item.findtext("pubDate") or None
            if title and link:
                events.append((title, link, published))
    elif root.tag.endswith("feed"):
        ns = "{http://www.w3.org/2005/Atom}"
        for item in root.findall(f"{ns}entry"):
            title = (item.findtext(f"{ns}title") or "").strip()
            links = [el.attrib.get("href", "") for el in item.findall(f"{ns}link")]
            link = next((el for el in links if el), "")
            published = item.findtext(f"{ns}published") or item.findtext(f"{ns}updated")
            if title and link:
                events.append((title, link, published))
    else:
        raise ValueError("NOT_RSS_OR_ATOM")
    output = []
    for title, link, published in events:
        digest = hashlib.sha256((source_url + "\n" + link).encode("utf-8")).hexdigest()
        output.append({
            "id": digest,
            "source": source_url,
            "title": title[:500],
            "url": link,
            "published_at_raw": published,
            "retrieved_at": retrieved_at,
            "research_status": "UNVERIFIED",
        })
    return output


def append_unique(events: list[dict], out: str | Path) -> int:
    path = Path(out)
    path.parent.mkdir(parents=True, exist_ok=True)
    known = set()
    if path.exists():
        with path.open(encoding="utf-8") as stream:
            for line in stream:
                if line.strip():
                    known.add(json.loads(line)["id"])
    new_events = []
    for event in events:
        if event["id"] not in known:
            known.add(event["id"])
            new_events.append(event)
    with path.open("a", encoding="utf-8") as stream:
        for event in new_events:
            stream.write(json.dumps(event, ensure_ascii=False) + "\n")
    return len(new_events)


def poll_feeds(sources: list[str], out: str | Path) -> dict:
    """Only explicitly approved HTTPS feed URLs; no built-in scraping targets."""
    if not sources:
        return {"status": "NO_FEEDS_CONFIGURED", "new_events": 0, "sources": 0}
    if len(sources) > 20:
        raise ValueError("TOO_MANY_FEEDS")
    now = datetime.now(timezone.utc).isoformat()
    count = 0
    for url in sources:
        parsed = urlparse(url)
        if parsed.scheme != "https" or not parsed.netloc:
            raise ValueError("FEED_URL_MUST_BE_HTTPS")
        request = urllib.request.Request(url, headers={"User-Agent": "A-Share-Alpha-Lab/0.1 (research)"})
        with urllib.request.urlopen(request, timeout=12) as response:
            raw = response.read(2_000_001)
        count += append_unique(parse_feed(raw, url, now), out)
    return {"status": "COLLECTED_UNVERIFIED", "new_events": count, "sources": len(sources)}
