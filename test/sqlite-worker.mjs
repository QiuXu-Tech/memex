import { LocalStoreCore } from '../packages/memex-core/lib/store.js'

const [action, root, id, label = 'worker'] = process.argv.slice(2)
const store = new LocalStoreCore({ root, capacityTokens: 100000, defaultLevels: { l2: false, l3: false } })
const update = (value) => store.write({ id, kind: 'fact', title: 'Concurrency fixture',
  summary: value, body: value, workspaceKey: 'wk-lock', scope: 'workspace' })
try {
  if (action === 'update') update('new body and summary')
  else if (action === 'new') store.write({ kind: 'fact', title: 'Generated record', summary: 'generated summary',
    body: 'generated body', workspaceKey: 'wk-lock', scope: 'workspace' })
  else if (action === 'loop') for (let i = 0; i < 12; i += 1) update(label + ':' + i)
  else if (action === 'archive') store.archiveCold(id)
  else if (action === 'restore') store.restoreCold(id)
  else if (action === 'forget') store.forget(id)
  else if (action === 'gc') store.gcCold({ workspaceKey: 'wk-lock', keepTokens: 0 })
  else if (action === 'read') store.get(id)
  else throw new Error('unknown test action')
  console.log('completed')
} catch (error) {
  if (error?.recordId) console.error('record-id=' + error.recordId)
  throw error
} finally {
  store.close()
}
