/**
 * app.js - FIIA Intelligence Interface
 * Versão 2.3 - Histórico e Replay no Dashboard
 *
 * Regras:
 * - não recalcula hash no frontend;
 * - não altera payload da API;
 * - replay é explícito e só roda quando o usuário solicita;
 * - histórico não chama motor nem scraping por padrão;
 * - renderiza campos ausentes sem quebrar;
 * - mantém cards bloqueados visíveis.
 */

document.addEventListener('DOMContentLoaded', () => {
    inicializarNavegacao();
    inicializarTransacoes();
    criarPainelHistorico();
    carregarCarteira();
});

document.getElementById('btnRadar')?.addEventListener('click', async () => {
    const welcomeView = document.getElementById('welcomeView');
    const loading = document.getElementById('loading');
    const resultsGrid = document.getElementById('results');
    const btnRadar = document.getElementById('btnRadar');
    welcomeView?.classList.add('hidden');
    resultsGrid?.classList.add('hidden');
    loading?.classList.remove('hidden');
    btnRadar.disabled = true;
    btnRadar.innerHTML = '<span class="icon">⌛</span> Processando...';

    try {
        const apiKey = obterApiKey();
        if (!apiKey) {
            alert('Configure sua chave de API (fiia_api_key) no localStorage antes de ligar o radar.');
            return;
        }
        // Contrato de payload: a origem permanece fetch('/api/radar'), apenas com headers autenticados.
        const response = await fetch('/api/radar', { headers: headersAutenticados() });
        if (!response.ok) {
            throw new Error(`Radar retornou HTTP ${response.status}`);
        }
        const data = await response.json();
        loading?.classList.add('hidden');
        resultsGrid?.classList.remove('hidden');
        renderResults(data.oportunidades || [], 'results');
    } catch (error) {
        console.error(error);
        alert('Erro ao ligar o radar. Verifique se o servidor está rodando.');
        loading?.classList.add('hidden');
        welcomeView?.classList.remove('hidden');
    } finally {
        btnRadar.disabled = false;
        btnRadar.innerHTML = '<span class="icon">🔍</span> Ligar Radar';
    }
});

document.getElementById('btnClear')?.addEventListener('click', () => window.location.reload());

function obterApiKey() {
    return localStorage.getItem('fiia_api_key') || '';
}

function headersAutenticados(extra = {}) {
    const apiKey = obterApiKey();
    return apiKey ? { ...extra, 'X-API-Key': apiKey } : extra;
}

function inicializarNavegacao() {
    const btnCarteira = document.getElementById('btnCarteira');
    const btnRadarTab = document.getElementById('btnRadarTab');
    const btnRadarAction = document.getElementById('btnRadar');
    const portfolioView = document.getElementById('portfolioView');
    const welcomeView = document.getElementById('welcomeView');
    const resultsView = document.getElementById('results');
    const loadingView = document.getElementById('loading');

    btnCarteira?.addEventListener('click', () => {
        btnCarteira.classList.add('active');
        btnRadarTab?.classList.remove('active');
        portfolioView?.classList.remove('hidden');
        welcomeView?.classList.add('hidden');
        resultsView?.classList.add('hidden');
        loadingView?.classList.add('hidden');
        btnRadarAction?.classList.add('hidden');
        carregarCarteira();
    });

    btnRadarTab?.addEventListener('click', () => {
        btnRadarTab.classList.add('active');
        btnCarteira?.classList.remove('active');
        portfolioView?.classList.add('hidden');
        welcomeView?.classList.remove('hidden');
        resultsView?.classList.add('hidden');
        btnRadarAction?.classList.remove('hidden');
    });
}

