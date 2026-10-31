#!/usr/bin/env python3
"""Four additional issue pairs with bounded excess-tool responses."""
import importlib.util
import pathlib

import prospective_agent_v28 as agent

REPO = pathlib.Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location('pilot_v27', REPO / 'scripts/prospective-gateway-pilot-v27.py')
previous = importlib.util.module_from_spec(spec)
spec.loader.exec_module(previous)
pilot = previous.pilot
pilot.TASKS = {'432': 'qs', '7350': 'express', '581': 'cheerio', '3620': 'mathjs'}
pilot.SEED = 2026103133
pilot.BASES = {p: f'/opt/memex-pilot/workspaces/{p}-base' for p in pilot.TASKS.values()}
pilot.COMMITS = {'qs': '43baea4655cb9b543fb1c5cc0db95cde42852140',
                 'express': '1c6f1b0fe4000977b9a7b4f34097e4d527dd9824',
                 'cheerio': '70b0dcefb8514298d255ca7ca0ec26b7bc63475a',
                 'mathjs': '4f5d049e8d6790d6774acbf73e774c19f5e20db7'}
pilot.ROOT = '/opt/memex-pilot/workspaces/gateway-recovery-v28'
previous.OWNERS = {'qs': 'ljharb/qs', 'express': 'expressjs/express',
                   'cheerio': 'cheeriojs/cheerio', 'mathjs': 'josdejong/mathjs'}
previous.GUEST_HASHES = {
    '/opt/memex-pilot/node/bin/node': '6bf69d0eda41a12030d5f28d958cd09ce323bc0c13f1ab4d8bb426933aa08812',
    '/home/mk-q.guest/staging/qs-runtime-v27/package-lock.json': '67f76e8af7644c57990698358560828277c80844b51f012ea207120b8751efcd',
    '/home/mk-q.guest/staging/express-runtime-v27/package-lock.json': '7469cd3624c70242507cb024f3fe6912c7200323e028d34893e3032b0cf6cd4a',
    '/home/mk-q.guest/staging/cheerio-runtime-v28/package-lock.json': '695729b40267f060b4e4fd1835cda0e002f2f48f0d27cfac05958b8a7d98390f',
    '/home/mk-q.guest/staging/mathjs-runtime-20261031/package-lock.json': '2195cbcd933fd1a2ed008d97cbb5862e13fea87b78739ce9a4b28961ee46973e'}


def prepare(root, snapshot):
    previous.prepare(root, snapshot)
    manifest = pilot.integrity(root)
    manifest['kind'] = 'registered-four-distinct-project-issue-pairs-v28'
    manifest['runtime'] = 'Node 24.18.0 with pinned dependency locks; Cheerio source uses a test-only TypeScript hook.'
    manifest['toolOverflowPolicy'] = 'Execute at most four tool calls per model response; log and return explicit not-executed results for every excess call, then continue within the original turn budget.'
    manifest['costTarget'] = 'Below $1 estimated for four pairs, not a hard cap; requested model limits may be exceeded according to earlier usage.'
    manifest['limitations'].append('The math.js issue is distinct from batch 27 but touches the same source file, so these tasks may be correlated.')
    manifest['limitations'].append('The qs and Cheerio references are narrow manual ports of public proposed PRs, not accepted upstream patches.')
    manifest['files']['scripts/prospective-gateway-pilot-v28.py'] = pilot.SHA(pathlib.Path(__file__).read_bytes())
    manifest['files']['scripts/prospective_agent_v28.py'] = pilot.SHA((REPO / 'scripts/prospective_agent_v28.py').read_bytes())
    pilot.save(root / 'manifest.json', manifest)
    pilot.integrity(root)
    print('final v28 manifest sha256:', pilot.SHA((root / 'manifest.json').read_bytes()))


pilot.prepare = prepare
pilot.solve = lambda root: agent.solve(pilot, root)

if __name__ == '__main__':
    pilot.main()
