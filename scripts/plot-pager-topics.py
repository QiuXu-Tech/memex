#!/usr/bin/env python3
"""Plot a small synthetic topic diagnostic, not a human-labelled benchmark."""
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
base = Path(__file__).resolve().parent.parent / 'docs/assets/benchmarks'
d = json.loads((base / 'pager-recall/aggregate.json').read_text())['topicFixture']['groups']
keys = ['explicit-topic','paraphrase','lexical-disjoint']; labels = ['Explicit topic terms','Paraphrase with shared terms','Lexically disjoint synonyms']
counts = [d[k]['facts']['after-rule'] for k in keys]; totals = [d[k]['cases'] for k in keys]; perc = [100*n/t for n,t in zip(counts,totals)]
fig, ax = plt.subplots(figsize=(11,5.5)); fig.patch.set_facecolor('#f6f7f8'); ax.set_facecolor('#f6f7f8')
fig.text(.075,.9,'Natural-language diagnostic: lexical boundary',fontsize=21,weight='bold',color='#142b3a')
fig.text(.075,.835,'20 handcrafted synthetic questions · rule and hybrid had the same counts',fontsize=11,color='#526a78')
ax.barh(range(3),perc,color=['#2e8e90','#355e8d','#ca775b'],height=.55);ax.set_yticks(range(3),labels);ax.invert_yaxis();ax.set_xlim(0,112);ax.set_xticks([0,25,50,75,100]);ax.set_xlabel('Target fact present in materialized window (%)',color='#526a78')
ax.spines[['top','right','left']].set_visible(False);ax.spines['bottom'].set_color('#cad1d8');ax.tick_params(axis='y',length=0,labelsize=11,colors='#263746');ax.tick_params(axis='x',colors='#627382');ax.grid(axis='x',color='#dbe1e6',linewidth=.7);ax.set_axisbelow(True)
for i,(value,total) in enumerate(zip(counts,totals)):ax.text(perc[i]+1.5,i,f'{value}/{total}',va='center',fontsize=11,weight='bold',color='#213745')
fig.text(.075,.11,'Eight topics; four cold targets; 50 newer distractors. The previous pager returned 0/20 target facts.',fontsize=9.5,color='#526a78')
fig.text(.075,.07,'Small synthetic diagnostic; no answer model or human labels. Results are not estimates of production accuracy.',fontsize=9.5,color='#526a78')
fig.subplots_adjust(left=.32,right=.96,top=.74,bottom=.23)
out=base/'pager-topic-diagnostic.png';fig.savefig(out,dpi=160,facecolor=fig.get_facecolor());print(out)
