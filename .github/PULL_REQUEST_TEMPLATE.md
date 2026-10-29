## What changed

<!-- One paragraph: the behavior before and after. -->

## Area

- [ ] store / retrieval
- [ ] checkpoint / eviction / compression
- [ ] tools / commands / API / UI
- [ ] tests / benchmarks
- [ ] docs

## Verification

- [ ] `node scripts/build-bundle.mjs && node scripts/check-bundle.mjs`
- [ ] `node --import ./test/register.mjs ./test/run.mjs` (98/98 expected)
- [ ] benchmark/eval run when the change affects retrieval or capacity

## Notes for reviewers

<!-- Trade-offs, follow-ups, or anything intentionally out of scope. -->
