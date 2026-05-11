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
                <div class="ticker-box">
                    <span class="ticker-symbol">${fii.ticker}</span>
                    <span class="segment-badge">${fii.segmento || 'FII'}</span>
                </div>
                <div class="decision-badge ${fii.decisao.toLowerCase()}">${fii.decisao.replace('_', ' ')}</div>
            </div>

            <div class="confidence-bar">
                <span class="label">Confiança:</span>
                <span class="confidence-value ${fii.confianca.toLowerCase()}">${fii.confianca}</span>
            </div>

            <div class="price-grid">
                <div class="price-item">
                    <span class="label">Preço Atual</span>
                    <span class="value">R$ ${fii.preco_atual?.toFixed(2) || '---'}</span>
                </div>
                <div class="price-item highlight">
                    <span class="label">Preço Justo</span>
                    <span class="value">R$ ${fii.preco_justo?.toFixed(2) || '---'}</span>
                </div>
                <div class="price-item">
                    <span class="label">Entrada Ideal</span>
                    <span class="value">R$ ${fii.preco_entrada?.toFixed(2) || '---'}</span>
                </div>
            </div>

            <div class="metrics-grid">
                <div class="metric">
                    <span class="label">Margem</span>
                    <span class="value ${fii.margem > 0 ? 'pos' : 'neg'}">${fii.margem > 0 ? '+' : ''}${fii.margem}%</span>
                </div>
                <div class="metric">
                    <span class="label">P/VP</span>
                    <span class="value">${fii.pvp?.toFixed(2) || '---'}</span>
                </div>
                <div class="metric">
                    <span class="label">DY 12M</span>
                    <span class="value">+${fii.dy_12m_pct?.toFixed(1) || '---'}%</span>
                </div>
                <div class="metric">
                    <span class="label">Recorrência</span>
                    <span class="value">${fii.pct_recorrente || '---'}%</span>
                </div>
            </div>

            <div class="gate-trail">
                <div class="gate-title">Esteira de Qualidade (8 Gates)</div>
                <div class="gates-container">
                    ${fii.trilha_gates.map(gate => `<span class="gate-tag">${gate}</span>`).join('')}
                </div>
            </div>

            <div class="ai-analysis">
                <div class="ai-header">
                    <span class="ai-icon">🧠</span>
                    <span class="ai-label">Inteligência FIIA</span>
                    <span class="ai-score">Score: ${fii.score_ia || '?'}/10</span>
                </div>
                <div class="ai-content">
                    ${fii.motivo || 'Aguardando processamento...'}
                </div>
            </div>

            ${fii.alertas && fii.alertas.length > 0 ? `
                <div class="alerts-box">
                    ${fii.alertas.map(alert => `<div class="alert-item">⚠️ ${alert}</div>`).join('')}
                </div>
            ` : ''}

            <div class="card-footer">
                <span class="footer-info">Próxima Revisão: ${fii.revisao || 'Próximo Radar'}</span>
            </div>
        `;
        
        grid.appendChild(card);
    });
}
