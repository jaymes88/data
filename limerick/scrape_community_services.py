"""Scrape Limerick.ie community services (browse listing -> detail pages) to CSV."""
import csv, html, re, sys, time
import requests

BASE = "https://www.limerick.ie"
LIST = BASE + "/discover/living/in-your-community/community-services/browse"
S = requests.Session()
S.headers["User-Agent"] = "Mozilla/5.0 (research; community services audit)"

def get(url, **kw):
    for i in range(4):
        try:
            r = S.get(url, timeout=30, **kw)
            if r.status_code == 200:
                return r.text
        except requests.RequestException:
            pass
        time.sleep(2 ** i)
    raise RuntimeError(f"failed: {url}")

def listing_urls():
    seen, page = {}, 0
    while True:
        t = get(LIST, params={"category": "All", "keyword": "", "region": "All", "page": page})
        links = re.findall(r'<article about="([^"]+)" class="node node--type-amenity', t)
        new = [l for l in links if l not in seen]
        if not new:
            break
        for l in new:
            seen[l] = 1
        print(f"page {page}: {len(new)} new, {len(seen)} total", file=sys.stderr)
        page += 1
    return list(seen)

def clean(s):
    s = re.sub(r"<br\s*/?>|</p>|</div>", "\n", s)
    s = html.unescape(re.sub(r"<[^>]+>", " ", s))
    return re.sub(r"\s*\n\s*", ", ", re.sub(r"[ \t]+", " ", s)).strip(" ,\n")

def field(t, name):
    m = re.search(rf'field--name-field-{name}\b[^>]*>(.*?)(?=<div class="field field--name-|</article>)', t, re.S)
    if not m:
        return ""
    s = re.sub(r'<div class="field__label[^>]*>.*?</div>', "", m.group(1), flags=re.S)
    return clean(s)

def detail(path):
    t = get(BASE + path)
    lat = re.search(r'data-lat="([^"]*)"', t)
    lng = re.search(r'data-lng="([^"]*)"', t)
    title = re.search(r"<h1[^>]*>(.*?)</h1>", t, re.S)
    tags = re.findall(r'href="/taxonomy/term/\d+[^"]*"[^>]*>([^<]+)<', t)
    cat = re.search(r'/community-services/([^/]+)/', path)
    return {
        "name": clean(title.group(1)) if title else "",
        "category": cat.group(1) if cat else "",
        "address": field(t, "address"),
        "region": field(t, "region"),
        "telephone": field(t, "telephone"),
        "latitude": lat.group(1) if lat else "",
        "longitude": lng.group(1) if lng else "",
        "url": BASE + path,
    }

if __name__ == "__main__":
    urls = listing_urls()
    print(f"{len(urls)} listings", file=sys.stderr)
    rows = []
    for i, u in enumerate(urls, 1):
        rows.append(detail(u))
        if i % 25 == 0:
            print(f"detail {i}/{len(urls)}", file=sys.stderr)
        time.sleep(0.3)
    with open("limerick_community_services.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {len(rows)} rows", file=sys.stderr)