function inicializarTransacoes() {
    const btnOpenModal = document.getElementById('btnOpenModal');
    const btnCloseModal = document.getElementById('btnCloseModal');
    const transactionModal = document.getElementById('transactionModal');
    const transactionForm = document.getElementById('transactionForm');

    btnOpenModal?.addEventListener('click', () => transactionModal?.classList.remove('hidden'));
    btnCloseModal?.addEventListener('click', () => transactionModal?.classList.add('hidden'));
    window.addEventListener('click', (e) => {
        if (e.target === transactionModal) transactionModal.classList.add('hidden');
    });

    transactionForm?.addEventListener('submit', async (e) => {
        e.preventDefault();
        const apiKey = obterApiKey();
        if (!apiKey) {
            alert('Configure sua chave de API (fiia_api_key) no localStorage antes de registrar operações.');
            return;
        }
        const submitBtn = transactionForm.querySelector('.btn-submit');
        submitBtn.disabled = true;
        submitBtn.innerHTML = 'Gravando...';
        const payload = {
            ticker: document.getElementById('txTicker').value.trim().toUpperCase(),
            quantidade: parseFloat(document.getElementById('txQtd').value),
            preco: parseFloat(document.getElementById('txPreco').value),
            segmento: document.getElementById('txSegmento').value || null,
            custos: 0.0,
            origem: 'PWA_DASHBOARD'
        };
        try {
            const response = await fetch('/api/carteira/compra', {
                method: 'POST',
                headers: headersAutenticados({ 'Content-Type': 'application/json' }),
                body: JSON.stringify(payload)
            });
            const data = await response.json();
            if (data.status === 'ok') {
                alert('Transação registrada com sucesso!');
                transactionForm.reset();
                transactionModal?.classList.add('hidden');
                carregarCarteira();
            } else {
                alert('Erro ao registrar transação: ' + (data.mensagem || 'Erro desconhecido'));
            }
        } catch (error) {
            console.error('Erro de envio:', error);
            alert('Falha ao conectar com a API para registrar a compra.');
        } finally {
            submitBtn.disabled = false;
            submitBtn.innerHTML = 'Registrar Compra';
        }
    });
}

async function carregarCarteira() {
    const grid = document.getElementById('portfolioGrid');
    if (!grid) return;
    grid.innerHTML = '<div class="loading-simple">⌛ Carregando ativos...</div>';

    try {
        const response = await fetch('/api/carteira/posicoes', { headers: headersAutenticados() });
        const data = await response.json();
        if (data.status === 'ok' && data.posicoes && data.posicoes.length > 0) {
            renderResults(data.posicoes, 'portfolioGrid', true);
        } else {
            grid.innerHTML = `
                <div class="empty-state-container glass-card">
                    <h3>Sua carteira está vazia!</h3>
                    <p>Registre suas operações clicando no botão <strong>+ Registrar Transação</strong> acima.</p>
                    <span class="demo-badge">Abaixo você vê um exemplo de como seus ativos serão analisados:</span>
                </div>
                <div id="demoGrid" class="results-grid"></div>
            `;
            renderResults([mockAtivo()], 'demoGrid', false);
        }
    } catch (error) {
        console.error('Erro ao buscar posições da carteira:', error);
        grid.innerHTML = '<div class="error-simple">❌ Erro ao conectar ao servidor. Exibindo dados de demonstração:</div><div id="demoGrid" class="results-grid"></div>';
        renderResults([mockAtivo()], 'demoGrid', false);
    }
}

function criarPainelHistorico() {
    const container = document.querySelector('.app-container') || document.body;
    if (document.getElementById('historicoDecisoes')) return;

    const section = document.createElement('section');
    section.id = 'historicoDecisoes';
    section.className = 'history-panel glass-card';
    section.innerHTML = `
        <div class="history-header">
            <div>
                <h2>Histórico e Replay</h2>
                <p>Consulta auditável de decisões salvas. Replay só é executado por ação explícita.</p>
            </div>
            <button id="btnHistoricoDecisoes" class="btn-transaction">Carregar histórico</button>
        </div>
        <div id="historicoLista" class="history-list">
            <div class="audit-empty">Histórico ainda não carregado.</div>
        </div>
        <div id="historicoDetalhe" class="history-detail hidden"></div>
    `;
    container.appendChild(section);
    document.getElementById('btnHistoricoDecisoes')?.addEventListener('click', carregarHistoricoDecisoes);
}

