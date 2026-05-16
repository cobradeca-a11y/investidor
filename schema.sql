-- FIIA — Schema v1.1
-- Criar com: python main.py --setup
-- Sincronizado com implementações P2/P3 e ciclo operacional de aprendizado.

PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

-- ─────────────────────────────────────────
-- FIIs cadastrados
-- ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS fiis (
    ticker              TEXT PRIMARY KEY,
    nome                TEXT,
    tipo                TEXT,
    segmento            TEXT,
    ativo               INTEGER DEFAULT 1,
    criado_em           TEXT DEFAULT (datetime('now','localtime'))
);

-- ─────────────────────────────────────────
-- Snapshot diário de indicadores
-- ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS indicadores (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker              TEXT NOT NULL,
    data                TEXT NOT NULL,
    preco               REAL,
    preco_timestamp     TEXT,
    preco_fonte         TEXT,
    preco_moeda         TEXT,
    pvp                 REAL,
    liquidez_diaria     REAL,
    ultimo_dividendo    REAL,
    dy_3m               REAL,
    dy_6m               REAL,
    dy_12m              REAL,
    dy_patrimonial      REAL,
    vacancia_fisica     REAL,
    vacancia_financeira REAL,
    patrimonio_liquido  REAL,
    vpa                 REAL,
    qtd_ativos          INTEGER,
    fonte               TEXT,
    confiabilidade      INTEGER,
    coletado_em         TEXT DEFAULT (datetime('now','localtime')),
    UNIQUE(ticker, data),
    FOREIGN KEY (ticker) REFERENCES fiis(ticker)
);

-- ─────────────────────────────────────────
-- Histórico mensal de dividendos
-- ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS dividendos (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker              TEXT NOT NULL,
    data_pagamento      TEXT NOT NULL,
    data_base           TEXT,
    data_com            TEXT,
    valor               REAL NOT NULL,
    tipo                TEXT DEFAULT 'INDEFINIDO',
    fonte               TEXT,
    protocolo           TEXT,
    url_documento       TEXT,
    UNIQUE(ticker, data_pagamento),
    FOREIGN KEY (ticker) REFERENCES fiis(ticker)
);

-- ─────────────────────────────────────────
-- CVM — Informes mensais FII versionados
-- ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS cvm_informes_mensais_fii (
    id                         INTEGER PRIMARY KEY AUTOINCREMENT,
    cnpj_fundo                 TEXT NOT NULL,
    competencia                TEXT NOT NULL,
    versao                     INTEGER NOT NULL DEFAULT 1,
    reapresentacao             INTEGER NOT NULL DEFAULT 0,
    patrimonio_liquido         REAL,
    valor_patrimonial_cota     REAL,
    num_cotistas               INTEGER,
    num_cotas                  REAL,
    fonte                      TEXT NOT NULL DEFAULT 'CVM_INF_MENSAL',
    ano                        INTEGER,
    arquivo_origem             TEXT,
    coletado_em                TEXT NOT NULL,
    payload_json               TEXT,
    UNIQUE(cnpj_fundo, competencia, versao)
);

-- ─────────────────────────────────────────
-- FNET — Dividendos oficiais de avisos aos cotistas
-- ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS fnet_dividendos_fii (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker              TEXT NOT NULL,
    cnpj_fundo          TEXT,
    data_base           TEXT,
    data_com            TEXT,
    data_pagamento      TEXT NOT NULL,
    valor               REAL NOT NULL,
    tipo                TEXT DEFAULT 'INDEFINIDO',
    fonte               TEXT NOT NULL DEFAULT 'FNET_AVISO_COTISTAS',
    protocolo           TEXT,
    url_documento       TEXT,
    assunto             TEXT,
    arquivo_origem      TEXT,
    coletado_em         TEXT NOT NULL,
    payload_json        TEXT,
    dedupe_key          TEXT UNIQUE
);

-- ─────────────────────────────────────────
-- FNET — Classificações NLP/Gemini
-- ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS fnet_nlp_classificacoes (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    documento_hash      TEXT NOT NULL UNIQUE,
    documento_id        TEXT,
    ticker              TEXT,
    nivel               TEXT NOT NULL,
    motivo              TEXT,
    termos_detectados   TEXT,
    modelo              TEXT,
    criado_em           TEXT NOT NULL,
    payload_json        TEXT
);

-- ─────────────────────────────────────────
-- CVM — Informes trimestrais operacionais
-- ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS inf_trimestral_imoveis (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker              TEXT NOT NULL,
    cnpj                TEXT NOT NULL,
    data_referencia     TEXT NOT NULL,
    nome_imovel         TEXT,
    classe              TEXT,
    area                REAL,
    vacancia_pct        REAL,
    inadimplencia_pct   REAL,
    receita_pct         REAL,
    locado_pct          REAL,
    UNIQUE(cnpj, data_referencia, nome_imovel)
);

