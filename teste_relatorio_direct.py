from coleta.relatorio_fnet import _FNET_PDF, _HEADERS, _session, obter_relatorio
import requests

texto = obter_relatorio('CPUR11')
print('LEN', len(texto))
print(texto[:2000])

url = _FNET_PDF.format(doc_id='905195')
print('URL', url)
resp = _session.get(url, headers=_HEADERS, timeout=(5,30), stream=True)
print('STATUS', resp.status_code)
print('CONTENT-TYPE', resp.headers.get('Content-Type'))
print('FIRST BYTES', resp.content[:200])
