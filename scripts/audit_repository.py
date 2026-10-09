"""Read-only publication checks; never prints candidate secret values.

Heuristic detection is not a comprehensive security assessment. Ignored .env
and local data are intentionally not scanned or deleted by this command.
"""
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
PATTERNS = {
    'private key': re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----'),
    'GitHub token': re.compile(r'\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})\b'),
    'AWS access key': re.compile(r'\b(?:AKIA|ASIA)[A-Z0-9]{16}\b'),
    'credential URL': re.compile(r'(?:postgres(?:ql)?(?:\+\w+)?|mysql)://[^\s/:]+:([^\s/@]+)@'),
}


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT, text=True, encoding='utf-8', errors='replace')


def findings(content, source=''):
    result = []
    for label, pattern in PATTERNS.items():
        for match in pattern.finditer(content):
            if label == 'credential URL' and source == 'tests/test_etl.py' and match[1] == 'p%40ss%3A%2Fword':
                continue  # Exact URL-encoding fixture, not an active credential.
            if label == 'credential URL' and (match[1] in ('test', 'password', 'change_me') or '${' in match[0]):
                continue  # Known test literals and environment substitutions.
            result.append(label)
    return result


def main():
    files = git('ls-files', '--cached', '--others', '--exclude-standard').splitlines()
    issues = []
    for name in files:
        path = ROOT / name
        if not path.is_file(): continue
        if path.name == '.env' or path.suffix.lower() in ('.pem', '.key'):
            issues.append(f'Private file would be published: {name}')
        if path.suffix.lower() in ('.docx', '.pbix', '.pbit'):
            issues.append(f'Local binary artifact would be published: {name}')
        try:
            content = path.read_text(encoding='utf-8')
        except (UnicodeError, OSError):
            continue
        for label in findings(content, name): issues.append(f'{label} candidate in {name}')
        if path.suffix == '.md':
            for target in re.findall(r'\[[^\]]*\]\(([^)]+)\)', content):
                if re.match(r'\w+://', target) or target.startswith('#'): continue
                target = target.split('#')[0].strip('<>')
                if not (path.parent / target).exists():
                    issues.append(f'Broken documentation link in {name}: {target}')
    # Check historical high-confidence token/private-key patterns without
    # displaying patches, author email addresses or secret values.
    history = git('log', '--all', '--format=', '-p')
    for label in ('private key', 'GitHub token', 'AWS access key'):
        if PATTERNS[label].search(history): issues.append(f'{label} candidate in Git history')
    if issues:
        print('\n'.join(issues))
        return 1
    print(f'PASS: {len(files)} publishable files; local links and credential-pattern checks; high-confidence Git-history scan')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
