// Falha se alguma dependência de produção do Node tiver licença GPL/AGPL (incompatível com PolyForm NC).
// LGPL é permitida (ligação dinâmica). Ver THIRD_PARTY.md.

import { execFileSync } from 'node:child_process'

const FORBIDDEN = /(^|[^L])(A?GPL)|General Public License/i
const ALLOWED_EXCEPTIONS = /LGPL|Lesser General Public License/i

const raw = execFileSync('pnpm', ['licenses', 'list', '--prod', '--json'], { encoding: 'utf8' })
const byLicense = JSON.parse(raw)

const offenders = []
for (const [license, pkgs] of Object.entries(byLicense)) {
  if (FORBIDDEN.test(license) && !ALLOWED_EXCEPTIONS.test(license)) {
    for (const pkg of pkgs) offenders.push(`${pkg.name}@${pkg.versions?.join(',') ?? '?'} (${license})`)
  }
}

if (offenders.length) {
  console.error('Dependências Node com licença proibida:\n  ' + offenders.join('\n  '))
  process.exit(1)
}
console.log(`licenças Node ok: ${Object.keys(byLicense).sort().join(', ')}`)
