#!/usr/bin/env python3
"""Plot anonymous machine-judged historical replay aggregate."""
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

base = Path(__file__).resolve().parent.parent / 'docs/assets/benchmarks'
data = json.loads((base / 'pager-replay-aggregate.json').read_text())
c = data['machineJudgement']['validPairResults']; n = c['complete']
labels = ['Rule wins in both orders', 'Hybrid wins in both orders', 'Tie in both orders', 'Result changes with order']
values = [c.get('stable_rule', 0), c.get('stable_hybrid', 0), c.get('stable_tie', 0), c.get('order_conflict', 0)]
fig, ax = plt.subplots(figsize=(11, 5.5))
fig.patch.set_facecolor('#f6f7f8'); ax.set_facecolor('#f6f7f8')
fig.text(.075, .9, 'Historical replay: machine-judge stability', fontsize=21, weight='bold', color='#142b3a')
fig.text(.075, .835, f'One session · 10 questions · 2 answer models · {n} valid pairs', fontsize=11, color='#526a78')
ax.barh(range(4), values, color=['#355e8d', '#2e8e90', '#9ab6be', '#ca775b'], height=.56)
ax.set_yticks(range(4), labels); ax.invert_yaxis(); ax.set_xlim(0, max(n, max(values) + 2)); ax.set_xlabel('Valid question × model pairs', color='#526a78')
ax.spines[['top','right','left']].set_visible(False);ax.spines['bottom'].set_color('#cad1d8');ax.tick_params(axis='y', length=0, labelsize=11, colors='#263746');ax.tick_params(axis='x', colors='#627382');ax.grid(axis='x',color='#dbe1e6',linewidth=.7);ax.set_axisbelow(True)
for i, value in enumerate(values): ax.text(value + .15, i, f'{value}/{n}', va='center', fontsize=11, weight='bold', color='#213745')
fig.text(.075, .11, 'GPT-6 Astra judged both presentation orders; reference excerpts were clipped. This is machine judgement, not human annotation.', fontsize=9.5, color='#526a78')
excluded = data['answerSettings']['possiblePairs'] - n
fig.text(.075, .07, f'{excluded} of {data["answerSettings"]["possiblePairs"]} pairs excluded because at least one answer was empty. A single session is not a production benchmark.', fontsize=9.5, color='#526a78')
fig.subplots_adjust(left=.31, right=.96, top=.74, bottom=.23)
out = base / 'pager-replay-judgement.png'; fig.savefig(out, dpi=160, facecolor=fig.get_facecolor()); print(out)
