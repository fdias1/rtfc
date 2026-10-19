// Gera src/generated.ts a partir do JSON Schema exportado pelo backend Python.
// Uso: node scripts/gen.mjs [--check]
//   --check  falha (exit 1) se o arquivo gerado estiver desatualizado (usado no CI).

import { execFileSync } from 'node:child_process'
import { readFileSync, writeFileSync, existsSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { compile } from 'json-schema-to-typescript'

const here = dirname(fileURLToPath(import.meta.url))
const backend = resolve(here, '../../../backend')
const out = resolve(here, '../src/generated.ts')
const check = process.argv.includes('--check')

const schemaJson = execFileSync('uv', ['run', '--project', backend, 'python', '-m', 'rtfc.protocol.schema'], {
  encoding: 'utf8',
  stdio: ['ignore', 'pipe', 'inherit']
})

const ts = await compile(JSON.parse(schemaJson), 'RtfcProtocol', {
  bannerComment:
    '/* eslint-disable */\n// GERADO por packages/protocol/scripts/gen.mjs a partir de backend/src/rtfc/protocol.\n// Não edite à mão: rode `pnpm protocol:gen`.',
  additionalProperties: false,
  unreachableDefinitions: true,
  style: { singleQuote: true, semi: false, printWidth: 100 }
})

if (check) {
  const current = existsSync(out) ? readFileSync(out, 'utf8') : ''
  if (current !== ts) {
    console.error('packages/protocol/src/generated.ts está desatualizado. Rode `pnpm protocol:gen`.')
    process.exit(1)
  }
  console.log('protocol: tipos em dia')
} else {
  writeFileSync(out, ts)
  console.log(`protocol: gerado ${out}`)
}
