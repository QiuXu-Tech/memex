#!/usr/bin/env python3
"""Freeze one additional owner-disjoint issue before any rescue trial calls."""
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
out = private / 'integrity-permissions-rescue-source'
spec = importlib.util.spec_from_file_location('screen', root / 'scripts/prospective-long-source-20261102.py')
screen = importlib.util.module_from_spec(spec)
spec.loader.exec_module(screen)
owner, repo, number = 'markedjs', 'marked', 4099
criterion = ('Explain the reported quadratic unmatched-emphasis scan and a targeted scaling reproduction; '
             'distinguish worker isolation from a parser fix, record the proposed early-exit PR as unverified, '
             'and identify CommonMark delimiter-compatibility checks without treating reported timings as confirmed.')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    os.umask(0o077)
    assert not out.exists()
    prior = [json.loads((private / name / 'manifest.json').read_text()) for name in (
        'cohort30-source', 'supplement-source', 'integrity-source', 'integrity-long-source',
        'integrity-post-permissions-source', 'integrity-permissions-extra-source')]
    assert owner.lower() not in {t['repo'].split('/')[0].lower() for group in prior for t in group}
    query = ('query { repository(owner:' + json.dumps(owner) + ',name:' + json.dumps(repo) + ') {'
             ' nameWithOwner defaultBranchRef { target { oid } } issue(number:' + str(number) + ') {'
             ' number title url state body createdAt comments(first:100) { pageInfo { hasNextPage }'
             ' nodes { body createdAt url author { login } } } } } }')
    response = json.loads(subprocess.check_output(['gh', 'api', 'graphql', '-f', 'query=' + query], text=True))
    item = response['data']['repository']; issue = item['issue']; comments = issue['comments']['nodes']
    parse = lambda value: datetime.datetime.fromisoformat(value.replace('Z', '+00:00'))
    span = (parse(comments[-1]['createdAt']) - parse(issue['createdAt'])).days
    assert issue['number'] == number and issue['state'] == 'OPEN' and len(comments) >= 3
    assert not issue['comments']['pageInfo']['hasNextPage'] and span >= 7
    out.mkdir(mode=0o700)
    tid = 'rescue-01'; archive = out / f'{tid}.tar.gz'; metadata = out / f'{tid}.issue.json'
    commit = item['defaultBranchRef']['target']['oid']
    with urllib.request.urlopen(f'https://codeload.github.com/{owner}/{repo}/tar.gz/{commit}', timeout=90) as response, archive.open('xb') as target:
        while block := response.read(1024 * 1024):
            target.write(block)
            if target.tell() > 50 * 1024 * 1024:
                raise ValueError('compressed archive exceeds 50 MiB')
    expanded = screen.checked_archive(archive)
    metadata.write_text(json.dumps(issue, ensure_ascii=False, indent=2) + '\n')
    task = {'id': tid, 'repo': item['nameWithOwner'], 'issue': number, 'issueUrl': issue['url'], 'title': issue['title'],
            'sourceCommit': commit, 'issueSha256': digest(metadata), 'archiveSha256': digest(archive),
            'archiveBytes': archive.stat().st_size, 'expandedBytes': expanded, 'commentCount': len(comments),
            'createdAt': issue['createdAt'], 'lastCommentAt': comments[-1]['createdAt'], 'discussionSpanDays': span,
            'frozenAcceptance': criterion}
    manifest = out / 'manifest.json'; manifest.write_text(json.dumps([task], ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'task': tid, 'repo': item['nameWithOwner'], 'days': span,
                      'expandedMiB': round(expanded / 1048576, 1), 'manifestSha256': digest(manifest)}), flush=True)


if __name__ == '__main__':
    main()
