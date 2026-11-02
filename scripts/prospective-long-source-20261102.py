#!/usr/bin/env python3
"""Freeze a second cohort from locally staged issue snapshots and archives.

The earlier local screening files named below are prerequisites, not distributed
fixtures. The resulting registration publishes task URLs, criteria and hashes.
"""
import datetime
import hashlib
import json
import os
import pathlib
import posixpath
import tarfile
import urllib.request

private = pathlib.Path.home() / '.local/share/memex-forward-20261102'
previous = private / 'integrity-eligible-source'
out = private / 'integrity-long-source'
tmp = pathlib.Path('/tmp/memex-new-eval-20261102')
criteria = {
'jasmine/jasmine': (2075, 'Explain the proposed clock operation to advance to the last current timer, including the discussion of timers scheduled during execution and relevant compatibility checks.'),
'mqttjs/MQTT.js': (1939, 'Explain the reported missing error event for packet/stream errors, distinguish a close event and debug logging from a surfaced error, and propose an isolated check.'),
'google/zx': (876, 'Explain the reported difference between global process.cwd and zx within-local working-directory state after cd(), and distinguish documented behavior from the proposed implementation change.'),
'mswjs/msw': (2635, 'Explain the reported loss of request interception after a hidden tab, the worker inactivity and active-client state discussion, and limitations of reload or reactivation workarounds.'),
'socketio/socket.io': (5512, 'Explain the proposed Standard Schema event contract, the distinction between runtime validation and TypeScript inference, and the tradeoff with an existing userland helper.'),
'webpack/webpack': (20536, 'Explain the reported module concatenation bailout with shared parent chunks and identify a focused chunk-graph investigation without treating the speculative processing-order cause as confirmed.'),
'open-telemetry/opentelemetry-js': (6816, 'Explain the request to supply a clock to instrumentation and the discussion of API scope, propagation and compatibility; distinguish proposals from established behavior.'),
'marmelab/react-admin': (10892, 'Explain the reported lazy-loading indicator behavior with React Router v7 and the discussion of the documentation example versus application layout, including reproduction uncertainty.'),
'localForage/localForage': (1101, 'Explain the reported _tryReconnect null database error and the insufficient environment information in the discussion; propose an initialization and browser-storage reproduction.'),
}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def checked_archive(path):
    with tarfile.open(path) as tar:
        members = tar.getmembers()
        top = members[0].name.split('/')[0]
        for member in members:
            parts = pathlib.PurePosixPath(member.name)
            if parts.is_absolute() or '..' in parts.parts or parts.parts[0] != top:
                raise ValueError('unsafe archive path')
            if member.issym() or member.islnk():
                target = posixpath.normpath(posixpath.join(posixpath.dirname(member.name) if member.issym() else '', member.linkname))
                if target != top and not target.startswith(top + '/'):
                    raise ValueError('escaping archive link')
        expanded = sum(member.size for member in members if member.isfile())
    if expanded > 150 * 1024 * 1024:
        raise ValueError('expanded archive exceeds 150 MiB')
    return expanded


