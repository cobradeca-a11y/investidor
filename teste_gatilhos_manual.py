"""
Teste 8.1 — Disparar gatilhos com valores forçados.
Roda sem servidor. Precisa de pelo menos uma posição em carteira.
"""
from decisao import gatilhos
from carteira.repositorio_carteira import listar_posicoes

posicoes = listar_posicoes()

if not posicoes:
    print("Nenhuma posição em carteira. Registre uma compra na PWA antes de rodar este teste.")
else:
    print(f"Posições encontradas: {len(posicoes)}\n")
    for pos in posicoes:
        resultado = gatilhos.verificar(
            ticker=pos['ticker'],
            pvp=1.25,          # acima de 1.20 → dispara REALIZAR_PARCIAL_30
            vacancia=None,
            margem=0.05,
            score_ia=8,
            dy_recorrente_atual=None,
        )
        print(f"Ticker: {resultado['ticker']}")
        print(f"  acao_principal : {resultado['acao_principal']}")
        print(f"  total_gatilhos : {resultado['total_gatilhos']}")
        for g in resultado['gatilhos']:
            print(f"  gatilho        : {g['nome']} → {g['acao']}")
            print(f"  motivo         : {g['motivo']}")
        print()