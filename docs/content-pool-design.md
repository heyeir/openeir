# Eir 公共池内容系统技术设计文档

> **版本**: v1.0 简化版  
> **日期**: 2026-04-04  
> **目标**: 24h TTL RSS 内容 → 去重 → 合并 → 公共池 → 用户个性化推送

---

## 1. 核心概念

### 1.1 数据分层

| 层级 | 名称 | 说明 | 存储 |
|------|------|------|------|
| L0 | 原始 RSS | 28+ 源，24h 内新内容 | 内存/临时 |
| L1 | 公共池 | 去重、合并后的标准化文章 | `content_pool` container |
| L2 | 用户池 | 每个用户的个性化候选列表 | `users.content_pool_ids[]` |
| L3 | 已推送 | 用户已看过的内容记录 | `users.pushed_content_ids[]` |

### 1.2 内容 ID 设计

```
短 ID 格式: {lang}_{hash8}_{timestamp}

示例:
- zh_a3f7b2d1_1775311200  (中文版本)
- en_a3f7b2d1_1775311200  (英文版本)
- 同 hash8 = 同一原文的不同语言版本
```

**语言映射**: 同语言内用 `translations: { zh: "id", en: "id" }` 关联

---

## 2. 数据模型

### 2.1 公共池文章 (content_pool)

复用现有 picks content 结构，新增 TTL 和 embedding 字段：

```typescript
interface ContentPoolItem {
  // 核心 ID
  id: string;           // 短 ID: zh_a3f7b2d1_1775311200
  hash8: string;        // 原文指纹 (用于跨语言关联)
  
  // 多语言关联
  lang: "zh" | "en";
  translations: {
    zh?: string;        // 中文版本 ID
    en?: string;        // 英文版本 ID
  };
  
  // 内容 (复用现有结构)
  dot: {
    hook: string;       // ≤15 字
    category: "focus" | "attention" | "seed";
    color_hint: string;
  };
  
  l1: {
    title: string;
    summary: string;    // 80-120 字
    key_quote: string;
    via: string[];      // 来源名称
    bullets: string[];  // 3-4 条，每条 ≤20 字
  };
  
  l2: {
    content: string;    // 500-2000 字
    bullets: Array<{ text: string; confidence: number }>;
    context: string;
    eir_take: string;
    related_topics: string[];
  };
  
  // 来源信息
  sources: Array<{
    url: string;
    title: string;
    name: string;       // 站点名
    published_at: string; // ISO 8601
  }>;
  
  // 元数据
  topics: string[];     // 关联的兴趣话题 slug
  embedding: number[];  // 256d 向量 (Matryoshka)
  
  // TTL
  ttl_hours: number;    // 默认 24
  expires_at: number;   // Unix timestamp
  
  // 统计
  push_count: number;   // 被推送次数
  click_count: number;  // 点击次数
  
  // 系统
  created_at: number;
  updated_at: number;
}
```

### 2.2 用户表扩展 (users)

```typescript
interface User {
  id: string;
  
  // 现有字段...
  
  // 内容池 (只存 ID，不存全文)
  content_pool_ids: string[];      // 候选内容短 ID 列表
  content_pool_updated_at: number; // 上次更新时间
  
  // 已推送记录 (简单去重)
  pushed_content_ids: string[];    // 已推送过的 hash8 列表
  pushed_content_at: { [hash8: string]: number }; // hash8 -> 推送时间
  
  // 兴趣 (复用现有)
  interests: {
    topics: Array<{
      slug: string;
      label: string;
      strength: number;  // 0-1
      embedding: number[]; // 256d 话题向量
    }>;
    user_embedding: number[]; // 用户整体兴趣向量
  };
  
  // 偏好
  preferences: {
    locale: "zh" | "en";
    bilingual: boolean;
    content_per_day: number; // 每日推送上限
  };
}
```

---

## 3. 系统架构

### 3.1 整体流程

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   RSS 源    │────→│  24h 过滤   │────→│  Crawl4AI   │
│  (28+ 源)   │     │  (pubDate)  │     │   爬取正文  │
└─────────────┘     └─────────────┘     └──────┬──────┘
                                               │
