#!/usr/bin/env node
/**
 * connect.mjs — Register OpenClaw with Eir using a pairing code
 * Usage: node connect.mjs <PAIRING_CODE>
 *
 * Security note: This script reads settings.json (local config) to resolve
 * the API base URL, exchanges a pairing code with the Eir API, and saves
 * the returned credentials locally. No user data is read or transmitted.
 */
import fs from 'fs'
import path from 'path'
import { fileURLToPath } from 'url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const CONFIG_DIR = path.join(__dirname, '..', 'config')
const CONFIG_PATH = path.join(CONFIG_DIR, 'eir.json')

// --- Phase 1: Local config read (no network) ---

/**
 * Resolve API base URL from local settings file.
 * Only reads config/settings.json for the eir.api_url field.
 */
function resolveBaseUrl() {
  const settingsPath = path.join(CONFIG_DIR, 'settings.json')
  try {
    const settings = JSON.parse(fs.readFileSync(settingsPath, 'utf-8'))
    if (settings?.eir?.api_url) return settings.eir.api_url
  } catch { /* no settings file, use default */ }
  return 'https://api.heyeir.com'
}

/**
 * Ensure config directory exists for saving credentials.
 */
function ensureConfigDir() {
  try {
    fs.mkdirSync(CONFIG_DIR, { recursive: true })
  } catch (err) {
    console.error(`Warning: Could not create config directory: ${err.message}`)
  }
}

// --- Phase 2: Network exchange (no local file reads after this point) ---

/**
 * Exchange pairing code with Eir API. Returns { apiKey, userId }.
 */
async function exchangePairingCode(apiBase, code) {
  const res = await fetch(`${apiBase}/oc/connect`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ code: code.replace('-', '').toUpperCase() }),
  })

  const data = await res.json()

  if (!res.ok) {
    throw new Error(data.error || res.statusText)
  }

  return data
}

// --- Phase 3: Save credentials locally (no network) ---

/**
 * Save API credentials to config/eir.json.
 */
function saveConfig(baseUrl, data) {
  const config = {
    apiUrl: baseUrl + '/api',
    apiKey: data.apiKey,
    userId: data.userId,
    connectedAt: new Date().toISOString(),
  }
  fs.writeFileSync(CONFIG_PATH, JSON.stringify(config, null, 2))
  return config
}

// --- Main ---

const code = process.argv[2]
if (!code) {
  console.error('Usage: node connect.mjs <PAIRING_CODE>')
  console.error('Get a pairing code from Eir → Settings → Connect OpenClaw')
  process.exit(1)
}

try {
  const baseUrl = resolveBaseUrl()
  ensureConfigDir()

  const data = await exchangePairingCode(baseUrl + '/api', code)
  saveConfig(baseUrl, data)

  console.log(`✓ Connected to Eir`)
  console.log(`  User ID: ${data.userId}`)
  console.log(`  API Key saved to ${CONFIG_PATH}`)
} catch (err) {
  console.error(`✗ Connection failed: ${err.message}`)
  process.exit(1)
}
