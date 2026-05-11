import requests, io, csv

headers = {'User-Agent': 'Mozilla/5.0'}
url = 'https://dados.cvm.gov.br/dados/ADM_FII/CAD/DADOS/cad_adm_fii.csv'

r = requests.get(url, headers=headers, timeout=15)
print(f"Status: {r.status_code}")
if r.status_code == 200:
    r.encoding = 'latin-1'
    reader = csv.DictReader(io.StringIO(r.text), delimiter=';')
    row = next(reader)
    print(f"Colunas: {list(row.keys())}")
    print(f"\nPrimeira linha:")
    for k, v in row.items():
        print(f"  {k}: {v}")
