#!/usr/bin/env python3
"""Plot the post-hoc retry without treating it as an independent new issue."""
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

root = Path(__file__).resolve().parents[1]
folder = root / 'docs/assets/benchmarks/production-longhorizon-20261101'
data = json.loads((folder / 'chalk-retry-results.json').read_text())
fig = plt.figure(figsize=(15, 5.5), facecolor='#f6f8fb')
grid = fig.add_gridspec(1, 3, left=.06, right=.97, top=.69, bottom=.25, wspace=.42, width_ratios=[1.1, 1.05, .9])
axes = [fig.add_subplot(grid[0, i]) for i in range(3)]
for axis in axes:
    axis.set_facecolor('#f6f8fb')
    for spine in axis.spines.values(): spine.set_visible(False)
    axis.tick_params(length=0, colors='#334155', labelsize=9)
fig.text(.06, .91, 'Chalk #690: post-hoc agent retry', fontsize=19, weight='bold', color='#0f172a')
fig.text(.06, .83, 'Same historical issue after timeouts · fresh randomized workspaces · AI review', fontsize=10, color='#475569')
arms = data['arms']
colors = ['#94a3b8', '#2563eb']
ax = axes[0]
for y, (arm, color) in enumerate(zip(('baseline', 'memex'), colors)):
    outcome = arms[arm]['outcome']
    n = outcome['sessionsCompleted'] if outcome else sum(s['responseCompleted'] for s in arms[arm]['stages'])
    status = ('PASS' if outcome['testExitCode'] == 0 else 'FAIL') if outcome else 'unknown'
    ax.barh(y, n, color=color, height=.45)
    legacy = data.get('posthocCompatibility', {}).get('results', {}).get(arm, {}).get('exitCode')
    legacy_label = '\nlegacy assertion ' + ('PASS' if legacy == 0 else 'FAIL') if legacy is not None else ''
    ax.text(n + .07, y, f'{n}/3 · fixed {status}{legacy_label}', va='center', fontsize=9, color='#0f172a')
ax.set_yticks([0, 1], ['Control', 'Memex']); ax.invert_yaxis(); ax.set_xlim(0, 4.5); ax.set_xticks([0, 1, 2, 3])
ax.set_xlabel('Completed sessions', fontsize=9); ax.set_title('Completion and fixed check', loc='left', fontsize=11, weight='bold', pad=14)
ax = axes[1]
values = []
for arm in ('baseline', 'memex'):
    usage = arms[arm]['reportedUsage']; values.append(sum(usage[k] for k in ('input_tokens', 'cache_creation_input_tokens', 'cache_read_input_tokens')) / 1000)
ax.barh([0, 1], values, color=colors, height=.45)
ax.set_yticks([0, 1], ['Control', 'Memex']); ax.invert_yaxis()
ax.set_xlim(0, max(values + [1]) * 1.35)
for y, (arm, value) in enumerate(zip(('baseline', 'memex'), values)):
    suffix = '+' if arms[arm]['missingUsageSessions'] else ''
    ax.text(value + max(values + [1])*.03, y, f'{value:.1f}k{suffix}', va='center', fontsize=9, color='#0f172a')
ax.set_xlabel('Thousand input tokens, including cache', fontsize=9); ax.set_title('Reported model usage', loc='left', fontsize=11, weight='bold', pad=14)
ax = axes[2]; ax.axis('off'); ax.set_title('Blind AI scores', loc='left', fontsize=11, weight='bold', pad=14)
ax.text(0, .96, 'Reviewer', transform=ax.transAxes, fontsize=9, weight='bold', color='#475569')
ax.text(.55, .96, 'Control / Memex', transform=ax.transAxes, fontsize=9, weight='bold', color='#475569')
main = next(r for r in data['reviews'] if r['reviewer'] == 'gpt-6.1-sol')
extra = {r['role']: r for r in data['supplementalReviews']}
chosen = [(main, 'GPT'), (extra.get('second-supplemental-review', {}), 'DeepSeek*'), (extra.get('second-supplemental-adjudication', {}), 'Gemini*')]
for i, (review, name) in enumerate(chosen):
    y = .72 - i * .25; scores = review.get('scores', {})
    def show(key): return str(scores[key]) if scores.get(key) is not None else '—'
    ax.text(0, y, name, transform=ax.transAxes, fontsize=9, color='#334155')
    ax.text(.55, y, f"{show('baseline')} / {show('memex')}", transform=ax.transAxes, fontsize=10, weight='bold', color='#0f172a')
fig.text(.06, .14, 'Legacy assertion encodes the old behavior and may need updating; upstream tests were absent from the agent workspaces.', fontsize=9, color='#475569')
fig.text(.06, .10, '* Post-hoc DeepSeek/Gemini review: Claude was empty and Qwen truncated. One retried issue cannot establish a population effect.', fontsize=9, color='#475569')
fig.text(.06, .06, 'Advisory tool limits can be exceeded; fixed checks are not the full upstream suite or maintainer acceptance.', fontsize=9, color='#475569')
target = folder / 'chalk-retry.svg'
fig.savefig(target, format='svg', facecolor=fig.get_facecolor())
target.write_text('\n'.join(line.rstrip() for line in target.read_text().splitlines()) + '\n')
fig.savefig(target.with_suffix('.png'), dpi=150, facecolor=fig.get_facecolor())
