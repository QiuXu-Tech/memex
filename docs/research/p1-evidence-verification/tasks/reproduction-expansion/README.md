# Remaining source/environment qualifications

**Fourteen of fourteen remaining candidates were attempted; ten newly satisfy the local qualification rule. Together with the two earlier runs, twelve of sixteen candidates qualify.** Four have concrete bounded limitations. These are environment and source qualifications of a candidate pool, not formal P1 samples, method-arm results, or sample exclusions. No models were called. The earlier Flask #5014 and Requests #6028 successes were not rerun.

The authoritative machine-readable result is [summary.json](summary.json). It contains the final 16-candidate inventory, references to immutable attempt receipts, actual phase counts, aggregate time spent per candidate, and limitations. [qualification-revisions.json](qualification-revisions.json) records a read-only interpretation correction for the two SymPy native-runner results; their original receipts and logs remain unchanged.

## Observed results

P = passed; F = assertion failure; E = error/uncaught exception; S = skipped; X = expected failure. Counts come from actual JUnit test cases, except the two SymPy rows, which use the upstream native runner's terminal summary. Native summaries are explicitly distinguished from JUnit. Unknown/unexecuted counts are not zero-filled.

| Candidate | Actual cases per phase | Base | After official source patch | Local qualification |
| --- | ---: | --- | --- | --- |
| `pallets__flask-5014` | 60 | 59 P, 1 F | 60 P | Prior success; not repeated |
| `psf__requests-6028` | 214 | 201 P, 2 F, 11 S | 203 P, 11 S | Prior success; not repeated |
| `pytest-dev__pytest-5262` | 116 | 109 P, 1 F, 6 S | 110 P, 6 S | Newly qualified |
| `pytest-dev__pytest-7982` | 80 | 78 P, 1 F, 1 S | 79 P, 1 S | Newly qualified |
| `pytest-dev__pytest-7432` | 79 | 78 P, 1 F | 79 P | Newly qualified |
| `pylint-dev__pylint-7080` | 125 | 123 P, 1 F, 1 S | 124 P, 1 S | Newly qualified |
| `sphinx-doc__sphinx-8721` | 5 | 4 P, 1 F | 5 P | Newly qualified |
| `sympy__sympy-14711` | 4 | 3 P, 1 E | 4 P | Newly qualified after documented interpretation correction |
| `pydata__xarray-4629` | 33 | 32 P, 1 F | 33 P | Newly qualified |
| `pydata__xarray-6461` | 249 | 247 P, 1 F, 1 S | 248 P, 1 S | Newly qualified |
| `mwaskom__seaborn-3069` | 175 | 168 P, 2 F, 5 S | 170 P, 5 S | Newly qualified |
| `mwaskom__seaborn-3187` | 256 | 249 P, 2 F, 5 S | 251 P, 5 S | Newly qualified |
| `psf__requests-5414` | 290 | 283 P, 5 F, 1 E, 1 S | 284 P, 4 F, 1 E, 1 S | Target regression fixed; network-dependent module checks remain blocked |
| `pylint-dev__pylint-4970` | Not executed | Setup blocked | Setup blocked | No compatible `wrapt==1.12.1` binary wheel under this Python 3.9 profile |
| `sympy__sympy-19637` | 50 | 40 P, 3 E, 5 S, 2 X | 41 P, 2 E, 5 S, 2 X | Official expected transitions pass; two other module errors remain |
| `sphinx-doc__sphinx-9367` | 42 | 41 P, 1 F | 42 P | Module regression fixed; official P2P label mapping remains incomplete |

Qualification requires both the complete expected-label transition and a completed fixed-module process with exit code zero. Fixing only the named regression is insufficient. Optional skipped tests are visible in the counts; they are not counted as passing. The rule accepts a base `FAILED` or native `ERROR` result, requires `PASSED` after the patch, and never treats absent, skipped, or already passing tests as a reproduced failure.

### Four remaining limitations

- **Requests #5414:** The target failure changes to pass, but the fixed module still has four failures and one error. The preserved sandbox has no host resolver configuration; other tests assume external name resolution or an unreachable-network behavior that this host does not provide. Network controls were left unchanged. The full official P2P inventory is not claimed to pass.
- **Pylint #4970:** Its historical `astroid==2.7.3` dependency requires the old wrapt range. The selected `wrapt==1.12.1` has no compatible wheel for this CPython 3.9 binary-only installation. No forced dependency substitution or source-package build was attempted. This is a limitation of the declared local profile, not evidence that the official image cannot run.
- **SymPy #19637:** The target and all official expected-label transitions pass, while two other tests still raise Python 3.9 AST compatibility exceptions. The fixed native runner exits one; the module remains unqualified.
- **Sphinx #9367:** The module has 42 actual cases and finishes with all passing after the patch. The target F2P identity agrees. Fifteen of the 25 historical P2P label identities do not match the current pinned official parser/pytest output: whitespace truncation and duplicate-parameter naming differ. The raw mismatch is retained privately; no custom permissive normalization is used to declare the official inventory complete.

