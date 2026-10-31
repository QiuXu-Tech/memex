#!/usr/bin/env python3
"""Draw explicitly incomplete assignment outcomes from the sanitized ledger."""
import html,json,pathlib
root=pathlib.Path(__file__).resolve().parent.parent
path=root/'docs/assets/benchmarks/production-prospective-agent-batches/aggregate.json'
data=json.loads(path.read_text()); labels={'eslint-1':'ESLint initial','lodash-interrupted':'Lodash interrupted','lodash-repair':'Lodash search repair','eslint-2':'ESLint additional','lodash-model-check':'Lodash alternate model','mixed-3':'Pino + Prettier','prettier-4':'Prettier follow-up','eslint-3':'ESLint suggestions','mixed-4':'ESLint + Prettier','prettier-interrupted':'Prettier interrupted','prettier-route':'Prettier alternate route'}
colors={'PASS':'#3d8c78','CHECKS_NONZERO':'#c66f5e','INCOMPLETE':'#c89b58','UNKNOWN':'#8d87a2','NOT_RUN':'#c9d1d5'}
parts=['<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="900" viewBox="0 0 1200 900" role="img" aria-labelledby="title desc">','<title id="title">Agent instrumentation outcomes by batch</title>','<desc id="desc">Assigned task-arm slots grouped into passed checks with complete final, nonzero checks, incomplete response, unknown or interrupted, and not run. These small batches do not demonstrate production impact.</desc>','<rect width="1200" height="900" fill="#f7f8fa"/>','<text x="52" y="53" font-family="Arial,sans-serif" font-size="28" font-weight="700" fill="#19313e">Real-issue agent instrumentation · incomplete study</text>','<text x="52" y="84" font-family="Arial,sans-serif" font-size="15" fill="#526a78">Assigned task–arm slots by registration; re-registered unstarted slots appear more than once</text>']
for i,batch in enumerate(data['batches']):
 y=120+i*58;c=batch['outcomes'];values=[('PASS',c.get('PASS',0)),('CHECKS_NONZERO',c.get('CHECKS_NONZERO',0)),('INCOMPLETE',c.get('INCOMPLETE',0)),('UNKNOWN',c.get('UNKNOWN',0)+c.get('INTERRUPTED',0)),('NOT_RUN',c.get('NOT_RUN',0))]
 parts.append(f'<text x="52" y="{y+25}" font-family="Arial,sans-serif" font-size="17" fill="#19313e">{html.escape(labels[batch["batch"]])}</text>');x=310
 for key,value in values:
  if value:
   w=value*70;parts.append(f'<rect x="{x}" y="{y}" width="{w}" height="36" fill="{colors[key]}"/>');parts.append(f'<text x="{x+w/2}" y="{y+25}" text-anchor="middle" font-family="Arial,sans-serif" font-size="17" font-weight="700" fill="{ "#19313e" if key=="NOT_RUN" else "white"}">{value}</text>');x+=w
 parts.append(f'<text x="{x+14}" y="{y+25}" font-family="Arial,sans-serif" font-size="15" fill="#526a78">{batch["plannedAssignments"]} assigned</text>')
legend=[('PASS','Complete + checks pass'),('CHECKS_NONZERO','Checks nonzero'),('INCOMPLETE','Incomplete'),('UNKNOWN','Unknown / interrupted'),('NOT_RUN','Not run')]
x=52
for key,label in legend:
 parts.append(f'<rect x="{x}" y="785" width="14" height="14" fill="{colors[key]}"/>');parts.append(f'<text x="{x+20}" y="797" font-family="Arial,sans-serif" font-size="13" fill="#344e5c">{html.escape(label)}</text>');x+=len(label)*7+65
parts.append('<text x="52" y="860" font-family="Arial,sans-serif" font-size="14" fill="#526a78">A passed check is not project acceptance. Small, post-observation batches do not show production impact.</text>');parts.append('</svg>')
(root/'docs/assets/benchmarks/production-prospective-agent-outcomes.svg').write_text('\n'.join(parts)+'\n')
