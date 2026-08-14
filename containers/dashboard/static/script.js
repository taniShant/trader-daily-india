// Dashboard JavaScript
let pnlChart = null;
let currentTab = 'trades';

// Tab switching
function switchTab(tabName, button) {
    currentTab = tabName;
    
    // Update tab buttons
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.classList.remove('active');
    });
    if (button) button.classList.add('active');
    
    ['pnlChartCard', 'tradesCard', 'learningCard', 'marketCard', 'signalsCard', 'statusCard', 'controlsCard', 'intelligenceCard'].forEach(id => {
        document.getElementById(id).style.display = 'none';
    });

    if (tabName === 'trades') {
        document.getElementById('filters').style.display = 'flex';
        document.getElementById('pnlChartCard').style.display = 'block';
        document.getElementById('tradesCard').style.display = 'block';
        fetchTrades();
        fetchPNL();
    } else if (tabName === 'signals') {
        document.getElementById('filters').style.display = 'none';
        document.getElementById('signalsCard').style.display = 'block';
        fetchSignals();
    } else if (tabName === 'statusView') {
        document.getElementById('filters').style.display = 'none';
        document.getElementById('statusCard').style.display = 'block';
        fetchStatus();
    } else if (tabName === 'controls') {
        document.getElementById('filters').style.display = 'none';
        document.getElementById('controlsCard').style.display = 'block';
    } else if (tabName === 'learning') {
        document.getElementById('filters').style.display = 'none';
        document.getElementById('learningCard').style.display = 'block';
        fetchLearningPatterns();
    } else if (tabName === 'market') {
        document.getElementById('filters').style.display = 'none';
        document.getElementById('marketCard').style.display = 'block';
        fetchMarketState();
    } else if (tabName === 'intelligence') {
        document.getElementById('filters').style.display = 'none';
        document.getElementById('intelligenceCard').style.display = 'block';
        fetchIntelligence();
    }
}

// Fetch bot status
async function fetchStatus() {
    try {
        const res = await fetch('/api/status');
        const data = await res.json();
        
        document.getElementById('positions').textContent = data.active_positions || 0;
        const risk = data.risk_usage || {};
        
        const pnlValue = data.today_pnl || 0;
        const pnlElement = document.getElementById('pnl');
        pnlElement.innerHTML = pnlValue >= 0 ? `+₹${pnlValue.toFixed(2)}` : `-₹${Math.abs(pnlValue).toFixed(2)}`;
        pnlElement.className = pnlValue >= 0 ? 'stat-value positive' : 'stat-value negative';

        const profitValue = Number(risk.today_profit || 0);
        const profitElement = document.getElementById('todayProfit');
        profitElement.innerHTML = `₹${profitValue.toFixed(2)}`;
        profitElement.className = 'stat-value positive';
        
        document.getElementById('winrate').textContent = `${(data.win_rate || 0).toFixed(1)}%`;
        
        const statusHtml = `<span class="status-badge status-${data.status}">${data.status}</span>`;
        document.getElementById('status').innerHTML = statusHtml;
        renderStatusDetails(data);
    } catch(e) {
        console.error('Status fetch failed:', e);
    }
}

function renderStatusDetails(data) {
    const heartbeat = data.heartbeat || {};
    const risk = data.risk_usage || {};
    document.getElementById('heartbeatDetails').innerHTML = `
        <dt>Mode</dt><dd>${data.mode || '-'}</dd>
        <dt>Market</dt><dd>${data.market_hours || '-'}</dd>
        <dt>Last analysis</dt><dd>${data.last_analysis || '-'}</dd>
        <dt>Cycle</dt><dd>${heartbeat.cycle ?? '-'}</dd>
    `;
    document.getElementById('riskDetails').innerHTML = `
        <dt>Today profit</dt><dd>₹${Number(risk.today_profit || 0).toFixed(2)}</dd>
        <dt>Today loss</dt><dd>₹${Number(risk.today_loss || 0).toFixed(2)}</dd>
        <dt>Today P&L</dt><dd>₹${Number(risk.today_pnl || 0).toFixed(2)}</dd>
        <dt>Daily loss limit</dt><dd>${risk.daily_loss_limit || '-'}%</dd>
        <dt>Trades</dt><dd>${risk.trade_count || 0}</dd>
    `;

    const tbody = document.querySelector('#positionsTable tbody');
    const positions = data.open_positions || [];
    if (positions.length === 0) {
        tbody.innerHTML = '<tr><td colspan="5" class="loading">No open positions</td></tr>';
        return;
    }
    tbody.innerHTML = positions.map(position => `
        <tr>
            <td><strong>${position.symbol || '-'}</strong></td>
            <td>${position.quantity || 0}</td>
            <td>₹${Number(position.average_price || 0).toFixed(2)}</td>
            <td>₹${Number(position.last_price || 0).toFixed(2)}</td>
            <td class="${Number(position.unrealized_pnl || 0) >= 0 ? 'positive' : 'negative'}">₹${Number(position.unrealized_pnl || 0).toFixed(2)}</td>
        </tr>
    `).join('');
}

