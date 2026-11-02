#!/usr/bin/env python3
"""Render the integrity follow-up figure from the reconciled JSON."""
import json
import pathlib
import sys
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

root = pathlib.Path(__file__).resolve().parent.parent
out = root / 'docs/assets/benchmarks/production-integrity-followup-20261102'
data = json.loads((out / 'results.json').read_text())
cohorts = [('Initial follow-up', data['firstEight']), ('Long-discussion follow-up', data['longFollowup'])]
cohorts = [(name, row) for name, row in cohorts if row.get('validRatedPairs', 0) > 0]
matplotlib.rcParams.update({'font.family': 'DejaVu Sans', 'svg.fonttype': 'none', 'font.size': 10})
fig, (ax, bx) = plt.subplots(1, 2, figsize=(12, 4.3), gridspec_kw={'width_ratios': [1.12, 1]})
fig.patch.set_facecolor('#f9fafc')
for axis in (ax, bx):
    axis.set_facecolor('#f9fafc')
    axis.spines[['top', 'right', 'left']].set_visible(False)
    axis.spines['bottom'].set_color('#d5dce4')
    axis.tick_params(axis='y', length=0)
    axis.tick_params(axis='x', colors='#56657a')
fig.text(.06, .94, 'Memex integrity follow-up', fontsize=19, fontweight='bold', color='#162840')
fig.text(.06, .885, 'Historical public-issue replay · anonymous AI review · descriptive counts', fontsize=10.5, color='#56657a')
y = np.arange(len(cohorts))
left = np.zeros(len(cohorts))
for key, label, color in [('baselineHigher', 'Control higher', '#d99043'), ('tie', 'Tie', '#aab8c8'), ('memexHigher', 'Memex higher', '#36a493')]:
    values = np.array([row.get('scoreDirections', {}).get(key, 0) for _, row in cohorts])
    bars = ax.barh(y, values, left=left, color=color, height=.42, label=label)
    for bar, value in zip(bars, values):
        if value: ax.text(bar.get_x() + bar.get_width()/2, bar.get_y()+bar.get_height()/2, str(value), ha='center', va='center', color='white', fontweight='bold')
    left += values
ax.set_yticks(y, [f'{name}\n(n={row["validRatedPairs"]} rated)' for name, row in cohorts])
ax.invert_yaxis()
ax.set_title('Adjudicated score comparison', loc='left', fontsize=11, fontweight='bold', pad=14)
ax.set_xlabel('Number of rated task pairs')
ax.set_xlim(0, max(left) * 1.1 if len(left) and max(left) else 1)
ax.xaxis.set_major_locator(matplotlib.ticker.MaxNLocator(integer=True, nbins=5))
ax.legend(loc='lower left', bbox_to_anchor=(0, -.43), frameon=False, ncol=3, fontsize=8)
for j, (arm, label, color) in enumerate([('baseline','Control','#d99043'), ('memex','Memex','#36a493')]):
    proportions=[]
    for _, row in cohorts:
        total=row.get('completePairs', 0)
        count=row.get('laterDiscussionExposure', {}).get(arm, {}).get('exposedLaterComment', 0)
        proportions.append(count/total if total else 0)
    bars=bx.barh(y+(j-.5)*.22, proportions, height=.19, label=label, color=color)
    for bar, (_,row), value in zip(bars,cohorts,proportions):
        count=row.get('laterDiscussionExposure', {}).get(arm, {}).get('exposedLaterComment', 0)
        bx.text(min(value+.025,1.04), bar.get_y()+bar.get_height()/2, f'{count}/{row.get("completePairs",0)}', va='center', fontsize=9, color='#24364b')
bx.set_yticks(y, [name for name,_ in cohorts])
bx.invert_yaxis()
bx.set_xlim(0,1.16)
bx.set_xticks([0,.25,.5,.75,1], ['0%','25%','50%','75%','100%'])
bx.set_title('Later discussion exposed in session 2', loc='left', fontsize=11, fontweight='bold', pad=14)
bx.set_xlabel('Share of completed pairs, post-hoc tool-output check')
bx.legend(loc='lower left', bbox_to_anchor=(0,-.43), frameon=False, ncol=2, fontsize=8)
fig.text(.06,.025,'Exposure is not proof of understanding or causal use. Different cohorts use different prompts and commits.', fontsize=8.5,color='#56657a')
fig.subplots_adjust(left=.19, right=.96, top=.72, bottom=.27, wspace=.68)
svg = out / 'integrity-followup.svg'
fig.savefig(svg, facecolor=fig.get_facecolor())
svg.write_text('\n'.join(line.rstrip() for line in svg.read_text().splitlines()) + '\n')
fig.savefig('/tmp/memex-integrity-followup-preview.png', dpi=160, facecolor=fig.get_facecolor())
