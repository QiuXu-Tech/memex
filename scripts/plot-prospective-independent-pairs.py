#!/usr/bin/env python3
"""Plot distinct registered follow-up issues and blind-review coverage."""
import html
import json
import pathlib

root = pathlib.Path(__file__).resolve().parent.parent
summary = json.loads((root / 'docs/assets/benchmarks/production-prospective-agent-batches/aggregate.json').read_text())['distinctIssueFollowupSupplementaryCoverage']
rows = summary['issues']
colors = {'PASS': '#397d6d', 'CHECKS_NONZERO': '#bd604f', 'INCOMPLETE': '#a87529',
          'UNKNOWN': '#766f8a', 'INTERRUPTED': '#766f8a', 'NOT_RUN': '#dce3e6'}
labels = {'PASS': 'Checks pass', 'CHECKS_NONZERO': 'Checks nonzero', 'INCOMPLETE': 'Incomplete',
          'UNKNOWN': 'Unknown', 'INTERRUPTED': 'Interrupted', 'NOT_RUN': 'Not run'}
height = 180 + len(rows) * 38 + 105
parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="1150" height="{height}" viewBox="0 0 1150 {height}" role="img" aria-labelledby="title desc">',
         '<title id="title">Follow-up issue pairs: execution and AI review</title>',
         '<desc id="desc">Keyword and Memex arms show partial-check outcomes. The final column shows whether each completed pair has two format-valid AI ratings per arm and all rating disagreements adjudicated. Missing work is not success.</desc>',
         f'<rect width="1150" height="{height}" fill="#f7f8fa"/>',
         '<text x="42" y="48" font-family="Arial,sans-serif" font-size="25" font-weight="700" fill="#19313e">New issue follow-up · execution and AI review</text>',
         '<text x="42" y="78" font-family="Arial,sans-serif" font-size="14" fill="#526a78">Separate adaptive batches · partial checks · public issues · not a production study</text>',
         '<text x="290" y="118" font-family="Arial,sans-serif" font-size="15" font-weight="700" fill="#19313e">Keyword</text>',
         '<text x="520" y="118" font-family="Arial,sans-serif" font-size="15" font-weight="700" fill="#19313e">Memex</text>',
         '<text x="750" y="118" font-family="Arial,sans-serif" font-size="15" font-weight="700" fill="#19313e">Two AI ratings per arm + disputes</text>']
for index, row in enumerate(rows):
    y = 135 + index * 38
    parts.append(f'<text x="42" y="{y+22}" font-family="Arial,sans-serif" font-size="15" fill="#19313e">{html.escape(row["project"])} #{html.escape(row["issue"])}</text>')
    for x, arm in ((290, 'keyword'), (520, 'memex')):
        outcome = row['arms'].get(arm, 'NOT_RUN')
        parts.append(f'<rect x="{x}" y="{y}" width="200" height="28" rx="4" fill="{colors[outcome]}"/>')
        ink = '#19313e' if outcome == 'NOT_RUN' else '#ffffff'
        parts.append(f'<text x="{x+100}" y="{y+19}" text-anchor="middle" font-family="Arial,sans-serif" font-size="13" fill="{ink}">{labels[outcome]}</text>')
    if row['bothArmsCompleteWithDisagreementsResolved']:
        label, fill = ('Complete *' if row.get('usedSupplementaryReviews') else 'Complete'), '#397d6d'
    elif row['bothArmsCompleteWithTwoFormatValidReviews']:
        label, fill = 'Dispute unresolved', '#a87529'
    else:
        label, fill = 'Not complete', '#766f8a'
    parts.append(f'<text x="750" y="{y+20}" font-family="Arial,sans-serif" font-size="14" fill="{fill}">{label}</text>')
foot = 150 + len(rows) * 38
parts.append(f'<text x="42" y="{foot+25}" font-family="Arial,sans-serif" font-size="14" fill="#526a78">A check pass is not maintainer acceptance; a format-valid AI rating is not a verified correctness label.</text>')
parts.append(f'<text x="42" y="{foot+48}" font-family="Arial,sans-serif" font-size="14" fill="#526a78">* Includes post-hoc alternate AI reviews. Shared projects and solution exposure limit interpretation.</text>')
parts.append('</svg>')
(root / 'docs/assets/benchmarks/production-prospective-independent-pairs.svg').write_text('\n'.join(parts) + '\n')
