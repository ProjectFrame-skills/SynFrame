"""Read-only exact contract delivery bounded by serialized bytes, not learning depth."""
import hashlib
import json
from pathlib import Path


def encode_bundle(value):
    """The CLI uses these exact bytes, including its final newline."""
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False) + '\n'


def read_contracts(root, request, max_bytes):
    """Return explicit ranges or their exact continuation; never certify reading.

    Byte accounting covers only this compact JSON response. The calling host must
    separately allow for its outer tool envelope, tokenizer and actual context.
    """
    if type(max_bytes) is not int or max_bytes < 1:
        raise ValueError('max_bytes must be a positive response byte budget')
    if (type(request) is not dict or not {'ranges'} <= set(request)
            or set(request) - {'ranges', 'retained'} or type(request['ranges']) is not list):
        raise ValueError('request needs ranges and optional explicit current-context retained declaration')
    root = Path(root).resolve()
    catalog = {str(p.relative_to(root)): p for p in
               [root/'SKILL.md', *sorted((root/'references').glob('*.md'))]}
    contents = {}
    ranges = []
    for spec in request['ranges']:
        if type(spec) is not dict or set(spec) != {'name', 'sha256', 'offset', 'end'}:
            raise ValueError('each range needs exactly name, sha256, offset and end')
        name = spec['name']
        if type(name) is not str or name not in catalog:
            raise ValueError('unknown bundled contract')
        if name not in contents:
            path = catalog[name].resolve()
            if not path.is_relative_to(root):
                raise ValueError('bundled contract resolves outside skill directory')
            raw = path.read_bytes()
            contents[name] = (raw.decode('utf-8'), hashlib.sha256(raw).hexdigest())
        content, checksum = contents[name]
        if spec['sha256'] != checksum:
            raise ValueError('contract changed; restart this file read against its current identity')
        start, end = spec['offset'], spec['end']
        if type(start) is not int or type(end) is not int or not 0 <= start <= end <= len(content):
            raise ValueError('invalid Unicode character range')
        if any(r['name'] == name and (spec == r or start < r['end'] and r['offset'] < end) for r in ranges):
            raise ValueError('overlapping requested ranges; request each exact interval once')
        ranges.append(dict(spec))

    retained = request.get('retained')
    coverage = {}
    if retained is not None:
        if (type(retained) is not dict or set(retained) != {'retained_in_current_context', 'ranges'}
                or retained['retained_in_current_context'] is not True or type(retained['ranges']) is not list):
            raise ValueError('retained ranges require explicit actual retention in current context; clear after context loss')
        for receipt in retained['ranges']:
            if type(receipt) is not dict or not {'name', 'sha256', 'offset', 'end', 'chunk_sha256'} <= set(receipt):
                raise ValueError('retained range needs exact delivery name/hash/bounds/chunk hash')
            name = receipt['name']
            if type(name) is not str or name not in contents or receipt['sha256'] != contents[name][1]:
                continue  # Old identities cannot suppress current text.
            content = contents[name][0]
            start, end = receipt['offset'], receipt['end']
            if (type(start) is not int or type(end) is not int or not 0 <= start <= end <= len(content)
                    or hashlib.sha256(content[start:end].encode('utf-8')).hexdigest() != receipt['chunk_sha256']):
                raise ValueError('retained range does not match delivered bytes')
            coverage.setdefault(name, []).append((start, end))

    def chunk(spec, end):
        content = contents[spec['name']][0]
        text = content[spec['offset']:end]
        covered = spec['offset']
        for start, stop in sorted(coverage.get(spec['name'], [])):
            if start <= covered:
                covered = max(covered, stop)
        reused = covered >= end and end > spec['offset']
        return {**spec, 'end': end, 'characters': len(content),
                'text': '' if reused else text, 'reused_retained': reused,
                'chunk_sha256': hashlib.sha256(text.encode('utf-8')).hexdigest()}

    def response(delivered, remaining, byte_budget=max_bytes):
        value = {'ranges': delivered, 'remaining': remaining, 'complete': not remaining,
                 'budget': {'max_bytes': byte_budget, 'serialized_bytes': 0,
                            'unit': 'UTF-8 compact JSON including final newline; outer envelope and tokens excluded'},
                 'scope': 'Exact delivery only. Host must notice outer truncation and actually read required text. '
                          'Retention requires current-context possession; no understanding or sufficiency approval.'}
        while True:
            size = len(encode_bundle(value).encode('utf-8'))
            if size == value['budget']['serialized_bytes']:
                return value
            value['budget']['serialized_bytes'] = size

    def minimum_budget(delivered, remaining):
        minimum = 1
        while True:
            needed = response(delivered, remaining, minimum)['budget']['serialized_bytes']
            if needed <= minimum:
                return minimum
            minimum = needed  # The reported budget's own digit width is part of its response.

    delivered = []
    for index, spec in enumerate(ranges):
        tail = ranges[index+1:]
        whole = chunk(spec, spec['end'])
        value = response(delivered + [whole], tail)
        if value['budget']['serialized_bytes'] <= max_bytes:
            delivered.append(whole)
            continue
        # Find a complete Unicode prefix that fits after ALL response metadata.
        low, high, best = spec['offset'] + 1, spec['end'] - 1, None
        if not whole['reused_retained']:
            while low <= high:
                end = (low + high) // 2
                value = response(delivered + [chunk(spec, end)], [{**spec, 'offset': end}, *tail])
                if value['budget']['serialized_bytes'] <= max_bytes:
                    best = value
                    low = end + 1
                else:
                    high = end - 1
        if best is not None:
            return best
        value = response(delivered, ranges[index:])
        if not delivered or value['budget']['serialized_bytes'] > max_bytes:
            end = min(spec['offset'] + 1, spec['end'])
            minimum = (minimum_budget(delivered + [whole], tail) if whole['reused_retained'] else
                       minimum_budget(delivered + [chunk(spec, end)],
                                      ([{**spec, 'offset': end}] if end < spec['end'] else []) + tail))
            raise ValueError('response byte budget too small for metadata and next complete character; '
                             f'need at least {minimum} bytes')
        return value
    value = response(delivered, [])
    if value['budget']['serialized_bytes'] > max_bytes:
        raise ValueError('response byte budget too small for metadata; '
                         f'need at least {minimum_budget(delivered, [])} bytes')
    return value
