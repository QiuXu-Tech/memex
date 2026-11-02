#!/usr/bin/env python3
"""Plot independently reconciled three-session replay results as an SVG."""
import json
import pathlib
import sys

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter, MaxNLocator

source, destination = map(pathlib.Path, sys.argv[1:3])
data = json.loads(source.read_text())
rescue = json.loads(pathlib.Path(sys.argv[4]).read_text()) if len(sys.argv) > 4 else None
plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 10, 'svg.fonttype': 'none', 'svg.hashsalt': 'memex-task-state-20261102'})
fig, axes = plt.subplots(2, 2, figsize=(13, 7.6))
fig.patch.set_facecolor('#f8fafc')
for ax in axes.flat:
    ax.set_facecolor('#ffffff')
    for spine in ax.spines.values(): spine.set_visible(False)
    ax.grid(axis='x', color='#e5eaf0', linewidth=.8)
    ax.set_axisbelow(True)
    ax.xaxis.set_major_locator(MaxNLocator(integer=True))

flow_labels = ['Registered', 'Started', 'Complete pairs', 'Primary valid ratings']
flow_values = [data['registered'], data['started'], data['completePairs'], data['validRatedPairs']]
score_labels = ['Control higher', 'Tied', 'Memex higher']
score_values = [data['scoreDirections'][x] for x in ('baselineHigher', 'tie', 'memexHigher')]
started = [row for row in data['tasks'] if row.get('started') and row.get('memory')]
memory_labels = ['Agent wrote in session 1/2', 'Agent record opened later', 'Checkpoint recalled later', 'Checkpoint opened later']
memory_values = [sum(bool(row['memory'][key]) for row in started) for key in ('agentSuccessfulWrites', 'agentWriteThenSuccessfulOpen', 'automaticCheckpointThenRecall', 'automaticCheckpointThenSuccessfulOpen')]

def bars(ax, labels, values, colors, title, denominator):
    positions = list(range(len(labels)))
    ax.barh(positions, values, color=colors, height=.6)
    ax.set_yticks(positions, labels); ax.invert_yaxis(); ax.set_title(title, loc='left', weight='bold', pad=10)
    maximum = max([denominator, *values, 1]); ax.set_xlim(0, maximum * 1.18)
    for i, value in enumerate(values): ax.text(value + maximum * .018, i, str(value), va='center', color='#263445', weight='bold')
    ax.set_xlabel('Tasks')

bars(axes[0, 0], flow_labels, flow_values, ['#b8c5d6', '#8397b0', '#4e739b', '#24547c'], 'Trial completion', data['registered'])
if rescue:
    ax = axes[0, 1]; positions = list(range(len(score_labels)))
    sensitivity = [rescue['postHocScoreDirections'][x] for x in ('baselineHigher', 'tie', 'memexHigher')]
    ax.barh([i - .18 for i in positions], score_values, height=.31, color='#547aa2', label=f"Primary (n={data['validRatedPairs']})")
    ax.barh([i + .18 for i in positions], sensitivity, height=.31, color='#38a38f', label=f"Post-hoc (n={rescue['postHocValidRatedPairs']})")
    ax.set_yticks(positions, score_labels); ax.invert_yaxis(); ax.set_xlim(0, rescue['postHocValidRatedPairs'] * 1.18)
    ax.set_title('Final AI blind ratings', loc='left', weight='bold', pad=10); ax.set_xlabel('Tasks')
    for i, (first, second) in enumerate(zip(score_values, sensitivity)):
        ax.text(first + .4, i - .18, str(first), va='center', color='#263445', weight='bold')
        ax.text(second + .4, i + .18, str(second), va='center', color='#263445', weight='bold')
    ax.legend(loc='lower right', frameon=False, fontsize=8)
else:
    bars(axes[0, 1], score_labels, score_values, ['#d78064', '#c2cbd3', '#38a38f'], f"Final AI blind ratings (n={data['validRatedPairs']})", data['validRatedPairs'])
bars(axes[1, 0], memory_labels, memory_values, ['#6d86ad', '#476d98', '#80b7ad', '#31967f'], f'Observed memory activity (n={len(started)} started)', len(started))
ax = axes[1, 1]; n = data['verifiedTokenPairs']; tokens = data['verifiedTokens']
ax.set_title(f'Verified input tokens (n={n} complete pairs)', loc='left', weight='bold', pad=10)
if n:
    values = [tokens[arm]['input'] / n for arm in ('baseline', 'memex')]
    ax.barh([0, 1], values, color=['#8397b0', '#38a38f'], height=.6)
    ax.set_yticks([0, 1], ['Control', 'Memex']); ax.invert_yaxis(); ax.set_xlabel('Mean input tokens per pair, including cache')
    ax.xaxis.set_major_locator(MaxNLocator(nbins=5))
    ax.xaxis.set_major_formatter(FuncFormatter(lambda value, _: f'{value / 1000:,.0f}k'))
    ax.set_xlim(0, max(values) * 1.22 if max(values) else 1)
    for i, value in enumerate(values): ax.text(value + max(values) * .02, i, f'{value:,.0f}', va='center', weight='bold', color='#263445')
else:
    ax.set_yticks([]); ax.set_xticks([]); ax.text(.5, .5, 'No fully reconciled token pairs', transform=ax.transAxes, ha='center', va='center', color='#526273')
fig.suptitle('Memex: three-session historical issue replay', x=.06, y=.985, ha='left', fontsize=17, weight='bold', color='#152a3e')
fig.text(.06, .035, 'Public issue triage, not deployed production work. AI ratings are not human review; memory calls do not prove causal use.', fontsize=9, color='#526273')
fig.text(.06, .012, f"Memex source commit {data['memexCommit'][:12]} · failures and missing usage remain in the linked results", fontsize=8.5, color='#617284')
fig.tight_layout(rect=(.035, .075, .985, .94), h_pad=2.5, w_pad=3)
destination.parent.mkdir(parents=True, exist_ok=True)
fig.savefig(destination, format='svg', facecolor=fig.get_facecolor(), metadata={'Date': None})
destination.write_text('\n'.join(line.rstrip() for line in destination.read_text().splitlines()) + '\n')
if len(sys.argv) > 3:
    fig.savefig(pathlib.Path(sys.argv[3]), format='png', dpi=130, facecolor=fig.get_facecolor())
