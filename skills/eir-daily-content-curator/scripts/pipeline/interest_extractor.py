#!/usr/bin/env python3
"""
Interest Extractor — Post-process and sync interests with Eir.

This script handles:
1. Loading interests extracted by OpenClaw (from local file)
2. Syncing with Eir profile (merge + push)
3. Applying decay to stale interests

The actual extraction from conversations should be done by OpenClaw using
the prompt in references/interest-extraction-prompt.md. This script just
handles the sync and persistence.

Usage:
  python3 scripts/pipeline/interest_extractor.py              # sync + decay
  python3 scripts/pipeline/interest_extractor.py --push       # push local to Eir
  python3 scripts/pipeline/interest_extractor.py --pull       # pull from Eir
  python3 scripts/pipeline/interest_extractor.py --stats      # show current profile
  python3 scripts/pipeline/interest_extractor.py --add '{"slug":"ai-agents","strength":0.7}'
"""

import argparse
import json
import os
import sys
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Optional

# === Config ===
sys.path.insert(0, str(Path(__file__).parent))
from eir_config import (
    SKILL_DIR, WORKSPACE, CONFIG_DIR, DATA_DIR,
    load_config as _load_eir_config, get_api_url, get_api_key,
)

REFERENCES_DIR = SKILL_DIR / "references"
INTERESTS_FILE = CONFIG_DIR / "interests.json"
SETTINGS_FILE = CONFIG_DIR / "settings.json"
EIR_CONFIG = CONFIG_DIR / "eir.json"
TOPIC_ENRICHMENTS_FILE = DATA_DIR / "topic_enrichments.json"

# Decay settings
DECAY_HALF_LIFE_DAYS = 14  # Strength halves every 14 days without signals


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def load_settings() -> Dict:
    if SETTINGS_FILE.exists():
        return json.loads(SETTINGS_FILE.read_text())
    return {"mode": "standalone"}


def load_interests() -> Dict:
    if INTERESTS_FILE.exists():
        return json.loads(INTERESTS_FILE.read_text())
    return {
        "topics": {},
        "disliked": [],
        "patterns": {},
        "lastSynced": None,
    }


