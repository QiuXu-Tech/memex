/** Study-only stdio proxy: enforce an identical recovered-text ceiling for B and C. */
import { spawn } from 'node:child_process'
import { readFileSync, writeFileSync } from 'node:fs'
import { createInterface } from 'node:readline'

const [budgetFile, server, ...args] = process.argv.slice(2)
if (!budgetFile || !server) throw new Error('Usage: budget-proxy BUDGET_FILE SERVER [ARGS]')
const child = spawn(process.execPath, [server, ...args], { stdio: ['pipe', 'pipe', 'inherit'] })
const calls = new Set()

createInterface({ input: process.stdin }).on('line', line => {
  const message = JSON.parse(line)
  if (message.method === 'tools/call' && message.id !== undefined) calls.add(message.id)
  child.stdin.write(line + '\n')
}).on('close', () => child.stdin.end())

createInterface({ input: child.stdout }).on('line', line => {
  const response = JSON.parse(line)
  if (calls.delete(response.id) && response.result?.content) {
    const budget = JSON.parse(readFileSync(budgetFile, 'utf8'))
    if (!Number.isSafeInteger(budget.remaining) || budget.remaining < 0) throw new Error('Invalid recovery budget')
    const content = response.result.content
    const chars = content.reduce((total, block) => total + (block.type === 'text' ? block.text.length : Infinity), 0)
    if (chars <= budget.remaining) {
      budget.remaining -= chars
      budget.delivered += chars
    } else {
      budget.refused += 1
      response.result = { isError: true, content: [{ type: 'text',
        text: 'Recovery budget: request fewer search results or a smaller open page, or leave unsupported details UNKNOWN.' }] }
    }
    writeFileSync(budgetFile, JSON.stringify(budget) + '\n')
  }
  process.stdout.write(JSON.stringify(response) + '\n')
})

child.on('error', error => { throw error })
child.on('close', code => { process.exitCode = code ?? 1 })
