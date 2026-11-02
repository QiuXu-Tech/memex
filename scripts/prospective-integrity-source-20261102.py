#!/usr/bin/env python3
"""Freeze selected public issue discussions and pinned source archives for a new replay."""
import hashlib
import json
import pathlib
import posixpath
import tarfile
import urllib.request

ROOT = pathlib.Path.home() / '.local/share/memex-forward-20261102/integrity-source'
DETAILS = pathlib.Path('/tmp/memex-new-eval-20261102/details.json')
TASKS = {
    'avajs/ava': (3343, 'Explain the awaited Axios/JSDOM error and reported serialization or reporting failures; distinguish the suggested Concordance cause from a demonstrated cause and propose a diagnostic.'),
    'graphql/graphql-js': (4834, 'Explain the GraphQL diagnostics channel and Cloudflare Tail Worker structured-cloning report; distinguish successful requests, logging failures, environment-side investigation and the temporary-disable proposal.'),
    'hapijs/hapi': (4582, 'Explain the difference between handler and validator Boom error data, the Joi shared-error mutation discussion, and the fresh-error workaround without declaring an unverified fix.'),
    'postcss/postcss': (2133, 'Explain the version-dependent BOM behavior and the distinction between PostCSS preserving an input BOM and bundlers concatenating multiple files; discuss uncertainty about removing internal U+FEFF.'),
    'preactjs/preact': (4994, 'Explain the core-versus-compat JSX type mismatch using the SVG property example, and identify a TypeScript check that distinguishes the two configurations.'),
    'sequelize/sequelize': (18253, 'Explain the requested native UUIDv7 generation, the discussion that UUIDv7 support already exists, and the separate Node/PostgreSQL version and dependency tradeoff.'),
    'typicode/json-server': (1709, 'Explain why an array of primitive strings causes the reported id-assignment error, the object-array workaround and its compatibility cost, and a minimal reproduction.'),
    'fastify/fastify': (6454, 'Explain the getSchema/addSchema reference or copying performance concern, compare the proposed Symbol and WeakSet approaches, and identify a regression or benchmark needed before claiming improvement.'),
}

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    ROOT.mkdir(mode=0o700, parents=True, exist_ok=False)
    entries = json.loads(DETAILS.read_text())['data']
    found = {item['nameWithOwner']: item for item in entries.values() if item and item.get('issue')}
    manifest = []
    for index, (repo, (number, criterion)) in enumerate(TASKS.items(), 1):
        item = found[repo]
        issue = item['issue']
        assert issue['number'] == number and issue['state'] == 'OPEN'
        assert not issue['comments']['pageInfo']['hasNextPage'] and len(issue['comments']['nodes']) >= 3
        commit = item['defaultBranchRef']['target']['oid']
        slug = f'integrity-{index:02d}'
        archive = ROOT / f'{slug}.tar.gz'
        metadata = ROOT / f'{slug}.issue.json'
        with urllib.request.urlopen(f'https://codeload.github.com/{repo}/tar.gz/{commit}', timeout=120) as response, archive.open('xb') as target:
            while block := response.read(1024 * 1024):
                target.write(block)
                if target.tell() > 50 * 1024 * 1024:
                    raise ValueError(f'{repo}: compressed archive exceeds 50 MiB')
        with tarfile.open(archive) as tar:
            members = tar.getmembers()
            if any(pathlib.PurePosixPath(member.name).is_absolute() or '..' in pathlib.PurePosixPath(member.name).parts for member in members):
                raise ValueError(f'{repo}: unsafe archive member')
            for member in members:
                if not (member.issym() or member.islnk()):
                    continue
                target = posixpath.normpath(posixpath.join(posixpath.dirname(member.name) if member.issym() else '', member.linkname))
                top = member.name.split('/')[0]
                if target != top and not target.startswith(top + '/'):
                    raise ValueError(f'{repo}: archive link escapes source root')
            expanded = sum(member.size for member in members if member.isfile())
            if expanded > 350 * 1024 * 1024:
                raise ValueError(f'{repo}: expanded archive exceeds 350 MiB')
        metadata.write_text(json.dumps(issue, ensure_ascii=False, indent=2) + '\n')
        manifest.append({'id': slug, 'repo': repo, 'issue': number, 'issueUrl': issue['url'], 'title': issue['title'],
                         'sourceCommit': commit, 'issueSha256': digest(metadata), 'archiveSha256': digest(archive),
                         'archiveBytes': archive.stat().st_size, 'expandedBytes': expanded,
                         'commentCount': len(issue['comments']['nodes']), 'createdAt': issue['createdAt'],
                         'lastCommentAt': issue['comments']['nodes'][-1]['createdAt'], 'frozenAcceptance': criterion})
        print(json.dumps({'repo': repo, 'issue': number, 'archiveMiB': round(archive.stat().st_size / 1048576, 2), 'expandedMiB': round(expanded / 1048576, 2)}), flush=True)
    (ROOT / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'tasks': len(manifest), 'manifestSha256': digest(ROOT / 'manifest.json')}), flush=True)

if __name__ == '__main__':
    main()