def save_interests(interests: Dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    INTERESTS_FILE.write_text(json.dumps(interests, indent=2, ensure_ascii=False))


def load_eir_api_key() -> Optional[str]:
    if EIR_CONFIG.exists():
        config = json.loads(EIR_CONFIG.read_text())
        return config.get("apiKey")
    return None


def apply_decay(interests: Dict) -> Dict:
    """Apply time-based decay to interest strengths."""
    topics = interests.get("topics", {})
    now = datetime.now(timezone.utc)
    
    for slug, data in topics.items():
        last_signal = data.get("lastSignal")
        if not last_signal:
            continue
        
        try:
            last_dt = datetime.fromisoformat(last_signal.replace("Z", "+00:00"))
            days_since = (now - last_dt).days
            
            if days_since > 0:
                # Exponential decay: strength * 0.5^(days/half_life)
                decay_factor = 0.5 ** (days_since / DECAY_HALF_LIFE_DAYS)
                old_strength = data.get("strength", 0.5)
                data["strength"] = round(old_strength * decay_factor, 3)
                data["decayApplied"] = now_iso()
        except Exception:
            pass
    
    # Remove topics with strength < 0.1
    interests["topics"] = {k: v for k, v in topics.items() if v.get("strength", 0) >= 0.1}
    
    return interests


def add_interest(interests: Dict, signal: Dict) -> Dict:
    """Add or update a single interest from OpenClaw extraction."""
    topics = interests.get("topics", {})
    slug = signal.get("slug")
    
    if not slug:
        return interests
    
    if slug in topics:
        # Update existing
        old = topics[slug]
        old["occurrences"] = old.get("occurrences", 0) + 1
        old["lastSignal"] = now_iso()
        # Weighted update: keep 70% old, add 30% new
        old_strength = old.get("strength", 0.5)
        new_strength = signal.get("strength", 0.5)
        old["strength"] = min(1.0, old_strength * 0.7 + new_strength * 0.3)
        if signal.get("label"):
            old["label"] = signal["label"]
        if signal.get("evidence"):
            old["lastEvidence"] = signal["evidence"]
    else:
        # Create new
        topics[slug] = {
            "slug": slug,
            "label": signal.get("label", slug.replace("-", " ").title()),
            "strength": signal.get("strength", 0.5) * 0.8,  # Start slightly lower
            "occurrences": 1,
            "sources": ["conversation"],
            "category": signal.get("category", "other"),
            "signalType": signal.get("signal_type", "implicit"),
            "firstSeen": now_iso(),
            "lastSignal": now_iso(),
            "lastEvidence": signal.get("evidence"),
        }
    
    interests["topics"] = topics
    return interests


def add_disliked(interests: Dict, slug: str) -> Dict:
    """Add a topic to disliked list."""
    disliked = interests.get("disliked", [])
    if slug not in disliked:
        disliked.append(slug)
    interests["disliked"] = disliked
    
    # Remove from topics if present
    topics = interests.get("topics", {})
    if slug in topics:
        del topics[slug]
        interests["topics"] = topics
    
    return interests


def pull_from_eir(interests: Dict, api_key: str) -> Dict:
    """Pull interests from Eir profile."""
    try:
        req = urllib.request.Request(
            f"{get_api_url()}/api/oc/profile",
            headers={"Authorization": f"Bearer {api_key}"}
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            profile = json.loads(resp.read())
        
        topics = interests.get("topics", {})
        
        # Merge remote interests
        for item in profile.get("short_term_interests", []) + profile.get("long_term_interests", []):
            slug = item.get("slug", "")
            if not slug:
                continue
            
            remote_strength = item.get("strength", 0.5)
            
            if slug in topics:
                # Keep max strength
                if remote_strength > topics[slug].get("strength", 0):
                    topics[slug]["strength"] = remote_strength
                topics[slug]["lastSynced"] = now_iso()
            else:
                topics[slug] = {
                    "slug": slug,
                    "label": item.get("topic", slug),
                    "strength": remote_strength,
                    "occurrences": item.get("occurrences", 1),
                    "sources": ["eir"],
                    "lastSignal": item.get("updated"),
                    "lastSynced": now_iso(),
                }
        
        interests["topics"] = topics
        interests["lastSynced"] = now_iso()
        print(f"  ✅ Pulled {len(profile.get('short_term_interests', []))} interests from Eir")
        return interests
        
    except Exception as e:
        print(f"  ⚠️ Pull failed: {e}")
        return interests


def push_to_eir(interests: Dict, api_key: str) -> bool:
    """Push local interests to Eir via POST /profile."""
    try:
        topics = interests.get("topics", {})
        
        # Build signals array
        signals = []
        for slug, data in topics.items():
            if data.get("strength", 0) >= 0.3:  # Only push meaningful interests
                signals.append({
                    "slug": slug,
                    "label": data.get("label", slug),
                    "strength": data.get("strength", 0.5),
                    "source": "openclaw",
                })
        
        if not signals:
            print("  No interests to push (all below threshold)")
            return True
        
        payload = json.dumps({"signals": signals}).encode()
        
        req = urllib.request.Request(
            f"{get_api_url()}/api/oc/profile",
            data=payload,
            method="POST",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read())
        
        print(f"  ✅ Pushed {len(signals)} interests to Eir")
        interests["lastSynced"] = now_iso()
        return True
        
    except Exception as e:
        print(f"  ⚠️ Push failed: {e}")
        return False


def load_topic_enrichments() -> Dict:
    """Load locally-generated topic enrichments."""
    if TOPIC_ENRICHMENTS_FILE.exists():
        try:
            return json.loads(TOPIC_ENRICHMENTS_FILE.read_text())
        except Exception:
            pass
    return {}


def save_topic_enrichments(enrichments: Dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    TOPIC_ENRICHMENTS_FILE.write_text(json.dumps(enrichments, indent=2, ensure_ascii=False))


def enrich_topics(interests: Dict, directives: List[Dict]) -> Dict:
    """Generate personalized topic descriptions from local interests + API directives.

    For each directive, produce:
    - description_enriched: expanded description using user's interest context
    - keywords_enriched: additional keywords from interest signals
    - search_queries: suggested search queries (if directive has none)
    - embedding_text: combined text optimized for embedding similarity matching

    This is a deterministic, no-LLM enrichment. It merges:
    1. API directive fields (description, keywords, search_hints)
    2. Local interest context (label, evidence, category)
    """
    topics = interests.get("topics", {})
    enrichments = load_topic_enrichments()

    for d in directives:
        slug = d.get("slug", "")
        if not slug:
            continue

        api_desc = d.get("description") or ""
        api_keywords = d.get("keywords") or []
        api_topic = d.get("topic") or slug
        hints = d.get("search_hints") or {}
        suggested_queries = hints.get("suggested_queries") or []

        # Find matching local interest
        local = topics.get(slug, {})
        local_label = local.get("label", "")
        local_evidence = local.get("lastEvidence", "")
        local_category = local.get("category", "")

        # Build enriched description
        desc_parts = []
        if api_desc:
            desc_parts.append(api_desc)
        elif local_label and local_label != slug:
            # API has no description — use local interest as base
            desc_parts.append(local_label)

        if local_evidence and local_evidence not in (api_desc or ""):
            desc_parts.append("User context: %s" % local_evidence)

        description_enriched = ". ".join(desc_parts) if desc_parts else api_topic

        # Build enriched keywords
        kw_set = set(api_keywords)
        # Add slug words as keywords
        for part in slug.split("-"):
            if len(part) > 2:
                kw_set.add(part)
        # Add local label words (if not Chinese, split by space)
        if local_label:
            for word in local_label.split():
                if len(word) > 2:
                    kw_set.add(word)
        keywords_enriched = list(kw_set)

        # Build search queries if API has none
        search_queries = list(suggested_queries)
        if not search_queries:
            # Generate basic queries from topic + keywords
            if api_keywords:
                search_queries.append(" ".join(api_keywords[:3]) + " latest news")
            search_queries.append(api_topic + " 2026")
            # Add English variant if topic is Chinese
            if any('\u4e00' <= c <= '\u9fff' for c in api_topic):
                if keywords_enriched:
                    en_kw = [k for k in keywords_enriched if not any('\u4e00' <= c <= '\u9fff' for c in k)][:3]
                    if en_kw:
                        search_queries.append(" ".join(en_kw) + " latest")

        # Build embedding text (optimized for matching article titles/content)
        embed_parts = [api_topic]
        if description_enriched and description_enriched != api_topic:
            embed_parts.append(description_enriched)
        if keywords_enriched:
            embed_parts.append(" ".join(keywords_enriched[:10]))
        embedding_text = " ".join(embed_parts)

        enrichments[slug] = {
            "slug": slug,
            "topic": api_topic,
            "description_enriched": description_enriched,
            "keywords_enriched": keywords_enriched,
            "search_queries": search_queries,
            "embedding_text": embedding_text,
            "source": "local+api",
            "updated_at": now_iso(),
        }

    save_topic_enrichments(enrichments)
    return enrichments


def show_extraction_prompt():
    """Print the extraction prompt for OpenClaw to use."""
    prompt_file = REFERENCES_DIR / "interest-extraction-prompt.md"
    if prompt_file.exists():
        print(prompt_file.read_text())
    else:
        print("⚠️ Extraction prompt not found. See references/interest-extraction-prompt.md")


def main():
    parser = argparse.ArgumentParser(description="Interest Extractor — Sync and manage interests")
    parser.add_argument("--push", action="store_true", help="Push local interests to Eir")
    parser.add_argument("--pull", action="store_true", help="Pull interests from Eir")
    parser.add_argument("--stats", action="store_true", help="Show current profile")
    parser.add_argument("--decay", action="store_true", help="Apply decay to stale interests")
    parser.add_argument("--add", type=str, help="Add interest: JSON object with slug, strength, etc.")
    parser.add_argument("--dislike", type=str, help="Add topic to disliked list")
    parser.add_argument("--prompt", action="store_true", help="Show extraction prompt for OpenClaw")
    args = parser.parse_args()
    
    if args.prompt:
        show_extraction_prompt()
        return
    
    settings = load_settings()
    mode = settings.get("mode", "standalone")
    interests = load_interests()
    api_key = load_eir_api_key()
    
    # Auto-detect mode mismatch
    if api_key and mode == "standalone":
        print("⚠️  Detected Eir connection (config/eir.json exists) but mode is 'standalone'")
        print("    Run: python3 scripts/setup.py  # to switch to eir mode")
        print("    Or manually edit config/settings.json: mode = 'eir'")
        print()
    
    print(f"🎯 Interest Manager ({mode} mode)")
    
    if args.stats:
        topics = interests.get("topics", {})
        disliked = interests.get("disliked", [])
        print(f"\n📊 {len(topics)} interests, {len(disliked)} disliked")
        
        if topics:
            sorted_topics = sorted(topics.items(), key=lambda x: x[1].get("strength", 0), reverse=True)
            print("\nTop interests:")
            for slug, data in sorted_topics[:10]:
                strength = data.get("strength", 0)
                occ = data.get("occurrences", 0)
                label = data.get("label", slug)
                print(f"  {strength:.2f}  {label} ({occ}x)")
        
        if disliked:
            print(f"\nDisliked: {', '.join(disliked[:10])}")
        return
    
    if args.add:
        try:
            signal = json.loads(args.add)
            interests = add_interest(interests, signal)
            save_interests(interests)
            print(f"  ✅ Added interest: {signal.get('slug')}")
        except json.JSONDecodeError as e:
            print(f"  ❌ Invalid JSON: {e}")
        return
    
    if args.dislike:
        interests = add_disliked(interests, args.dislike)
        save_interests(interests)
        print(f"  ✅ Added to disliked: {args.dislike}")
        return
    
    if args.decay:
        interests = apply_decay(interests)
        save_interests(interests)
        print(f"  ✅ Applied decay, {len(interests.get('topics', {}))} interests remaining")
        return
    
    if args.pull:
        if not api_key:
            print("  ❌ No Eir API key. Run /curate --connect first")
            return
        interests = pull_from_eir(interests, api_key)
        save_interests(interests)
        return
    
    if args.push:
        if not api_key:
            print("  ❌ No Eir API key. Run /curate --connect first")
            return
        push_to_eir(interests, api_key)
        save_interests(interests)
        return
    
    # Default: pull + decay + push + enrich (full sync)
    print("  Running full sync...")
    
    if api_key and mode == "eir":
        interests = pull_from_eir(interests, api_key)
    
    interests = apply_decay(interests)
    
    if api_key and mode == "eir":
        push_to_eir(interests, api_key)
    
    save_interests(interests)
    print(f"  💾 Saved {len(interests.get('topics', {}))} interests")
    
    # Enrich topic descriptions from directives + local interests
    if api_key and mode == "eir":
        directives_file = DATA_DIR / "directives.json"
        if directives_file.exists():
            try:
                data = json.loads(directives_file.read_text())
                all_dirs = data.get("directives", []) + data.get("tracked", [])
                enrichments = enrich_topics(interests, all_dirs)
                print(f"  🔖 Enriched {len(enrichments)} topic descriptions")
            except Exception as e:
                print(f"  ⚠️ Topic enrichment failed: {e}")


if __name__ == "__main__":
    main()
