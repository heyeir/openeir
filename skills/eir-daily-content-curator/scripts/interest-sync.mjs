#!/usr/bin/env node
/**
 * interest-sync.mjs — Daily interest synchronization script
 * 
 * Usage:
 *   node scripts/interest-sync.mjs [--dry-run]
 * 
 * What it does:
 * 1. Fetches /oc/interests/context (current interests + behavior + suggestions)
 * 2. Analyzes recent conversations to extract new interests
 * 3. Reviews system suggestions (demote, merge)
 * 4. Sends operations to POST /oc/interests/sync
 * 
 * Agent (LLM) responsibilities:
 * - New interest extraction from conversations
 * - Deciding merge operations (semantic understanding)
 * - Confirming system suggestions
 * 
 * Server responsibilities:
 * - Calculating strength, heat, engagement
 * - Applying decay
 * - Executing operations
 */

import { readFileSync, writeFileSync, existsSync, mkdirSync } from 'fs'
import { join } from 'path'

const API_URL = process.env.EIR_API_URL
const API_KEY = process.env.EIR_API_KEY
const DRY_RUN = process.argv.includes('--dry-run')

if (!API_URL) {
  console.error('Error: EIR_API_URL environment variable not set')
  console.error('Set it to your Eir API base URL (e.g., https://api.heyeir.com)')
  process.exit(1)
}

if (!API_KEY) {
  console.error('Error: EIR_API_KEY environment variable not set')
  process.exit(1)
}

// ===== Helpers =====

async function apiGet(path) {
  const res = await fetch(`${API_URL}/api${path}`, {
    headers: { 'Authorization': `Bearer ${API_KEY}` }
  })
  if (!res.ok) throw new Error(`GET ${path} failed: ${res.status}`)
  return res.json()
}

async function apiPost(path, body) {
  if (DRY_RUN) {
    console.log(`[DRY-RUN] POST ${path}:`, JSON.stringify(body, null, 2))
    return { ok: true, dry_run: true }
  }
  const res = await fetch(`${API_URL}/api${path}`, {
    method: 'POST',
    headers: { 
      'Authorization': `Bearer ${API_KEY}`,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify(body)
  })
  if (!res.ok) throw new Error(`POST ${path} failed: ${res.status}`)
  return res.json()
}

// ===== Main =====

async function main() {
  if (!API_KEY) {
    console.error('Error: EIR_API_KEY not set')
    process.exit(1)
  }

  console.log(`[interest-sync] Starting${DRY_RUN ? ' (dry-run)' : ''}...`)
  console.log(`[interest-sync] API: ${API_URL}`)

  // 1. Fetch current context
  console.log('[interest-sync] Fetching /oc/interests/context...')
  const context = await apiGet('/oc/interests/context')
  
  console.log(`[interest-sync] User: ${context.user.id}`)
  console.log(`[interest-sync] Primary language: ${context.user.primary_language}`)
  console.log(`[interest-sync] Topics: ${context.topics.length}`)
  console.log(`[interest-sync] Suggestions: ${context.suggestions.length}`)
  console.log(`[interest-sync] Engagement health: ${context.behavior_summary.engagement_health}`)

  // 2. Collect operations
  const operations = []

  // 2a. Apply system suggestions (auto-confirm demote suggestions)
  for (const suggestion of context.suggestions) {
    if (suggestion.action === 'demote') {
      operations.push({
        op: 'demote',
        slug: suggestion.slug,
        reason: suggestion.reason
      })
    }
    // For merge suggestions, need LLM to confirm — skip in script
  }

  // 2b. TODO: Call LLM to analyze conversations and extract new interests
  // This is where the Agent (LLM) part would go:
  //
  // const conversations = await getRecentConversations()
  // const prompt = buildInterestExtractionPrompt(context, conversations)
  // const llmResponse = await callLLM(prompt)
  // operations.push(...llmResponse.operations)

  // 3. Execute operations
  if (operations.length === 0) {
    console.log('[interest-sync] No operations to execute')
    return
  }

  console.log(`[interest-sync] Executing ${operations.length} operations...`)
  const result = await apiPost('/oc/interests/sync', { operations })
  
  console.log(`[interest-sync] Applied: ${result.applied}`)
  console.log(`[interest-sync] Results:`, JSON.stringify(result.results, null, 2))

  // 4. Backup locally
  const backupDir = join(process.cwd(), 'data', 'interest-sync')
  if (!existsSync(backupDir)) mkdirSync(backupDir, { recursive: true })
  
  const timestamp = new Date().toISOString().replace(/[:.]/g, '-')
  writeFileSync(
    join(backupDir, `sync-${timestamp}.json`),
    JSON.stringify({ context, operations, result }, null, 2)
  )
  console.log(`[interest-sync] Backup saved to data/interest-sync/sync-${timestamp}.json`)

  console.log('[interest-sync] Done!')
}

main().catch(err => {
  console.error('[interest-sync] Error:', err.message)
  process.exit(1)
})
