"""List and fetch planning file documents from Limerick's iDocs viewer (after the copyright notice, accepted with the user's go-ahead)."""
import re, sys, html, requests
BASE = 'https://eplan.limerick.ie/iDocsWebDPSS/'
import threading
_tl = threading.local()
class _S:
    def __getattr__(self, k):
        if not hasattr(_tl, 's'):
            _tl.s = requests.Session(); _tl.s.headers['User-Agent'] = 'Mozilla/5.0'
        return getattr(_tl.s, k)
S = _S()
def form(t):
    return {k: html.unescape(v) for k, v in re.findall(r'name="(__\w+)" id="__\w+" value="([^"]*)"', t)}
def open_file(ref):
    u = f'{BASE}copyright.aspx?catalog=planning&id={ref}'
    t = S.get(u, timeout=60).text
    d = form(t); d.update({'__EVENTTARGET': 'chkAgree', '__EVENTARGUMENT': '', 'chkAgree': 'on'})
    r = S.post(u, data=d, timeout=60)
    return r
if __name__ == '__main__':
    r = open_file(sys.argv[1])
    print(r.status_code, r.url, len(r.text))
    open('cmp/idocs_list.html', 'w').write(r.text)


def listing(ref):
    open_file(ref)
    t = S.get(f'{BASE}listfiles.aspx?catalog=planning&id={ref}', timeout=60).text
    rows = re.findall(r"<td>([^<]*)</td><td>([^<]*)</td><td>(\d+)</td><td>([^<]*)</td><td>[^<]*</td><td><a target=_blank href='ViewFiles\.aspx\?docid=(\d+)&format=\w+'>View</a></td>", t)
    return [dict(type=html.unescape(a).strip(), comment=html.unescape(b).replace('&nbsp;', '').strip(), files=int(c), size=d, docid=e) for a, b, c, d, e in rows]


def fetch(docid, out):
    t = S.get(f'{BASE}ViewFiles.aspx?docid={docid}&format=pdf', timeout=120).text
    m = re.search(r'src="(ViewPdf\.aspx\?[^"]+)"', t)
    if not m:
        return None
    f = re.search(r'file=([\w-]+\.pdf)', m.group(1)).group(1)
    r = S.get(f'{BASE}files/{f}', timeout=300)
    open(out, 'wb').write(r.content)
    return r.headers.get('content-type'), len(r.content)
