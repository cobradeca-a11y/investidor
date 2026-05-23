"""
Teste 9 — Avaliador temporal (janelas 90/365 dias).
Roda sem servidor.
Com banco sem decisões antigas: avaliacoes_processadas = 0.
Com decisões de 90+ dias: avaliacoes_processadas > 0.
"""
from servicos.agendador_avaliador import executar_avaliador_temporal

resultado = executar_avaliador_temporal(forcar=True)

print(f"Status              : {resultado.get('status')}")
print(f"Executado em        : {resultado.get('executado_em')}")
print(f"Duração (s)         : {resultado.get('duracao_segundos')}")
print(f"Avaliações proc.    : {resultado.get('avaliacoes_processadas')}")
print(f"Taxa acerto 90d     : {resultado.get('taxa_acerto_90d')}")
print(f"Taxa acerto 365d    : {resultado.get('taxa_acerto_365d')}")
print(f"Forçado             : {resultado.get('forcado')}")

if resultado.get('status') == 'erro':
    print(f"Erro                : {resultado.get('erro')}")
