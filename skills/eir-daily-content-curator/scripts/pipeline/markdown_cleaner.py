#!/usr/bin/env python3
"""
Markdown Cleaner — Strip navigation garbage, boilerplate, and noise from crawled markdown.

Used by backfill_snippets.py after crawling to improve content quality.

Usage:
  from markdown_cleaner import clean_markdown
  cleaned = clean_markdown(raw_markdown)
"""

import re
from typing import Optional


# Lines matching these patterns are removed entirely
REMOVE_LINE_PATTERNS = [
    # Navigation
    r'^\s*(?:Skip to (?:content|main|navigation|menu))',
    r'^\s*(?:Home|About|Contact|Blog|FAQ|Help|Support|Careers|Press)\s*$',
    r'^\s*(?:Menu|Navigation|Sidebar|Header|Footer)\s*$',
    # Auth / subscription
    r'^\s*(?:Sign (?:up|in)|Log ?(?:in|out)|Subscribe|Create (?:account|free account))',
    r'^\s*(?:Already (?:have|a) (?:subscriber|member|account))',
    r'^\s*(?:Free trial|Start (?:free|your) trial|Join (?:for free|now))',
    # Social sharing
    r'^\s*(?:Share|Tweet|Email|Pin|Post)\s*(?:this|on|via)?\s*$',
    r'^\s*(?:Share on (?:Facebook|Twitter|LinkedIn|X|Reddit))',
    r'^\s*(?:Follow (?:us|me) on)',
    # Cookie / legal
    r'^\s*(?:We use cookies|This (?:site|website) uses cookies|Cookie (?:policy|consent|settings))',
    r'^\s*(?:Accept (?:all|cookies)|Reject (?:all|cookies))',
    r'^\s*(?:Privacy Policy|Terms of (?:Service|Use)|Legal Notice)',
    r'^\s*(?:All [Rr]ights [Rr]eserved)',
    r'^\s*©\s*\d{4}',
    # Ads
    r'^\s*(?:Advertisement|Sponsored|Ad)\s*$',
    r'^\s*(?:Promoted|Paid (?:content|partnership))',
    # Navigation elements
    r'^\s*(?:Previous|Next) (?:article|post|story|page)',
    r'^\s*(?:Read (?:more|next|also)|See (?:also|more))\s*$',
    r'^\s*(?:Related|Recommended|Popular|Trending) (?:articles|stories|posts|reads)',
    r'^\s*(?:You (?:might|may) (?:also )?like)',
    r'^\s*(?:More (?:from|in|on) )',
    # Empty formatting
    r'^\s*(?:\|[\s-]*\|[\s-]*\|?)\s*$',  # empty table rows
    r'^\s*(?:---+|===+|\*\*\*+)\s*$',     # horizontal rules (standalone)
    r'^\s*!\[.*?\]\(data:image',           # base64 images
    # Common site chrome
    r'^\s*\[?\s*(?:Back to top|Go to top|↑|⬆)',
    r'^\s*(?:Loading|Please wait|Fetching)',
    r'^\s*(?:Comments|Leave a (?:comment|reply)|Join the (?:conversation|discussion))\s*$',
    r'^\s*\d+\s*(?:comments?|replies|views|shares|likes)\s*$',
]

# Blocks matching these are collapsed or removed
REMOVE_BLOCK_PATTERNS = [
    r'javascript:',
    r'\[.*?\]\(javascript:.*?\)',  # javascript: links
]

# Image/link noise at the start of documents
LEADING_NOISE = [
    r'^(?:\s*(?:\[!\[.*?\]\(.*?\)\]\(.*?\)|!\[.*?\]\(.*?\))\s*\n?)+',  # leading images/badges
    r'^(?:\s*\[.*?\]\(.*?\)\s*\n?){3,}',  # 3+ consecutive bare links
]


