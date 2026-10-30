/** Small synthetic natural-language topic checks against the same store before/after. */
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import { pathToFileURL } from 'node:url'
import { LocalStoreCore } from '../packages/memex-local/lib/store.js'
import { materializeStoreContext } from '../packages/memex-core/lib/context-pager.js'
const arg = (key) => { const i = process.argv.indexOf(`--${key}`); return i < 0 ? undefined : process.argv[i + 1] }
const baselineRepo = arg('baseline'), root = arg('store'), output = arg('out')
if (!baselineRepo || !root || !output) throw new Error('usage: --baseline BASELINE_REPO --store NEW_DIRECTORY --out NEW_FILE')
if (existsSync(output)) throw new Error('output already exists')
mkdirSync(root)
const topics = [
  { id: 'deployment', title: 'deployment release decision', summary: 'deployment release and rollback plan', body: 'Deployment uses pinned builds; rollback selects the previous deployment identifier.', fact: 'previous deployment identifier', queries: ['How did we handle deployment?', 'How can we roll back a published release?', 'How do we undo the launch?'] },
  { id: 'database', title: 'database storage decision', summary: 'SQLite WAL and lazy migration', body: 'The database uses SQLite WAL; migrations run lazily and idempotently.', fact: 'migrations run lazily', queries: ['What was the database decision?', 'Which storage uses WAL and lazy migrations?', 'Which persistence engine implements write-ahead logging?'] },
  { id: 'api', title: 'API endpoint decision', summary: 'owner-scoped HTTP GET and POST endpoints', body: 'The owner-scoped API exposes GET memory.index and POST memory.compress.', fact: 'POST memory.compress', queries: ['What API endpoints did we choose?', 'Which GET and POST endpoints are owner scoped?'] },
  { id: 'ui', title: 'UI context ring decision', summary: 'session and workspace capture ring colors', body: 'The context ring uses teal for session capture and blue for workspace capture.', fact: 'teal for session capture', queries: ['What was the UI context ring decision?', 'Which colors distinguish session and workspace capture?'] },
  { id: 'review', title: 'review requirements', summary: 'review needs tests, bundle parity and private data checks', body: 'Review requires passing tests, bundle parity and no personal data in fixtures.', fact: 'bundle parity', queries: ['What are the review requirements?', 'What checks must pass before merging?', 'Which approval criteria govern code acceptance?'] },
  { id: 'incident', title: 'installation incident', summary: 'host crash because generated bundle missed a module', body: 'An installation crashed because a generated bundle lacked a module; rebuilding fixed it.', fact: 'rebuilding fixed it', queries: ['What caused the installation incident?', 'Why did the host crash on installation?'] },
  { id: 'backup', title: 'backup and restore decision', summary: 'backup snapshots and sha256 verification', body: 'Backups use VACUUM INTO and sha256 manifests; restore checks the manifest.', fact: 'sha256 manifests', queries: ['How does backup and restore work?', 'How do we verify a restored snapshot?'] },
  { id: 'privacy', title: 'privacy boundary decision', summary: 'privacy keeps secrets in private session scope', body: 'Secret-looking spans remain in L2 session scope or eviction is skipped.', fact: 'L2 session scope', queries: ['What is the privacy boundary?', 'Which secrets must stay in the session scope?', 'Where do confidential credentials belong?'] },
]
const store = new LocalStoreCore({ root, capacityTokens: 10_000_000, sessionCapacityTokens: 10_000_000, defaultLevels: { l2: false, l3: false } })
try {
  for (const [i, t] of topics.entries()) {
    store.write({ id: `topic-${t.id}`, kind: 'fact', title: t.title, summary: t.summary, body: t.body, workspaceKey: 'topic-eval', scope: 'workspace' })
    if (i % 2 === 0) store.archiveCold(`topic-${t.id}`)
  }
  for (let i = 0; i < 50; i += 1) store.write({ id: `distractor-${i}`, kind: 'fact', title: `unrelated project note ${i}`, summary: 'ordinary unrelated project notes', body: 'This is an unrelated project note without the requested fact. '.repeat(10), workspaceKey: 'topic-eval', scope: 'workspace' })
  const before = await import(pathToFileURL(join(baselineRepo, 'packages/memex-core/lib/context-pager.js')).href)
  const weights = JSON.parse(readFileSync(new URL('../packages/memex-core/lib/lexical-reranker.json', import.meta.url), 'utf8'))
  const probes = []
  for (const t of topics) for (const [index, query] of t.queries.entries()) {
    const base = { store, workspaceKey: 'topic-eval', scopes: ['workspace'], query, budgetTokens: 500, pageTokenCap: 80, learnedPageMaxTokens: 200 }
    const conditions = {}
    for (const [phase, fn] of [['before', before.materializeStoreContext], ['after', materializeStoreContext]]) {
      for (const name of ['rule', 'hybrid']) {
        const r = fn({ ...base, ...(name === 'hybrid' ? { learnedRerank: weights, learnedTopK: 4 } : {}) })
        conditions[`${phase}-${name}`] = { candidate: r.sources.some((x) => x.recordId === `topic-${t.id}`), selected: r.includedIds.includes(`topic-${t.id}`), fact: r.text.includes(t.fact), tokens: r.tokens }
      }
    }
    probes.push({ topic: t.id, kind: index === 0 ? 'explicit-topic' : index === 1 ? 'paraphrase' : 'lexical-disjoint', conditions })
  }
  const result = { kind: 'synthetic-topic-pager-comparison', baseline: 'c05dd12', cases: probes.length, design: '8 topics: 8 explicit, 8 paraphrased and 4 lexical-disjoint questions; target records precede 50 distractors; no target injection; 4 cold targets', probes }
  writeFileSync(output, JSON.stringify(result, null, 2))
  console.log(JSON.stringify(Object.fromEntries(['before-rule', 'before-hybrid', 'after-rule', 'after-hybrid'].map((c) => [c, probes.filter((p) => p.conditions[c].fact).length]))))
} finally { store.close() }
