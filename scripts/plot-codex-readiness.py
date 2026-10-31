#!/usr/bin/env python3
"""Draw the observed Codex integration attempts, including failures."""
import html
import json
from pathlib import Path

root = Path(__file__).resolve().parent.parent
data = json.loads((root / 'docs/assets/benchmarks/codex-readiness-smoke.json').read_text())
labels = [
    ('Write in read-only check', 'DENIED', '#af5a50'),
    ('Read with invalid fixture', 'INVALID FIXTURE', '#a87529'),
    ('Read with corrected fixture', 'READ + SCOPE VERIFIED', '#397d6d'),
    ('Writable workspace cycle', 'SCRIPTED WRITE + READ', '#397d6d'),
]
assert len(labels) == len(data['attempts'])
parts = [
    '<svg xmlns="http://www.w3.org/2000/svg" width="1050" height="410" viewBox="0 0 1050 410" role="img" aria-labelledby="title desc">',
    '<title id="title">Codex integration smoke attempts</title>',
    '<desc id="desc">Four synthetic checks include a denied write, invalid test data, a corrected scope read, and a scripted write-search-open cycle. No production A/B or autonomous lifecycle was completed.</desc>',
    '<rect width="1050" height="410" fill="#f7f8fa"/>',
    '<text x="38" y="44" font-family="Arial,sans-serif" font-size="24" font-weight="700" fill="#19313e">Codex integration checks</text>',
    '<text x="38" y="73" font-family="Arial,sans-serif" font-size="14" fill="#526a78">Four synthetic attempts · same model · failures retained</text>',
    '<text x="39" y="110" font-family="Arial,sans-serif" font-size="13" font-weight="700" fill="#526a78">ATTEMPT</text>',
    '<text x="370" y="110" font-family="Arial,sans-serif" font-size="13" font-weight="700" fill="#526a78">RESULT</text>',
    '<text x="775" y="110" font-family="Arial,sans-serif" font-size="13" font-weight="700" fill="#526a78">INPUT / OUTPUT TOKENS</text>',
]
for i, ((label, outcome, color), row) in enumerate(zip(labels, data['attempts'])):
    y = 126 + i * 54
    parts.append(f'<text x="39" y="{y+23}" font-family="Arial,sans-serif" font-size="15" fill="#19313e">{i+1}. {html.escape(label)}</text>')
    parts.append(f'<rect x="370" y="{y}" width="330" height="32" rx="5" fill="{color}"/>')
    parts.append(f'<text x="535" y="{y+21}" text-anchor="middle" font-family="Arial,sans-serif" font-size="13" font-weight="700" fill="#fff">{outcome}</text>')
    parts.append(f'<text x="775" y="{y+22}" font-family="Arial,sans-serif" font-size="14" fill="#19313e">{row["inputTokens"]:,} / {row["outputTokens"]:,}</text>')
parts += [
    '<text x="39" y="373" font-family="Arial,sans-serif" font-size="14" fill="#526a78">No production task pair or autonomous write-read lifecycle was completed; actual cost is unknown.</text>',
    '</svg>',
]
(root / 'docs/assets/benchmarks/codex-readiness-smoke.svg').write_text('\n'.join(parts) + '\n')
