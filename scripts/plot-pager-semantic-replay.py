#!/usr/bin/env python3
"""Draw the private-session replay machine-judge aggregate."""
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator
base=Path(__file__).resolve().parent.parent/'docs/assets/benchmarks'
d=json.loads((base/'pager-semantic/replay-aggregate.json').read_text());c=d['machineJudgement']['validPairResults'];n=c['complete']
labels=['Previous rule wins in both orders','Expanded rule wins in both orders','Tie in both orders','Unknown in both orders','Result changes with answer order'];keys=['stable_rule','stable_hybrid','stable_tie','stable_unknown','order_conflict'];values=[c.get(k,0) for k in keys]
fig,ax=plt.subplots(figsize=(11.5,5.5));fig.patch.set_facecolor('#f6f7f8');ax.set_facecolor('#f6f7f8');fig.text(.07,.9,'Historical replay: paired machine judgement',fontsize=20,weight='bold',color='#142b3a');fig.text(.07,.835,f'One session · 10 questions · 2 answer models · {n} valid pairs',fontsize=10.5,color='#526a78')
ax.barh(range(5),values,color=['#355e8d','#2e8e90','#9ab6be','#b4b8bd','#ca775b'],height=.56);ax.set_yticks(range(5),labels);ax.invert_yaxis();ax.set_xlim(0,max(n,max(values,default=0)+2));ax.set_xlabel('Valid question × model pairs',color='#526a78');ax.xaxis.set_major_locator(MaxNLocator(integer=True));ax.spines[['top','right','left']].set_visible(False);ax.spines['bottom'].set_color('#cad1d8');ax.tick_params(axis='y',length=0,labelsize=10);ax.grid(axis='x',color='#dbe1e6',linewidth=.7);ax.set_axisbelow(True)
for i,v in enumerate(values):ax.text(v+.15,i,f'{v}/{n}',va='center',fontsize=10,weight='bold',color='#213745')
fig.text(.07,.11,'GPT-6 Astra judged both answer orders against clipped reference excerpts; this is not human annotation.',fontsize=9,color='#526a78');fig.text(.07,.07,'One reconstructed session is not a production benchmark. Pair outcomes can depend on answer order.',fontsize=9,color='#526a78');fig.subplots_adjust(left=.35,right=.96,top=.74,bottom=.23)
out=base/'pager-semantic-replay.png';fig.savefig(out,dpi=160,facecolor=fig.get_facecolor());print(out)
