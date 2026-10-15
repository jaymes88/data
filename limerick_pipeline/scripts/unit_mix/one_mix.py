import sys, re, os, time
import eplan_docs as E
from ocr import ocr
ref = sys.argv[1]
L = E.listing(ref)
dec = [int(d['docid']) for d in L if d['type'].startswith(('Notification of Decision', 'Final Grant'))]
cut = min(dec) if dec else 10 ** 12
pre = [d for d in L if d['type'].startswith('Planners Report') and int(d['docid']) < cut and 'memo' not in d['comment'].lower()]
print(ref, 'docs', len(L), 'pre-decision planner reports', [(d['docid'], d['size']) for d in pre])
for d in pre[-2:]:
    out = f'eplan/{ref}_{d["docid"]}.pdf'
    if not os.path.exists(out):
        E.fetch(d['docid'], out)
    txt = out[:-4] + '.txt'
    t0 = time.time()
    if not os.path.exists(txt):
        open(txt, 'w').write(ocr(out, 1, 45))
    lines = [l.rstrip() for l in open(txt) if re.search(r'\d ?x? ?bed|bedroom|studio|unit mix|house type|apartment type', l, re.I)]
    print(f'-- {out} ({time.time()-t0:.0f}s)'); print('\n'.join(lines[:80]))
