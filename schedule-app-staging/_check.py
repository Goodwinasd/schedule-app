import urllib.request, http.cookiejar, json

cj = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))

req = urllib.request.Request('http://127.0.0.1:5001/api/auth/login', data=json.dumps({'password':'admin123'}).encode(), method='POST')
req.add_header('Content-Type','application/json')
opener.open(req)

for ep in ['subjects','teachers','classrooms_list','groups']:
    r = opener.open(urllib.request.Request(f'http://127.0.0.1:5001/api/{ep}'))
    items = json.loads(r.read())
    print(f'{ep}: {len(items)} items')
    for i in items[:3]:
        print(f'  id={i["id"]} name={i["name"]}')
