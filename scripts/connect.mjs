#!/usr/bin/env node
/**
 * connect.mjs — Register OpenClaw with Eir using a pairing code
 * Usage: node connect.mjs <PAIRING_CODE>
 */
import fs from 'fs'
import path from 'path'
import { fileURLToPath } from 'url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const CONFIG_PATH = path.join(__dirname, '..', 'config.json')
const BASE_URL = 'https://api.heyeir.com/api'

const code = process.argv[2]
if (!code) {
  console.error('Usage: node connect.mjs <PAIRING_CODE>')
  console.error('Get a pairing code from Eir → Settings → Connect OpenClaw')
  process.exit(1)
}

try {
  const res = await fetch(`${BASE_URL}/oc/connect`, {
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
