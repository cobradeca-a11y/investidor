import requests
from bs4 import BeautifulSoup

headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}

for ticker in ['HGLG11', 'KNCR11', 'CPTS11']:
    url = f"https://www.fundamentus.com.br/detalhes.php?papel={ticker}"
    res = requests.get(url, headers=headers, timeout=10)
    res.encoding = 'latin-1'
    soup = BeautifulSoup(res.text, 'html.parser')
    
    # Pega todo texto da página e busca padrão de CNPJ
    import re
    texto = soup.get_text()
    cnpjs = re.findall(r'\d{2}[\.\-]?\d{3}[\.\-]?\d{3}[\/\.\-]?\d{4}[\-\.]?\d{2}', texto)
    
    # Também busca campo específico
    campos = {}
    for row in soup.find_all('tr'):
        cells = [c.text.strip() for c in row.find_all(['td', 'th'])]
        for i in range(0, len(cells)-1, 2):
            if cells[i]:
                campos[cells[i]] = cells[i+1] if i+1 < len(cells) else ''
    
    print(f"\n{ticker}:")
    print(f"  CNPJs encontrados no texto: {cnpjs[:5]}")
    # Mostra campos que podem conter CNPJ
    for k, v in campos.items():
        if any(x in k.upper() for x in ['CNPJ', 'CGC', 'CADASTRO']):
            print(f"  Campo '{k}': {v}")

print("\nCampos disponíveis HGLG11 (primeiros 20):")
url = "https://www.fundamentus.com.br/detalhes.php?papel=HGLG11"
res = requests.get(url, headers=headers, timeout=10)
res.encoding = 'latin-1'
soup = BeautifulSoup(res.text, 'html.parser')
for i, row in enumerate(soup.find_all('tr')[:20]):
    cells = [c.text.strip() for c in row.find_all(['td', 'th'])]
    if cells:
        print(f"  {cells}")