// Fetch recent trades
async function fetchTrades() {
    if (currentTab !== 'trades') return;
    
    try {
        const stock = document.getElementById('stockFilter').value;
        const days = document.getElementById('daysFilter').value;
        
        let url = `/api/trades?limit=50&days=${days}`;
        if (stock) url += `&stock=${stock}`;
        
        const res = await fetch(url);
        const data = await res.json();
        
        const tbody = document.querySelector('#tradesTable tbody');
        
        if (!data.trades || data.trades.length === 0) {
            tbody.innerHTML = '<tr><td colspan="7" class="loading">No trades found</td></tr>';
            return;
        }
        
        tbody.innerHTML = data.trades.map(trade => {
            const price = Number(trade.price || 0);
            const quantity = Math.abs(Number(trade.quantity || 0));
            const tradeValue = price * quantity;
            const pnl = Number(trade.pnl || 0);

            return `
                <tr>
                    <td>${trade.timestamp ? new Date(trade.timestamp).toLocaleString() : '-'}</td>
                    <td><strong>${trade.stock_symbol || 'N/A'}</strong></td>
                    <td class="${(trade.action || '').toLowerCase()}">${trade.action || 'HOLD'}</td>
                    <td>₹${price.toFixed(2)}</td>
                    <td>${trade.quantity || 0}</td>
                    <td>₹${tradeValue.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</td>
                    <td class="${pnl >= 0 ? 'positive' : 'negative'}">
                        ${pnl >= 0 ? '+' : ''}₹${pnl.toFixed(2)}
                    </td>
                </tr>
            `;
        }).join('');
    } catch(e) {
        console.error('Trades fetch failed:', e);
    }
}

async function fetchSignals() {
    if (currentTab !== 'signals') return;

    try {
        const res = await fetch('/api/signals?limit=100');
        const data = await res.json();
        const tbody = document.querySelector('#signalsTable tbody');

        if (!data.signals || data.signals.length === 0) {
            tbody.innerHTML = '<tr><td colspan="6" class="loading">No signals found</td></tr>';
            return;
        }

        tbody.innerHTML = data.signals.map(signal => {
            const reasons = signal.skip_reasons && signal.skip_reasons.length ? signal.skip_reasons : signal.reasons || [];
            return `
                <tr>
                    <td>${signal.created_at ? new Date(signal.created_at).toLocaleString() : '-'}</td>
                    <td><strong>${signal.symbol || '-'}</strong></td>
                    <td class="${(signal.action || '').toLowerCase()}">${signal.action || '-'}</td>
                    <td>${signal.confidence ?? '-'}</td>
                    <td><span class="status-badge status-${(signal.trade_status || '').toLowerCase()}">${signal.trade_status || '-'}</span></td>
                    <td>${reasons.join(', ') || '-'}</td>
                </tr>
            `;
        }).join('');
    } catch(e) {
        console.error('Signals fetch failed:', e);
    }
}

