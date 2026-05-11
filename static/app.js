/**
 * app.js - FIIA Intelligence Interface
 * Versão 2.0 - Integração com Motor de Decisão
 */

document.getElementById('btnRadar').addEventListener('click', async () => {
    const welcomeView = document.getElementById('welcomeView');
    const loading = document.getElementById('loading');
    const resultsGrid = document.getElementById('results');
    const btnRadar = document.getElementById('btnRadar');
    
    // UI State: Loading
    welcomeView.classList.add('hidden');
    resultsGrid.classList.add('hidden');
    loading.classList.remove('hidden');
    btnRadar.disabled = true;
    btnRadar.innerHTML = '<span class="icon">⌛</span> Processando...';

    try {
        const response = await fetch('/api/radar');
        const data = await response.json();
        
        loading.classList.add('hidden');
        resultsGrid.classList.remove('hidden');
        renderResults(data.oportunidades);
    } catch (error) {
        console.error(error);
        alert('Erro ao ligar o radar. Verifique se o servidor está rodando ou se a chave API é válida.');
        loading.classList.add('hidden');
        welcomeView.classList.remove('hidden');
    } finally {
        btnRadar.disabled = false;
        btnRadar.innerHTML = '<span class="icon">🔍</span> Ligar Radar';
    }
});

document.getElementById('btnClear').addEventListener('click', () => {
    window.location.reload();
});

function renderResults(oportunidades) {
    const grid = document.getElementById('results');
    grid.innerHTML = ''; // Limpa resultados anteriores
    
    oportunidades.forEach((fii, index) => {
        const card = document.createElement('div');
        card.className = 'fii-card';
        
        // Dados do motor de decisão
        const v = fii.veredito || {};
        const qual = fii.qualitativo || {};
        
        // Classes de status
        const statusClass = `status-${v.decisao?.toLowerCase().replace('_', '-') || 'monitorar'}`;
        const emojiDecisao = {
            'COMPRAR': '🟢', 'COMPRAR_PARCIAL': '🟡', 'AGUARDAR': '🔵', 
            'MANTER': '⚪', 'MONITORAR': '🟠', 'EVITAR': '🔴'
        }[v.decisao] || '⚪';

        const fmtReais = (val) => val ? `R$ ${parseFloat(val).toLocaleString('pt-BR', {minimumFractionDigits: 2})}` : 'N/A';
        const fmtPct = (val) => val ? `${val > 0 ? '+' : ''}${parseFloat(val).toFixed(1)}%` : 'N/A';

        card.innerHTML = `
            <div class="card-header">
                <div class="ticker-info">
                    <h3>${fii.ticker}</h3>
                    <span class="segment-badge">${v.segmento || 'Fundo'}</span>
                </div>
                <div class="veredito-badge ${statusClass}">
                    ${emojiDecisao} ${v.decisao?.replace('_', ' ') || 'ANALISANDO'}
                </div>
            </div>
            
            <div class="prices-grid">
                <div class="price-item">
                    <span class="price-label">Preço Atual</span>
                    <span class="price-value">${fmtReais(v.preco_atual)}</span>
                </div>
                <div class="price-item">
                    <span class="price-label">Preço Justo</span>
                    <span class="price-value">${fmtReais(v.preco_justo)}</span>
                </div>
                <div class="price-item">
                    <span class="price-label">Entrada Ideal</span>
                    <span class="price-value price-highlight">${fmtReais(v.preco_entrada)}</span>
                </div>
            </div>

            <div style="display: flex; gap: 20px; margin-bottom: 20px; font-size: 0.85rem; color: var(--text-dim);">
                <div>Margem: <strong style="color: var(--text-main)">${fmtPct(v.margem)}</strong></div>
                <div>P/VP: <strong style="color: var(--text-main)">${v.pvp || 'N/A'}</strong></div>
                <div>DY 12M: <strong style="color: var(--text-main)">${fmtPct(v.dy_12m_pct)}</strong></div>
            </div>

            <div class="card-ia">
                <div class="ia-header">
                    <span class="ia-title">🧠 Inteligência FIIA</span>
                    <span class="ia-score">Score: ${v.score_ia || '?'}/10</span>
                </div>
                <p class="ia-resumo">${qual.resumo || 'Análise qualitativa não realizada para este fundo (fora do Top 3 ou bloqueada).'}</p>
                <div class="riscos-tags">
                    ${(v.riscos_ia || []).slice(0, 3).map(r => `<span class="tag-risco">${r}</span>`).join('')}
                    ${v.ia_status === 'BLOQUEADO_DADOS_INSUFICIENTES' ? '<span class="tag-risco">Dados insuficientes p/ IA</span>' : ''}
                </div>
            </div>
            
            <div style="margin-top: 15px; font-size: 0.75rem; color: var(--text-dim);">
                <p><strong>Motivo:</strong> ${v.motivo || 'N/A'}</p>
            </div>
        `;
        
        grid.appendChild(card);
    });
}
