#!/usr/bin/env python3
"""Render the single-issue canary status from the published aggregate."""
import json,pathlib
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
root=pathlib.Path(__file__).resolve().parent.parent
r=json.loads((root/'docs/assets/benchmarks/production-prospective-canary/results.json').read_text())
original=sum(x['originalTestStatus']!='NOT_RUN' for x in r['candidateResults']);posthoc=sum(x['posthocTestStatus']=='PASS' for x in r['candidateResults']);reviews=[x for x in r['trialCalls'] if x['stage'].startswith('review:')]
fig,axes=plt.subplots(1,2,figsize=(12,4.8),gridspec_kw={'width_ratios':[1.1,1]});fig.patch.set_facecolor('#f7f8fa')
for ax in axes:ax.set_facecolor('#f7f8fa');ax.spines[['top','right']].set_visible(False)
ax=axes[0];bars=ax.barh(['Post-hoc: tests passed','Registered: tests executed'],[posthoc,original],color=['#4b6ea8','#c17458'],height=.46);ax.set_xlim(0,3.6);ax.set_xticks([0,1,2,3]);ax.set_xlabel('Number of candidates (out of 3)');ax.set_title('One selected issue, three conditions',loc='left',weight='bold');
for bar,val in zip(bars,[posthoc,original]):ax.text(val+.08,bar.get_y()+bar.get_height()/2,f'{val}/3',va='center',weight='bold')

ax=axes[1];groups=['DeepSeek','Astra'];side=[sum(x.get('sideEffects')==1 for x in reviews if x['model']=='deepseek-flash'),sum(x.get('sideEffects')==2 for x in reviews if x['model']=='gpt-6-astra')];bars=ax.bar(groups,side,color=['#dc9c5a','#5d8eaa'],width=.52);ax.set_ylim(0,3.8);ax.set_yticks([0,1,2,3]);ax.set_ylabel('Same side-effect score across 3 reviews');ax.set_title('AI reviewers disagreed on risk',loc='left',weight='bold');
for bar,score in zip(bars,['1 / 2','2 / 2']):ax.text(bar.get_x()+bar.get_width()/2,bar.get_height()+.08,score,ha='center',weight='bold')
fig.suptitle('Exploratory canary: process check, not production evidence',x=.07,ha='left',fontsize=15,weight='bold');fig.text(.07,.015,'One manually selected issue • no verified task improvement • machine review, not human labels',fontsize=9,color='#475569');fig.tight_layout(rect=[0,.12,1,.93]);fig.savefig(root/'docs/assets/benchmarks/production-prospective-canary.png',dpi=180,bbox_inches='tight');plt.close(fig)
