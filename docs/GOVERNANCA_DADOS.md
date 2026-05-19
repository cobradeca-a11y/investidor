# FIIA — Governança de Dados e Fontes

Este documento descreve a camada de governança de fontes do FIIA para monitorar disponibilidade, frescor, divergência e confiabilidade histórica sem alterar motor, gates, thresholds ou decisão final.

## 1. Objetivo

A governança de dados mede a saúde das fontes usadas pelo FIIA antes que elas sejam consumidas por camadas decisórias ou exibidas em auditorias.

Fontes monitoradas:

- CVM;
- FNET;
- Yahoo;
- Fundamentus;
- Banco Central do Brasil — BCB.

## 2. Status padronizados

Cada fonte deve ser classificada em um dos status abaixo:

```text
OK
VENCIDA
DIVERGENTE
INDISPONIVEL
SUSPEITA
```

Definições:

- `OK`: fonte disponível, dentro do frescor esperado e sem divergência relevante.
- `VENCIDA`: fonte disponível, mas com idade acima do limite configurado.
- `DIVERGENTE`: fonte disponível, mas divergente de referência acima da tolerância.
- `INDISPONIVEL`: fonte sem payload utilizável ou indisponível.
- `SUSPEITA`: fonte disponível, mas sem metadados suficientes para confiança, como data de atualização.

## 3. Métricas avaliadas

A camada avalia:

- `disponivel`;
- `data_ultima`;
- `idade_dias`;
- `max_idade_dias`;
- `valor_principal`;
- `valor_referencia`;
- `divergencia_pct`;
- `disponibilidade_pct`;
- `score_confianca_fonte`.

## 4. Frescor padrão por fonte

Limites iniciais:

```text
CVM: 95 dias
FNET: 45 dias
YAHOO: 3 dias
FUNDAMENTUS: 7 dias
BCB: 5 dias
```

Esses limites servem para monitoramento. Eles não alteram thresholds dos gates e não mudam decisão final.

## 5. Persistência

A tabela aditiva `governanca_fontes` registra:

- fonte;
- ticker;
- data de referência;
- status;
- motivo;
- idade;
- divergência;
- disponibilidade;
- score de confiança;
- payload estruturado;
- data de criação.

A migração é aditiva:

- não altera tabelas existentes;
- não executa `DROP`;
- não recria tabela decisória;
- não muda contrato final da decisão.

## 6. Logs estruturados

Cada status pode gerar evento estruturado via observabilidade:

```json
{
  "nivel": "INFO ou WARN",
  "modulo": "validacao.governanca_fontes",
  "mensagem": "Status de fonte registrado",
  "fonte": "CVM",
  "contexto": {
    "status": "OK",
    "idade_dias": 18,
    "divergencia_pct": null,
    "score_confianca_fonte": 98.2
  }
}
```

Logs não devem conter segredos, bancos locais ou payloads sensíveis.

## 7. Uso sem rede em testes

A função `avaliar_fontes_por_payloads()` recebe payloads já fornecidos e não aciona rede.

Exemplo:

```python
from validacao.governanca_fontes import avaliar_fontes_por_payloads

resultado = avaliar_fontes_por_payloads(
    {
        "CVM": {"disponivel": True, "data_ultima": "2026-05-01"},
        "FNET": {"disponivel": False},
        "YAHOO": {"disponivel": True, "data_ultima": "2026-05-18"},
        "FUNDAMENTUS": {
            "disponivel": True,
            "data_ultima": "2026-05-18",
            "valor_principal": 110.0,
            "valor_referencia": 100.0,
            "tolerancia_divergencia_pct": 0.02,
        },
        "BCB": {"disponivel": True, "data_ultima": "2026-05-19"},
    },
    ticker="HGLG11",
    data_referencia="2026-05-19",
    persistir=False,
)
```

## 8. Contratos preservados

A governança de fontes não pode:

- alterar thresholds dos gates;
- alterar decisão final;
- chamar motor decisório;
- disparar coleta de rede em testes unitários;
- versionar logs, bancos, `.venv` ou caches;
- quebrar Zero DB Query Mode.

## 9. Testes obrigatórios

Executar:

```bash
python -m compileall -q coleta validacao sistema banco config
pytest teste_governanca_fontes.py teste_regressao_zero_db.py
```

## 10. Checklist operacional

```text
[ ] Todos os status possíveis são cobertos: OK, VENCIDA, DIVERGENTE, INDISPONIVEL, SUSPEITA.
[ ] Testes unitários não acionam rede.
[ ] Migração é aditiva.
[ ] Logs são estruturados.
[ ] Nenhum threshold de gate foi alterado.
[ ] Decisão final não foi alterada.
[ ] Zero DB Query Mode preservado.
```
