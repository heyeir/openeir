#!/usr/bin/env node
/**
 * connect.mjs — Register OpenClaw with Eir using a pairing code
 * Usage: node connect.mjs <PAIRING_CODE>
 */
import fs from 'fs'
import path from 'path'
import { fileURLToPath } from 'url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const CONFIG_DIR = path.join(__dirname, '..', 'config')
const CONFIG_PATH = path.join(CONFIG_DIR, 'eir.json')

// Read API URL from config/settings.json or fall back to production
function resolveBaseUrl() {
  const settingsPath = path.join(CONFIG_DIR, 'settings.json')
  try {
    const settings = JSON.parse(fs.readFileSync(settingsPath, 'utf-8'))
    if (settings?.eir?.api_url) return settings.eir.api_url
  } catch { /* no settings file, use default */ }
  return 'https://api.heyeir.com'
}
const BASE_URL = resolveBaseUrl()

// Ensure config directory exists
try {
  fs.mkdirSync(CONFIG_DIR, { recursive: true })
} catch (err) {
  console.error(`Warning: Could not create config directory: ${err.message}`)
}
const API_BASE = BASE_URL + '/api'

const code = process.argv[2]
if (!code) {
  console.error('Usage: node connect.mjs <PAIRING_CODE>')
  console.error('Get a pairing code from Eir → Settings → Connect OpenClaw')
  process.exit(1)
}

try {
  const res = await fetch(`${API_BASE}/oc/connect`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ code: code.replace('-', '').toUpperCase() }),
  })

  const data = await res.json()

  if (!res.ok) {
    console.error(`✗ Failed: ${data.error || res.statusText}`)
    process.exit(1)
  }

  const config = {
    apiUrl: BASE_URL + '/api',
    apiKey: data.apiKey,
    userId: data.userId,
    connectedAt: new Date().toISOString(),
  }

  fs.writeFileSync(CONFIG_PATH, JSON.stringify(config, null, 2))
  console.log(`✓ Connected to Eir`)
  console.log(`  User ID: ${data.userId}`)
  console.log(`  API Key saved to ${CONFIG_PATH}`)
} catch (err) {
  console.error(`✗ Connection failed: ${err.message}`)
  process.exit(1)
}
