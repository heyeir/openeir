# Interest Extraction Prompt

Use this prompt when analyzing conversations to extract new interests.

## Context

You have access to:
1. User's current interest profile (from `/oc/interests/context`)
2. Recent conversations to analyze
3. System suggestions (topics to demote/merge)

## Instructions

Analyze the conversations and output structured operations for the interest sync API.

**Your responsibilities**:
- Identify NEW interests from conversations
- Decide on `decay_type` (event/ongoing/evergreen)
- Confirm or reject system merge suggestions
- Identify topics that should be merged (semantic overlap)
- **Generalize specific contexts into universal interests** (privacy protection)

**NOT your responsibilities**:
- Calculating strength/heat (server does this)
- Tracking engagement metrics (server does this)
- Applying decay (server does this)

## Prompt Template

```
You are analyzing conversations to extract user interests for Eir.

**User's primary language**: {primary_language}
All interest labels should be in this language.

**Current interests** (do NOT re-add these):
{current_topics_list}

**System suggestions**:
{suggestions_list}

**Recent conversations**:
{conversations}

---

## 🔒 Privacy Rules (CRITICAL)

Interest labels are stored and may be processed by third-party services. 
**Protect user privacy while preserving useful public context.**

### The Key Distinction: Private vs Public

**✅ Public/Well-known (OK to include)**:
- Famous companies: Microsoft, Apple, Google, Tesla, OpenAI, Anthropic
- Public products: iPhone, GPT-4, Claude, VS Code, React, Kubernetes
- Public figures: Elon Musk, Sam Altman (in news context)
- Open source projects: Linux, Node.js, LangChain
- Public events: WWDC, Google I/O, CES
- Cities/regions: 上海, 北京, San Francisco, Tokyo (general level)
- Famous institutions: 清华, 北大, MIT, Stanford, Harvard (newsworthy)

**❌ Private/Personally-identifiable (NEVER include)**:
- User's employer or clients (unless Fortune 500 / globally famous)
- User's own projects, startups, or products they're building
- Internal codenames, team names, department names
- Colleagues, family, friends by name
- Specific addresses, neighborhoods, buildings
- User's own school/hospital (unless globally famous AND in news context)
- Financial details, health conditions
- Private dates: birthdays, appointments, deadlines

### Quick Test
Ask: **"Would a random person on the internet recognize this?"**
- ✅ "Microsoft" — yes, everyone knows Microsoft
- ❌ "Acme Corp" — no, this is likely user's employer/client
- ✅ "Tesla Model Y" — yes, public product
- ❌ "Project Phoenix" — no, internal codename

### ✅ Generalization Examples:

| User context | → Interest label | Why |
|--------------|------------------|-----|
| "微软的 AI 新闻" | → "微软 AI" ✅ | Public company, OK |
| "Apple Vision Pro 发布" | → "Apple Vision Pro" ✅ | Public product |
| "OpenAI 的 GPT-5" | → "GPT-5" 或 "OpenAI" ✅ | Public |
| "Acme Corp 的提案" | → "商业提案写作" | Private client |
| "我们公司的 OKR" | → "OKR 方法论" | Private employer |
| "Eir 产品设计" | → "产品设计" | User's own project |
| "LangChain 集成" | → "LangChain" ✅ | Public OSS |
| "给 John 的报告" | → "报告写作" | Private person |
| "Sam Altman 的演讲" | → "Sam Altman" 或 "AI 行业动态" ✅ | Public figure |

### Reason field
Also keep reason strings generic — don't leak private context there either.

## What Makes a Good Interest

✅ **Strong signals**:
- Explicit request: "I want to follow news about X"
- Deep discussion: 3+ turns exploring a topic
- Curious questions: "How does X work?"
- Repeated mentions: Same topic in multiple conversations

⚠️ **Weak signals** (usually skip):
- Single mention, never revisited
- Mentioned while doing a task
- From a document being processed

❌ **NOT signals**:
- "Debug this React code" → NOT interest in React
- "I don't care about crypto" → This is DISLIKE, not interest
- Tool commands: "Search for X" is a command

## decay_type Selection

- **event**: Time-sensitive news/releases (GPT-5 launch, MCP 2.0 release)
  → Fast decay: 70% at 7 days
- **ongoing**: Active interest areas (AI safety, developer tools)
  → Slow decay: 85% at 30 days
- **evergreen**: Fundamental interests (productivity, design thinking)
  → Minimal decay: 90% at 60 days

## Output Format

```json
{
  "operations": [
    {
      "op": "add",
      "slug": "topic-slug-kebab-case",
      "label": "Topic Label in User's Language",
      "decay_type": "event|ongoing|evergreen",
      "reason": "Why this is a genuine interest (do NOT include private details here either)"
    },
    {
      "op": "merge",
      "from": ["slug-1", "slug-2"],
      "to": "merged-slug",
      "to_label": "Merged Topic Label",
      "reason": "Why these should be combined"
    },
    {
      "op": "delete",
      "slug": "topic-to-remove",
      "reason": "Why this should be removed"
    },
    {
      "op": "boost",
      "slug": "existing-topic",
      "reason": "User explicitly asked to track this"
    }
  ],
  "skipped_suggestions": [
    {
      "slug": "topic-slug",
      "action": "demote",
      "reason": "Why we're NOT applying this suggestion"
    }
  ],
  "notes": "Optional notes about the analysis"
}
```

## Rules

1. **Privacy first**: Generalize all specific contexts to universal interests
2. **Label language**: Always use the user's `primary_language`
3. **Slug format**: kebab-case, English, descriptive (e.g., `product-design` not `eir-product-design`)
4. **No duplicates**: Check against current topics before adding
5. **Quality over quantity**: 3-5 high-confidence interests > 20 weak ones
6. **Demote confirmations**: Apply system demote suggestions unless you have a reason not to
7. **Merge carefully**: Only merge if topics truly overlap semantically
8. **Reason field**: Also avoid private info in reason strings — keep generic
```

## Example

**Input**:
```
primary_language: zh
current_topics: ["ai-agents", "mcp-protocol"]
suggestions: [{ slug: "rust-programming", action: "demote", reason: "0 clicks" }]

conversations:
- User asked about building AI agents with LangGraph for their startup "Acme AI"
- User discussed concerns about AI alignment
- User mentioned debugging a Python script for the Acme dashboard (one-off)
- User expressed excitement about Apple Vision Pro announcement
- User is designing the Eir content curation feature
```

**Output**:
```json
{
  "operations": [
    {
      "op": "add",
      "slug": "ai-alignment",
      "label": "AI 对齐",
      "decay_type": "ongoing",
      "reason": "Discussed AI alignment concerns in depth"
    },
    {
      "op": "add",
      "slug": "apple-vision-pro",
      "label": "Apple Vision Pro",
      "decay_type": "event",
      "reason": "Showed excitement about product announcement"
    },
    {
      "op": "add",
      "slug": "content-curation",
      "label": "内容策展",
      "decay_type": "ongoing",
      "reason": "Actively working on content curation design"
    },
    {
      "op": "demote",
      "slug": "rust-programming",
      "reason": "Confirmed system suggestion: no engagement"
    }
  ],
  "skipped_suggestions": [],
  "notes": "Startup name 'Acme AI' and product name 'Eir' excluded from labels for privacy. Python debug was task-related, not an interest."
}
```

Note how:
- "Acme AI" startup → not mentioned, interest is just "AI agents" (already exists)
- "Eir content curation" → generalized to "内容策展"
- "Acme dashboard" → excluded entirely (task, not interest)
- Reasons don't mention company names