These candidates remain available for subsequent environment or label adjudication. This qualification work does not authorize their exclusion from a future formal sample.

## Attempts and budgets

There are **29 independent numbered source-qualification attempts**: 14 initial attempts, 11 explicit setup followups, and four final environment diagnostics. Every earlier failure remains in its original directory. These are development/qualification attempts, not repeated formal model attempts.

- Initial receipts: `<candidate>/reproduction.json`.
- Setup followups: `followup-2/<candidate>/reproduction.json`.
- Final diagnostics: `diagnostic-3/<candidate>/reproduction.json`.

The initial runner omitted a sandbox account record, making historical setuptools unable to resolve `~`. The correction binds a generated, single-account `/etc/passwd` inside the candidate sandbox. It reads no host account database and does not reset `HOME` or `CODEX_HOME`. Two wheel-only dependency selections were corrected transparently: atomicwrites 1.4.1 to 1.4.0, and py-cpuinfo 8.0.0 to 9.0.0. Both satisfy their corresponding source constraints; initial failures and original profiles are retained.

The four final diagnostics corrected two driver/profile issues. Requests loads the actual declared `pytest_httpbin.plugin` entry point. The three pytest projects fetch official commit ancestry and tags because shallow clones made setuptools-scm report `0.1.dev1`, below the projects' existing minversion. No source version was pretended, and no minversion guard was edited. Each diagnostic first verifies the exact fixed source and test hashes, reverses only the known production patch, and repeats base/fixed phases with the same test patch. The archived diagnostic script and every command are included in the evaluator-only evidence package.

Across all attempts combined, each candidate stays below **360 seconds of setup and 180 seconds for each of the base and fixed phases**. Actual maxima are recorded in the summary. No candidate reached a timeout. There were **34 actual top-level test-phase process invocations: 30 pytest and four SymPy `bin/test` invocations**. Six of the pytest invocations exited at the version guard before collection. The pytest projects' own tests can spawn nested pytester processes; those indirect invocation counts were not instrumented and remain `null`. This does not represent 34 independent experimental tasks. Model requests, formal method-arm runs, and formal sample exclusions are all zero.

## Source and environment provenance

