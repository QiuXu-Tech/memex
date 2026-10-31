#!/usr/bin/env python3
"""Render honest screening counts as a dependency-free SVG."""
import json,pathlib,collections
root=pathlib.Path(__file__).resolve().parent.parent
rows=json.loads((root/'docs/assets/benchmarks/production-prospective-canary/issue-audit.json').read_text())['rows']
counts=collections.Counter('excluded' if x['disposition'].startswith('EXCLUDE') else 'pending' for x in rows)
assert sum(counts.values())==len(rows)
svg=f'''<svg xmlns="http://www.w3.org/2000/svg" width="960" height="420" viewBox="0 0 960 420" role="img" aria-labelledby="title desc">
<title id="title">Prospective candidate screening status</title>
<desc id="desc">{counts['excluded']} issues excluded and {counts['pending']} pending among {len(rows)} issues checked. No 30-task randomized results yet.</desc>
<rect width="960" height="420" fill="#f7f8fa"/>
<text x="58" y="58" font-family="Arial, sans-serif" font-size="28" font-weight="700" fill="#142b3a">Prospective candidate screening</text>
<text x="58" y="94" font-family="Arial, sans-serif" font-size="16" fill="#526a78">{len(rows)} issues checked for current status · eligibility review ongoing</text>
<text x="58" y="171" font-family="Arial, sans-serif" font-size="18" fill="#142b3a">Excluded after audit</text>
<rect x="300" y="142" width="{counts['excluded']*20}" height="42" rx="5" fill="#c17458"/>
<text x="{310+counts['excluded']*20}" y="171" font-family="Arial, sans-serif" font-size="18" font-weight="700" fill="#142b3a">{counts['excluded']}</text>
<text x="58" y="243" font-family="Arial, sans-serif" font-size="18" fill="#142b3a">Pending acceptance audit</text>
<rect x="300" y="214" width="{counts['pending']*20}" height="42" rx="5" fill="#6486a4"/>
<text x="{310+counts['pending']*20}" y="243" font-family="Arial, sans-serif" font-size="18" font-weight="700" fill="#142b3a">{counts['pending']}</text>
<line x1="300" x2="800" y1="286" y2="286" stroke="#aebbc5"/>
<text x="58" y="346" font-family="Arial, sans-serif" font-size="16" fill="#526a78">Pending does not mean eligible. No 30-task randomized results yet.</text>
</svg>'''
(root/'docs/assets/benchmarks/production-prospective-screening.svg').write_text(svg+'\n')