CREATE TABLE IF NOT EXISTS inf_trimestral_contratos (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker              TEXT NOT NULL,
    cnpj                TEXT NOT NULL,
    data_referencia     TEXT NOT NULL,
    venc_ate_3m         REAL,
    venc_3a6m           REAL,
    venc_6a12m          REAL,
    venc_acima_36m      REAL,
    indexador_igpm      REAL,
    indexador_ipca      REAL,
    UNIQUE(cnpj, data_referencia)
);

-- ─────────────────────────────────────────
-- Dados macroeconômicos diários
-- ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS macro (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    data                TEXT NOT NULL UNIQUE,
    selic               REAL,
    cdi                 REAL,
    ipca                REAL,
    ifix                REAL,
    coletado_em         TEXT DEFAULT (datetime('now','localtime'))
);

-- ─────────────────────────────────────────
-- Carteira pessoal
-- ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS carteira (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker              TEXT NOT NULL,
    data_compra         TEXT NOT NULL,
    preco_entrada       REAL NOT NULL,
    qtd_cotas           INTEGER NOT NULL,
    motivo              TEXT,
    tese                TEXT,
    ativo               INTEGER DEFAULT 1,
    criado_em           TEXT DEFAULT (datetime('now','localtime')),
    FOREIGN KEY (ticker) REFERENCES fiis(ticker)
);

-- ─────────────────────────────────────────
-- Decisões do sistema
-- ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS decisoes (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker              TEXT NOT NULL,
    data                TEXT NOT NULL,
    preco_na_decisao    REAL,
    status              TEXT NOT NULL,
    score_qualidade     REAL,
    score_preco         REAL,
    score_risco         REAL,
    score_renda         REAL,
    score_mercado       REAL,
    score_confianca     REAL,
    margem_seguranca    REAL,
    premio_cdi          REAL,
    alertas             TEXT,
    justificativa       TEXT,
    explicacao_simples  TEXT,
    score_ia            REAL,
    versao_modelo       TEXT DEFAULT '1.0',
    criado_em           TEXT DEFAULT (datetime('now','localtime')),
    FOREIGN KEY (ticker) REFERENCES fiis(ticker)
);

CREATE TABLE IF NOT EXISTS decisoes_resultado (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    decisao_id           INTEGER NOT NULL,
    data_avaliacao       TEXT NOT NULL,
    janela_dias          INTEGER,
    preco_avaliacao      REAL,
    retorno_preco        REAL,
    retorno_dividendos   REAL,
    retorno_total        REAL,
    retorno_cdi_periodo  REAL,
    retorno_ifix_periodo REAL,
    acerto               INTEGER,
    tipo_erro            TEXT,
    observacao           TEXT,
    avaliado_em          TEXT DEFAULT (datetime('now','localtime')),
    FOREIGN KEY (decisao_id) REFERENCES decisoes(id)
);

