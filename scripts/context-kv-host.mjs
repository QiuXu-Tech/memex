#!/usr/bin/env node
// Runnable reference KV/prefix-cache host. It owns paged blocks and a prefix
// map; a real inference runtime can replace it with true KV tensors.
import { createServer } from 'node:http'
import { PagedKvContextHost } from '../packages/memex-core/lib/context-kv-host.js'

const port = Number(process.argv[process.argv.indexOf('--port') + 1]) || 8799
const host = new PagedKvContextHost({ capacityBlocks: 32, blockTokens: 256 })
const json = (response, status, body) => { response.writeHead(status, { 'content-type': 'application/json' }); response.end(JSON.stringify(body)) }
const readBody = async (request) => {
  let body = ''
  for await (const chunk of request) { body += chunk; if (body.length > 2_000_000) throw new Error('body too large') }
  return body.length === 0 ? {} : JSON.parse(body)
}
const server = createServer(async (request, response) => {
  try {
    const url = new URL(request.url, `http://127.0.0.1:${port}`)
    if (request.method === 'GET' && url.pathname === '/health') return json(response, 200, { ok: true, ...host.stats() })
    if (request.method === 'GET' && url.pathname === '/capabilities') return json(response, 200, host.negotiation())
    if (request.method === 'GET' && url.pathname === '/stats') return json(response, 200, host.stats())
    if (request.method === 'GET' && url.pathname === '/prefix') return json(response, 200, { key: url.searchParams.get('key'), blocks: host.resolvePrefix(url.searchParams.get('key')) })
    if (request.method === 'POST' && url.pathname === '/prefix') { const body = await readBody(request); return json(response, 200, { key: body.key, blocks: host.registerPrefix(body.key, body.texts ?? []) }) }
    if (request.method === 'POST' && url.pathname === '/page-in') { const body = await readBody(request); return json(response, 200, { span: body.span, blocks: host.pageIn(body.span, body.blocks ?? []) }) }
    if (request.method === 'POST' && url.pathname === '/page-out') { const body = await readBody(request); return json(response, 200, { span: body.span, removed: host.pageOut(body.span) }) }
    return json(response, 404, { error: 'not found' })
  } catch (error) {
    return json(response, 400, { error: String(error?.message ?? error) })
  }
})
server.listen(port, '127.0.0.1', () => console.log(`memex reference KV host: http://127.0.0.1:${port} (paged blocks + prefix cache)`))
