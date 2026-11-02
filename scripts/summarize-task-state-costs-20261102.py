#!/usr/bin/env python3
"""Post-hoc paired client list-price totals, never gateway charges."""
import json
import pathlib
import sys

source, destination = map(pathlib.Path, sys.argv[1:3])
data = json.loads(source.read_text())
known = []
for task in data['tasks']:
    if not task['completePair']: continue
    values = {arm: [task['sessions'][f'{arm}-s{stage}']['clientListPriceUsd'] for stage in (1, 2, 3)] for arm in ('baseline', 'memex')}
    if any(not isinstance(price, (int, float)) or isinstance(price, bool) or price < 0 for prices in values.values() for price in prices): continue
    known.append({arm: sum(prices) for arm, prices in values.items()})
totals = {arm: round(sum(row[arm] for row in known), 6) for arm in ('baseline', 'memex')}
out = {'kind': 'post-hoc-paired-client-list-prices', 'completePairs': data['completePairs'], 'completePairsWithKnownClientPrices': len(known),
       'clientListPriceTotalsUsd': totals,
       'clientListPriceMeanPerCompletePairUsd': {arm: round(totals[arm] / len(known), 6) if known else None for arm in totals},
       'limits': ['These are agent-client list prices, not APIMaster wallet charges.',
                  'Pairs with any unknown client price are excluded from this paired comparison. All started-session known totals and missing charges are reported separately.',
                  'Model review calls, infrastructure and labor are not included.']}
destination.write_text(json.dumps(out, ensure_ascii=False, indent=2) + '\n');print(json.dumps(out))
