# Interest Extraction & Sync Prompt

> This prompt is used by the OpenClaw agent to analyze conversations and sync interest operations to Eir.

## Overview

You analyze recent OpenClaw conversations to discover what the user genuinely cares about, then sync structured operations to the Eir interest API. 

**You decide WHAT the user is interested in. The server decides HOW MUCH (strength, heat, engagement).**

## What This IS

- Discovering genuine interests from conversation patterns
- Generalizing private contexts into universal topics  
- Confirming or rejecting server-generated suggestions
- Carefully merging semantically overlapping topics

## What This is NOT

- Tracking what tasks the user is doing (debugging React ≠ interest in React)
- Calculating strength/heat/engagement (server does this)
- Applying time-based decay (server does this)
- Replacing the content curation pipeline (that's a separate concern)

## Data Sources

### 1. Server Context
`GET /oc/interests/context` returns:
- Current topics with strength, heat, engagement data
- System suggestions (demote/merge) based on behavioral analysis
- User language settings

### 2. Local Conversations  
Read recent OpenClaw session transcripts from all agents to extract user messages. Focus on the last 24-48 hours. Look for:
- Topics the user actively discussed or asked about
- Recurring themes across multiple conversations
- Explicit interest signals ("I want to follow X", "this is fascinating")

## Instructions

### Step 1: Fetch Server Context
Call `GET /oc/interests/context` to get current topics and suggestions.

### Step 2: Analyze Conversations
Read recent session transcripts. For each user message, classify:

**✅ Strong signals (include):**
- Explicit request: "I want to follow news about X"
- Deep discussion: 3+ turns exploring a topic
- Curious questions: "How does X work?" "What's the latest on X?"
- Repeated mentions: Same topic across multiple conversations
- Emotional engagement: excitement, concern, strong opinions about a topic

**⚠️ Weak signals (usually skip):**
- Single mention, never revisited
- Mentioned while doing a task (tool usage ≠ interest)
- From a document being processed (reading about X ≠ interested in X)

**❌ NOT signals:**
- "Debug this React code" → task, not interest
- "Search for X" → command, not interest  
- "I don't care about crypto" → this is DISLIKE, handle separately

### Step 3: Apply Privacy Filter

Interest labels are stored and may be processed by third-party services. **Protect user privacy while preserving useful public context.**

**Quick test: "Would a random person on the internet recognize this?"**

| User context | → Interest label | Why |
|---|---|---|
| "Microsoft AI news" | "Microsoft AI" ✅ | Public company |
| "OpenAI GPT-5" | "GPT-5" ✅ | Public product |
| "Acme Corp proposal" | "Business proposals" | Private client |
| "Our company OKRs" | "OKR methodology" | Private employer |
| "My project Eir" | "Content curation" | User's own project |
| "Report for John" | "Report writing" | Private person |
| "LangChain integration" | "LangChain" ✅ | Public OSS |

**Also keep `reason` strings generic — don't leak private context there either.**

### Step 4: Process Server Suggestions

**Demote suggestions → default accept.** Server has engagement data you don't. If the server says "user hasn't clicked on X in 14 days", trust it — unless you see clear evidence in recent conversations that the user is still interested.

**Merge suggestions → independent judgment.** Server may suggest merging based on keyword overlap, but you need to verify semantic equivalence. See merge strategy below.

### Step 5: Decide Merge Operations

**Conservative merge strategy — only merge when ALL conditions are met:**

1. Topics are truly semantically equivalent (not just related)
2. Both topics have strength < 0.5 (user isn't deeply engaged in the distinction)
3. No recent conversation evidence that the user treats them as separate concerns

**Examples:**
- `react-hooks` + `react-state-management` → probably DON'T merge (developers care about the distinction)
- `ai-safety` + `ai-alignment` → probably DON'T merge (researchers distinguish these)
- `typescript-tips` + `typescript-tricks` → merge to `typescript` (no meaningful distinction)
- `home-automation` + `smart-home` → merge (same thing, different words)

**When in doubt, don't merge.** Extra topics are cheap; lost engagement history is expensive.

### Step 6: Set decay_type for New Interests

| decay_type | Use when | Examples |
|---|---|---|
| `event` | Time-sensitive news, product launches | GPT-5 launch, WWDC 2026, specific conference |
| `ongoing` | Active interest area, likely to persist months | AI safety, developer tools, product design |
| `evergreen` | Fundamental interest, part of identity | Productivity, systems thinking, design philosophy |

### Step 7: Output Operations

```json
{
  "operations": [
    {
      "op": "add",
      "slug": "topic-slug-kebab-case",
      "label": "Topic Label in User's Primary Language",
      "decay_type": "event|ongoing|evergreen",
      "reason": "Brief reason (no private info)"
    },
    {
      "op": "boost",
      "slug": "existing-topic",
      "reason": "User explicitly asked to track this"
    },
    {
      "op": "demote",
      "slug": "topic-to-demote",
      "reason": "Confirmed server suggestion: no engagement"
    },
    {
      "op": "delete",
      "slug": "topic-to-remove",
      "reason": "User explicitly said not interested"
    },
    {
      "op": "merge",
      "from": ["slug-1", "slug-2"],
      "to": "merged-slug",
      "to_label": "Merged Topic Label",
      "reason": "Semantically identical, both low engagement"
    }
  ],
  "skipped_suggestions": [
    {
      "slug": "topic-slug",
      "action": "demote",
      "reason": "Recent conversation shows continued interest despite low clicks"
    }
  ],
  "notes": "Optional: brief summary of what changed and why"
}
```

Then POST this to `POST /oc/interests/sync`.

## Rules

1. **Privacy first**: Generalize specific contexts to universal interests
2. **Label language**: Always use the user's `primary_language` from context
3. **Slug format**: kebab-case, English, descriptive (`product-design` not `eir-product-design`)
4. **No duplicates**: Check against current topics before adding
5. **Quality over quantity**: 3-5 high-confidence interests > 20 weak ones
6. **Demote = default accept**: Trust server engagement data
7. **Merge = conservative**: Only when semantically identical AND both low-strength
8. **Reason = also private-safe**: No company names, project names, or personal info in reason strings
9. **Interest ≠ task**: Distinguish genuine curiosity from work execution
