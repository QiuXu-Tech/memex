#!/usr/bin/env python3
"""Draw the query-expansion diagnostics from the published aggregate."""
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
base=Path(__file__).resolve().parent.parent/'docs/assets/benchmarks'
d=json.loads((base/'pager-semantic/aggregate.json').read_text())
fig,axes=plt.subplots(1,2,figsize=(13.6,6.5));fig.patch.set_facecolor('#f6f7f8')
fig.text(.06,.92,'Pager query expansion: paired diagnostics',fontsize=21,weight='bold',color='#142b3a')
fig.text(.06,.86,'10 seeded store layouts · 12 handcrafted questions reused across seeds',fontsize=10.5,color='#526a78')
for ax,policy in zip(axes,['rule','hybrid']):
 vals=[d['synonym']['conditions'][f'before-{policy}']['fact'],d['synonym']['conditions'][f'after-default-{policy}']['fact'],d['synonym']['conditions'][f'after-expanded-{policy}']['fact']];total=d['synonym']['probes'];labels=['Previous pager','New pager, no rewrite','New pager + model rewrite']
 ax.set_facecolor('#f6f7f8');ax.barh(range(3),vals,color=['#9db0c3','#728da3','#2e8e90'],height=.55);ax.set_yticks(range(3),labels);ax.invert_yaxis();ax.set_xlim(0,total*1.13);ax.set_xlabel('Target fact present in window',color='#526a78');ax.set_title(policy.capitalize(),loc='left',fontsize=13,weight='bold',color='#203846');ax.spines[['top','right','left']].set_visible(False);ax.spines['bottom'].set_color('#cad1d8');ax.tick_params(axis='y',length=0,labelsize=10);ax.grid(axis='x',color='#dbe1e6',linewidth=.7);ax.set_axisbelow(True)
 for i,v in enumerate(vals):ax.text(v+2,i,f'{v}/{total}',va='center',fontsize=10,weight='bold',color='#213745')
fig.text(.06,.11,'The 120 observations reuse the same 12 questions; seeded layouts are not independent tasks. No human labels.',fontsize=9,color='#526a78')
fig.text(.06,.075,'Rewrites were generated once from each question by a hosted model. This does not estimate production accuracy or cost savings.',fontsize=9,color='#526a78')
fig.subplots_adjust(left=.19,right=.96,top=.74,bottom=.25,wspace=.75)
out=base/'pager-semantic-comparison.png';fig.savefig(out,dpi=160,facecolor=fig.get_facecolor());print(out)