-- ─────────────────────────────────────────
-- Aprendizado operacional / paper trading
-- ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS aprendizado_simulacoes (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker              TEXT NOT NULL,
    acao_simulada       TEXT NOT NULL,
    decisao_origem      TEXT,
    segmento            TEXT,
    score_final         REAL,
    confianca           TEXT,
    risco               TEXT,
    fonte_patrimonial   TEXT,
    gate55_status       TEXT,
    peso_versao         TEXT DEFAULT 'base',
    payload_json        TEXT,
    criada_em           TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS aprendizado_resultados (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    simulacao_id        INTEGER NOT NULL,
    ticker              TEXT NOT NULL,
    janela_dias         INTEGER NOT NULL,
    retorno_pct         REAL,
    superou_benchmark   INTEGER,
    resultado           TEXT NOT NULL,
    falso_positivo      INTEGER DEFAULT 0,
    falso_negativo      INTEGER DEFAULT 0,
    observado_em        TEXT NOT NULL,
    observacao          TEXT,
    FOREIGN KEY(simulacao_id) REFERENCES aprendizado_simulacoes(id)
);

CREATE TABLE IF NOT EXISTS aprendizado_ajustes_pesos (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    regra               TEXT NOT NULL,
    peso_anterior       REAL,
    peso_sugerido       REAL,
    motivo              TEXT NOT NULL,
    evidencia           TEXT,
    aplicado            INTEGER DEFAULT 0,
    criado_em           TEXT NOT NULL
);

-- ─────────────────────────────────────────
-- Snapshots históricos para replay futuro
-- ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS snapshots_indicadores (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker              TEXT NOT NULL,
    data_snapshot       TEXT NOT NULL,
    origem_snapshot     TEXT NOT NULL DEFAULT 'rotina_diaria',
    payload_json        TEXT NOT NULL,
    hash_snapshot       TEXT NOT NULL,
    criado_em           TEXT NOT NULL,
    UNIQUE(ticker, data_snapshot, hash_snapshot)
);

-- ─────────────────────────────────────────
-- Versões do modelo de pesos
-- ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS versoes_modelo (
    versao              TEXT PRIMARY KEY,
    data                TEXT NOT NULL,
    descricao           TEXT,
    pesos_json          TEXT NOT NULL,
    motivo_mudanca      TEXT,
    aprovado_em         TEXT
);

CREATE TABLE IF NOT EXISTS sugestoes_ajuste (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    data                TEXT NOT NULL,
    tipo_fundo          TEXT NOT NULL,
    peso_afetado        TEXT NOT NULL,
    valor_atual         REAL NOT NULL,
    valor_sugerido      REAL NOT NULL,
    amostras            INTEGER NOT NULL,
    diferenca_vs_cdi    REAL NOT NULL,
    consistencia_segmentos REAL NOT NULL,
    explicacao          TEXT,
    aprovado            INTEGER DEFAULT NULL,
    aprovado_em         TEXT,
    criado_em           TEXT DEFAULT (datetime('now','localtime'))
);

-- ─────────────────────────────────────────
-- Índices para performance
-- ─────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_indicadores_ticker_data ON indicadores(ticker, data);
CREATE INDEX IF NOT EXISTS idx_dividendos_ticker ON dividendos(ticker);
CREATE INDEX IF NOT EXISTS idx_dividendos_ticker_data ON dividendos(ticker, data_pagamento);
CREATE INDEX IF NOT EXISTS idx_cvm_mensal_cnpj_competencia ON cvm_informes_mensais_fii(cnpj_fundo, competencia, versao);
CREATE INDEX IF NOT EXISTS idx_fnet_dividendos_ticker_data ON fnet_dividendos_fii(ticker, data_pagamento);
CREATE INDEX IF NOT EXISTS idx_fnet_nlp_ticker ON fnet_nlp_classificacoes(ticker);
CREATE INDEX IF NOT EXISTS idx_trimestral_imoveis_ticker_data ON inf_trimestral_imoveis(ticker, data_referencia);
CREATE INDEX IF NOT EXISTS idx_trimestral_contratos_ticker_data ON inf_trimestral_contratos(ticker, data_referencia);
CREATE INDEX IF NOT EXISTS idx_decisoes_ticker ON decisoes(ticker);
CREATE INDEX IF NOT EXISTS idx_decisoes_resultado_decisao ON decisoes_resultado(decisao_id);
CREATE INDEX IF NOT EXISTS idx_macro_data ON macro(data);
CREATE INDEX IF NOT EXISTS idx_aprendizado_sim_ticker ON aprendizado_simulacoes(ticker);
CREATE INDEX IF NOT EXISTS idx_aprendizado_resultados_sim ON aprendizado_resultados(simulacao_id);
CREATE INDEX IF NOT EXISTS idx_snapshots_ticker_data ON snapshots_indicadores(ticker, data_snapshot);

-- ─────────────────────────────────────────
-- Dados iniciais — versão 1.0 do modelo
-- ─────────────────────────────────────────
INSERT OR IGNORE INTO versoes_modelo (versao, data, descricao, pesos_json, motivo_mudanca, aprovado_em)
VALUES (
    '1.0',
    date('now'),
    'Versão inicial — pesos conservadores para renda de longo prazo',
    '{
        "PAPEL":       {"qualidade":0.15,"renda":0.25,"preco":0.20,"risco":0.25,"liquidez":0.10,"gestao":0.05},
        "TIJOLO":      {"qualidade":0.20,"renda":0.20,"preco":0.20,"risco":0.20,"liquidez":0.10,"gestao":0.10},
        "FOF":         {"qualidade":0.15,"renda":0.20,"preco":0.20,"risco":0.20,"liquidez":0.15,"gestao":0.10},
        "HIBRIDO":     {"qualidade":0.17,"renda":0.22,"preco":0.20,"risco":0.20,"liquidez":0.10,"gestao":0.11},
        "DESENVOLVIMENTO": {"qualidade":0.10,"renda":0.10,"preco":0.15,"risco":0.35,"liquidez":0.15,"gestao":0.15},
        "OUTRO":       {"qualidade":0.17,"renda":0.20,"preco":0.20,"risco":0.23,"liquidez":0.10,"gestao":0.10}
    }',
    'Criação inicial do projeto',
    date('now')
);