┌─────────────┐     ┌─────────────┐     ┌──────▼──────┐
│  公共池存储 │←────│  去重/合并  │←────│   生成内容  │
│ content_pool│     │ (hash8+emb) │     │  (l1+l2)    │
└──────┬──────┘     └─────────────┘     └─────────────┘
       │
       │  用户登录/定时推送
       ▼
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  用户匹配   │────→│  用户池更新 │────→│   前端展示  │
│ (cosine>thr)│     │(只存ID列表) │     │  (按ID拉取) │
└─────────────┘     └─────────────┘     └─────────────┘
```

### 3.2 核心模块

#### A. RSS 采集器 (rss_ingest.py)

**职责**: 每天跑一次，抓取 24h 内新内容

```python
def fetch_rss_feeds(sources: list, ttl_hours=24) -> list[RawArticle]:
    """
    1. 解析每个 RSS feed
    2. 过滤 pubDate 在 24h 内的条目
    3. 返回: [{url, title, pub_date, source_name}]
    """

def dedup_by_url(articles: list) -> list[RawArticle]:
    """
    URL 精确去重 (同一文章可能在多个源出现)
    """
```

#### B. 内容处理器 (content_processor.py)

**职责**: 爬取、生成、存入公共池

```python
def process_batch(articles: list[RawArticle]):
    """
    1. Crawl4AI 爬取正文
    2. 生成 hash8 (URL + title 的 short hash)
    3. 检查公共池: 如果 hash8 存在且未过期，跳过
    4. 生成内容 (l1, l2)
    5. 生成 embedding (title + summary)
    6. 写入 content_pool
    """

def generate_content(article: RawArticle) -> ContentPoolItem:
    """
    调用 LLM 生成:
    - dot: hook, category, color
    - l1: title, summary, bullets, via
    - l2: content, context, eir_take
    """

def compute_embedding(text: str) -> list[float]:
    """
    使用 EmbeddingGemma-300M → 256d
    """
```

#### C. 用户匹配器 (user_matcher.py)

**职责**: 为用户填充个性化候选池

```python
def match_for_user(user: User, pool: list[ContentPoolItem]) -> list[str]:
    """
    1. 过滤已推送: 排除 pushed_content_ids
    2. 过滤过期: 排除 expires_at < now
    3. 计算相似度: cosine(user.user_embedding, article.embedding)
    4. 过滤低分: score > threshold (默认 0.55)
    5. 按话题分组: 每个话题取 top-N
    6. 返回: 短 ID 列表 (按匹配分数排序)
    """

def update_user_pool(user_id: str, content_ids: list[str]):
    """
    更新 users.content_pool_ids
    保留最近 100 条候选
    """
```

#### D. 推送服务 (push_service.py)

**职责**: 定时推送或用户主动获取

```python
def get_push_candidates(user: User, limit: int = 3) -> list[ContentPoolItem]:
    """
    1. 从 users.content_pool_ids 取前 N 个
    2. 按用户偏好 locale 选择语言版本
    3. 标记为已推送 (更新 pushed_content_ids)
    4. 返回完整内容
    """

def daily_cleanup():
    """
    1. 删除公共池中 expires_at < now 的内容
    2. 清理用户 pushed_content_ids 中 7 天前的记录
    """
```

---

## 4. 去重策略 (简化版)

### 4.1 三层去重

| 层级 | 方法 | 时机 | 说明 |
|------|------|------|------|
| L1 | URL 精确匹配 | RSS 采集后 | 同一文章在不同源出现 |
| L2 | hash8 匹配 | 内容生成前 | 已存在于公共池 |
| L3 | 语义相似度 | 内容生成后 | cosine > 0.82 视为重复 |

### 4.2 hash8 生成

```python
import hashlib

def make_hash8(url: str, title: str) -> str:
    """8位十六进制指纹"""
    key = f"{url}|{title.lower().strip()}"
    return hashlib.sha256(key.encode()).hexdigest()[:8]
```

### 4.3 语义去重

```python
def is_semantic_duplicate(new_emb: list, pool: list) -> bool:
    """
    计算与公共池所有文章的 cosine 相似度
    如果 max(score) > 0.82，视为重复
    """
```

---

## 5. 相似度计算

### 5.1 用户-内容匹配

```
score = cosine(user_embedding, article_embedding)

阈值建议:
- ≥ 0.70: 高度相关，优先推送
- 0.55-0.70: 相关，放入候选池
- < 0.55: 不相关，跳过
```

### 5.2 多兴趣加权

如果用户有多个兴趣话题：

```python
def multi_interest_score(user: User, article: ContentPoolItem) -> float:
    scores = []
    for topic in user.interests.topics:
        if topic.slug in article.topics:
            scores.append(topic.strength)  # 用户对该话题的兴趣强度
    
    # 基础相似度 + 话题匹配加成
    base = cosine(user.user_embedding, article.embedding)
    bonus = max(scores) * 0.2 if scores else 0
    return min(1.0, base + bonus)