def main():
    out.mkdir(mode=0o700, parents=True, exist_ok=True)
    snapshots = []
    for file in ('backups.json', 'details.json'):
        snapshots.extend(x for x in json.loads((tmp / file).read_text())['data'].values() if x and x.get('issue'))
    snapshots.append(json.loads((tmp / 'zx-detail.json').read_text())['data']['repository'])
    found = {(item['nameWithOwner'], item['issue']['number']): item for item in snapshots}
    manifest = []
    # These source files and criteria were screened in the earlier local pass.
    import ast
    module = ast.parse((tmp / 'freeze_extra.py').read_text())
    prior_criteria = next(ast.literal_eval(x.value) for x in module.body if isinstance(x, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'tasks' for t in x.targets))
    for oldid in range(1, 19):
        metadata = previous / f'long-{oldid:02d}.issue.json'
        issue = json.loads(metadata.read_text())
        parts = issue['url'].split('/')
        repo = '/'.join(parts[3:5])
        number, criterion = prior_criteria[repo]
        assert issue['number'] == number
        item = next(x for x in json.loads((tmp / 'more-details.json').read_text())['data'].values() if x and x['nameWithOwner'] == repo)
        source = previous / f'long-{oldid:02d}.tar.gz'
        append(manifest, repo, item, criterion, source)
    rejected = [
        {'repo': 'ionic-team/ionic-framework', 'reason': 'compressed archive exceeded 50 MiB'},
        {'repo': 'mapbox/mapbox-gl-js', 'reason': 'source download stopped after the prior candidate exceeded the workspace budget'},
        {'repo': 'webdriverio/webdriverio', 'reason': 'compressed archive exceeded 50 MiB and discussion span below seven days'},
        {'repo': 'open-telemetry/opentelemetry-js', 'reason': 'initial source preparation selected the wrong issue number; corrected before model calls'},
    ]
    for repo, (number, criterion) in criteria.items():
        if len(manifest) >= 25:
            break
        item = found[(repo, number)]
        assert item['issue']['number'] == number
        download = out / ('download-' + repo.replace('/', '_') + '.tar.gz')
        try:
            if not download.exists():
                with urllib.request.urlopen(f"https://codeload.github.com/{repo}/tar.gz/{item['defaultBranchRef']['target']['oid']}", timeout=90) as response, download.open('xb') as target:
                    while block := response.read(1024 * 1024):
                        target.write(block)
                        if target.tell() > 50 * 1024 * 1024:
                            raise ValueError('compressed archive exceeds 50 MiB')
            append(manifest, repo, item, criterion, download)
        except Exception as error:
            rejected.append({'repo': repo, 'issue': number, 'reason': f'{type(error).__name__}: {str(error)[:100]}'})
            print(json.dumps({'rejected': repo, 'reason': type(error).__name__}), flush=True)
    for name, value in (('manifest.json', manifest), ('rejections.json', rejected)):
        path = out / name
        text = json.dumps(value, ensure_ascii=False, indent=2) + '\n'
        if path.exists() and path.read_text() != text:
            raise ValueError(f'{path}: existing frozen output differs')
        if not path.exists():
            path.write_text(text)
    print(json.dumps({'tasks': len(manifest), 'manifestSha256': sha(out / 'manifest.json')}), flush=True)


def append(manifest, repo, item, criterion, source):
    issue = item['issue']
    parse = lambda value: datetime.datetime.fromisoformat(value.replace('Z', '+00:00'))
    span = (parse(issue['comments']['nodes'][-1]['createdAt']) - parse(issue['createdAt'])).days
    if issue['state'] != 'OPEN' or issue['comments']['pageInfo']['hasNextPage'] or len(issue['comments']['nodes']) < 3 or span < 7:
        raise ValueError('issue is not eligible')
    expanded = checked_archive(source)
    slug = f'long-{len(manifest) + 1:02d}'
    archive, metadata = out / f'{slug}.tar.gz', out / f'{slug}.issue.json'
    if archive.exists():
        if sha(source) != sha(archive):
            raise ValueError('existing source archive differs')
    else:
        os.link(source, archive)
    metadata_text = json.dumps(issue, ensure_ascii=False, indent=2) + '\n'
    if metadata.exists():
        if metadata.read_text() != metadata_text:
            raise ValueError('existing issue snapshot differs')
    else:
        metadata.write_text(metadata_text)
    manifest.append({'id': slug, 'repo': repo, 'issue': issue['number'], 'issueUrl': issue['url'], 'title': issue['title'],
                     'sourceCommit': item['defaultBranchRef']['target']['oid'], 'issueSha256': sha(metadata), 'archiveSha256': sha(archive),
                     'archiveBytes': archive.stat().st_size, 'expandedBytes': expanded, 'commentCount': len(issue['comments']['nodes']),
                     'createdAt': issue['createdAt'], 'lastCommentAt': issue['comments']['nodes'][-1]['createdAt'],
                     'discussionSpanDays': span, 'frozenAcceptance': criterion})
    print(json.dumps({'task': slug, 'repo': repo, 'spanDays': span, 'expandedMiB': round(expanded / 1048576, 1)}), flush=True)


if __name__ == '__main__':
    main()
