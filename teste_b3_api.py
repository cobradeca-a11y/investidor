import requests, json, base64

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Accept': 'application/json, text/plain, */*',
    'Referer': 'https://sistemaswebb3-listados.b3.com.br/',
    'Origin': 'https://sistemaswebb3-listados.b3.com.br',
}

BASE = "https://sistemaswebb3-listados.b3.com.br/fundsProxy/fundsCall"

def b64(obj):
    return base64.b64encode(json.dumps(obj, separators=(',',':')).encode()).decode()

# Lista de FIIs paginada
payload = {"language":"pt-br","typeFund":"FII","pageNumber":1,"pageSize":20,"keyword":""}
url = f"{BASE}/GetListedFundsSIG/{b64(payload)}"
print(f"URL: {url}\n")

r = requests.get(url, headers=headers, timeout=10)
print(f"Status: {r.status_code} | Tamanho: {len(r.text)}")
if r.text.strip():
    try:
        data = r.json()
        print(json.dumps(data, indent=2, ensure_ascii=False)[:1500])
    except:
        print(r.text[:500])
else:
    print("Resposta vazia")

# Testa detalhe
print("\n--- Detalhe HGLG ---")
for p in [
    {"language":"pt-br","idCEM":"HGLG","typeFund":"FII"},
    {"language":"pt-br","idFNET":17500,"idCEM":"HGLG","typeFund":"FII"},
]:
    url2 = f"{BASE}/GetDetailFundSIG/{b64(p)}"
    r2 = requests.get(url2, headers=headers, timeout=10)
    print(f"Status: {r2.status_code} | payload: {p}")
    if r2.text.strip():
        print(f"  {r2.text[:400]}")
