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

## 5. Persistência instantânea

A tabela aditiva `governanca_fontes` registra a leitura pontual da fonte:

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

## 6. Score histórico de fonte

A tabela aditiva `governanca_fontes_score_historico` registra a série longitudinal da confiabilidade por fonte.

Cada registro deve conter:

- `fonte`;
- `ticker`, quando aplicável;
- `data_referencia`;
- `status`;
- `score_confianca_fonte`;
- `motivo`;
- `payload_json`;
- `criado_em`.

Esse score é apenas insumo auditável. Ele não altera decisão automaticamente, não muda thresholds dos gates e não funciona como regra oculta.

## 7. Auditoria longitudinal

A camada `validacao.score_fontes` permite:

- registrar um ponto histórico com `registrar_score_fonte()`;
- converter status instantâneo em histórico com `registrar_score_a_partir_status()`;
- consultar histórico com `consultar_historico_fonte()`;
- resumir confiabilidade com `resumir_confiabilidade_fonte()`.

O resumo explicita:

```text
uso = AUDITORIA_APENAS
altera_decisao_automaticamente = False
```

## 8. Migração

As migrações de governança são aditivas:

- não alteram tabelas existentes;
- não executam `DROP`;
- não recriam tabela decisória;
- não mudam contrato final da decisão.

## 9. Logs estruturados

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

## 10. Uso sem rede em testes

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

## 11. Contratos preservados

A governança de fontes não pode:

- alterar thresholds dos gates;
- alterar decisão final;
- chamar motor decisório;
- disparar coleta de rede em testes unitários;
- versionar logs, bancos, `.venv` ou caches;
- quebrar Zero DB Query Mode;
- usar score histórico como decisão automática.

## 12. Testes obrigatórios

Executar:

```bash
python -m compileall -q validacao coleta banco config
pytest teste_score_fontes.py teste_governanca_fontes.py
```

## 13. Checklist operacional

```text
[ ] Todos os status possíveis são cobertos: OK, VENCIDA, DIVERGENTE, INDISPONIVEL, SUSPEITA.
[ ] Testes unitários não acionam rede.
[ ] Migração é aditiva.
[ ] Logs são estruturados.
[ ] Registros históricos contêm fonte, ticker, data, status, score e motivo.
[ ] Score histórico está marcado como AUDITORIA_APENAS.
[ ] Nenhum threshold de gate foi alterado.
[ ] Decisão final não foi alterada.
[ ] Zero DB Query Mode preservado.
```
