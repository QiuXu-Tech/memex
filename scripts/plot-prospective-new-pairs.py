#!/usr/bin/env python3
"""Plot registered task-arm outcomes without treating missing slots as successes."""
import html
import json
import pathlib

root = pathlib.Path(__file__).resolve().parent.parent
data = json.loads((root / 'docs/assets/benchmarks/production-prospective-agent-batches/aggregate.json').read_text())
batches = {'prettier-gateway', 'dayjs-gateway', 'moment-mathjs', 'dayjs-mathjs', 'prettier-late', 'mathjs-late', 'validator-new', 'luxon-new', 'lodash-new', 'yup-new', 'validator-chartjs', 'chartjs-unstarted'}
rows = {}
no_history = set()
for batch in data['batches']:
    if batch['batch'] not in batches:
        continue
    for run in batch['runs']:
        key = (run['project'] or 'unknown', run['issue'])
        rows.setdefault(key, {})[run['arm']] = run['attemptOutcome']
        if run.get('historyRecords') == 0:
            no_history.add(key)

colors = {'PASS': '#3d8c78', 'CHECKS_NONZERO': '#c66f5e', 'INCOMPLETE': '#c89b58',
          'UNKNOWN': '#8d87a2', 'INTERRUPTED': '#8d87a2', 'NOT_RUN': '#c9d1d5'}
names = {'PASS': 'Complete + checks pass', 'CHECKS_NONZERO': 'Checks nonzero',
         'INCOMPLETE': 'Incomplete', 'UNKNOWN': 'Unknown', 'INTERRUPTED': 'Interrupted', 'NOT_RUN': 'Not run'}
height = 180 + len(rows) * 38 + 105
parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="1050" height="{height}" viewBox="0 0 1050 {height}" role="img" aria-labelledby="title desc">',
         '<title id="title">New issue pairs: execution and partial checks</title>',
         '<desc id="desc">Keyword and Memex arms for each newly registered public issue. Cells show completed checks, failures, incomplete, unknown, and unstarted assignments; this is not production evidence.</desc>',
         f'<rect width="1050" height="{height}" fill="#f7f8fa"/>',
         '<text x="48" y="48" font-family="Arial,sans-serif" font-size="25" font-weight="700" fill="#19313e">New public-issue pairs · partial checks</text>',
         '<text x="48" y="78" font-family="Arial,sans-serif" font-size="14" fill="#526a78">Separate adaptive registrations; short issue discussions; not a production study</text>',
         '<text x="370" y="118" font-family="Arial,sans-serif" font-size="16" font-weight="700" fill="#19313e">Keyword retrieval</text>',
         '<text x="680" y="118" font-family="Arial,sans-serif" font-size="16" font-weight="700" fill="#19313e">Memex pager</text>']
for index, ((project, issue), arms) in enumerate(rows.items()):
    y = 135 + index * 38
    marker = ' †' if (project, issue) in no_history else ''
    parts.append(f'<text x="48" y="{y+22}" font-family="Arial,sans-serif" font-size="15" fill="#19313e">{html.escape(project)} #{html.escape(issue)}{marker}</text>')
    for x, arm in ((370, 'keyword'), (680, 'memex')):
        outcome = arms.get(arm, 'NOT_RUN')
        parts.append(f'<rect x="{x}" y="{y}" width="250" height="28" rx="4" fill="{colors[outcome]}"/>')
        ink = '#19313e' if outcome == 'NOT_RUN' else '#ffffff'
        parts.append(f'<text x="{x+125}" y="{y+19}" text-anchor="middle" font-family="Arial,sans-serif" font-size="13" fill="{ink}">{names[outcome]}</text>')
foot = 150 + len(rows) * 38
parts.append(f'<text x="48" y="{foot+25}" font-family="Arial,sans-serif" font-size="14" fill="#526a78">Cells record one assignment each; a pass is not upstream acceptance. AI review validity is reported separately.</text>')
parts.append(f'<text x="48" y="{foot+48}" font-family="Arial,sans-serif" font-size="14" fill="#526a78">† No discussion history; negative control. Shared projects and public solutions limit causal inference.</text>')
parts.append('</svg>')
(root / 'docs/assets/benchmarks/production-prospective-new-pairs.svg').write_text('\n'.join(parts) + '\n')
