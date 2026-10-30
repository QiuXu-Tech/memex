#!/usr/bin/env python3
"""Plot checked-in synthetic pager comparisons; no private replay data."""
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

base = Path(__file__).resolve().parent.parent / 'docs/assets/benchmarks'
datasets = [json.loads((base / x / 'aggregate.json').read_text()) for x in ('pager-10m', 'pager-10m-node24')]
fig, axes = plt.subplots(1, 2, figsize=(13.6, 6.6))
fig.patch.set_facecolor('#f6f7f8')
fig.text(.065, .92, '10M archive: retrieval and materialization', fontsize=22, weight='bold', color='#142b3a')
fig.text(.065, .862, 'Two runtime cohorts · 5 seeds and 200 synthetic probes each · 1,800 estimated-token window', fontsize=11, color='#526a78')
labels = ['Separate search: hit@1', 'Pager contains target', 'Rule: fact in window', 'Hybrid: fact in window']
colors = ['#2e8e90', '#9ab6be', '#355e8d', '#ca775b']
for ax, data in zip(axes, datasets):
    ax.set_facecolor('#f6f7f8')
    ax.spines[['top', 'right', 'left']].set_visible(False)
    ax.spines['bottom'].set_color('#cad1d8')
    ax.tick_params(axis='y', length=0, labelsize=10.5, colors='#263746')
    ax.tick_params(axis='x', colors='#627382')
    ax.grid(axis='x', color='#dbe1e6', linewidth=.7)
    ax.set_axisbelow(True)
    metrics = data['metrics']['all']
    vals = [metrics['searchHit1'], metrics['conditions']['rule']['targetInCandidates'], metrics['conditions']['rule']['factPresent'], metrics['conditions']['hybrid']['factPresent']]
    ax.barh(range(4), vals, color=colors, height=.55)
    ax.set_yticks(range(4), labels)
    ax.invert_yaxis(); ax.set_xlim(0, 225); ax.set_xticks([0, 50, 100, 150, 200]); ax.set_xlabel('Probes out of 200', color='#526a78')
    for i, value in enumerate(vals): ax.text(value + 3, i, f'{value}/200', va='center', fontsize=10.5, weight='bold', color='#213745')
    ax.set_title(f"Node {data['environment']['node'].lstrip('v')}", loc='left', fontsize=13, weight='bold', pad=13, color='#203846')
fig.text(.065, .11, 'Synthetic exact-cue data; 20 resident + 20 nonresident probes per seed. Search results are not injected into the pager.', fontsize=9.5, color='#526a78')
fig.text(.065, .075, '10M is an assigned archive size, not model-tokenizer measurement. No answer model or human labels. Quiet gate not met.', fontsize=9.5, color='#526a78')
fig.subplots_adjust(left=.18, right=.965, top=.74, bottom=.25, wspace=.65)
out = base / 'pager-10m-comparison.png'
fig.savefig(out, dpi=160, facecolor=fig.get_facecolor())
print(out)
