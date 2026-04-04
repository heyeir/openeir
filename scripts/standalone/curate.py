#!/usr/bin/env python3
"""
Standalone content curation script.
Reads config, fetches RSS based on interests, outputs formatted content.
"""

import json
import os
import sys
import hashlib
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any, Optional, Set
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET
import re

# ─── Paths ────────────────────────────────────────────────────────────────────

SCRIPT_DIR = Path(__file__).parent.parent.parent  # skill root
CONFIG_DIR = Path.home() / ".openclaw" / "curator"
USER_CONFIG = CONFIG_DIR / "config.json"
SEEN_FILE = CONFIG_DIR / "seen.json"
SKILL_SOURCES = SCRIPT_DIR / "config" / "sources.json"

# ─── Interest → Source Mapping ────────────────────────────────────────────────

INTEREST_SOURCE_MAP = {
    "ai": ["Simon Willison", "LangChain Blog", "OpenAI Blog", "Google AI Blog", "Latent Space", "InfoQ AI/ML", "IEEE Spectrum AI"],
    "llm": ["Simon Willison", "LangChain Blog", "OpenAI Blog", "Latent Space"],
    "agent": ["Simon Willison", "LangChain Blog", "Latent Space"],
    "ml": ["Google AI Blog", "InfoQ AI/ML", "IEEE Spectrum AI"],
    "machine learning": ["Google AI Blog", "InfoQ AI/ML", "IEEE Spectrum AI"],
    "developer tools": ["GitHub Blog", "Hacker News (best)", "Lobsters", "TLDR Newsletter"],
    "dev tools": ["GitHub Blog", "Hacker News (best)", "Lobsters", "TLDR Newsletter"],
    "programming": ["Hacker News (best)", "Lobsters", "GitHub Blog"],
    "startup": ["TechCrunch", "a16z", "Product Hunt"],
    "tech": ["Techmeme", "TechCrunch", "The Verge", "Ars Technica", "TLDR Newsletter"],
    "product": ["Product Hunt", "Stratechery"],
    "design": ["Dezeen", "Smashing Magazine"],
    "ux": ["Smashing Magazine"],
    "ev": ["CnEVPost", "InsideEVs", "CarNewsChina"],
    "electric vehicle": ["CnEVPost", "InsideEVs"],
    "automotive": ["CnEVPost", "InsideEVs", "CarNewsChina"],
    "health": ["Fierce Healthcare"],
    "healthcare": ["Fierce Healthcare"],
    "system design": ["ByteByteGo"],
    "architecture": ["ByteByteGo", "Dezeen"],
    "culture": ["The Marginalian", "Aeon"],
    "philosophy": ["Aeon", "The Marginalian"],
}

# Always include these high-quality general sources
DEFAULT_SOURCES = ["Techmeme", "Hacker News (best)"]

# ─── Helpers ──────────────────────────────────────────────────────────────────

def load_user_config() -> Dict[str, Any]:
    """Load user config or create default."""
    default = {"interests": [], "language": "zh", "max_items": 5}
    if not USER_CONFIG.exists():
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        USER_CONFIG.write_text(json.dumps(default, indent=2, ensure_ascii=False))
        return default
    try:
        return json.loads(USER_CONFIG.read_text())
    except:
        return default

def load_skill_sources() -> List[Dict[str, Any]]:
    """Load RSS sources from skill config."""
    if not SKILL_SOURCES.exists():
        return []
    try:
        data = json.loads(SKILL_SOURCES.read_text())
        return data.get("rss", [])
    except:
        return []

def load_seen() -> Set[str]:
    """Load seen URLs for deduplication."""
    if not SEEN_FILE.exists():
        return set()
    try:
        data = json.loads(SEEN_FILE.read_text())
        cutoff = (datetime.now() - timedelta(days=7)).isoformat()
        return {url for url, ts in data.items() if ts > cutoff}
    except:
        return set()

def save_seen(urls: Set[str]):
    """Save seen URLs with timestamps."""
    existing = {}
    if SEEN_FILE.exists():
        try:
            existing = json.loads(SEEN_FILE.read_text())
        except:
            pass
    now = datetime.now().isoformat()
    for url in urls:
        if url not in existing:
            existing[url] = now
    cutoff = (datetime.now() - timedelta(days=7)).isoformat()
    pruned = {url: ts for url, ts in existing.items() if ts > cutoff}
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    SEEN_FILE.write_text(json.dumps(pruned, indent=2))

def strip_html(text: str) -> str:
    """Remove HTML tags and clean up text."""
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'https?://\S+', '', text)
    text = re.sub(r'\s+', ' ', text)
    cleaned = text.strip()[:300]
    if cleaned.startswith("Article URL:") or len(cleaned) < 20:
        return ""
    return cleaned

def match_sources_to_interests(interests: List[str], all_sources: List[Dict]) -> List[Dict]:
    """Select RSS sources based on user interests."""
    source_names = set(DEFAULT_SOURCES)
    
    for interest in interests:
        interest_lower = interest.lower()
        # Direct match
        if interest_lower in INTEREST_SOURCE_MAP:
            source_names.update(INTEREST_SOURCE_MAP[interest_lower])
        # Partial match
        for key, sources in INTEREST_SOURCE_MAP.items():
            if key in interest_lower or interest_lower in key:
                source_names.update(sources)
    
    # Filter to sources we have
    matched = [s for s in all_sources if s.get("name") in source_names]
    
    # If no matches, use top-rated sources
    if not matched:
        matched = [s for s in all_sources if s.get("rating") in ("S", "A")][:5]
    
    return matched

