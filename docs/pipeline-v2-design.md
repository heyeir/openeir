# Eir Content Pipeline v2 — 架构设计

> 目标：简单可靠，逐条处理，中断可恢复

---

## High-Level 架构

```
  08:00 Cron 触发
         │
         ▼
  ┌──────────────┐     GET /oc/curation
  │   1. Plan    │────────────────────→ 15 directives
  │              │     GET /oc/sources
  │              │────────────────────→ 已推送 URLs (去重)
  │              │
  │  输出: task_list.json (N 个待处理 directive)
  └──────┬───────┘
         │
         ▼
  ┌──────────────────────────────────────────────────┐
  │   2. Process Loop (逐条处理)                      │
  │                                                    │
  │   for each task in task_list (status=pending):     │
  │                                                    │
  │   ┌─────────┐   ┌──────────┐   ┌─────────────┐   │
  │   │ Search  │──→│ Generate │──→│   Publish    │   │
  │   │ & Crawl │   │ (LLM)   │   │ POST /oc/    │   │
  │   └─────────┘   └──────────┘   │   content    │   │
  │                                 └──────┬──────┘   │
  │                                        │          │
  │                         task.status = "done" ✅    │
  │                         ──── next task ────→       │
  └──────────────────────────────────────────────────┘
         │
         │  超时/失败？
         │  已完成的 task 已经发布了，不丢
         │  下次运行从 status=pending 继续
         │
         ▼
  ┌──────────────┐
  │  3. Report   │──→ 发送摘要到飞书
  └──────────────┘
```

---

## task_list.json 设计

```json
{
  "date": "2026-04-07",
  "created_at": "2026-04-07T08:00:00+08:00",
  "tasks": [
    {
      "id": "t_001",
      "directive_slug": "conversational-ai-products",
      "directive_label": "对话式AI产品",
      "tier": "focus",
      "status": "done",
      "content_id": "a3k9m2x7_zh",
      "posted_at": "2026-04-07T08:05:32+08:00"
    },
    {
      "id": "t_002",
      "directive_slug": "huawei-automotive",
      "directive_label": "华为汽车",
      "tier": "tracked",
      "status": "done",
      "content_id": "b5m2k9x7_zh",
      "posted_at": "2026-04-07T08:08:15+08:00"
    },
    {
      "id": "t_003",
      "directive_slug": "ai-companion-ethics",
      "directive_label": "AI 陪伴伦理",
      "tier": "tracked",
      "status": "pending",
      "error": null
    },
    {
      "id": "t_004",
      "directive_slug": "content-creation",
      "directive_label": "content creation",
      "tier": "focus",
      "status": "skipped",
      "skip_reason": "no quality content found"
    }
  ]
}
```

**状态流转**:
```
pending → searching → generating → publishing → done
                                              → failed (记录 error)
                                              → skipped (无合适内容)
```

---

## 关键设计：逐条处理，即时发布

```
  传统 batch 设计（v8.0）         新设计（v2）

  Search ALL                      Search #1
  Generate ALL                    Generate #1
  Post ALL                        Post #1  ✅ 已安全
  ──────────                      Search #2
  超时？全丢                       Generate #2
                                  Post #2  ✅ 已安全
                                  Search #3
                                  ──────────
                                  超时？#1 #2 已发布，只丢 #3
```

---

## 中断恢复

```
  首次运行 (08:00, 超时 900s)
  ├── task 1: done ✅  (已 POST)
  ├── task 2: done ✅  (已 POST)
  ├── task 3: generating... ⏱️ 超时中断
  ├── task 4: pending
  └── task 5: pending

  自动恢复运行 (或手动触发)
  ├── task 1: done ✅  跳过
  ├── task 2: done ✅  跳过
  ├── task 3: pending  ← 从这里继续
  ├── task 4: pending
  └── task 5: pending
```

恢复逻辑：
- 读取当天的 `task_list.json`
- 跳过 `status=done` 和 `status=skipped`
- 从第一个 `pending` 开始继续

---

## 单日时序

```
08:00  ┬─ Plan: 拉 directives + 去重 → task_list.json
       │
08:01  ├─ Task 1: search → crawl → generate zh → generate en → POST → done ✅
08:04  ├─ Task 2: search → crawl → generate zh → generate en → POST → done ✅
08:07  ├─ Task 3: search → crawl → generate zh → generate en → POST → done ✅
08:10  ├─ Task 4: search → no good results → skipped ⏭️
08:11  ├─ Task 5: search → crawl → generate zh → generate en → POST → done ✅
08:14  ├─ Task 6: search → crawl → generate zh → generate en → POST → done ✅
       │
08:15  └─ Report: 5/6 成功, 1 跳过, 发送飞书摘要
```

---

## 与 v8.0 对比

```
  v8.0                              v2
  ─────                             ──
  8 cron jobs                       1 cron job
  batch 处理                         逐条处理
  超时全丢                           超时只丢当前
  无恢复                             task_list 恢复
  long-lived pool                   当天清理
  客户端评分                         服务端评分
  17 个脚本                          1 个 pipeline.py
  subagent 并行                      主 agent 串行
```

---

*待 review*
