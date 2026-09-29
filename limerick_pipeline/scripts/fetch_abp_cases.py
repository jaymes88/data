import re,html,urllib.request,json
refs=['307631','309999','315273','311588','312683','313124']
out={}
for r in refs:
    u=f"https://www.pleanala.ie/en-ie/case/{r}"
    t=urllib.request.urlopen(u,timeout=60).read().decode('utf8','ignore')
    t=re.sub(r'<script.*?</script>|<style.*?</style>','',t,flags=re.S);t=html.unescape(re.sub(r'<[^>]+>',' ',t));t=re.sub(r'\s+',' ',t)
    g=lambda p: (re.search(p,t).group(1).strip() if re.search(p,t) else '')
    out[r]=dict(url=u,decision=g(r'Decision (.*?) Date signed'),signed=g(r'Date signed (\d\d/\d\d/\d{4})'),desc=g(r'Description (.*?) Case type'),casetype=g(r'Case type (.*?) Decision'))
    print(r,out[r]['decision'],out[r]['signed'],out[r]['desc'][:90])
json.dump(out,open('abp.json','w'))