# ─── RSS Fetching ─────────────────────────────────────────────────────────────

def fetch_rss(source: Dict[str, str]) -> List[Dict[str, Any]]:
    """Fetch items from RSS/Atom feed."""
    items = []
    try:
        req = urllib.request.Request(
            source["url"],
            headers={"User-Agent": "Mozilla/5.0 (compatible; OpenClaw/1.0)"}
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            content = resp.read().decode("utf-8", errors="replace")
        
        root = ET.fromstring(content)
        
        # RSS 2.0
        for item in root.findall(".//item")[:10]:
            title = item.findtext("title", "")
            link = item.findtext("link", "")
            desc = item.findtext("description", "")
            pub = item.findtext("pubDate", "")
            if title and link:
                items.append({
                    "title": title.strip(),
                    "url": link.strip(),
                    "summary": strip_html(desc),
                    "source": source.get("name", "RSS"),
                    "source_rating": source.get("rating", "B"),
                    "published": pub,
                })
        
        # Atom
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        for entry in root.findall(".//atom:entry", ns)[:10]:
            title = entry.findtext("atom:title", "", ns)
            link_el = entry.find("atom:link", ns)
            link = link_el.get("href", "") if link_el is not None else ""
            summary = entry.findtext("atom:summary", "", ns) or entry.findtext("atom:content", "", ns)
            updated = entry.findtext("atom:updated", "", ns)
            if title and link:
                items.append({
                    "title": title.strip(),
                    "url": link.strip(),
                    "summary": strip_html(summary),
                    "source": source.get("name", "Atom"),
                    "source_rating": source.get("rating", "B"),
                    "published": updated,
                })
    except Exception as e:
        print(f"# RSS fetch error ({source.get('name', source['url'])}): {e}", file=sys.stderr)
    
    return items

# ─── Main ─────────────────────────────────────────────────────────────────────

def curate(dry_run: bool = False, output_json: bool = False) -> str:
    """Run curation cycle. Returns formatted output."""
    config = load_user_config()
    all_sources = load_skill_sources()
    seen = load_seen()
    
    interests = config.get("interests", [])
    language = config.get("language", "zh")
    max_items = config.get("max_items", 5)
    
    # Match sources to interests
    sources = match_sources_to_interests(interests, all_sources)
    
    if not sources:
        return "No RSS sources available. Check skill config/sources.json"
    
    print(f"# Fetching from {len(sources)} sources: {[s['name'] for s in sources]}", file=sys.stderr)
    
    # Fetch from all matched sources
    all_items = []
    for source in sources:
        items = fetch_rss(source)
        all_items.extend(items)
    
    # Deduplicate by URL
    unique_items = []
    new_seen = set(seen)
    for item in all_items:
        url = item.get("url", "")
        if url and url not in new_seen:
            new_seen.add(url)
            unique_items.append(item)
    
    # Sort by recency first (newest first), then source rating
    # Parse published date for sorting
    def parse_date(item):
        pub = item.get("published", "")
        if not pub:
            return ""
        # Try to extract ISO-ish date
        import re
        # Match YYYY-MM-DD or similar
        m = re.search(r'(\d{4})-?(\d{2})-?(\d{2})', pub)
        if m:
            return f"{m.group(1)}{m.group(2)}{m.group(3)}"
        # Match "03 Apr 2026" or "Apr 03 2026"
        m = re.search(r'(\d{1,2})\s+(\w{3})\s+(\d{4})', pub)
        if m:
            months = {'Jan':'01','Feb':'02','Mar':'03','Apr':'04','May':'05','Jun':'06',
                      'Jul':'07','Aug':'08','Sep':'09','Oct':'10','Nov':'11','Dec':'12'}
            mon = months.get(m.group(2), '01')
            return f"{m.group(3)}{mon}{m.group(1).zfill(2)}"
        return pub
    
    rating_order = {"S": 0, "A": 1, "B": 2}
    unique_items.sort(key=lambda x: (parse_date(x), -rating_order.get(x.get("source_rating", "B"), 2)), reverse=True)
    
    # Take top items with diversity (max 2 per source)
    source_count = {}
    result_items = []
    for item in unique_items:
        src = item.get("source", "")
        if source_count.get(src, 0) >= 2:
            continue
        source_count[src] = source_count.get(src, 0) + 1
        result_items.append(item)
        if len(result_items) >= max_items:
            break
    
    if not dry_run:
        save_seen(new_seen)
    
    if output_json:
        return json.dumps(result_items, indent=2, ensure_ascii=False)
    
    # Format as readable text
    if not result_items:
        return "No new content found."
    
    lines = []
    for item in result_items:
        title = item["title"]
        summary = item["summary"]
        source = item["source"]
        url = item["url"]
        
        if summary:
            lines.append(f"• **{title}** ({source})\n  {summary}\n  {url}\n")
        else:
            lines.append(f"• **{title}** ({source})\n  {url}\n")
    
    return "\n".join(lines)

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Curate content based on interests")
    parser.add_argument("--dry-run", action="store_true", help="Don't update seen cache")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()
    
    output = curate(dry_run=args.dry_run, output_json=args.json)
    print(output)

if __name__ == "__main__":
    main()
