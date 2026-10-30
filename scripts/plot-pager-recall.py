#!/usr/bin/env python3
"""Plot paired synthetic pager results from the checked-in aggregate."""
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

base = Path(__file__).resolve().parent.parent / 'docs/assets/benchmarks'
data = json.loads((base / 'pager-recall/aggregate.json').read_text())
fig, axes = plt.subplots(1, 2, figsize=(13.6, 6.6))
fig.patch.set_facecolor('#f6f7f8')
fig.text(.065, .92, 'Pager recall: paired before and after', fontsize=22, weight='bold', color='#142b3a')
fig.text(.065, .86, 'Same 10M assigned-token synthetic stores · 5 seeds and 200 probes per runtime', fontsize=11, color='#526a78')
labels = ['Rule before', 'Rule after', 'Hybrid before', 'Hybrid after']
keys = ['before-rule', 'after-rule', 'before-hybrid', 'after-hybrid']
colors = ['#9db0c3', '#355e8d', '#a8c5c5', '#2e8e90']
for ax, key, title in zip(axes, ['node25','node24'], ['Node 25.9.0','Node 24.21.0']):
    group = data['cohorts'][key]; n = group['probes']; values = [group['conditions'][k]['fact'] for k in keys]
    ax.set_facecolor('#f6f7f8'); ax.spines[['top','right','left']].set_visible(False); ax.spines['bottom'].set_color('#cad1d8')
    ax.tick_params(axis='y', length=0, labelsize=11, colors='#263746');ax.tick_params(axis='x', colors='#627382');ax.grid(axis='x',color='#dbe1e6',linewidth=.7);ax.set_axisbelow(True)
    ax.barh(range(4), values, color=colors, height=.55);ax.set_yticks(range(4),labels);ax.invert_yaxis();ax.set_xlim(0,n*1.13);ax.set_xticks([0,50,100,150,200]);ax.set_xlabel('Target fact present in window',color='#526a78')
    for i, value in enumerate(values): ax.text(value+3,i,f'{value}/{n}',va='center',fontsize=11,weight='bold',color='#213745')
    ax.set_title(title,loc='left',fontsize=13,weight='bold',pad=13,color='#203846')
fig.text(.065,.11,'Exact-cue synthetic probes; 20 resident + 20 nonresident targets per seed. Both candidate retrieval and selection changed.',fontsize=9.5,color='#526a78')
fig.text(.065,.075,'10M is assigned token accounting, not model-tokenizer measurement. No answer model or human labels. Quiet gate not met.',fontsize=9.5,color='#526a78')
fig.subplots_adjust(left=.17,right=.965,top=.74,bottom=.25,wspace=.58)
out=base/'pager-recall-comparison.png';fig.savefig(out,dpi=160,facecolor=fig.get_facecolor());print(out)