async function carregarHistoricoDecisoes() {
    const lista = document.getElementById('historicoLista');
    if (!lista) return;
    const apiKey = obterApiKey();
    if (!apiKey) {
        lista.innerHTML = '<div class="audit-blocks">Configure <strong>fiia_api_key</strong> no localStorage para consultar histórico auditável.</div>';
        return;
    }
    lista.innerHTML = '<div class="loading-simple">⌛ Consultando histórico sem replay...</div>';
    try {
        const response = await fetch('/api/auditoria/decisoes/auditaveis?limite=30', { headers: headersAutenticados() });
        const data = await response.json();
        const decisoes = data.decisoes || [];
        if (!decisoes.length) {
            lista.innerHTML = '<div class="audit-empty">Nenhuma decisão auditável encontrada.</div>';
            return;
        }
        lista.innerHTML = decisoes.map(renderLinhaHistorico).join('');
        lista.querySelectorAll('[data-decisao-detalhe]').forEach((btn) => {
            btn.addEventListener('click', () => consultarDetalheHistorico(btn.dataset.decisaoDetalhe, false));
        });
        lista.querySelectorAll('[data-decisao-replay]').forEach((btn) => {
            btn.addEventListener('click', () => consultarDetalheHistorico(btn.dataset.decisaoReplay, true));
        });
    } catch (error) {
        console.error('Erro ao consultar histórico:', error);
        lista.innerHTML = '<div class="error-simple">❌ Falha controlada ao consultar histórico.</div>';
    }
}

function renderLinhaHistorico(item) {
    const id = item.id || item.decisao_id;
    return `
        <article class="history-row">
            <div class="history-row-main">
                <strong>${escapeHtml(item.ticker || '---')}</strong>
                <span>${escapeHtml(item.decisao || '---')}</span>
                <small>${escapeHtml(item.data_decisao || item.criado_em || 'Data não informada')}</small>
            </div>
            <div class="history-row-audit">
                <span title="${escapeHtml(item.payload_hash || '')}">Hash: ${escapeHtml(resumirHash(item.payload_hash))}</span>
                <span>Hash válido: ${item.hash_valido === true ? 'Sim' : item.hash_valido === false ? 'Não' : 'Não informado'}</span>
            </div>
            <div class="history-actions">
                <button class="btn-mini" data-decisao-detalhe="${escapeHtml(id)}">Ver auditoria</button>
                <button class="btn-mini replay" data-decisao-replay="${escapeHtml(id)}">Executar replay</button>
            </div>
        </article>
    `;
}

async function consultarDetalheHistorico(decisaoId, replayExplicito) {
    const detalhe = document.getElementById('historicoDetalhe');
    if (!detalhe) return;
    detalhe.classList.remove('hidden');
    detalhe.innerHTML = `<div class="loading-simple">⌛ ${replayExplicito ? 'Executando replay explícito' : 'Consultando auditoria'}...</div>`;
    try {
        // Consulta padrão sem replay: replay=false.
        const url = `/api/auditoria/decisoes/${encodeURIComponent(decisaoId)}/auditavel?incluir_payload=true&replay=${replayExplicito ? 'true' : 'false'}`;
        const response = await fetch(url, { headers: headersAutenticados() });
        const data = await response.json();
        detalhe.innerHTML = renderDetalheHistorico(data, replayExplicito);
    } catch (error) {
        console.error('Erro ao consultar detalhe/replay:', error);
        detalhe.innerHTML = '<div class="error-simple">❌ Falha controlada ao consultar detalhe da decisão.</div>';
    }
}

