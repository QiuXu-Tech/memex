#!/usr/bin/env python3
"""Freeze two additional public issues for a post-permissions-fix smoke."""
import datetime
import hashlib
import importlib.util
import json
import os
import pathlib
import subprocess
import urllib.request

root = pathlib.Path(__file__).resolve().parent.parent
private = pathlib.Path.home() / '.local/share/memex-forward-20261102'
out = private / 'integrity-post-permissions-source'
spec = importlib.util.spec_from_file_location('source_screen', root / 'scripts/prospective-long-source-20261102.py')
screen = importlib.util.module_from_spec(spec)
spec.loader.exec_module(screen)
items = [
    ('zloirock', 'core-js', 1556, 'Explain the reported npm allow-scripts warning for the postinstall donation message, the npm fund tradeoff, and the later deny-scripts command correction without treating proposed behavior as independently verified.'),
    ('localForage', 'localForage', 1101, 'Explain the reported _tryReconnect null database error and the insufficient environment information in the discussion; propose an initialization and browser-storage reproduction.'),
]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    os.umask(0o077)
    assert not out.exists(), 'source directory already exists; do not overwrite a frozen snapshot'
    prior = [json.loads((private / name / 'manifest.json').read_text()) for name in ('cohort30-source', 'supplement-source', 'integrity-source', 'integrity-long-source')]
    owners = {t['repo'].split('/')[0].lower() for cohort in prior for t in cohort}
    assert not owners.intersection(owner.lower() for owner, _, _, _ in items)
    out.mkdir(mode=0o700)
    rejected = private / 'integrity-post-permissions-rejected-react-admin' / 'perm-01.tar.gz'
    screened = private / 'integrity-post-permissions-screened-lodash' / 'manifest.json'
    (out / 'rejections.json').write_text(json.dumps([{'repo': 'marmelab/react-admin', 'issue': 10892,
        'reason': 'compressed source archive exceeded the 50 MiB limit', 'partialArchiveBytes': rejected.stat().st_size,
        'partialArchiveSha256': digest(rejected)}, {'repo': 'lodash/lodash', 'issue': 6274,
        'reason': 'the issue appeared in an earlier baseline-only screening; excluded to keep this follow-up independent',
        'screenedManifestSha256': digest(screened)}], indent=2) + '\n')
    tasks = []
    for index, (owner, repo, number, criterion) in enumerate(items, 1):
        query = ('query { repository(owner:' + json.dumps(owner) + ',name:' + json.dumps(repo) + ') {'
                 ' nameWithOwner defaultBranchRef { target { oid } } issue(number:' + str(number) + ') {'
                 ' number title url state body createdAt comments(first:100) { pageInfo { hasNextPage }'
                 ' nodes { body createdAt url author { login } } } } } }')
        response = json.loads(subprocess.check_output(['gh', 'api', 'graphql', '-f', 'query=' + query], text=True))
        item = response['data']['repository']; issue = item['issue']
        comments = issue['comments']['nodes']
        parse = lambda value: datetime.datetime.fromisoformat(value.replace('Z', '+00:00'))
        span = (parse(comments[-1]['createdAt']) - parse(issue['createdAt'])).days
        assert issue['number'] == number and issue['state'] == 'OPEN' and len(comments) >= 3 and not issue['comments']['pageInfo']['hasNextPage'] and span >= 7
        tid = f'perm-{index:02d}'; archive = out / f'{tid}.tar.gz'; metadata = out / f'{tid}.issue.json'
        commit = item['defaultBranchRef']['target']['oid']
        with urllib.request.urlopen(f'https://codeload.github.com/{owner}/{repo}/tar.gz/{commit}', timeout=90) as response, archive.open('xb') as target:
            while block := response.read(1024 * 1024):
                target.write(block)
                if target.tell() > 50 * 1024 * 1024:
                    raise ValueError('compressed archive exceeds 50 MiB')
        expanded = screen.checked_archive(archive)
        metadata.write_text(json.dumps(issue, ensure_ascii=False, indent=2) + '\n')
        tasks.append({'id': tid, 'repo': item['nameWithOwner'], 'issue': number, 'issueUrl': issue['url'], 'title': issue['title'],
                      'sourceCommit': commit, 'issueSha256': digest(metadata), 'archiveSha256': digest(archive),
                      'archiveBytes': archive.stat().st_size, 'expandedBytes': expanded, 'commentCount': len(comments),
                      'createdAt': issue['createdAt'], 'lastCommentAt': comments[-1]['createdAt'], 'discussionSpanDays': span,
                      'frozenAcceptance': criterion})
        print(json.dumps({'task': tid, 'repo': item['nameWithOwner'], 'days': span, 'expandedMiB': round(expanded / 1048576, 1)}), flush=True)
    manifest = out / 'manifest.json'; manifest.write_text(json.dumps(tasks, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'tasks': len(tasks), 'manifestSha256': digest(manifest)}), flush=True)


if __name__ == '__main__':
    main()
