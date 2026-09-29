import re
W = {'one':1,'two':2,'three':3,'four':4,'five':5,'six':6,'single':1,'1':1,'2':2,'3':3,'4':4,'5':5,'6':6}
NUMW = {'one':1,'two':2,'three':3,'four':4,'five':5,'six':6,'seven':7,'eight':8,'nine':9,'ten':10,'eleven':11,'twelve':12}
BED = r'(one|two|three|four|five|six|[1-6])\s*[-\s]?\s*(?:bed(?:room)?s?|b)(?![a-z])'
CNT = r'(\d{1,4}|' + '|'.join(NUMW) + r')'
MARK = r'\s*(?:x\s*)?(?:no\s*\.?|nr\.?|number|units?\s+of)?\s*(?:of\s+)?'
PAT = re.compile(CNT + r'\s*(?:x\s*no\.?|no\.?|nr\.?|x)\s*(?:\(\s*\w+\s*\)\s*)?' + r'((?:(?!\d+\s*(?:x\s*)?no\.?)[^;:()]){0,45}?)' + BED + r'([^;:()\d]{0,60})', re.I)
PAT2 = re.compile(r'(?<![\d.])(\d{1,4})\s+' + BED + r'([^;:()\d]{0,60})', re.I)
STUDIO = re.compile(CNT + r'\s*(?:x\s*no\.?|no\.?|x)?\s*(?:[a-z\s-]{0,20})studio', re.I)
APT = re.compile(r'apartment|duplex|flat|maisonette|apt|triplex|penthouse', re.I)
HSE = re.compile(r'house|dwelling|detached|semi|terrace|bungalow|townhouse|dormer|mews', re.I)

def num(s):
    s = s.lower()
    return int(s) if s.isdigit() else NUMW.get(s)

def kind(txt):
    a, h = APT.search(txt), HSE.search(txt)
    if a and (not h or a.start() < h.start()):
        return 'apt'
    if h:
        return 'house'
    return 'unit'

def parse(desc):
    """Return dict of counts: (kind, beds) -> n ; and total."""
    if not isinstance(desc, str):
        return {}, 0
    d = desc.replace('\n', ' ')
    d = re.sub(r'(\d)\s*no\s*\.?\s*(?=\d)', r'\1 no. ', d)
    out = {}
    spans = []
    for m in PAT.finditer(d):
        n = num(m.group(1)); b = W[m.group(3).lower()]
        if not n or n > 2000:
            continue
        k = kind(m.group(2) + ' ' + m.group(4)[:60])
        if k == 'unit':
            k = kind(d[m.end():m.end() + 120].split(';')[0])  # e.g. '... 2 bed & 4 bed houses'
        out[(k, min(b, 5))] = out.get((k, min(b, 5)), 0) + n
        spans.append((m.start(), m.end()))
    for m in PAT2.finditer(d):
        if any(s <= m.start() < e for s, e in spans):
            continue
        n = int(m.group(1)); b = W[m.group(2).lower()]
        if n > 2000 or n == 0:
            continue
        k = kind(m.group(3))
        out[(k, min(b, 5))] = out.get((k, min(b, 5)), 0) + n
    for m in STUDIO.finditer(d):
        n = num(m.group(1))
        if n and n < 2000:
            out[('apt', 0)] = out.get(('apt', 0), 0) + n
    return out, sum(out.values())
