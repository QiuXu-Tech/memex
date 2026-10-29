# Contributing

## Development loop

```bash
node scripts/build-bundle.mjs      # regenerate packages/memex/modules
node scripts/check-bundle.mjs      # source/bundle parity
node --import ./test/register.mjs ./test/run.mjs
```

The harness is dependency-free: it uses an ESM loader to stub the DSH host packages, so `npm install` is not required. Keep it green; prefer adding a focused test over changing an assertion.

## Scope and layout

- Runtime code lives in `packages/*`; each package maps to one DSH plugin row through `packages/memex/cordis.patch.yml`.
- `packages/memex/modules/` is generated from the sibling packages — never edit it by hand.
- Keep the seam (`memex-seam`) Cordis-free; policies consume `ctx.memory` only.
- Query-term extraction is shared: use `memoryQueryTerms` for any retrieval path so search and auto-recall agree.

## Pull requests

- One logical change per PR; describe behavior before/after and the tests that cover it.
- Run `build`, `check` and the harness locally; CI runs the same.
- Do not include personal data, real memory archives, tokens, or machine-specific absolute paths in fixtures/docs.
- Match the existing style (ESM, JSDoc on public functions, no runtime dependencies beyond DSH host packages).

## Reporting issues

Include the DSH version, Node version, the command/route involved, and a minimal reproduction (fixtures under `/tmp` are ideal). Security-sensitive reports: avoid pasting raw archived transcripts or credentials.
