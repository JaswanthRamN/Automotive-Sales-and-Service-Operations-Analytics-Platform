"""Validate PBIR JSON using Microsoft's published schemas (network required)."""
import json
from pathlib import Path
import sys
from urllib.request import urlopen
from urllib.parse import urldefrag

from jsonschema import Draft7Validator
from referencing import Registry, Resource

ROOT = Path(__file__).resolve().parents[1] / 'powerbi/ExecutiveOverview'
CACHE = {}


def retrieve(url):
    url=urldefrag(url)[0]
    if not url.startswith('https://developer.microsoft.com/json-schemas/'):
        raise ValueError(f'Unexpected schema host: {url}')
    if url not in CACHE:
        # Published embedded schemas sometimes declare a dotted $id although
        # the actual Microsoft endpoint uses a hyphenated filename.
        endpoint=url.replace('/schema.embedded.json','/schema-embedded.json')
        with urlopen(endpoint, timeout=30) as response:
            CACHE[url]=json.load(response)
    return CACHE[url]


def main():
    count=0
    for path in sorted(ROOT.rglob('*.json')):
        if '.pbi' in path.parts or 'local-data' in path.parts:
            continue
        document=json.loads(path.read_text(encoding='utf-8-sig'))
        url=document.get('$schema')
        if not url:
            continue
        schema=retrieve(url)
        registry=Registry(retrieve=lambda uri:Resource.from_contents(retrieve(uri)))
        errors=list(Draft7Validator(schema,registry=registry).iter_errors(document))
        if errors:
            for error in errors:
                print(path.relative_to(ROOT),list(error.absolute_path),error.message)
            raise SystemExit(1)
        count+=1
    print(f'PASS: {count} report files validated against Microsoft schemas')


if __name__=='__main__': main()
