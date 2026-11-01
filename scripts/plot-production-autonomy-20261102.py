#!/usr/bin/env python3
"""Plot only measured, reconciled results from the two preregistered cohorts."""
import json,pathlib
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
import numpy as np
root=pathlib.Path(__file__).resolve().parent.parent
folder=root/'docs/assets/benchmarks/production-autonomy-20261102'
d=json.loads((folder/'results.json').read_text());names=['original','supplement'];labels=['Original protocol','Recovery protocol'];colors=['#2563eb','#0d9488']
fig=plt.figure(figsize=(14,8),facecolor='#f7f9fc');gs=fig.add_gridspec(2,2,left=.07,right=.96,top=.79,bottom=.14,hspace=.55,wspace=.32)
a=fig.add_subplot(gs[0,0]);b=fig.add_subplot(gs[0,1]);c=fig.add_subplot(gs[1,0]);e=fig.add_subplot(gs[1,1])
for ax in (a,b,c,e):
 ax.set_facecolor('#f7f9fc');ax.spines[['top','right','left']].set_visible(False);ax.spines['bottom'].set_color('#cbd5e1');ax.tick_params(length=0,labelsize=9,colors='#334155')
fig.text(.07,.94,'Memex: cross-session issue investigations',fontsize=20,weight='bold',color='#0f172a')
fig.text(.07,.895,'Two separately registered protocols · real public issues replayed in fresh agent sessions',fontsize=11,color='#475569')
fig.text(.07,.855,f"Snapshot: {d['generatedAt'][:19].replace('T',' ')} UTC · AI reviews are not human reviews",fontsize=9.5,color='#475569')
x=np.arange(4);width=.35;fields=['started','finished','completePairs','validRatedPairs'];ticks=['Started','Finished','Complete pairs','Valid AI ratings']
for j,n in enumerate(names):
 v=[d[n].get(k,0) for k in fields];bars=a.bar(x+(j-.5)*width,v,width,color=colors[j],label=labels[j])
 for z in bars:a.text(z.get_x()+z.get_width()/2,z.get_height()+.5,str(int(z.get_height())),ha='center',fontsize=8,color='#334155')
a.set_xticks(x,ticks,rotation=8);a.set_ylim(0,34);a.set_title('Task flow (30 registered in each cohort)',loc='left',fontweight='bold',fontsize=11);a.legend(frameon=False,fontsize=8,loc='upper right')
b.set_title('Blinded AI score comparison',loc='left',fontweight='bold',fontsize=11)
for i,n in enumerate(names):
 row=d[n];k=row.get('validRatedPairs',0);dirs=row.get('scoreDirections',{})
 if not k:b.text(.03,i,'Review pending or incomplete',transform=b.get_yaxis_transform(),va='center',fontsize=9,color='#475569');continue
 left=0
 for key,col,label in [('baselineHigher','#f97316','Control higher'),('tie','#94a3b8','Tie'),('memexHigher','#2563eb','Memex higher')]:
  value=dirs.get(key,0);b.barh(i,value,left=left,height=.42,color=col,label=label if i==0 else None)
  if value:b.text(left+value/2,i,str(value),ha='center',va='center',fontsize=9,color='white',weight='bold')
  left+=value
b.set_yticks(range(2),labels);b.invert_yaxis();b.set_xlabel('Comparable rated pairs',fontsize=9)
b.set_ylim(1.55,-.55);b.set_xlim(0,max(1,max(d[n].get('validRatedPairs',0) for n in names))*1.1)
if any(d[n].get('validRatedPairs',0) for n in names):b.legend(handles=[Patch(color='#f97316',label='Control higher'),Patch(color='#94a3b8',label='Tie'),Patch(color='#2563eb',label='Memex higher')],frameon=False,fontsize=8,loc='lower right')
c.set_title('Input tokens per complete pair',loc='left',fontweight='bold',fontsize=11)
row=d['original'];n=row.get('fullTokenPairs',0)
if n:
 values=[row['tokenTotals'][arm]['input']/n/1000 for arm in ('baseline','memex')]
 bars=c.barh(['Control','Memex'],values,color=['#94a3b8','#2563eb'],height=.5);c.invert_yaxis()
 for bar,v in zip(bars,values):c.text(v+max(values)*.02,bar.get_y()+bar.get_height()/2,f'{v:.1f}k',va='center',fontsize=9)
 c.set_xlim(0,max(values)*1.28);c.set_xlabel(f'Original cohort, n={n}; includes cache reads and writes',fontsize=8)
else:c.text(.04,.5,'No comparable token totals yet',transform=c.transAxes,fontsize=10,color='#475569')
e.set_title('Observed memory lifecycle',loc='left',fontweight='bold',fontsize=11)
y=np.arange(2);w=.33
for j,n in enumerate(names):
 row=d[n];v=[row.get('agentWrites',0),row.get('automaticCheckpoints',0)];bars=e.barh(y+(j-.5)*w,v,w,color=colors[j],label=labels[j])
 for bar in bars:e.text(bar.get_width()+.15,bar.get_y()+bar.get_height()/2,str(int(bar.get_width())),va='center',fontsize=8)
e.set_yticks(y,['Agent wrote ≥1 record','Stop hook saved ≥1 checkpoint']);e.invert_yaxis();e.set_xlim(0,max(5,max(d[n].get('agentWrites',0) for n in names)+3,max(d[n].get('automaticCheckpoints',0) for n in names)+3));e.set_xlabel('Tasks; categories can overlap',fontsize=9)
fig.text(.07,.055,'Historical triage, not live production or a verified code fix. Recovery-token totals may be unknown; client list price is not the gateway bill.',fontsize=9,color='#475569')
svg=folder/'autonomy-summary.svg';fig.savefig(svg,format='svg',facecolor=fig.get_facecolor())
svg.write_text('\n'.join(line.rstrip() for line in svg.read_text().splitlines())+'\n')
fig.savefig(folder/'autonomy-summary.png',dpi=150,facecolor=fig.get_facecolor())
print('wrote',folder/'autonomy-summary.svg')