function renderDetalheHistorico(data, replayExplicito) {
    const decisao = data.decisao || {};
    const auditoria = data.auditoria || {};
    const replay = data.replay || { executado: false };
    const payload = data.payload || {};
    const gates = normalizarGatesDetalhes(payload.gates_detalhes || decisao.gates_detalhes || {});
    return `
        <details class="audit-panel history-detail-panel" open>
            <summary>Detalhe auditável da decisão #${escapeHtml(decisao.id || data.decisao_id || '---')}</summary>
            <div class="audit-note">Replay solicitado: <strong>${replayExplicito ? 'Sim' : 'Não'}</strong>. Consulta padrão não reexecuta motor nem scraping.</div>
            <div class="audit-grid">
                <div><span>Ticker</span><strong>${escapeHtml(decisao.ticker || payload.ticker || '---')}</strong></div>
                <div><span>Decisão</span><strong>${escapeHtml(decisao.decisao || payload.decisao || '---')}</strong></div>
                <div><span>Hash salvo</span><strong title="${escapeHtml(auditoria.payload_hash_salvo || decisao.payload_hash || '')}">${escapeHtml(resumirHash(auditoria.payload_hash_salvo || decisao.payload_hash))}</strong></div>
                <div><span>Hash calculado</span><strong title="${escapeHtml(auditoria.payload_hash_calculado || '')}">${escapeHtml(resumirHash(auditoria.payload_hash_calculado))}</strong></div>
                <div><span>Hash válido</span><strong>${auditoria.hash_valido === true ? 'Sim' : auditoria.hash_valido === false ? 'Não' : 'Não informado'}</strong></div>
                <div><span>Contexto</span><strong>${escapeHtml(auditoria.contexto_versao || decisao.contexto_versao || 'Não informado')}</strong></div>
                <div><span>Motor</span><strong>${escapeHtml(auditoria.versao_motor || decisao.versao_motor || 'Não informado')}</strong></div>
                <div><span>Replay</span><strong>${replay.executado ? (replay.divergencia_replay ? 'Divergente' : 'Conferido') : 'Não executado'}</strong></div>
                <div><span>Fonte replay</span><strong>${escapeHtml(replay.fonte_replay || 'Não informado')}</strong></div>
            </div>
            <div class="audit-gates-title">gates_detalhes do payload salvo</div>
            <div class="audit-gates-list">${renderGateDetalhes(gates)}</div>
        </details>
    `;
}

function mockAtivo() {
    return {
        ticker: 'SNAG11', segmento: 'FIAGRO', decisao: 'COMPRAR', confianca: 'ALTA',
        preco_atual: 10.61, preco_justo: 11.08, preco_entrada: 10.50, margem: 4.4,
        pvp: 0.95, dy_12m_pct: 14.57, pct_recorrente: 100,
        trilha_gates: ['G0:APROVADO_DADOS', 'G1:APROVADO_ELEG', 'G2:APROVADO_ESTR'],
        gates_detalhes: { '0': { gate: 0, status: 'APROVADO_DADOS', aprovado: true, fontes: ['contexto'], metricas: { semaforo: 'VERDE' }, motivos: ['Dados mínimos presentes.'], penalidades: [] } },
        payload_hash: 'demo-hash', contexto_versao: 'asset-context-v1.3', versao_motor: 'demo', score_ia: 9,
        motivo: 'Exemplo de card com explicabilidade e auditoria.', alertas: []
    };
}

