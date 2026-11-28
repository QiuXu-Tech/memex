# Remaining-work integration evidence

Date: 2026-11-28 (Asia/Shanghai). **Engineering completion evidence; NOT READY / NOT SUBMITTED; no new research results.** This work made zero external model-generation calls, consumed no native or method attempts, and made no canonical cash-ledger writes. Public dependency downloads and actual local loopback tests are separate from model requests.

## What is retained here

| File or directory | Observed evidence |
|---|---|
| [validation.json](validation.json) | Final suite counts, retained initial failures, correction scope and limits. |
| [runtime-code-identity.json](runtime-code-identity.json) | 63 implementation files checked against the published runtime commit/tree; hashes are independent of later documentation-only commits. |
| [ledger-verification.json](ledger-verification.json) | Exact original authorization/plan/budget/PDF/ZIP hashes; seven-event ledger status; preserved original four-event byte prefix. |
| [checks/](checks/) | Initial and final research-suite logs, portable fixture regression, driver fixture correction and repository-suite log. Local checkout paths are replaced with `<repo>` / `<scratch>`; initial test failures are retained. |
| [tokenizer-check.json](tokenizer-check.json) | Actual fixed official tokenizer loading and deterministic text counts; reference counting is not provider-billing exactness. |
| [host-schema-check.json](host-schema-check.json) | Installed Codex 0.153.0 experimental JSON-RPC schema export; no model or native attempt. |
| [macos-dependency-setup.json](macos-dependency-setup.json) | Real Mac Python 3.12.13 orchestration environment, 37 wheel-only packages, official tokenizer/cache, guarded SDK construction and private settings. No API method called. Git/Xcode license blocker remains explicit. |
| [macos-runtime-deployment.json](macos-runtime-deployment.json) | Published source tree verified and installed into the existing canonical runtime; 771 static files checked, 761 newly installed, eight old code files backed up and modes normalized. Original authorization and ledger remain in place. |
| [macos-native-preflight.json](macos-native-preflight.json) | Actual default inspection on the prepared Mac, with settings supplied: auth/relocation/reader/tokenizer and task pins checked; dispatch blocked with zero model, network, child-process or credential-content access. This is a path-redacted public projection. |
| [macos-preflight-postcheck-correction.json](macos-preflight-postcheck-correction.json) | Retained correction of a deployment-wrapper counter assertion; the initial driver itself returned 0, protected bytes were unchanged, and only the default read-only inspection was repeated to retain its report. |
| [deepseek-price-basis.json](deepseek-price-basis.json) | Dated official price facts and conditional serial reservation arithmetic; not an invoice, account-balance statement or permission grant. |
| [native-driver/](native-driver/) | Actual default read-only local preflight, blocked with native allowance exhausted; no settings/remote credential claim is inferred. |
| [reporting/](reporting/) | Actual zero-result report and design analysis, with eight source bindings, empty accepted-study denominator, null effects/intervals/N and no power simulation. |

Separate actual Mac environment and OS-isolation evidence is retained in [public-workspace checks](../checks/public-workspace/). Python 3.10.16 environments match both fixed task dependency sets (17 and 15 pins), and each real sandbox canary passed. Earlier failed canaries and installation stages remain visible. These are environment/canary observations, not agent task trials.

The separate Python 3.12 orchestration environment reuses an existing interpreter and installs the fixed baseline dependencies plus `tokenizers==0.22.2`. Its actual guarded import/SDK/tokenizer check observed zero network attempts and zero credential-file access attempts. The fixed upstream Raw-RAG source archive has nine verified pinned files, but is explicitly **not a Git checkout**. System Git and the one attempted Homebrew bottle installation stopped at the Mac's Xcode license gate; no terms were accepted. Real B remains blocked pending a usable Git checkout, existing provider credentials and verified billing.

The deployed source is commit `b0af94569d3915d1dc3364b899b18881aa0e3afc`, tree `107a0b93b62678022ec26928535f69310f82b222`. The six protected authorization/plan/budget/ledger files retain their bytes and modes. Both installed public task digests match the original authorization. The default Mac driver returned 0 while reporting `dispatch_ready=false`: `native_attempt_budget_exhausted`, `embedding_environment_unavailable`, `reranker_environment_unavailable`, and `scope_specs_required`. No unverified prices or scopes were invented to remove these blockers. The driver's `remote_device_queried=false` means the driver made no remote-device API call; it actually ran locally on the Mac, as the deployment receipt and Darwin/Python metadata record.

The first deployment-wrapper postcheck mistakenly expected two **remaining** native attempts, whereas the original 7/2/0 shorthand meant seven events, two **reserved** native attempts and zero reserved method units. Its protected-file checks had already passed. That wrapper error and its cause are retained, with `prior_driver_report_retained=false`; the first complete driver report was not saved. Only a second default read-only inspection was performed to retain the final report. No deployment, model request, source test, cash reservation or ledger event was repeated.

## Final verification

| Scope | Passed | Failed | Skipped | Interpretation |
|---|---:|---:|---:|---|
| Research Node | 123 | 0 | 0 | Real helper/archive behavior, bounded transports and offline/controller contracts. |
| Research Python | 487 | 0 | 9 | 496 discovered cases. Nine tests require the old local Python 3.10 fixture environments, absent on this inspection machine. No pass is imputed to them. |
| Main repository | 197 | 0 | 4 | Four generated-bundle checks skipped because bundles were not built; kept separate from research counts. |

The whole research suite therefore has **610 passes and 9 explicit skips**, not 619 passes. The Python suite used the installed OpenAI SDK and HTTP client through the isolated baseline environment; its real-SDK fixture was not skipped. Upstream HTTP responses in these tests are memory fixtures. The real loopback HTTP transport is local test traffic, not a DeepSeek service run.

Commands, executed from the checkout root:

```bash
node --test test/paper1-*.mjs

PYTHONPATH=<isolated-baseline-env>/lib/python3.12/site-packages \
  <inspection-runtime-env>/bin/python -B -m unittest discover \
  -s test -p 'test_paper1_*.py' -v

npm test
```

The initial Node run had 122 passes and one copied-ledger fixture failure. The initial Python run discovered 495 cases, with four failures, six errors and nine skips. Corrections address stale test assumptions and a price fixture: the copied current ledger already contains the earlier diagnostic reservation; an archived plan keeps its original absolute paths; the current serial proof requires complete dated price fields. Tests now check the incremental cash change, use explicit temporary relocated fixtures, and verify that original plan/authorization bytes are not silently changed. The new archived-path regression increases the final Python count by one. No production cash check or protected historical record was relaxed to make the tests pass.

## Unchanged scope and scientific status

The canonical ledger still has seven events: two consumed native attempts, zero method units, and the earlier single DeepSeek diagnostic. CNY 3.00 remains held as an unknown-cost reservation within the original CNY 100.00 cap; CNY 97.00 is remaining reservation capacity, not a verified account balance. Actual added cash remains null.

The current paired runtime, controller, relay and driver have not performed a new real native four-arm run. The persistent in-process launcher was exercised with an explicit development fixture, including A/C/D, first-attempt recording, usage/seal/join and no interrupted replay. It supplies no empirical B comparison or accepted task. Price/source bindings and private receipts constrain the trusted runtime path; they are not an attestation against a filesystem owner rewriting code or logs.

Human review, author facts, complete paired measurements, formal design/freeze and actual submission remain real external/research gates. The complete implementation handoff and concrete next-batch proposal are in [REMAINING_WORK.md](../../REMAINING_WORK.md). Original authorizations remain effective; the proposed four additional native preparations are explicitly **not approved or activated** by this record.