The inputs are the fixed [SWE-bench Verified dataset revision](https://huggingface.co/datasets/SWE-bench/SWE-bench_Verified/tree/78f471bf655a3137b2e8a75af1501690ec009ec3). The downloaded 6,304,616-byte Parquet SHA-256 is `030cfd7f2a704c4c0226e7f104c725a3b41230b1d3517f9c915ad7ea5be3fa25`. Every selected row's canonical hash, base commit, production patch hash, test patch hash, and allowed changed-file paths are checked before execution. Original test patches remain identical between base and fixed phases.

The source patches are the dataset's curated patches at its exact base commit. An upstream merge commit is a provenance locator; it is not substituted for a full base-to-merge diff. Exact upstream URLs, full commits, row hashes, test module paths, and source-license references are in each receipt and in the unchanged [acquisition manifest](../acquisition/candidate-manifest.json).

Official log parsing uses the unchanged function/constant AST from [SWE-bench commit `02e7a74ffd0b707aab73d203fe87bdc7c76afc8e`](https://github.com/SWE-bench/SWE-bench/tree/02e7a74ffd0b707aab73d203fe87bdc7c76afc8e):

| Official file | SHA-256 |
| --- | --- |
| `swebench/harness/log_parsers/python.py` | `cd56156414f8327221e525665ace9b184f7d73e83b272d9eb3f545fb17c2d9bc` |
| `swebench/harness/constants/__init__.py` | `8895ab5313d874349c4b07bd223bb9eb00acaee377b432e67cc7ad840341e79b` |

All new candidates use a separately installed CPython 3.9.21 runtime and per-candidate virtual environments. `profiles-initial.json`, `profiles-followup-2.json`, and `profiles.json` retain the profile history. Each attempt has its own profile digest. Successful installations have complete resolved `pip freeze --all` output. `installed-environments-index.json` and per-environment inventories preserve version, METADATA, RECORD, and direct-URL metadata digests for 335 installed distributions across 14 environments. These metadata digests are not represented as original wheel archive hashes. New downloads in the corrected runner have pip report archive hashes; initial downloads did not record all archive-byte hashes, and reused packages do not acquire fabricated download measurements.

Project installation and tests use the existing bwrap user/pid/ipc/uts isolation, with only that candidate's repository, virtual environment, logs, and Python runtime mounted. Other project directories, credential stores, host account records, and host resolver configuration are not mounted. The network namespace remains shared, as in the earlier qualification runs; no networking isolation or connectivity is claimed beyond the actual recorded controls. Dependency acquisition preserves existing transport proxy settings in a minimal environment without printing their values. This is a pinned **local compatibility profile**, not an execution of or an equivalence claim about the official Docker image.

## Reproduce from fixed inputs

The reusable entry point is `scripts/paper1/reproduce_sources.py`. It uses the standard library. It never reads `.env`, never calls a model, and defaults to dry-run. Source acquisition is from the exact official GitHub base; project requirements are exact version pins. The optional bootstrap below needs pyarrow only to read the official Parquet.

Create an evaluator-only directory outside this repository. Obtain CPython 3.9.21 using the pinned installation command in `provenance.json`, and install `pyarrow==16.1.0` plus `numpy==1.26.4` in a separate bootstrap environment using binary wheels. Download the fixed Parquet URL in the acquisition manifest and verify its byte hash before parsing it. Save only the 14 selected full rows privately as `<candidate_id>.official-row.json`; their complete original fields are needed to verify the recorded canonical row hashes. Do not copy them into the public checkout. Fetch the two official parser files above at their exact commit and verify their hashes, saving them privately as `official-log-parsers-python.py` and `official-harness-constants.py`.

With those verified inputs, the following command is a dry-run and launches no subprocesses:

```sh
python scripts/paper1/reproduce_sources.py \
  --manifest docs/research/p1-evidence-verification/tasks/acquisition/candidate-manifest.json \
  --profiles docs/research/p1-evidence-verification/tasks/reproduction-expansion/profiles.json \
  --private-root /absolute/evaluator-only/reproduction-inputs \
  --output /absolute/new-local-qualification-receipts \
  --python /absolute/cpython-3.9.21/bin/python3.9
```

Add `--run` to authorize actual acquisition, installation, and bounded program tests. Use `--candidate <id>` to select a subset. The two prior successes are skipped. An existing attempt reservation prevents automatic reruns. A single explicit `--retry-setup` is available only for a failed setup before any test phase, retains the initial receipt, and subtracts the earlier time from the same setup budget. The archived final diagnostics are separately recorded development actions; the general runner does not silently retry a completed test failure. Fresh runs using the final profile include the corrected entry point and SCM history acquisition.

The original run commands include local absolute paths and are preserved in the receipts. A fresh reproduction should use new output directories. It should not overwrite this evidence set or present a new run as the old one.

## Evidence and publication boundary

Public files contain source locators, version pins, commands without secret values, content hashes, aggregate actual counts, and qualification decisions. Raw official rows, production/test patches, labels, full stdout/stderr, JUnit files, and parser/command snapshots are evaluator-only. The private archive has a path map and byte-hash manifest so each public raw-log reference can be located without placing the raw evidence in public Git or on a model machine.

Repository-level license notices remain in [acquisition/licenses](../acquisition/licenses); their scope is unchanged. The harness MIT notice is not applied to all nested code, issue text, benchmark rows, or dependencies. Pylint's existing `NOASSERTION` SPDX observation is preserved. No source code, hidden patch, hidden label array, or full issue body is redistributed in this public result directory.

The runner's focused tests were written before their corresponding implementation changes. Observed red states included missing implementation, parser module constants omitted, absent cumulative retry checks, missing synthetic account setup, candidate path traversal acceptance, and native ERROR handling. The final 17 boundary tests pass; their receipts are in `validation-receipt.json`. These unit tests exercise driver contracts and do not produce research results.

### Post-execution implementation review

After the evidence package was sealed, independent review found that the driver recorded test-file integrity but did not use a false result to block qualification after the fixed test process. The current driver now returns `evidence_integrity_failure` unless that result is exactly true. A synthetic regression test first reproduced the erroneous qualified status, then passed after the guard was added; the current suite has **18 passing tests**. [implementation-revision-1/revision.json](implementation-revision-1/revision.json) binds the red/green outputs and the new code hash. A read-only check confirmed the nine originally qualified receipts and the SymPy #14711 revised qualification all already have `test_file_unchanged_between_phases=true`. All 29 historical receipt bytes and the original private archive are unchanged. No source test phase or model was rerun for this implementation revision.
