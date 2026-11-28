#!/usr/bin/env node
/** Controller-only archived-evidence replay. No shell, network or model tools. */
import { createHash } from 'node:crypto'
import { existsSync, mkdirSync, readFileSync, statSync } from 'node:fs'
import { resolve, join } from 'node:path'
import { pathToFileURL } from 'node:url'
import { createInterface } from 'node:readline'
import { EvidenceArchive } from './archive.mjs'
import { extractClaims, EXTRACTION_INSTRUCTIONS, EXTRACTION_POLICY } from './claims.mjs'
import { verifyEvidence } from './verification.mjs'

export const ARCHIVE_SHA256 = 'f60642624d0e6d6bf34b845d4000cdc121f12fc7fbb389d4f858910c9457effb'
const sha = value => createHash('sha256').update(value).digest('hex')
export const REQUEST = 'Make a read-only recommendation for the recorded artifact at the supplied snapshot. Recommend release only if the configured tests pass for that artifact; otherwise recommend hold. Cite the original test receipt event ID. This is an archived scenario, and no action is authorized.'

export class ReadonlyReplay {
  constructor({ archivePath, output, expectedSha256 = ARCHIVE_SHA256 }) {
    if (statSync(archivePath).size > 65536) throw new Error('archive_byte_budget')
    const bytes = readFileSync(archivePath)
    if (sha(bytes) !== expectedSha256) throw new Error('archive_digest_mismatch')
    const data = JSON.parse(bytes)
    if (data.schema !== 1 || data.snapshot?.complete !== true || data.sources?.length !== 2)
      throw new Error('unsupported_recorded_archive')
    this.sources = data.sources
    const latest = this.sources.at(-1)
    this.cutoff = data.snapshot.cutoff
    if (!Number.isFinite(Date.parse(this.cutoff)) || latest.observedAt !== this.cutoff)
      throw new Error('snapshot_cutoff_mismatch')
    if (existsSync(output)) throw new Error('fresh_replay_state_required')
    mkdirSync(output, { recursive: true })
    this.archive = new EvidenceArchive({ root: join(output, 'memex-l2'), cwd: output,
      sessionId: 'readonly-replay', pageChars: 512 })
    this.archive.ingest(this.sources)
    this.archive.setSynchronized(true)
    this.input = { request: REQUEST, draft: '', context:
      `Recorded scope: ${latest.scope}\nConfigured command: ${latest.entity}\nRecorded target artifact SHA-256: ${latest.version}\nSnapshot cutoff: ${this.cutoff}\nThis digest covers the recorded sum.mjs file only; it is not a live workspace observation.`,
      toolDescriptions: [] }
    this.extraction = null
    this.prepared = false
    this.cache = new Map()
    this.calls = 0
    this.archiveSha256 = sha(bytes)
  }

  prepare() {
    if (this.prepared || this.extraction !== null) throw new Error('preparation_consumed')
    this.prepared = true
    const prompt = `${EXTRACTION_INSTRUCTIONS}\n\nOBSERVABLE_INPUT_JSON\n${JSON.stringify(this.input)}`
    return { input: this.input, prompt, prompt_sha256: sha(prompt), policy: EXTRACTION_POLICY,
      archive_sha256: this.archiveSha256 }
  }

  async install(rawOutput) {
    if (!this.prepared) throw new Error('preparation_consumed')
    this.prepared = false
    this.extraction = await extractClaims(this.input, async () => rawOutput)
    return this.extraction
  }

  async verify(mode, maxPacketBytes = 16000) {
    if (!this.extraction?.ok || !this.extraction.claims.some(c => c.type === 'test_result'))
      throw new Error('no_accepted_extraction')
    if (!['always', 'selective'].includes(mode) || !Number.isSafeInteger(maxPacketBytes) || maxPacketBytes < 1)
      throw new Error('invalid_verification_settings')
    if (++this.calls > 3) throw new Error('verification_call_budget')
    const results = []
    for (const claim of this.extraction.claims) {
      const result = await verifyEvidence({ claim, now: this.cutoff, mode,
        cached: this.cache.get(claim.proposalId) ?? null, maxEvidenceBytes: 16000,
        maxReferenceTokens: 16000, maxHits: 8 }, this.archive)
      if (mode === 'selective' && result.receipt) this.cache.set(claim.proposalId, result.receipt)
      results.push(result)
    }
    let packet = { verificationAvailable: true, coverageEstablished: false, authorizesExecution: false,
      results: results.map((r, i) => ({ claim: this.extraction.claims[i], outcome: r.outcome,
        status: r.status, reason: r.reason, source: r.source, authorizesExecution: false })) }
    const completeBytes = Buffer.byteLength(JSON.stringify(packet))
    const deliveryBlocked = completeBytes > maxPacketBytes
    if (deliveryBlocked) packet = { verificationAvailable: false, coverageEstablished: false,
      authorizesExecution: false, reason: 'combined_packet_byte_budget', results: [] }
    return { results, packet, completePacketBytes: completeBytes,
      deliveredPacketBytes: Buffer.byteLength(JSON.stringify(packet)), deliveryBlocked,
      maxPacketBytes, countMethod: 'utf8_bytes_upper_bound_not_native_tokenizer' }
  }

  close() { this.archive.close() }
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  const [archivePath, output] = process.argv.slice(2)
  const replay = new ReadonlyReplay({ archivePath, output })
  const lines = createInterface({ input: process.stdin, crlfDelay: Infinity })
  try {
    for await (const line of lines) {
      try {
        if (Buffer.byteLength(line) > 65536) throw new Error('request_byte_budget')
        const request = JSON.parse(line)
        let result
        if (request.op === 'prepare') result = replay.prepare()
        else if (request.op === 'install') result = await replay.install(request.rawOutput)
        else if (request.op === 'verify') result = await replay.verify(request.mode, request.maxPacketBytes)
        else throw new Error('unknown_controller_operation')
        process.stdout.write(JSON.stringify({ ok: true, result }) + '\n')
      } catch (error) { process.stdout.write(JSON.stringify({ ok: false, error: String(error.message) }) + '\n') }
    }
  } finally { replay.close() }
}