async function submitControl(action) {
    const token = document.getElementById('controlToken').value;
    const result = document.getElementById('controlResult');
    const isKill = action === 'kill-switch';
    const reason = document.getElementById(isKill ? 'killReason' : 'squareReason').value;
    const symbol = isKill ? null : document.getElementById('squareSymbol').value || null;

    try {
        const res = await fetch(`/api/controls/${action}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'x-dashboard-token': token
            },
            body: JSON.stringify({ reason, symbol })
        });
        const data = await res.json();
        result.textContent = res.ok ? `Accepted: ${data.command.command_id}` : `Rejected: ${data.detail}`;
        result.className = res.ok ? 'control-result positive' : 'control-result negative';
    } catch(e) {
        result.textContent = 'Control request failed';
        result.className = 'control-result negative';
    }
}

// Fetch P&L data and update chart
async function fetchPNL() {
    if (currentTab !== 'trades') return;
    
    try {
        const days = document.getElementById('daysFilter').value;
        const res = await fetch(`/api/pnl?days=${days}`);
        const data = await res.json();
        
        if (pnlChart) pnlChart.destroy();
        
        const ctx = document.getElementById('pnlChart').getContext('2d');
        pnlChart = new Chart(ctx, {
            type: 'line',
            data: {
                labels: data.dates || [],
                datasets: [
                    {
                        label: 'Cumulative P&L',
                        data: data.cumulative_pnl || [],
                        borderColor: '#38bdf8',
                        backgroundColor: 'rgba(56, 189, 248, 0.1)',
                        fill: true,
                        tension: 0.1
                    },
                    {
                        label: 'Daily P&L',
                        data: data.daily_pnl || [],
                        borderColor: '#eab308',
                        backgroundColor: 'transparent',
                        borderDash: [5, 5],
                        tension: 0.1
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: true,
                plugins: {
                    legend: { position: 'top', labels: { color: '#e2e8f0' } },
                    tooltip: { callbacks: { label: (ctx) => `${ctx.dataset.label}: ₹${ctx.raw.toFixed(2)}` } }
                },
                scales: { y: { ticks: { color: '#94a3b8' }, grid: { color: '#334155' } },
                          x: { ticks: { color: '#94a3b8', maxRotation: 45 }, grid: { color: '#334155' } } }
            }
        });
    } catch(e) {
        console.error('PNL fetch failed:', e);
    }
}

// Fetch learning patterns
async function fetchLearningPatterns() {
    try {
        const res = await fetch('/api/learning?limit=20');
        const data = await res.json();
        
        const tbody = document.querySelector('#learningTable tbody');
        
        if (!data.patterns || data.patterns.length === 0) {
            tbody.innerHTML = '<tr><td colspan="6" class="loading">No learning patterns yet</td></tr>';
            return;
        }
        
        tbody.innerHTML = data.patterns.map(pattern => `
            <tr>
                <td>${pattern.date || '-'}</td>
                <td>${pattern.pattern_type || '-'}</td>
                <td>${pattern.rsi_range || '-'}</td>
                <td>${pattern.sentiment_threshold || '-'}</td>
                <td class="${(pattern.win_rate || 0) >= 50 ? 'positive' : 'negative'}">${(pattern.win_rate || 0).toFixed(1)}%</td>
                <td>${pattern.sample_size || 0}</td>
            </tr>
        `).join('');
    } catch(e) {
        console.error('Learning patterns fetch failed:', e);
    }
}

// Fetch market state
async function fetchMarketState() {
    try {
        const res = await fetch('/api/market-state?days=7');
        const data = await res.json();
        
        const tbody = document.querySelector('#marketTable tbody');
        
        if (!data.market_states || data.market_states.length === 0) {
            tbody.innerHTML = '<tr><td colspan="5" class="loading">No market state data yet</td></tr>';
            return;
        }
        
        tbody.innerHTML = data.market_states.map(state => `
            <tr>
                <td>${state.date || '-'}</td>
                <td class="${state.global_sentiment === 'positive' ? 'positive' : (state.global_sentiment === 'negative' ? 'negative' : '')}">
                    ${state.global_sentiment || 'neutral'}
                </td>
                <td>${state.india_vix || '-'}</td>
                <td>${(state.watchlist || []).join(', ') || '-'}</td>
                <td>${(state.key_news || []).slice(0, 2).join(', ') || '-'}</td>
            </tr>
        `).join('');
    } catch(e) {
        console.error('Market state fetch failed:', e);
    }
}

async function fetchIntelligence() {
    try {
        const res = await fetch('/api/intelligence');
        const data = await res.json();
        const health = data.source_health || {};
        const macro = data.global_macro || {};
        const latestNews = data.latest_news || {};

        document.getElementById('sourceHealthDetails').innerHTML = `
            <dt>Status</dt><dd><span class="status-badge status-${health.status || 'pending'}">${health.status || '-'}</span></dd>
            <dt>Score</dt><dd>${Number(health.score ?? 0).toFixed(2)}</dd>
            <dt>Blocked</dt><dd>${health.live_trade_blocked ? 'yes' : 'no'}</dd>
            <dt>Reasons</dt><dd>${(health.reasons || []).join(', ') || '-'}</dd>
        `;
        document.getElementById('globalMacroDetails').innerHTML = `
            <dt>Sentiment</dt><dd>${macro.global_sentiment || '-'}</dd>
            <dt>Updated</dt><dd>${macro.updated_at || '-'}</dd>
            <dt>News sentiment</dt><dd>${latestNews.latest_sentiment ?? '-'}</dd>
            <dt>News updated</dt><dd>${latestNews.updated_at || '-'}</dd>
        `;

        const tbody = document.querySelector('#intelligenceTable tbody');
        const events = data.events || [];
        if (events.length === 0) {
            tbody.innerHTML = '<tr><td colspan="3" class="loading">No intelligence events found</td></tr>';
            return;
        }
        tbody.innerHTML = events.map(event => `
            <tr>
                <td>${event.type || '-'}</td>
                <td>${event.title || '-'}</td>
                <td>${event.source || '-'}</td>
            </tr>
        `).join('');
    } catch(e) {
        console.error('Intelligence fetch failed:', e);
    }
}

// Fetch all data based on current tab
async function fetchAllData() {
    const now = new Date();
    document.getElementById('lastUpdated').textContent = `Last updated: ${now.toLocaleTimeString()}`;
    
    await fetchStatus();
    
    if (currentTab === 'trades') {
        await fetchTrades();
        await fetchPNL();
    } else if (currentTab === 'signals') {
        await fetchSignals();
    } else if (currentTab === 'statusView') {
        await fetchStatus();
    } else if (currentTab === 'learning') {
        await fetchLearningPatterns();
    } else if (currentTab === 'market') {
        await fetchMarketState();
    } else if (currentTab === 'intelligence') {
        await fetchIntelligence();
    }
}

// Auto-refresh every 30 seconds
fetchAllData();
setInterval(fetchAllData, 30000);