def clean_markdown(text: str, min_line_len: int = 3) -> str:
    """
    Clean crawled markdown by removing navigation, boilerplate, and noise.
    
    Args:
        text: Raw markdown from Crawl4AI or similar
        min_line_len: Minimum line length to keep (shorter lines removed unless blank)
    
    Returns:
        Cleaned markdown string
    """
    if not text:
        return ""

    # 1. Remove javascript: links
    for pattern in REMOVE_BLOCK_PATTERNS:
        text = re.sub(pattern, '', text)

    # 2. Process line by line
    lines = text.split('\n')
    cleaned_lines = []
    consecutive_empty = 0
    
    for line in lines:
        stripped = line.strip()
        
        # Skip lines matching remove patterns
        should_remove = False
        for pattern in REMOVE_LINE_PATTERNS:
            if re.match(pattern, stripped, re.IGNORECASE):
                should_remove = True
                break
        
        if should_remove:
            continue
        
        # Collapse multiple empty lines
        if not stripped:
            consecutive_empty += 1
            if consecutive_empty <= 2:
                cleaned_lines.append('')
            continue
        else:
            consecutive_empty = 0
        
        # Skip very short non-empty lines that look like nav fragments
        if len(stripped) < min_line_len and not stripped.startswith('#'):
            continue
        
        cleaned_lines.append(line)
    
    result = '\n'.join(cleaned_lines).strip()
    
    # 3. Remove leading image/link noise
    for pattern in LEADING_NOISE:
        result = re.sub(pattern, '', result, flags=re.MULTILINE).strip()
    
    # 4. Remove trailing boilerplate (last 10 lines often have footer noise)
    lines = result.split('\n')
    if len(lines) > 15:
        # Check last 10 lines for footer patterns
        footer_start = len(lines)
        footer_patterns = [
            r'^\s*(?:©|Copyright|All rights)',
            r'^\s*(?:Privacy|Terms|Legal|Contact|About)',
            r'^\s*(?:Follow|Subscribe|Newsletter)',
            r'^\s*(?:Powered by|Built with)',
        ]
        for i in range(len(lines) - 1, max(len(lines) - 10, 0), -1):
            is_footer = any(re.match(p, lines[i].strip(), re.IGNORECASE) for p in footer_patterns)
            if is_footer:
                footer_start = i
            elif lines[i].strip():
                break
        
        if footer_start < len(lines):
            lines = lines[:footer_start]
            result = '\n'.join(lines).strip()
    
    # 5. Final cleanup: collapse excessive whitespace
    result = re.sub(r'\n{4,}', '\n\n\n', result)
    
    return result


def clean_snippet_file(filepath: str, dry_run: bool = False) -> dict:
    """Clean a snippet JSON file in place. Returns stats."""
    import json
    from pathlib import Path
    
    p = Path(filepath)
    data = json.loads(p.read_text())
    
    content = data.get("content") or data.get("markdown") or ""
    if isinstance(content, dict):
        content = content.get("raw_markdown", content.get("markdown", ""))
    
    if not content:
        return {"status": "empty", "before": 0, "after": 0}
    
    before_len = len(content)
    cleaned = clean_markdown(content)
    after_len = len(cleaned)
    reduction = (before_len - after_len) / before_len * 100 if before_len else 0
    
    if not dry_run and after_len != before_len:
        data["content"] = cleaned
        data["content_cleaned"] = True
        data["clean_stats"] = {
            "before_chars": before_len,
            "after_chars": after_len,
            "reduction_pct": round(reduction, 1),
        }
        p.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    
    return {
        "status": "cleaned" if reduction > 1 else "already_clean",
        "before": before_len,
        "after": after_len,
        "reduction_pct": round(reduction, 1),
    }


def main():
    """Clean all snippets in data/snippets/."""
    import argparse
    import glob
    import json
    from pathlib import Path
    
    parser = argparse.ArgumentParser(description="Clean crawled markdown snippets")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--stats", action="store_true", help="Show quality stats only")
    args = parser.parse_args()
    
    snippets_dir = Path(__file__).parent.parent / "data" / "snippets"
    files = glob.glob(str(snippets_dir / "*.json"))
    
    total = len(files)
    cleaned = 0
    total_before = 0
    total_after = 0
    
    for f in files:
        result = clean_snippet_file(f, dry_run=args.dry_run or args.stats)
        if result["status"] == "cleaned":
            cleaned += 1
        total_before += result["before"]
        total_after += result["after"]
    
    reduction = (total_before - total_after) / total_before * 100 if total_before else 0
    mode = "DRY RUN" if args.dry_run else "STATS" if args.stats else "CLEANED"
    
    print(f"📄 Markdown Cleaner [{mode}]")
    print(f"  Total snippets: {total}")
    print(f"  Cleaned: {cleaned}")
    print(f"  Total chars: {total_before:,} → {total_after:,} ({reduction:.0f}% reduction)")
    print(f"  Saved: {(total_before - total_after) / 1024:.0f} KB")


if __name__ == "__main__":
    main()
