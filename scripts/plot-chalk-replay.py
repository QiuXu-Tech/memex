#!/usr/bin/env python3
"""Plot a single new issue replay, including incomplete sessions and reviews."""
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

root = Path(__file__).resolve().parents[1]
folder = root / 'docs/assets/benchmarks/production-longhorizon-20261101'
data = json.loads((folder / 'chalk-results.json').read_text())
fig = plt.figure(figsize=(12, 4.8), facecolor='#f6f8fb')
grid = fig.add_gridspec(1, 2, left=.08, right=.96, top=.69, bottom=.23, wspace=.38, width_ratios=[1.0, 1.0])
ax, ax2 = (fig.add_subplot(grid[0, i]) for i in range(2))
for axis in (ax, ax2):
    axis.set_facecolor('#f6f8fb')
    for spine in axis.spines.values(): spine.set_visible(False)
    axis.tick_params(length=0, colors='#334155', labelsize=10)
fig.text(.08, .91, 'One new issue: three-session agent replay', fontsize=19, weight='bold', color='#0f172a')
fig.text(.08, .83, 'Chalk #690 · Claude Code · randomized arm order · historical public-issue replay', fontsize=10, color='#475569')

arms = data['arms']
for y, (arm, label, color) in enumerate((('baseline', 'Control', '#94a3b8'), ('memex', 'Memex', '#2563eb'))):
    outcome = arms[arm]['outcome']
    completed = outcome['sessionsCompleted'] if outcome else sum(s['responseCompleted'] for s in arms[arm]['stages'])
    ax.barh(y, completed, color=color, height=.45)
    verdict = ('PASS' if outcome['testExitCode'] == 0 else 'FAIL') if outcome else 'not available'
    ax.text(completed + .07, y, f'{completed}/3  ·  fixed check: {verdict}', va='center', color='#0f172a', fontsize=10)
ax.set_yticks([0, 1], ['Control', 'Memex']); ax.invert_yaxis(); ax.set_xlim(0, 4.9)
ax.set_xticks([0, 1, 2, 3]); ax.set_xlabel('Completed sessions', fontsize=9)
ax.set_title('Completion and investigator check', loc='left', fontsize=11, weight='bold', pad=16)
ax2.axis('off'); ax2.set_title('Blind AI assessments', loc='left', fontsize=11, weight='bold', pad=16)
ax2.text(0, .96, 'Reviewer', transform=ax2.transAxes, fontsize=9, weight='bold', color='#475569')
ax2.text(.52, .96, 'Control / Memex', transform=ax2.transAxes, fontsize=9, weight='bold', color='#475569')
for i, review in enumerate(data['reviews']):
    y = .72 - i * .25
    scores = review.get('scores', {})
    def show(key): return str(scores[key]) if scores.get(key) is not None else '—'
    name = {'gpt-6.1-sol': 'GPT', 'claude-haiku-4-5': 'Claude', 'adjudication': 'Adjudicator'}[review['reviewer']]
    ax2.text(0, y, name, transform=ax2.transAxes, fontsize=10, color='#334155')
    ax2.text(.52, y, f"{show('baseline')} / {show('memex')}", transform=ax2.transAxes, fontsize=10, weight='bold', color='#0f172a')
if all(arms[a]['outcome'] and arms[a]['outcome']['sessionsCompleted'] == 0 for a in arms):
    note = 'Both timed out before editing was enabled; 0/0 reviews rate empty artifacts, not an A/B effect.'
else:
    note = 'Incomplete sessions and missing ratings are retained. One selected issue cannot establish an A/B effect.'
fig.text(.08, .11, note, fontsize=9, color='#475569')
fig.text(.08, .065, 'One selected historical issue; its discussion includes a proposed fix. Checks are not the full suite or maintainer acceptance.', fontsize=9, color='#475569')
target = folder / 'chalk-replay.svg'
fig.savefig(target, format='svg', facecolor=fig.get_facecolor())
target.write_text('\n'.join(line.rstrip() for line in target.read_text().splitlines()) + '\n')
fig.savefig(target.with_suffix('.png'), dpi=150, facecolor=fig.get_facecolor())