```

---

## 6. API 设计

### 6.1 公共池管理 (内部)

```
POST /internal/content-pool/ingest
  Body: { rss_items: [...] }
  → 触发 RSS 处理流程

GET /internal/content-pool/stats
  → { total: 1234, expiring_24h: 56, by_topic: {...} }

DELETE /internal/content-pool/cleanup
  → 删除过期内容
```

### 6.2 用户内容池

```
POST /api/oc/content-pool/refresh
  → 手动触发匹配更新
  → 返回: { matched: 12, pool_size: 45 }

GET /api/oc/content-pool
  → 获取用户当前候选池 (ID 列表)
  → Response: { ids: ["zh_a3f7...", ...], updated_at: 123456 }

GET /api/oc/content-pool/items?ids=zh_a3f7...,en_x9d2...
  → 批量获取内容详情
  → Response: { items: [ContentPoolItem, ...] }
```

### 6.3 推送

```
GET /api/oc/push?limit=3
  → 获取今日推送内容
  → 自动标记为已推送
  → Response: { items: [ContentPoolItem, ...], remaining: 5 }

POST /api/oc/push/:id/feedback
  Body: { action: "click" | "skip" | "dismiss" }
  → 记录反馈，用于优化推送
```

---

## 7. 存储方案

### 7.1 Cosmos DB 容器

| 容器 | Partition Key | 说明 |
|------|---------------|------|
| `content_pool` | `/lang` | 公共池文章 |
| `users` | `/id` | 用户数据，含 content_pool_ids |

### 7.2 索引建议

**content_pool**:
```json
{
  "indexingPolicy": {
    "includedPaths": [
      { "path": "/hash8" },
      { "path": "/topics/*" },
      { "path": "/expires_at" },
      { "path": "/embedding" }
    ]
  }
}
```

**users**:
```json
{
  "indexingPolicy": {
    "includedPaths": [
      { "path": "/content_pool_ids/*" },
      { "path": "/pushed_content_ids/*" }
    ]
  }
}
```

---

## 8. 定时任务

| 任务 | 频率 | 脚本 |
|------|------|------|
| RSS 采集 | 每 4 小时 | `rss_ingest.py` |
| 内容生成 | RSS 后触发 | `content_processor.py` |
| 用户匹配 | 用户登录时 + 每 6 小时 | `user_matcher.py` |
| 过期清理 | 每天 00:00 | `cleanup.py` |
| 统计报表 | 每天 08:00 | `daily_report.py` |

---

## 9. 冷启动策略

新用户没有 embedding 时：

1. **基于兴趣标签**: 用兴趣话题的 embedding 代替 user_embedding
2. **探索模式**: 前 7 天推送热门内容 (push_count 高的)，收集点击反馈
3. **快速学习**: 3-5 次点击后生成初始 user_embedding

---

## 10. 监控指标

| 指标 | 目标 | 告警 |
|------|------|------|
| 公共池大小 | 100-500 条 | < 50 或 > 1000 |
| 24h 内容新鲜度 | > 80% | < 60% |
| 用户池匹配率 | > 30% | < 10% |
| 平均推送点击率 | > 15% | < 5% |
| 生成成功率 | > 90% | < 70% |

---

## 11. 后续扩展

| 阶段 | 功能 | 复杂度 |
|------|------|--------|
| v1.0 | 24h TTL + 简单去重 + 用户池 | 低 |
| v1.1 | 多源搜索 (Brave/Tavily) | 中 |
| v1.2 | 协同过滤 (相似用户推荐) | 中 |
| v2.0 | 实时流处理 (Kafka) | 高 |
| v2.1 | A/B 测试框架 | 中 |

---

## 附录: 文件结构

```
openeir/
├── docs/
│   └── content-pool-design.md          # 本文档
├── scripts/
│   ├── rss_ingest.py                   # RSS 采集
│   ├── content_processor.py            # 内容生成
│   ├── user_matcher.py                 # 用户匹配
│   ├── push_service.py                 # 推送服务
│   └── cleanup.py                      # 清理任务
├── config/
│   └── sources.json                    # RSS 源配置
└── data/
    ├── content_pool/                   # 本地缓存 (可选)
    └── embeddings/                     # 向量缓存
```

---

**下一步**: 
1. 评审文档
2. 确认 Cosmos DB 容器创建
3. 实现 `rss_ingest.py` + `content_processor.py` MVP
4. 测试端到端流程
