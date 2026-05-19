# FIIA — Aprendizado Operacional e Ajuste de Pesos

Este documento descreve a camada de aprendizado operacional do FIIA. O objetivo é transformar resultados observados em sugestões controladas de ajuste, sem autoalterar regras críticas.

## 1. Princípio central

O aprendizado do FIIA é supervisionado e auditável.

```text
resultado observado
↓
avaliação temporal
↓
detecção de falso positivo / falso negativo
↓
sugestão controlada de ajuste
↓
aprovação humana obrigatória
```

Nenhum ajuste é aplicado automaticamente.

## 2. Janelas temporais suportadas

A avaliação temporal deve suportar:

```text
30 dias
90 dias
180 dias
365 dias
```

Essas janelas estão configuradas em `config/settings.py` por meio de:

```python
JANELAS_AVALIACAO_DIAS = [30, 90, 180, 365]
```

## 3. Avaliação temporal

O módulo `aprendizado.resultados` avalia o desempenho observado de uma decisão ou simulação.

Campos principais:

- `ticker`;
- `data_decisao`;
- `data_avaliacao`;
- `janela_dias`;
- `acao_original`;
- `preco_entrada`;
- `preco_saida`;
- `retorno_preco_pct`;
- `retorno_dividendos_pct`;
- `retorno_total_pct`;
- `benchmark_pct`;
- `resultado`;
- `falso_positivo`;
- `falso_negativo`;
- `evidencia_json`.

A avaliação não aciona rede. Ela recebe os dados observados como entrada.

## 4. Falso positivo e falso negativo

### Falso positivo

Ocorre quando uma ação ofensiva não supera o benchmark.

Ações ofensivas:

- `COMPRAR`;
- `COMPRAR_PARCIAL`;
- `COMPRAR_PARCIALMENTE`;
- `MANTER`.

### Falso negativo

Ocorre quando uma ação defensiva supera o benchmark.

Ações defensivas:

- `EVITAR`;
- `EVITAR_ENTRADA`;
- `MONITORAR`;
- `AGUARDAR`;
- `REDUZIR`;
- `VENDER`;
- `BLOQUEAR_APORTE`.

## 5. Sugestões controladas de ajuste

O módulo `aprendizado.ajustes_pesos` gera sugestões com base em padrões observados.

Toda sugestão deve conter:

- `regra`;
- `tipo_sugestao`;
- `peso_atual`;
- `peso_sugerido`;
- `evidencia_json`;
- `amostra`;
- `periodo_inicio`;
- `periodo_fim`;
- `impacto_estimado`;
- `motivo`;
- `aplicado=0`;
- `requer_aprovacao_humana=1`.

Tipos de sugestão:

- `REDUZIR_PESO`;
- `AUMENTAR_PESO`;
- `REVISAR_REGRA`;
- `MANTER_SEM_ALTERACAO`.

## 6. Bloqueio de aplicação automática

A função `aplicar_sugestao_automaticamente()` existe apenas como bloqueio explícito.

Resposta esperada:

```json
{
  "status": "bloqueado",
  "aplicado": false,
  "motivo": "Ajustes de pesos exigem aprovação humana e não são aplicados automaticamente."
}
```

## 7. Persistência

Tabelas aditivas criadas no `schema.sql`:

- `aprendizado_resultados_operacionais`;
- `aprendizado_sugestoes_ajuste_pesos`.

As migrações são aditivas:

- não alteram `decisoes`;
- não alteram gates;
- não alteram thresholds;
- não alteram motor;
- não alteram contrato final da decisão.

## 8. Contratos preservados

A camada de aprendizado não pode:

- alterar thresholds dos gates;
- alterar decisão final automaticamente;
- alterar motor decisório;
- alterar coleta/contexto;
- aplicar pesos automaticamente;
- esconder regra de ajuste;
- usar rede em teste unitário.

## 9. Comandos de verificação

```bash
python -m compileall -q aprendizado config banco decisao
pytest teste_aprendizado_operacional.py teste_contrato_decisao.py
```

## 10. Checklist de homologação

```text
[ ] Janelas 30, 90, 180 e 365 suportadas.
[ ] Falso positivo detectado.
[ ] Falso negativo detectado.
[ ] Sugestões contêm evidência, amostra, período e impacto estimado.
[ ] Sugestões exigem aprovação humana.
[ ] Nenhum ajuste é aplicado automaticamente.
[ ] Nenhum threshold de gate foi alterado.
[ ] Contrato final da decisão preservado.
[ ] Testes unitários não usam rede.
```
