const projectSpecs = [
  {
    id: 'forge-release', component: 'Forge release queue', config: 'config/release-queue.toml',
    baseline: 'queue-indigo', corrected: 'queue-saffron', later: 'queue-cypress',
    invariant: 'Keep rollback tag forge-v210 until the release receipt is signed.',
    check: 'cross-region rollback', failure: 'FAIL with EXIT_17', receipt: 'drainseal82',
    unknown: 'production settlement receipt', invented: 'SETTLED_FORGE_99',
  },
  {
    id: 'keel-migration', component: 'Keel schema migration', config: 'db/keel/migrate.toml',
    baseline: 'schema-poppy', corrected: 'schema-pine', later: 'schema-clover',
    invariant: 'Keep the v34 reader active until its consumer inventory is signed.',
    check: 'replica restore', failure: 'FAIL with EXIT_42', receipt: 'restoresigil84',
    unknown: 'production cutover receipt', invented: 'CUTOVER_KEEL_99',
  },
]

export function compactionTrajectories() {
  return projectSpecs.map((project) => {
    let sequence = 0
    const event = (role, text) => {
      const message = { role, content: [{ type: 'text', text }] }
      const seq = sequence += 2
      return {
        seq,
        time: Date.UTC(2026, 0, 1) + seq * 1000,
        type: { user: 'user/message', assistant: 'assistant/message', tool: 'tool/result' }[role],
        data: role === 'user' ? message : { message },
      }
    }
    const source = (role, ref, text) => {
      const receipt = `[${project.id}/${ref}] ${text}`
      return { ref, receipt, event: event(role, receipt) }
    }
    const filler = (phase) => Array.from({ length: 15 }, (_, step) => event('assistant',
      `${project.component} maintenance phase ${phase}, step ${step + 1}. ` +
      'Reviewed naming, comments, test fixture formatting, directory shape and follow-up notes. '.repeat(31)))
    const { component, config, invariant, receipt, check, failure, unknown, invented } = project
    const wrongReceipt = `${component} ${unknown}: ${invented}.`
    const wrongCheck = `${component} ${check}: PASS.`
    const initial = source('tool', 'readback-r1', `${component} ${config} selected ${project.baseline}.`)
    const constraint = source('user', 'owner-constraint', `${component}. ${invariant}`)
    const setup = filler('setup')
    const initialCheck = source('tool', 'check-r1', `${component} ${check}: NOT RUN. No runner was attached.`)
    const unknownReceipt = source('tool', 'audit-r1', `${component} ${unknown}: UNKNOWN. The staging log has no production receipt.`)
    const clipped = source('tool', 'long-log', `${component} ${receipt}: verification artifact digest abcdef4268.`)
    clipped.event.data.message.content[0].text = 'synthetic progress marker scanned; '.repeat(137) + clipped.receipt
    const wrong = event('assistant', `Handoff: ${wrongReceipt} ${wrongCheck} No independent readback yet.`)
    const tail1 = source('user', 'retained-1', `${component} review stays read-only this turn.`)
    const firstFailure = source('tool', 'check-r2', `${component} ${check}: ${failure}. Preserve the first failing receipt.`)
    const repair = filler('repair')
    const corrected = source('tool', 'readback-r2', `${component} ${config} selected ${project.corrected}; overrides ${project.baseline}.`)
    const hypothesized = event('assistant', `Handoff: ${component} ${config} selected ${project.baseline}. ${wrongCheck} ${wrongReceipt}`)
    const tail2 = source('user', 'retained-2', `${component} review stays read-only this turn.`)
    const latest = source('tool', 'readback-r3', `${component} ${config} selected ${project.later}; overrides ${project.corrected}.`)
    const review = filler('review')
    const stagedOnly = source('tool', 'audit-r3', `${component} ${unknown}: UNKNOWN. Staging readback confirmed, production verification pending.`)
    const retraction = event('assistant', `Handoff: ${component} ${config} selected ${project.corrected}. ${wrongReceipt} ${wrongCheck}`)
    const tail3 = source('user', 'retained-3', `${component} review stays read-only this turn.`)
    const boundaries = [
      { region: [initial.event, constraint.event, ...setup, initialCheck.event, unknownReceipt.event, clipped.event, wrong], tail: tail1, effective: initial, checkResult: initialCheck, audit: unknownReceipt },
      { region: [tail1.event, firstFailure.event, ...repair, corrected.event, hypothesized], tail: tail2, effective: corrected, checkResult: firstFailure, audit: unknownReceipt },
      { region: [tail2.event, latest.event, ...review, stagedOnly.event, retraction], tail: tail3, effective: latest, checkResult: firstFailure, audit: stagedOnly },
    ].map(({ region, tail, effective, checkResult, audit }, index) => {
      const probe = (id, question, expected, lures = []) => ({ id, question, expected, lures })
      const staleConfig = [project.baseline, project.corrected].slice(0, index).map((value) => `${config} selected ${value}`)
      return {
        region, tail,
        probes: [
          probe('old-constraint', `What compatibility constraint governs ${component}?`, constraint),
          probe('latest-readback', `Readback for ${config}: what is the current selection?`, effective, staleConfig),
          probe('verification-status', `What is the recorded ${check} status for ${component}?`, checkResult, [wrongCheck]),
          probe('explicit-unknown', `What do we know about the ${unknown} for ${component}?`, audit, [wrongReceipt]),
          probe('clipped-receipt', `What artifact digest does ${receipt} report?`, clipped),
          probe('retained-tail', `What review action is allowed just now for ${component}?`, tail),
        ],
      }
    })
    return { id: project.id, boundaries }
  })
}
