# Python port of tracker.js whatIf(), compared with the workbook tab
import json, math, openpyxl, sys
D = json.load(open('lhds/tracker_data.json')); M = D['meta']
TG = {int(k): v for k, v in M['target'].items()}; YRS = sorted(TG); REM = M['rem26']
WMON = 12 * (YRS[-1] - 2025); NOWM = (2026 - 2026) * 12 + 9 + (8 - 1) / 30.44
def whatif(n, w, tY):
    tgt = [0.0] * WMON; pip = [0.0] * WMON; r = D['areas'][n]['reg']
    def spread(arr, m0, m1, v):
        a, b = max(m0, 0), min(m1, WMON)
        if b <= a: return
        for m in range(math.floor(a), math.ceil(b)):
            lo, hi = max(a, m), min(b, m + 1); arr[m] += v * (hi - lo) / ((b - a) if m1 - m0 > 0 else 1)
    spread(tgt, NOWM, 12, tY(2026) * REM)
    for y in YRS:
        if y >= 2027: spread(tgt, (y - 2026) * 12, (y - 2025) * 12, tY(y))
    if w['pipe'] and r:
        spread(pip, NOWM, 12, r['est'][0])
        for i, y in enumerate([2027, 2028, 2029, 2030]): spread(pip, (y - 2026) * 12, (y - 2025) * 12, r['est'][i + 1])
        spread(pip, 60, 72, r['est'][5])
    C = P = N = 0; nc = []
    for m in range(WMON):
        C += tgt[m]; P += pip[m]; nn = max(N, C - P); nc.append(nn - N); N = nn
    out = {k: {y: 0 for y in ['before'] + YRS} for k in ['tgt', 'pip', 'nc', 'st', 'gr', 'ap']}
    def put(k, tau, v):
        if tau < NOWM: out[k]['before'] += v
        else:
            y = 2026 + math.floor(tau / 12)
            if y in out[k]: out[k][y] += v
    kq = 1 / max(0.01, 1 - w['q'] / 100); kr = 1 / max(0.01, 1 - w['r'] / 100)
    for m, v in enumerate(nc):
        mid = m + 0.5
        put('tgt', mid, tgt[m]); put('pip', mid, pip[m]); put('nc', mid, v); put('st', mid - w['lb'], v)
        put('gr', mid - w['lb'] - w['ls'], v * kq); put('ap', mid - w['lb'] - w['ls'] - w['ld'], v * kq * kr)
    return out, N
wb = openpyxl.load_workbook(sys.argv[1], data_only=True); X = wb['Pipeline & permissions needed']; CALC = wb['Pipeline calc']
# workbook targets by place, from the calc sheet input block
tg = {CALC.cell(r, 1).value: [CALC.cell(r, c).value for c in range(3, 18)] for r in range(3, 29)}
w = dict(pipe=True, ld=4.5, ls=16.0, lb=15, q=18, r=0)
names = {'Limerick': 'All'}
worst = 0
for r in range(3, 29):
    nm = CALC.cell(r, 1).value; n = names.get(nm, nm)
    out, N = whatif(n, w, lambda y: tg[nm][y - 2026])
    # headline rows in calc sheet
    for hr in range(1, CALC.max_row + 1):
        if CALC.cell(hr, 1).value == 'Place' and CALC.cell(hr, 2).value == 'Still to deliver': break
    row = hr + 1 + (r - 3)
    xs = [CALC.cell(row, c).value for c in range(2, 7)]
    js = [N, out['gr']['before'], sum(v for k, v in out['gr'].items() if k != 'before'), None, sum(v for k, v in out['ap'].items() if k != 'before')]
    d = max(abs(a - b) for a, b in zip(xs, js) if b is not None)
    worst = max(worst, d)
    if nm in ('Limerick', 'City Centre', 'Kilfinnane', 'Newcastle West'): print(nm, [round(x) for x in xs], [round(x) if x is not None else None for x in js])
print('max abs difference across places', round(worst, 3))