function escapeHtml(valor) {
    return textoSeguro(valor, '').replace(/[&<>"]/g, (char) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[char]));
}

function asArray(valor) {
    if (!valor) return [];
    if (Array.isArray(valor)) return valor;
    if (typeof valor === 'string') {
        try {
            const parsed = JSON.parse(valor);
            return Array.isArray(parsed) ? parsed : [parsed];
        } catch (e) { return [valor]; }
    }
    return [valor];
}

function asObject(valor) {
    if (!valor) return {};
    if (typeof valor === 'object' && !Array.isArray(valor)) return valor;
    if (typeof valor === 'string') {
        try {
            const parsed = JSON.parse(valor);
            return parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? parsed : {};
        } catch (e) { return {}; }
    }
    return {};
}

function textoSeguro(valor, fallback = 'Não informado') {
    if (valor === null || valor === undefined || valor === '') return fallback;
    return String(valor);
}

function numeroSeguro(valor, fallback = 0) {
    const n = Number(valor);
    return Number.isFinite(n) ? n : fallback;
}

function moeda(valor) {
    const n = Number(valor);
    if (!Number.isFinite(n) || n <= 0) return '---';
    return `R$ ${n.toFixed(2)}`;
}

function percentual(valor, casas = 1) {
    const n = Number(valor);
    if (!Number.isFinite(n)) return '---';
    return `${n > 0 ? '+' : ''}${n.toFixed(casas)}%`;
}

function normalizarClasse(valor) {
    return textoSeguro(valor, 'indefinido').toLowerCase().replace(/\s+/g, '_').replace(/[^a-z0-9_]/g, '_');
}

function resumirHash(hash) {
    const h = textoSeguro(hash, 'Não informado');
    return h.length > 18 ? `${h.slice(0, 12)}…${h.slice(-6)}` : h;
}

function renderListaRotulos(itens, classe = 'audit-chip') {
    const lista = asArray(itens).filter(Boolean).map(item => escapeHtml(textoSeguro(item)));
    if (!lista.length) return '<span class="audit-muted">Não informado</span>';
    return lista.map(item => `<span class="${classe}">${item}</span>`).join('');
}

function normalizarGatesDetalhes(raw) {
    const obj = asObject(raw);
    return Object.keys(obj).sort((a, b) => Number(a) - Number(b)).map((chave) => {
        const gate = obj[chave] || {};
        const metricas = asObject(gate.metricas);
        const status = textoSeguro(gate.status, 'SEM_STATUS');
        const aprovado = gate.aprovado === true || status.toUpperCase().includes('APROVADO');
        const eliminado = gate.eliminado === true || status.toUpperCase().includes('ELIMINADO') || status.toUpperCase().includes('BLOQUE');
        return {
            gate: gate.gate ?? chave,
            status,
            aprovado,
            eliminado,
            motivos: asArray(gate.motivos || gate.motivo).map(item => textoSeguro(item)),
            fontes: asArray(gate.fontes).map(item => textoSeguro(item)),
            penalidades: asArray(gate.penalidades).map(item => textoSeguro(item)),
            metricas
        };
    });
}

function normalizarAuditoria(fii, v) {
    const auditoria = asObject(fii.auditoria || v.auditoria);
    const replay = asObject(fii.replay || v.replay);
    const payload = asObject(fii.payload || v.payload);
    return {
        payload_hash: fii.payload_hash || v.payload_hash || auditoria.payload_hash_salvo || payload.payload_hash,
        hash_valido: auditoria.hash_valido,
        contexto_versao: fii.contexto_versao || v.contexto_versao || auditoria.contexto_versao || payload.contexto_versao,
        versao_motor: fii.versao_motor || v.versao_motor || auditoria.versao_motor || payload.versao_motor || payload.versao_modelo || v.versao_modelo,
        fonte_patrimonial: fii.fonte_patrimonial || v.fonte_patrimonial || payload.fonte_patrimonial,
        score_confianca_dados: fii.score_confianca_dados ?? v.score_confianca_dados ?? payload.score_confianca_dados,
        nivel_uso_dados: fii.nivel_uso_dados || v.nivel_uso_dados || payload.nivel_uso_dados,
        permitir_decisao: fii.permitir_decisao ?? v.permitir_decisao ?? payload.permitir_decisao,
        gate_parada: fii.gate_parada ?? v.gate_parada ?? payload.gate_parada,
        motivo_bloqueio: fii.motivo_bloqueio || v.motivo_bloqueio || payload.motivo_bloqueio,
        campos_ausentes: asArray(fii.campos_ausentes || v.campos_ausentes || payload.campos_ausentes),
        campos_vencidos: asArray(fii.campos_vencidos || v.campos_vencidos || payload.campos_vencidos),
        fontes_falharam: asArray(fii.fontes_falharam || v.fontes_falharam || payload.fontes_falharam),
        gates_detalhes: normalizarGatesDetalhes(fii.gates_detalhes || v.gates_detalhes || payload.gates_detalhes),
        replay
    };
}

function normalizarFii(fii) {
    const v = fii.veredito || {};
    const ind = fii.indicadores || {};
    let trilha_gates = asArray(fii.trilha_gates || v.trilha_gates || []);
    let dy_12m_pct = fii.dy_12m_pct ?? v.dy_12m_pct ?? ((v.dy_12m || ind.dy_12m || 0) * 100);
    if (dy_12m_pct > 0 && dy_12m_pct < 1.0) dy_12m_pct *= 100;
    const auditoria = normalizarAuditoria(fii, v);
    return {
        ticker: fii.ticker || v.ticker || '---', segmento: fii.segmento || v.segmento || 'FII',
        decisao: fii.decisao || v.decisao || 'MONITORAR', confianca: fii.confianca || v.confianca || 'MEDIA',
        preco_atual: fii.preco_atual ?? v.preco_atual ?? v.preco_na_decisao ?? 0.0,
        preco_justo: fii.preco_justo ?? v.preco_justo ?? 0.0,
        preco_entrada: fii.preco_entrada ?? v.preco_entrada ?? v.preco_teto ?? 0.0,
        margem: fii.margem ?? v.margem ?? v.margem_seguranca ?? 0.0,
        pvp: fii.pvp ?? v.pvp ?? ind.pvp ?? 1.0,
        dy_12m_pct, pct_recorrente: fii.pct_recorrente ?? v.pct_recorrente ?? 100.0,
        trilha_gates: trilha_gates.length ? trilha_gates : ['G0:DADOS_OK', 'G1:ELEGIVEL'],
        score_ia: fii.score_ia ?? v.score_ia ?? 7.0, motivo: fii.motivo || v.motivo || 'Ativo em monitoramento.',
        alertas: asArray(fii.alertas || v.alertas || []), quantidade: fii.quantidade ?? 0,
        preco_medio: fii.preco_medio ?? 0.0, custo_total: fii.custo_total ?? 0.0,
        revisao: fii.revisao || v.revisao || 'Próximo Radar', auditoria
    };
}

function renderResumoExplicabilidade(fii) {
    const auditoria = fii.auditoria;
    const bloqueado = auditoria.permitir_decisao === false || normalizarClasse(fii.decisao).includes('bloqueado');
    return `
        <section class="explain-summary ${bloqueado ? 'explain-blocked' : ''}">
            <div class="explain-item"><span>Status operacional</span><strong>${bloqueado ? 'Bloqueado / cautela' : 'Exibível'}</strong></div>
            <div class="explain-item"><span>Gate de parada</span><strong>${escapeHtml(textoSeguro(auditoria.gate_parada))}</strong></div>
            <div class="explain-item"><span>Fonte principal</span><strong>${escapeHtml(textoSeguro(auditoria.fonte_patrimonial, 'Não informada'))}</strong></div>
            <div class="explain-item"><span>Score dados</span><strong>${escapeHtml(textoSeguro(auditoria.score_confianca_dados))}</strong></div>
            ${bloqueado ? `<div class="explain-reason"><strong>Motivo:</strong> ${escapeHtml(textoSeguro(auditoria.motivo_bloqueio, 'Sem motivo específico informado.'))}</div>` : ''}
        </section>
    `;
}

function renderGateDetalhes(gates) {
    if (!gates || gates.length === 0) {
        return '<div class="audit-empty">Detalhamento de gates não informado. O card permanece visível para auditoria.</div>';
    }
    return gates.map(gate => {
        const metricas = Object.keys(gate.metricas || {}).slice(0, 6).map(k => `<span class="audit-metric"><b>${escapeHtml(k)}</b>: ${escapeHtml(gate.metricas[k])}</span>`).join('');
        const estadoClasse = gate.eliminado ? 'gate-eliminado' : gate.aprovado ? 'gate-aprovado' : 'gate-neutro';
        return `
            <div class="audit-gate ${estadoClasse}">
                <div class="audit-gate-head"><strong>Gate ${escapeHtml(gate.gate)}</strong><span>${escapeHtml(gate.status)}</span></div>
                <div class="audit-gate-body">
                    <div><em>Motivos</em>${renderListaRotulos(gate.motivos)}</div>
                    <div><em>Fontes</em>${renderListaRotulos(gate.fontes)}</div>
                    ${metricas ? `<div class="audit-metrics"><em>Métricas</em>${metricas}</div>` : '<div><em>Métricas</em><span class="audit-muted">Não informado</span></div>'}
                    <div><em>Penalidades</em>${renderListaRotulos(gate.penalidades, 'audit-chip penalty')}</div>
                </div>
            </div>
        `;
    }).join('');
}

function renderAuditoria(auditoria) {
    const bloqueios = [...auditoria.campos_ausentes, ...auditoria.campos_vencidos, ...auditoria.fontes_falharam];
    const replay = auditoria.replay || {};
    return `
        <details class="audit-panel">
            <summary>Auditoria e explicabilidade</summary>
            <div class="audit-note">Hash e payload auditável são apenas exibidos. O frontend não recalcula integridade.</div>
            <div class="audit-grid">
                <div><span>Hash salvo</span><strong title="${escapeHtml(textoSeguro(auditoria.payload_hash))}">${escapeHtml(resumirHash(auditoria.payload_hash))}</strong></div>
                <div><span>Hash válido</span><strong>${auditoria.hash_valido === undefined ? 'Não informado' : auditoria.hash_valido ? 'Sim' : 'Não'}</strong></div>
                <div><span>Contexto</span><strong>${escapeHtml(textoSeguro(auditoria.contexto_versao))}</strong></div>
                <div><span>Motor</span><strong>${escapeHtml(textoSeguro(auditoria.versao_motor))}</strong></div>
                <div><span>Fonte patrimonial</span><strong>${escapeHtml(textoSeguro(auditoria.fonte_patrimonial))}</strong></div>
                <div><span>Confiança dados</span><strong>${escapeHtml(textoSeguro(auditoria.score_confianca_dados))} / ${escapeHtml(textoSeguro(auditoria.nivel_uso_dados))}</strong></div>
                <div><span>Permitir decisão</span><strong>${auditoria.permitir_decisao === false ? 'Não' : auditoria.permitir_decisao === true ? 'Sim' : 'Não informado'}</strong></div>
                <div><span>Replay</span><strong>${replay.executado ? (replay.divergencia_replay ? 'Divergente' : 'Conferido') : 'Não executado'}</strong></div>
            </div>
            ${bloqueios.length ? `<div class="audit-blocks"><strong>Bloqueios/falhas:</strong><div class="audit-chip-row">${renderListaRotulos(bloqueios, 'audit-chip danger')}</div></div>` : ''}
            <div class="audit-gates-title">gates_detalhes</div>
            <div class="audit-gates-list">${renderGateDetalhes(auditoria.gates_detalhes)}</div>
        </details>
    `;
}

function renderResults(oportunidades, targetId = 'results', isPortfolio = false) {
    const grid = document.getElementById(targetId);
    if (!grid) return;
    grid.innerHTML = '';
    if (!oportunidades || oportunidades.length === 0) {
        grid.innerHTML = '<div class="empty-state-container glass-card"><h3>Nenhum ativo encontrado</h3><p>Não há cards para exibir neste momento.</p></div>';
        return;
    }
    oportunidades.forEach((raw) => {
        const fii = normalizarFii(raw || {});
        const bloqueado = fii.auditoria.permitir_decisao === false || normalizarClasse(fii.decisao).includes('bloqueado');
        const card = document.createElement('div');
        card.className = `fii-card ${bloqueado ? 'card-bloqueado' : ''}`;
        card.innerHTML = `
            <div class="card-header"><div class="ticker-box"><span class="ticker-symbol">${escapeHtml(fii.ticker)}</span><span class="segment-badge">${escapeHtml(fii.segmento)}</span></div><div class="decision-badge ${normalizarClasse(fii.decisao)}">${escapeHtml(fii.decisao.replace('_', ' '))}</div></div>
            <div class="confidence-bar"><span class="label">Confiança:</span><span class="confidence-value ${normalizarClasse(fii.confianca)}">${escapeHtml(fii.confianca)}</span></div>
            ${renderResumoExplicabilidade(fii)}
            ${isPortfolio ? `<div class="holding-details-container glass-card"><div class="holding-metric"><span class="label">Minhas Cotas</span><span class="value">${escapeHtml(fii.quantidade)}</span></div><div class="holding-metric"><span class="label">Preço Médio</span><span class="value">${moeda(fii.preco_medio)}</span></div><div class="holding-metric highlight"><span class="label">Total Aplicado</span><span class="value">R$ ${numeroSeguro(fii.custo_total).toLocaleString('pt-BR', {minimumFractionDigits: 2, maximumFractionDigits: 2})}</span></div></div>` : ''}
            <div class="price-grid"><div class="price-item"><span class="label">Preço Atual</span><span class="value">${moeda(fii.preco_atual)}</span></div><div class="price-item highlight"><span class="label">Preço Justo</span><span class="value">${moeda(fii.preco_justo)}</span></div><div class="price-item"><span class="label">Entrada Ideal</span><span class="value">${moeda(fii.preco_entrada)}</span></div></div>
            <div class="metrics-grid"><div class="metric"><span class="label">Margem</span><span class="value ${numeroSeguro(fii.margem) > 0 ? 'pos' : 'neg'}">${percentual(fii.margem)}</span></div><div class="metric"><span class="label">P/VP</span><span class="value">${numeroSeguro(fii.pvp).toFixed(2)}</span></div><div class="metric"><span class="label">DY 12M</span><span class="value">${percentual(fii.dy_12m_pct)}</span></div><div class="metric"><span class="label">Recorrência</span><span class="value">${escapeHtml(textoSeguro(fii.pct_recorrente, '---'))}%</span></div></div>
            <div class="gate-trail"><div class="gate-title">Esteira de Qualidade (8 Gates)</div><div class="gates-container">${fii.trilha_gates.map(gate => `<span class="gate-tag">${escapeHtml(gate)}</span>`).join('')}</div></div>
            <div class="ai-analysis"><div class="ai-header"><span class="ai-icon">🧠</span><span class="ai-label">Inteligência FIIA</span><span class="ai-score">Score: ${escapeHtml(fii.score_ia || '?')}/10</span></div><div class="ai-content">${escapeHtml(fii.motivo || 'Aguardando processamento...')}</div></div>
            ${fii.alertas.length ? `<div class="alerts-box">${fii.alertas.map(alert => `<div class="alert-item">⚠️ ${escapeHtml(alert)}</div>`).join('')}</div>` : ''}
            ${renderAuditoria(fii.auditoria)}
            <div class="card-footer"><span class="footer-info">Próxima Revisão: ${escapeHtml(fii.revisao)}</span></div>
        `;
        grid.appendChild(card);
    });
}
