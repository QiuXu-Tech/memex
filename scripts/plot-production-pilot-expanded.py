#!/usr/bin/env python3
"""Draw explicitly provisional figures from the public pilot aggregate."""
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter, MaxNLocator
p=Path(__file__).resolve().parent.parent/'docs/assets/benchmarks/production-pilot-expanded';d=json.loads((p/'aggregate.json').read_text());arms=d['arms'];keys=['recent_summary','keyword_archive','pager_only','pager_tools_readonly','pager_tools_write'];labels=['Recent + summary','Keyword search','Automatic pager','Pager + read tools','Pager + write tools'];bg='#f6f7f8';ink='#142b3a';muted='#526a78'
n=d['tasks']
fig,ax=plt.subplots(figsize=(12.2,9));fig.patch.set_facecolor(bg);ax.set_facecolor(bg);fig.text(.075,.95,'Blind machine review: exploratory replay',fontsize=20,weight='bold',color=ink);fig.text(.075,.91,f'{n} historical questions · separately evaluated model judges',fontsize=10.5,color=muted)
models=[('gpt-6-astra','Astra','#355e8d'),('deepseek-flash','DeepSeek','#a3b7c6')]
if d['reviews'].get('replacementReceived',0):models.append(('gpt-6.1-sol','Sol (post hoc)','#2e8e90'))
ys=[];names=[];values=[];colors=[];unknown=[]
for i,k in enumerate(keys):
 for j,(model,short,color) in enumerate(models):
  ys.append(i*(len(models)+1)+j);names.append(labels[i]+' · '+short);values.append(arms[k]['machineCorrectnessScores'][model].get('2',0));unknown.append(arms[k]['machineCorrectnessScores'][model].get('UNKNOWN',0));colors.append(color)
ax.barh(ys,values,height=.68,color=colors);ax.set_yticks(ys,names);ax.invert_yaxis();ax.set_xlim(0,n+1);ax.set_xticks(range(0,n+1,max(1,n//4)));ax.set_xlabel('Machine reviewer correctness rating 2 (not human-verified success)',color=muted);ax.spines[['top','right','left']].set_visible(False);ax.spines['bottom'].set_color('#cad1d8');ax.tick_params(axis='y',length=0,labelsize=9);ax.grid(axis='x',color='#dbe1e6');ax.set_axisbelow(True)
for yy,v,u in zip(ys,values,unknown):ax.text(v+.06,yy,f'{v}/{n} · {u} unknown',va='center',fontsize=9,color=ink)
fig.text(.075,.105,'Scores are model opinions against clipped evidence; UNKNOWN includes missing or invalid ratings.',fontsize=9,color=muted);fig.text(.075,.07,'Missing and invalid ratings remain unknown; this small replay does not establish a production effect.',fontsize=9,color=muted);fig.subplots_adjust(left=.31,right=.96,top=.84,bottom=.19)
fig.savefig(p.parent/'production-pilot-expanded-machine-review.png',dpi=160,facecolor=bg);plt.close(fig)
fig,axes=plt.subplots(1,2,figsize=(13.6,6.3));fig.patch.set_facecolor(bg);fig.text(.065,.93,'Pilot instrumentation: usage and tool behavior',fontsize=20,weight='bold',color=ink);fig.text(.065,.875,'Reported tokens and observed calls; billed cost and verified task success are unknown',fontsize=10,color=muted)
ax=axes[0];ins=[arms[k]['gatewayUsage'].get('promptTokens',0) for k in keys];outs=[arms[k]['gatewayUsage'].get('completionTokens',0) for k in keys];ax.barh(range(5),ins,color='#355e8d',label='Prompt');ax.barh(range(5),outs,left=ins,color='#2e8e90',label='Completion');ax.set_yticks(range(5),labels);ax.invert_yaxis();ax.set_xlabel(f'Gateway-reported tokens across {n} runs');ax.set_title('Task runs (reviews excluded)',loc='left',weight='bold');ax.xaxis.set_major_locator(MaxNLocator(nbins=5));ax.xaxis.set_major_formatter(FuncFormatter(lambda value,pos: f'{value/1000:,.0f}k' if value else '0'));ax.legend(frameon=False,fontsize=9)
ax=axes[1];au=d['autonomyObserved'];values=[sum(x['preQuestionWrites']>0 for x in au),sum(x['pagerIncludedOwnWrittenRecord'] for x in au),sum(x['answerSearchCalls']>0 for x in au),sum(x['answerOpens']>0 for x in au),sum(x['openedOwnWrittenRecord'] for x in au)];labs=['Wrote before question','Pager included own write','Searched after question','Opened after question','Opened own prior write'];ax.barh(range(5),values,color=['#a3b7c6','#86a4b5','#6d93ac','#427a8c','#2e8e90'],height=.58);ax.set_yticks(range(5),labs);ax.invert_yaxis();ax.set_xlim(0,n+1);ax.set_xticks(range(0,n+1,max(1,n//4)));ax.set_xlabel(f'Write-enabled runs (out of {n})');ax.set_title('Observed memory actions',loc='left',weight='bold')
for i,v in enumerate(values):ax.text(v+.08,i,f'{v}/{n}',va='center',fontsize=10,weight='bold',color=ink)
for ax in axes:ax.set_facecolor(bg);ax.spines[['top','right','left']].set_visible(False);ax.spines['bottom'].set_color('#cad1d8');ax.tick_params(axis='y',length=0,labelsize=9);ax.grid(axis='x',color='#dbe1e6');ax.set_axisbelow(True)
fig.text(.065,.095,'Token usage is not a bill; cached tokens may be included in prompt counts. Setup and reviewer calls are reported separately.',fontsize=9,color=muted);fig.text(.065,.06,'Tool calls alone do not establish necessary, faithful, or production-safe memory management.',fontsize=9,color=muted);fig.subplots_adjust(left=.18,right=.97,top=.75,bottom=.23,wspace=.78)
fig.savefig(p.parent/'production-pilot-expanded-usage.png',dpi=160,facecolor=bg)
print('pilot figures written')
