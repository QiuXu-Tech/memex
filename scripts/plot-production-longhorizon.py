#!/usr/bin/env python3
"""Render the scoped, non-production agent replay summary."""
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

root = Path(__file__).resolve().parents[1]
data = json.loads((root / 'docs/assets/benchmarks/production-longhorizon-20261101/results.json').read_text())
previous = json.loads((root / 'docs/assets/benchmarks/production-real30-20261101/results.json').read_text())
fig = plt.figure(figsize=(14, 5.4), facecolor='#f6f8fb')
gs = fig.add_gridspec(1, 3, width_ratios=[1.05, 1.30, 1.25], left=.06, right=.97, top=.73, bottom=.20, wspace=.38)
axes = [fig.add_subplot(gs[0, i]) for i in range(3)]
for ax in axes:
    ax.set_facecolor('#f6f8fb')
    for spine in ax.spines.values(): spine.set_visible(False)
    ax.tick_params(length=0, labelsize=9, colors='#334155')
fig.text(.06, .91, 'Memex: cross-session agent evaluation', fontsize=19, weight='bold', color='#0f172a')
fig.text(.06, .84, 'Historical public-issue replay · selected tasks · AI review · not a production trial', fontsize=10, color='#475569')

ax = axes[0]
pair = previous['usagePairedSessions']
values = [pair['baseline']['input_tokens'] / 1e6, pair['memex']['input_tokens'] / 1e6]
ax.barh(['Control', 'Memex'], values, color=['#94a3b8', '#2563eb'], height=.5)
ax.invert_yaxis(); ax.set_xlim(0, 14); ax.set_xlabel('Million input tokens, including cache', fontsize=9)
ax.set_title('Earlier study: 28 complete pairs', loc='left', fontsize=11, weight='bold', pad=16)
for y, value in enumerate(values): ax.text(value + .15, y, f'{value:.2f}M', va='center', fontsize=10, weight='bold', color='#0f172a')
ax.text(0, -.19, 'Memex +40.2%; tokens are not a bill.', fontsize=9, color='#475569', transform=ax.transAxes)

ax = axes[1]; ax.axis('off')
ax.set_title('New Codex replay: 0/3 complete pairs', loc='left', fontsize=11, weight='bold', pad=16)
ax.text(.00, .93, 'Issue', weight='bold', fontsize=9, transform=ax.transAxes)
ax.text(.38, .93, 'Control', weight='bold', fontsize=9, transform=ax.transAxes)
ax.text(.72, .93, 'Memex', weight='bold', fontsize=9, transform=ax.transAxes)
for i, task in enumerate(data['originalCodex']['tasks']):
    y = .76 - i*.22
    ax.text(.00, y, task['id'].title(), fontsize=10, transform=ax.transAxes)
    for xpos, arm in ((.38, 'baseline'), (.72, 'memex')):
        row = task['arms'][arm]; status = 'pass' if row['fixedVerifierExitCode'] == 0 else 'fail'
        incomplete = row['strictCompletedSessions'] < 3
        ax.text(xpos, y, f"{row['strictCompletedSessions']}/3 · {status}{'*' if incomplete else ''}", fontsize=9,
                color='#9a3412' if incomplete else '#166534', transform=ax.transAxes)
ax.text(0, .05, '* Incomplete session sequence; not a valid pair.', fontsize=8.5, color='#475569', transform=ax.transAxes)

ax = axes[2]; ax.axis('off')
ax.set_title('One post-hoc Claude continuation', loc='left', fontsize=11, weight='bold', pad=16)
ax.text(0, .92, 'Control / Memex', fontsize=9, weight='bold', color='#475569', transform=ax.transAxes)
lines = [('Original fixed checks', 'pass / pass'),
         ('Extra inherited-setter check', 'pass / FAIL'),
         ('AI adjudication, control / Memex', '2 / 1'),
         ('Memory written then opened', 'yes; content flawed')]
for i, (label, value) in enumerate(lines):
    y = .79 - i*.20
    ax.text(0, y, label, fontsize=9, color='#334155', transform=ax.transAxes)
    ax.text(0, y-.075, value, fontsize=10, weight='bold', color='#b91c1c' if 'FAIL' in value or 'flawed' in value else '#0f172a', transform=ax.transAxes)
fig.text(.06, .07, 'The continuation reused one issue and added an extra attempt. Checks are investigator-authored, not the upstream suite.', fontsize=9, color='#475569')
target = root / 'docs/assets/benchmarks/production-longhorizon-20261101.svg'
fig.savefig(target, format='svg', facecolor=fig.get_facecolor())
target.write_text('\n'.join(line.rstrip() for line in target.read_text().splitlines()) + '\n')
fig.savefig(target.with_suffix('.png'), dpi=150, facecolor=fig.get_facecolor())
