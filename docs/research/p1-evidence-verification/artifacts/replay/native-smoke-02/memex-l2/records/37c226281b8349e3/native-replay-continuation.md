---
id: "native-replay-continuation"
kind: "fact"
scope: "session"
workspace: ""
workspace_key: "37c226281b8349e3"
session_id: "01a21dfb-37dc-7bf2-ac93-361b53c5c285"
title: "native-smoke-02 node --test --test-reporter=tap sum.test.mjs test_result"
use_when: ""
status: "active"
trust: "untrusted"
tokens: 544
tags: {}
links: {}
provenance: {"shadowedSeqs":[1]}
created_at: 1795800939500
updated_at: 1795800939500
---
{"eventId":"exec-0fc7450a-e3a0-487e-986f-cf1689853d09","sourceId":"01a21dfb-37dc-7bf2-ac93-361b53c5c285:node-tests","sourceSequence":2,"observedAt":"2026-11-27T17:26:15.480693+00:00","type":"test_result","scope":"native-smoke-02","entity":"node --test --test-reporter=tap sum.test.mjs","version":"b80a36de74bb7c3f2fad39ead1e40fcd648f39898957c63e1e487d8582b6b2ec","role":"tool","kind":"command_execution","command":"node --test --test-reporter=tap sum.test.mjs","status":"failed","complete":true,"completed":true,"executed":true,"exitCode":1,"testCount":1,"skippedCount":0,"todoCount":0,"text":"TAP version 13\n# Subtest: sums\nnot ok 1 - sums\n  ---\n  duration_ms: 0.890959\n  type: 'test'\n  location: '<RUN_ROOT>/native-smoke-02/workspace/sum.test.mjs:4:1'\n  failureType: 'testCodeFailure'\n  error: |-\n    Expected values to be strictly equal:\n    \n    43 !== 42\n    \n  code: 'ERR_ASSERTION'\n  name: 'AssertionError'\n  expected: 42\n  actual: 43\n  operator: 'strictEqual'\n  stack: |-\n    TestContext.<anonymous> (file://<RUN_ROOT>/native-smoke-02/workspace/sum.test.mjs:4:27)\n    Test.runInAsyncScope (node:async_hooks:226:14)\n    Test.run (node:internal/test_runner/test:1201:25)\n    Test.start (node:internal/test_runner/test:1096:17)\n    startSubtestAfterBootstrap (node:internal/test_runner/harness:385:17)\n  ...\n1..1\n# tests 1\n# suites 0\n# pass 0\n# fail 1\n# cancelled 0\n# skipped 0\n# todo 0\n# duration_ms 64.048834\n","parserVersion":"native-node-tap-v1","transport":{"nativeLog":"native-smoke-02-resumed-final/host/events.jsonl","line":8,"phase":"continuation","threadId":"01a21dfb-37dc-7bf2-ac93-361b53c5c285","turnId":"01a21e0a-f015-7f01-ac64-34dc17798fd5","utc":"2026-11-27T17:26:15.480693+00:00","completedAtMs":1795800375479,"artifactBindingMode":"offline_controller_summary_version_mapping","artifact":"sum.mjs","versionStage":"changed","summaryPath":"native-smoke-02-resumed-final/summary.json","summarySha256":"19132202672f6c05d38e7a965a5db52477eb5b54c92ae977a18563c27863e37c","independentLiveBeforeAfterMeasurements":false,"liveWorkspaceRevalidation":false}}
