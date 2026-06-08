// ─── XSS Prevention ───────────────────────────────────────────
function escapeHtml(str) {
  if (str === null || str === undefined) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

function fmt(num) {
  return Number(num).toLocaleString('en-IN', { maximumFractionDigits: 2 });
}

// Global Error Visualizer for Debugging
function showError(msg) {
  const errDiv = document.createElement('div');
  errDiv.style.cssText = 'position:fixed;top:0;left:0;width:100%;background:#ef4444;color:#fff;padding:12px;z-index:999999;font-family:monospace;font-size:13px;box-shadow:0 4px 12px rgba(0,0,0,0.3);text-align:center';
  errDiv.innerHTML = `<strong>⚠️ Browser Console Error Detected:</strong> ${escapeHtml(msg)} <span style="cursor:pointer;margin-left:15px;text-decoration:underline" onclick="this.parentElement.remove()">[Dismiss]</span>`;
  document.body.appendChild(errDiv);
}

window.onerror = function(message, source, lineno, colno, error) {
  showError(`JS Error: ${message} at line ${lineno}, col ${colno} (${source})`);
  return false;
};

window.addEventListener('unhandledrejection', function(event) {
  showError(`Unhandled Promise Rejection: ${event.reason?.stack || event.reason?.message || event.reason}`);
});


// CRIT-05: In-memory token store — never persist JWTs to sessionStorage (XSS risk)
// tokenStore lives only in this closure; cleared on page reload (correct security trade-off)
const _tokenStore = (() => {
  let _t = null;
  return { set: (t) => { _t = t; }, get: () => _t, clear: () => { _t = null; } };
})();

const API = '';
const AUTH_KEY = 'smartretail_token';   // kept only for legacy session restore (removed below)
const USER_KEY = 'smartretail_user';    // user info (non-secret) may stay in sessionStorage
let products = [], cart = [], csvData = null, charts = {}, currentUser = null, allProducts = [];
let forecastDays = 7;
let modelsReady = false;

// ─── Page breadcrumb names ─────────────────────────────────────
const PAGE_NAMES = {
  dashboard: 'Sales Dashboard',
  billing: 'POS Billing',
  inventory: 'Inventory Manager',
  predictions: 'AI Predictions',
  reports: 'Reports & Analytics',
  festivals: 'Festival Calendar',
  settings: 'Settings',
  admin: 'Admin Panel',
};

function applyRoleUI() {
  const role = currentUser?.role || 'Staff';
  const adminNav = document.getElementById('nav-admin');
  if (adminNav) adminNav.style.display = role === 'Admin' ? 'flex' : 'none';
  const addBtn = document.getElementById('btnAddProduct');
  if (addBtn) addBtn.style.display = (role === 'Admin' || role === 'Manager') ? 'inline-flex' : 'none';
  const logoutBtn = document.getElementById('btnLogout');
  // CRIT-05: check _tokenStore instead of sessionStorage
  if (logoutBtn) logoutBtn.style.display = _tokenStore.get() ? 'inline-flex' : 'none';
}

function updateUserDisplay() {
  if (!currentUser) return;
  const initial = (currentUser.username || '?')[0].toUpperCase();
  const sAvatar = document.getElementById('sidebarAvatar');
  const sName = document.getElementById('sidebarUserName');
  const sRole = document.getElementById('sidebarUserRole');
  if (sAvatar) sAvatar.textContent = initial;
  if (sName) sName.textContent = currentUser.username;
  if (sRole) sRole.textContent = currentUser.role + ' Account';
  const avatar = document.getElementById('userAvatar');
  if (avatar) avatar.textContent = initial;
}

function canAccess(page) {
  const role = currentUser?.role || 'Staff';
  if (page === 'admin') return role === 'Admin';
  if (page === 'inventory' && arguments.length) return ['Admin', 'Manager', 'Staff'].includes(role);
  return true;
}

function getAuthHeaders() {
  const headers = { 'Content-Type': 'application/json', 'X-Requested-With': 'XMLHttpRequest' };
  // CRIT-05: read token from in-memory store, not sessionStorage
  const token = _tokenStore.get();
  if (token) headers['Authorization'] = 'Bearer ' + token;
  return headers;
}

async function doLogin() {
  const username = document.getElementById('loginUsername')?.value?.trim();
  const password = document.getElementById('loginPassword')?.value || '';
  const errEl = document.getElementById('loginError');
  if (!username || !password) {
    if (errEl) { errEl.textContent = 'Enter username and password'; errEl.style.display = 'block'; }
    return;
  }
  const res = await api('/api/login', { method: 'POST', body: { username, password } });
  if (res.error || !res.success) {
    if (errEl) { errEl.textContent = res.error || 'Login failed'; errEl.style.display = 'block'; }
    return;
  }
  // CRIT-05: store JWT only in memory, never in sessionStorage
  _tokenStore.set(res.token);
  sessionStorage.setItem(USER_KEY, JSON.stringify(res.user));  // user info (non-secret) is fine
  currentUser = res.user;
  document.getElementById('loginOverlay')?.classList.remove('visible');
  if (errEl) errEl.style.display = 'none';
  initApp();
  toast('Welcome, ' + res.user.username);
}

function doLogout() {
  // CRIT-05: clear in-memory token
  _tokenStore.clear();
  sessionStorage.removeItem(USER_KEY);
  currentUser = { username: 'Guest', role: 'Staff' };
  applyRoleUI();
  updateUserDisplay();
  toast('Signed out');
  const overlay = document.getElementById('loginOverlay');
  if (overlay && overlay.dataset.requireAuth === '1') overlay.classList.add('visible');
}

function restoreSession() {
  // CRIT-05: JWT is in-memory only — no token survives page reload (correct trade-off)
  // Restore display name from non-secret user info stored in sessionStorage
  try {
    const raw = sessionStorage.getItem(USER_KEY);
    if (raw) currentUser = JSON.parse(raw);
  } catch (_) {}
  if (!currentUser) currentUser = { username: 'admin', role: 'Admin' };
}

// ─── Mobile Sidebar Controls ───────────────────────────────────
function toggleSidebar(show) {
  const sidebar = document.querySelector('.sidebar');
  const overlay = document.getElementById('sidebarOverlay');
  if (!sidebar || !overlay) return;
  if (show === undefined) {
    sidebar.classList.toggle('open');
    overlay.classList.toggle('active');
  } else if (show) {
    sidebar.classList.add('open');
    overlay.classList.add('active');
  } else {
    sidebar.classList.remove('open');
    overlay.classList.remove('active');
  }
}

// ─── Navigation ────────────────────────────────────────────────
function nav(page) {
  document.querySelectorAll('.section').forEach(s => s.classList.remove('active'));
  document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
  
  const section = document.getElementById('sec-' + page);
  if (!section) { toast('Page not found: ' + page, 'error'); return; }
  section.classList.add('active');
  
  const navEl = document.getElementById('nav-' + page);
  if (navEl) navEl.classList.add('active');
  
  const bc = document.getElementById('breadcrumbPage');
  if (bc) bc.textContent = PAGE_NAMES[page] || page;
  
  if (page === 'dashboard')   loadDashboard();
  if (page === 'inventory')   loadInventory();
  if (page === 'billing')     loadBillingProducts();
  if (page === 'predictions') loadPredictions();
  if (page === 'reports')     loadReports();
  if (page === 'festivals')   loadFestivals();
  if (page === 'admin') {
    if (!canAccess('admin')) { toast('Access denied', 'error'); return; }
    loadAdmin();
  }
  
  toggleSidebar(false);
}

// ─── Toast ─────────────────────────────────────────────────────
function toast(msg, type = 'success') {
  const t = document.getElementById('toast');
  t.textContent = msg; t.className = 'toast ' + type; t.style.display = 'block';
  setTimeout(() => t.style.display = 'none', 3500);
}

// ─── API Helper ────────────────────────────────────────────────
async function api(path, opts = {}) {
  try {
    const r = await fetch(API + path, {
      headers: getAuthHeaders(),
      ...opts,
      body: opts.body ? JSON.stringify(opts.body) : undefined,
    });
    let data = {};
    const text = await r.text();
    if (text) {
      try { data = JSON.parse(text); } catch (_) { data = { error: text.slice(0, 200) }; }
    }
    if (r.status === 429) {
      toast(data.error || 'Too many requests. Please slow down.', 'warning');
      return { error: 'Rate limited' };
    }
    if (r.status === 401) {
      // CRIT-05: clear in-memory token on 401
      _tokenStore.clear();
      document.getElementById('loginOverlay')?.classList.add('visible');
      return { error: data.error || 'Please sign in' };
    }
    if (!r.ok) return { error: data.error || `Request failed (${r.status})` };
    return data;
  } catch (e) { return { error: e.message }; }
}

function fmt(n) { return Number(n||0).toLocaleString('en-IN', { maximumFractionDigits: 0 }); }

// ─── DateTime updater ──────────────────────────────────────────
function updateDateTime() {
  const dateEl = document.getElementById('topbarDateTime');
  if (dateEl) {
    const now = new Date();
    const options = { weekday: 'short', day: '2-digit', month: 'short', year: 'numeric' };
    const timeOpts = { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: true };
    dateEl.textContent = now.toLocaleDateString('en-IN', options) + ', ' + now.toLocaleTimeString('en-IN', timeOpts);
  }
}
setInterval(updateDateTime, 1000);

// ─── Dashboard ────────────────────────────────────────────────
async function ensureModelsTrained() {
  if (modelsReady) return true;
  const train = await api('/api/train', { method: 'POST', body: { product: 'ALL' } });
  if (train.success) {
    modelsReady = true;
    const info = document.getElementById('forecastModelInfo');
    if (info) info.textContent = train.message || 'Models trained from database';
    return true;
  }
  return false;
}

async function loadDashboardForecast(days) {
  const start = new Date();
  start.setDate(start.getDate() + 1);
  const end = new Date(start);
  end.setDate(end.getDate() + days - 1);
  const fmtD = d => d.toISOString().slice(0, 10);
  const pred = await api('/api/predict', {
    method: 'POST',
    body: { product: 'ALL', start_date: fmtD(start), end_date: fmtD(end) },
  });
  if (pred.error || !pred.predictions?.length) {
    if (charts.sales) charts.sales.destroy();
    const chartEl = document.getElementById('salesChart');
    if (chartEl) {
      charts.sales = new Chart(chartEl, {
        type: 'line',
        data: { labels: ['No forecast'], datasets: [{ label: 'Predicted units', data: [0], borderColor: '#8b5cf6' }] },
        options: chartOpts(),
      });
    }
    return;
  }
  const labels = pred.predictions.map(p => p.date);
  const adjusted = pred.predictions.map(p => p.predicted_qty);
  const historical = pred.historical || [];
  if (charts.sales) charts.sales.destroy();
  charts.sales = new Chart(document.getElementById('salesChart'), {
    type: 'line',
    data: {
      labels: [...historical.map(h => h.date), ...labels],
      datasets: [
        {
          label: 'Historical (units)',
          data: [...historical.map(h => h.quantity), ...new Array(labels.length).fill(null)],
          borderColor: '#10b981',
          tension: 0.4,
        },
        {
          label: 'AI forecast (units)',
          data: [...new Array(historical.length).fill(null), ...adjusted],
          borderColor: '#8b5cf6',
          backgroundColor: 'rgba(139,92,246,0.12)',
          fill: true,
          tension: 0.4,
        },
      ],
    },
    options: chartOpts(),
  });
  const festBadge = document.getElementById('festWindowBadge');
  const hasFest = pred.predictions.some(p => p.boosts?.length);
  if (festBadge) {
    festBadge.style.display = hasFest ? 'inline-block' : 'none';
    if (hasFest) festBadge.textContent = '🟢 Festival boost in forecast window';
  }
  if (pred.accuracy != null) {
    const lift = Math.max(0, Math.round(pred.accuracy - 50));
    const kpiAi = document.querySelector('.kpi-card.ai .value');
    if (kpiAi) kpiAi.textContent = pred.accuracy + '%';
    const kpiSub = document.querySelector('.kpi-card.ai .sub');
    if (kpiSub) kpiSub.textContent = `Model fit (R²) · ${days}-day horizon`;
  }
}

async function loadDashboard() {
  updateDateTime();
  const rep = await api('/api/reports');
  if (rep.error) return;
  
  const low = rep.stock_summary?.low || 0;
  const total = rep.stock_summary?.total || 0;
  
  const lowBadge = document.getElementById('lowBadge');
  if (lowBadge) {
    lowBadge.textContent = low;
    lowBadge.style.display = low > 0 ? 'inline-block' : 'none';
  }
  
  const notifDot = document.getElementById('notifDot');
  if (notifDot) notifDot.style.display = low > 0 ? 'block' : 'none';

  const todayRev = rep.today_revenue || 0;
  const yesterdayRev = rep.yesterday_revenue ?? 0;
  const revChange = yesterdayRev > 0 ? ((todayRev - yesterdayRev) / yesterdayRev * 100).toFixed(1) : (todayRev > 0 ? '100' : '0');
  
  document.getElementById('kpiCards').innerHTML = `
    <div class="kpi-card revenue">
      <div class="kpi-top">
        <div class="kpi-icon">₹</div>
        <div class="kpi-trend up">▲ ${Math.abs(revChange)}%</div>
      </div>
      <div class="value">₹${fmt(todayRev)}</div>
      <div class="label">TODAY'S REVENUE</div>
      <div class="sub">vs ₹${fmt(yesterdayRev)} yesterday</div>
    </div>
    <div class="kpi-card stock">
      <div class="kpi-top">
        <div class="kpi-icon">📋</div>
        <div class="kpi-trend info">▲ ${total > 0 ? Math.ceil(total/50) : 0} items</div>
      </div>
      <div class="value">${total}</div>
      <div class="label">ACTIVE STOCK LINES</div>
      <div class="sub">Across ${new Set((rep.top_products||[]).map(p=>p.category)).size || 0} categories</div>
    </div>
    <div class="kpi-card ${low > 0 ? 'danger' : 'stock'}">
      <div class="kpi-top">
        <div class="kpi-icon">⚠️</div>
        <div class="kpi-trend ${low > 0 ? 'warning' : 'up'}">▼ ${low > 0 ? 'Critical' : 'None'}</div>
      </div>
      <div class="value">${low}</div>
      <div class="label">CRITICAL ALERTS</div>
      <div class="sub">${low > 0 ? low + ' items need restock' : 'All stock healthy'}</div>
    </div>
    <div class="kpi-card ai">
      <div class="kpi-top">
        <div class="kpi-icon">✨</div>
        <div class="kpi-trend festival">▲ ML Ready</div>
      </div>
      <div class="value">—</div>
      <div class="label">AI MODEL FIT (R²)</div>
      <div class="sub">Train on Predictions page or auto-load</div>
    </div>`;

  const alerts = await api('/api/inventory-alerts');
  const ac = document.getElementById('alertsContainer');
  const alertCountEl = document.getElementById('alertCount');
  
  if (alerts.alerts?.length) {
    if (alertCountEl) alertCountEl.textContent = alerts.alerts.length;
    ac.innerHTML = alerts.alerts.map(a => {
      const shortage = Math.max(0, a.min_stock_level - a.current_stock);
      const stockPct = Math.min(100, Math.max(0, (a.current_stock / a.min_stock_level) * 100));
      const severity = stockPct < 30 ? 'critical' : 'warning';
      const daysLeft = Math.max(1, Math.ceil(a.current_stock / (a.min_stock_level * 0.5)));
      const demand = a.min_stock_level;
      
      return `<div class="alert-item ${severity}">
        <div class="alert-item-header">
          <span class="alert-item-name">🔥 ${escapeHtml(a.name)}</span>
          <span class="alert-item-severity ${severity}">${severity.toUpperCase()}</span>
        </div>
        <div class="alert-stock-label">
          <span>Stock Level</span>
          <span>${a.current_stock}/${a.min_stock_level} units</span>
        </div>
        <div class="alert-stock-bar">
          <div class="alert-stock-fill ${severity}" style="width:${stockPct}%"></div>
        </div>
        <div class="alert-stats">
          <span>Current: <strong>${a.current_stock} units</strong></span>
          <span>Demand: <strong>${demand} units</strong></span>
        </div>
        <div class="alert-stats">
          <span>Shortage: <strong>${shortage} units</strong></span>
          <span>Days left: <strong>${daysLeft}d</strong></span>
        </div>
        <div class="alert-demand-tag">🔥 DEMAND SPIKE</div>
        <!-- NEW-02: data-restock-id instead of inline onclick — CSP-compliant, handled by delegated listener below -->
        <button class="alert-restock-btn" data-restock-id="${parseInt(a.id)}">✨ Quick Restock</button>
      </div>`;
    }).join('');
    // NEW-02: Event delegation — single listener handles all Restock buttons;
    // avoids inline onclick which is blocked by CSP script-src 'self'.
    ac.addEventListener('click', function _restockDelegate(e) {
      const btn = e.target.closest('[data-restock-id]');
      if (btn) restock(parseInt(btn.dataset.restockId, 10));
    }, { once: true }); // replaced on every loadDashboard() call so use once:true
  } else {
    if (alertCountEl) alertCountEl.textContent = '0';
    ac.innerHTML = '<p style="color:var(--success)">✅ All stock levels healthy!</p>';
  }
  
  await ensureModelsTrained();
  await loadDashboardForecast(forecastDays);
}

function chartOpts(prefix='') {
  return { responsive:true, maintainAspectRatio:false,
    plugins:{ legend:{ labels:{ color:'#94a3b8' } } },
    scales:{ x:{ ticks:{ color:'#94a3b8' }, grid:{ color:'rgba(255,255,255,0.05)' } },
             y:{ ticks:{ color:'#94a3b8', callback:v=>prefix+fmt(v) }, grid:{ color:'rgba(255,255,255,0.05)' } } } };
}

function setForecastDays(days, el) {
  forecastDays = days;
  document.querySelectorAll('.pill-btn').forEach(b => b.classList.remove('active'));
  if (el) el.classList.add('active');
  const title = document.getElementById('forecastChartTitle');
  if (title) title.textContent = `${days}-Day AI Sales Forecast`;
  loadDashboard();
}

function setPredMode(mode, el) {
  document.querySelectorAll('.pill-tab').forEach(t => t.classList.remove('active'));
  if (el) el.classList.add('active');
  const singleInputs = document.getElementById('singleDateInputs');
  const rangeInputs = document.getElementById('rangeDateInputs');
  if (mode === 'single') {
    if (singleInputs) singleInputs.style.display = 'block';
    if (rangeInputs) rangeInputs.style.display = 'none';
  } else {
    if (singleInputs) singleInputs.style.display = 'none';
    if (rangeInputs) rangeInputs.style.display = 'block';
  }
}

// ─── POS Billing ──────────────────────────────────────────────
function updateBillingStats(rep) {
  if (!rep || rep.error) return;
  const totalEl = document.getElementById('billingTotal');
  const ordersEl = document.getElementById('ordersToday');
  const avgEl = document.getElementById('avgOrder');
  if (totalEl) totalEl.textContent = '₹' + fmt(rep.today_revenue || 0);
  if (ordersEl) ordersEl.textContent = String(rep.orders_today ?? 0);
  if (avgEl) avgEl.textContent = '₹' + fmt(rep.avg_order_value || 0);
}

async function loadBillingProducts() {
  const [res, rep] = await Promise.all([api('/api/products'), api('/api/reports')]);
  updateBillingStats(rep);
  products = res.products || [];
  const sel = document.getElementById('billProduct');
  sel.innerHTML = products.map(p =>
    `<option value="${parseInt(p.id)}" data-price="${parseFloat(p.price)}" data-stock="${parseInt(p.current_stock)}" data-unit="${escapeHtml(p.unit)}">${escapeHtml(p.name)} — ₹${parseFloat(p.price)}/${escapeHtml(p.unit)}</option>`
  ).join('');
  sel.onchange = () => updateStockInfo();
  updateStockInfo();
}

function updateStockInfo() {
  const opt = document.getElementById('billProduct').selectedOptions[0];
  if (opt) document.getElementById('stockInfo').textContent =
    `Available: ${opt.dataset.stock} ${opt.dataset.unit}s in stock`;
}

function addToCart() {
  const opt = document.getElementById('billProduct').selectedOptions[0];
  const qty = parseInt(document.getElementById('billQty').value);
  if (!opt || qty < 1) return toast('Select product and valid quantity','error');
  if (qty > parseInt(opt.dataset.stock)) return toast('Insufficient stock!','error');
  const existing = cart.find(c => c.product_id === parseInt(opt.value));
  if (existing) existing.quantity += qty;
  else cart.push({ product_id:parseInt(opt.value), name:opt.textContent.split('—')[0].trim(), price:parseFloat(opt.dataset.price), quantity:qty, unit:opt.dataset.unit });
  renderCart(); toast('Added to cart!');
}

function removeFromCart(i) { cart.splice(i,1); renderCart(); }

function renderCart() {
  const countEl = document.getElementById('cartCount');
  if (countEl) countEl.textContent = cart.length;
  const cartTable = document.getElementById('cartItems');
  cartTable.innerHTML = cart.length
    ? cart.map((c,i) => `<tr><td>${escapeHtml(c.name)}</td><td>${c.quantity} ${escapeHtml(c.unit)}</td><td>₹${c.price}</td><td>₹${(c.price*c.quantity).toFixed(2)}</td><td><button class="remove-btn" data-remove-idx="${i}">✕</button></td></tr>`).join('')
    : '<tr><td colspan="5" style="color:var(--text-dim);text-align:center;padding:20px">Cart empty — add products above</td></tr>';
  cartTable.onclick = function(e) {
    const btn = e.target.closest('[data-remove-idx]');
    if (btn) removeFromCart(parseInt(btn.dataset.removeIdx, 10));
  };
  document.getElementById('cartTotal').textContent = '₹' + cart.reduce((s,c)=>s+c.price*c.quantity,0).toFixed(2);
}

async function checkout() {
  if (!cart.length) return toast('Cart is empty!','error');
  const res = await api('/api/billing', { method:'POST', body:{ cart: cart.map(c=>({ product_id:c.product_id, quantity:c.quantity })) } });
  if (res.error) return toast(res.error,'error');
  document.getElementById('receiptArea').innerHTML =
    `<div class="receipt-card"><div style="text-align:center;margin-bottom:12px"><strong>SmartRetail AI</strong><br><small>${escapeHtml(res.timestamp)}</small></div>
    ${res.receipt.map(r=>`<div class="receipt-line"><span>${escapeHtml(r.name)} × ${r.qty} ${escapeHtml(r.unit)}</span><span>₹${r.total.toFixed(2)}</span></div>`).join('')}
    <div class="receipt-total">Grand Total: ₹${res.grand_total.toFixed(2)}</div></div>`;
  cart = []; renderCart(); loadBillingProducts(); loadDashboard();
  toast('Bill generated! Stock updated.');
}

// ─── Inventory ────────────────────────────────────────────────
async function loadInventory() {
  const res = await api('/api/products');
  allProducts = res.products || [];
  const cats = [...new Set(allProducts.map(p=>p.category))].sort();
  const catSel = document.getElementById('invCatFilter');
  catSel.innerHTML = '<option value="">All Categories</option>' + cats.map(c=>`<option>${escapeHtml(c)}</option>`).join('');
  const addBtn = document.getElementById('btnAddProduct');
  if (addBtn) addBtn.style.display = (currentUser?.role==='Admin'||currentUser?.role==='Manager') ? 'inline-flex' : 'none';
  
  const invStats = document.getElementById('invStats');
  if (invStats) {
    const totalProducts = allProducts.length;
    const lowStock = allProducts.filter(p => p.current_stock < p.min_stock_level).length;
    const totalValue = allProducts.reduce((s, p) => s + (p.price * p.current_stock), 0);
    invStats.innerHTML = `
      <div class="stat-card blue"><div class="stat-icon">📦</div><div class="stat-val">${totalProducts}</div><div class="stat-lbl">TOTAL PRODUCTS</div></div>
      <div class="stat-card green"><div class="stat-icon">✅</div><div class="stat-val">${totalProducts - lowStock}</div><div class="stat-lbl">IN STOCK</div></div>
      <div class="stat-card ${lowStock > 0 ? 'red' : 'green'}"><div class="stat-icon">⚠️</div><div class="stat-val">${lowStock}</div><div class="stat-lbl">LOW STOCK</div></div>
      <div class="stat-card purple"><div class="stat-icon">₹</div><div class="stat-val">₹${fmt(totalValue)}</div><div class="stat-lbl">INVENTORY VALUE</div></div>`;
  }
  
  renderInventoryTable(allProducts);
}

function filterInv(search) {
  const cat = document.getElementById('invCatFilter').value;
  let filtered = allProducts;
  if (search) filtered = filtered.filter(p => p.name.toLowerCase().includes(search.toLowerCase()));
  if (cat)    filtered = filtered.filter(p => p.category === cat);
  renderInventoryTable(filtered);
}

function renderInventoryTable(prods) {
  const invTable = document.getElementById('invTable');
  invTable.innerHTML = prods.map(p => {
    const status = p.current_stock < p.min_stock_level ? 'low' : p.current_stock < p.min_stock_level*2 ? 'warn' : 'ok';
    const tag = status==='low'
      ? `<span class="tag tag-red">🔴 Low</span>`
      : status==='warn'
      ? `<span class="tag tag-gold">🟡 Warning</span>`
      : `<span class="tag tag-green">🟢 OK</span>`;
    const canRestock = currentUser?.role==='Admin'||currentUser?.role==='Manager';
    return `<tr>
      <td><strong>${escapeHtml(p.name)}</strong></td><td>${escapeHtml(p.category)}</td><td>${escapeHtml(p.unit)}</td><td>₹${parseFloat(p.price)}</td>
      <td class="stock-${status}">${parseInt(p.current_stock)}</td><td style="color:var(--text-dim)">${parseInt(p.min_stock_level)}</td>
      <td>${tag}</td>
      <td>${canRestock?`<button class="btn btn-success btn-sm" data-restock-id="${parseInt(p.id)}">+ Restock</button>`:'—'}</td>
    </tr>`;
  }).join('');
  invTable.onclick = function(e) {
    const btn = e.target.closest('[data-restock-id]');
    if (btn) restock(parseInt(btn.dataset.restockId, 10));
  };
}

async function restock(pid) {
  if (!canAccess('inventory')) return toast('Access denied','error');
  const res = await api('/api/restock', { method:'POST', body:{ product_id:pid, quantity:50 } });
  if (res.error) return toast(res.error,'error');
  toast(`Restocked ${res.name}: ${res.old_stock} → ${res.new_stock} units`);
  loadInventory(); loadDashboard();
}

function showAddProduct() {
  document.getElementById('addProductModal').style.display = 'flex';
}

async function submitAddProduct() {
  const name      = document.getElementById('newProdName').value.trim();
  const category  = document.getElementById('newProdCat').value;
  const unit      = document.getElementById('newProdUnit').value;
  const price     = parseFloat(document.getElementById('newProdPrice').value);
  const stock     = parseInt(document.getElementById('newProdStock').value);
  const min_stock = parseInt(document.getElementById('newProdMin').value);
  if (!name || !price) return toast('Name and price required','error');
  const res = await api('/api/add-product', { method:'POST', body:{ name, category, unit, price, stock, min_stock } });
  if (res.error) return toast(res.error,'error');
  toast(`Product "${name}" added!`);
  document.getElementById('addProductModal').style.display = 'none';
  document.getElementById('newProdName').value = '';
  loadInventory();
}

// ─── AI Predictions ───────────────────────────────────────────
function parseCSVStats(text) {
  const lines = text.trim().split(/\r?\n/).filter(Boolean);
  if (lines.length < 2) return null;
  const products = new Set();
  let rows = 0;
  for (let i = 1; i < lines.length; i++) {
    const parts = lines[i].split(',');
    if (parts.length >= 3) {
      products.add(parts[1].trim());
      rows++;
    }
  }
  const dates = lines.slice(1).map(l => l.split(',')[0]).filter(Boolean);
  return { rows, products: products.size, from: dates[0], to: dates[dates.length - 1] };
}

function handleCSV(input) {
  const file = input.files[0];
  if (!file) return;
  if (!file.name.toLowerCase().endsWith('.csv')) {
    toast('Please upload a .csv file (Excel: save as CSV first)', 'error');
    return;
  }
  const reader = new FileReader();
  reader.onload = e => {
    csvData = e.target.result;
    document.getElementById('csvStatus').innerHTML =
      /* NEW-03: escapeHtml() prevents HTML injection from a crafted filename */
      `<span class="tag tag-green">✅ ${escapeHtml(file.name)} (${(file.size/1024).toFixed(1)} KB) — Ready to train</span>`;
    const stats = parseCSVStats(csvData);
    const analysis = document.getElementById('dataAnalysis');
    const analysisStats = document.getElementById('analysisStats');
    if (stats && analysis && analysisStats) {
      analysis.style.display = 'block';
      analysisStats.innerHTML = `
        <span class="tag tag-purple">${stats.rows} rows</span>
        <span class="tag tag-green">${stats.products} products</span>
        <span class="tag tag-gold">${stats.from} → ${stats.to}</span>`;
    }
    toast('CSV loaded! Click Predict to train.');
  };
  reader.readAsText(file);
}

async function loadPredictions() {
  const res = await api('/api/products');
  if (res.error) return;
  const prods = res.products || [];
  const sel = document.getElementById('predProduct');
  if (sel) {
    let html = '<option value="ALL" style="font-weight:bold;color:var(--accent)">🌟 All Products</option>';
    html += prods.map(p => `<option value="${escapeHtml(p.name)}">${escapeHtml(p.name)} (${escapeHtml(p.category)})</option>`).join('');
    sel.innerHTML = html;
  }
}

async function runPrediction(forceDB = false) {
  const singleInputs = document.getElementById('singleDateInputs');
  const isSingle = singleInputs && singleInputs.style.display !== 'none';

  let product, start, end;
  
  if (isSingle) {
    product = document.getElementById('predProduct').value.trim();
    start = document.getElementById('predSingleDate').value;
    end = start;
  } else {
    product = document.getElementById('predProduct').value.trim();
    start = document.getElementById('predStart').value;
    end = document.getElementById('predEnd').value || start;
  }
  
  if (!product || !start) return toast('Select product and date','error');
  if (!forceDB && !csvData) return toast('Upload a CSV or click "Use DB Data"','error');
  document.getElementById('predResults').innerHTML = '<p style="color:var(--text-dim);text-align:center;padding:20px">Training model...</p>';
  
  const trainBody = forceDB ? { product } : { csv_data: csvData, product };
  const train = await api('/api/train', { method:'POST', body: trainBody });
  if (!train.success) return toast(train.error || train.message, 'error');
  modelsReady = true;
  const src = train.source === 'database' ? '🗄️ Trained from database' : '📄 Trained from your CSV';
  document.getElementById('trainSource').textContent = `${src}: ${train.message}`;
  toast(train.message);
  updatePredictionAccuracyStats(train, train.message);
  
  const pred = await api('/api/predict', { method:'POST', body:{ product, start_date: start, end_date: end } });
  if (pred.error) return toast(pred.error,'error');
  renderPredictions(pred, train.message);
}

function formatAccuracyCell(prodName, accuracyByProduct) {
  const acc = accuracyByProduct?.[prodName];
  if (acc !== undefined && acc !== null) {
    const color = acc > 80 ? 'var(--success)' : acc > 50 ? '#f59e0b' : 'var(--red)';
    return `<span style="font-weight:600;color:${color}">${acc}%</span>`;
  }
  return '<span style="color:var(--text-dim)">Fallback</span>';
}

function updatePredictionAccuracyStats(data, trainMessage) {
  const accEl = document.getElementById('modelAccuracy');
  const accSub = document.getElementById('modelAccuracySub');
  if (!accEl) return;
  if (data.accuracy !== undefined && data.accuracy !== null) {
    accEl.textContent = data.accuracy + '%';
    if (accSub) accSub.textContent = 'In-sample R² on training data';
  } else {
    accEl.textContent = 'N/A';
    if (accSub) accSub.textContent = 'Train with enough sales history (Use DB Data or CSV)';
  }
  const recordsEl = document.getElementById('recordsLoaded');
  if (recordsEl && trainMessage) {
    const recMatch = trainMessage.match(/(\d+)\s+records?/i);
    const modelMatch = trainMessage.match(/Trained\s+(\d+)\s+models/i);
    if (recMatch) recordsEl.textContent = recMatch[1];
    else if (modelMatch) recordsEl.textContent = modelMatch[1] + ' models';
  }
}

function renderPredictions(data, trainMessage) {
  updatePredictionAccuracyStats(data, trainMessage);

  const srcLabel = data.source.includes('multiple') 
    ? '<span class="tag tag-gold">Source: Multiple Models</span>'
    : (data.source === 'database'
      ? '<span class="tag tag-green">Source: Database</span>'
      : '<span class="tag tag-purple">Source: Your CSV</span>');
  
  const bigPred = document.getElementById('bigPrediction');
  if (bigPred) {
    bigPred.style.display = 'block';
    document.getElementById('predUnits').textContent = data.total_predicted + ' units';
    document.getElementById('predSub').textContent = `${data.product === 'ALL' ? 'All Products' : data.product} — ${data.predictions.length} day forecast`;
  }
  
  const accuracyByProduct = data.accuracy_by_product || {};
  let breakdownHtml = '';
  if (data.breakdown && Object.keys(data.breakdown).length > 0) {
    const sortedBreakdown = Object.entries(data.breakdown).sort((a,b) => b[1] - a[1]);
    breakdownHtml = `
      <div style="margin-top: 16px;">
        <h3 style="margin-bottom: 8px;">Prediction Breakdown by Product</h3>
        <div class="table-responsive">
          <table>
            <thead><tr><th>Product Name</th><th>Total Predicted Units</th><th>Model Fit (R²)</th></tr></thead>
            <tbody>
              ${sortedBreakdown.map(([prodName, qty]) => 
                `<tr><td>${escapeHtml(prodName)}</td><td style="font-weight:bold;color:var(--accent)">${qty} units</td><td>${formatAccuracyCell(prodName, accuracyByProduct)}</td></tr>`
              ).join('')}
            </tbody>
          </table>
        </div>
      </div>
    `;
  }

  let accTag = '';
  if (data.accuracy !== undefined && data.accuracy !== null) {
    let accColor = data.accuracy > 80 ? 'tag-green' : data.accuracy > 50 ? 'tag-gold' : 'tag-red';
    accTag = `<span class="tag ${accColor}">Model Fit (R²): ${data.accuracy}%</span>`;
  } else {
    accTag = '<span class="tag tag-red">Model Fit: N/A (insufficient history)</span>';
  }

  window.currentPredictions = data.predictions;

  const predResults = document.getElementById('predResults');
  predResults.innerHTML =
    `<div style="margin-bottom:16px;display:flex;gap:8px;flex-wrap:wrap">
       <span class="tag tag-purple">Total Predicted: ${data.total_predicted} units</span>${srcLabel}${accTag}
     </div>
     <div style="font-size:12px;color:var(--text-dim);margin-bottom:8px">💡 Tip: Click on any date row to see a detailed product breakdown.</div>
     <div class="table-responsive">
       <table><thead><tr><th>Date</th><th>Day</th><th>Base</th><th>Adjusted</th><th>Boosts</th></tr></thead><tbody>
       ${data.predictions.map(p => {
          return `<tr class="clickable-row" style="cursor:pointer;" data-date="${p.date}">
           <td>${escapeHtml(p.date)}</td><td>${escapeHtml(p.day)}</td><td>${p.base_qty}</td>
           <td style="font-weight:700;color:var(--accent)">${p.predicted_qty}</td>
           <td>${p.boosts.length ? p.boosts.map(b=>`<span class="tag tag-gold">${escapeHtml(b)}</span>`).join(' ') : '<span class="tag tag-green">Normal</span>'}</td></tr>`;
       }).join('')}
       </tbody></table>
     </div>`;
     
  predResults.onclick = function(e) {
    const row = e.target.closest('[data-date]');
    if (row) openDailyAnalysis(row.dataset.date);
  };
     
  document.getElementById('aggregateBreakdownWrapper').innerHTML = breakdownHtml;
  
  const wrapper = document.getElementById('forecastChartWrapper');
  if (wrapper) wrapper.style.display = 'block';
  if (charts.forecast) charts.forecast.destroy();
  
  const hist = data.historical || [];
  const preds = data.predictions || [];
  
  const allLabels = [...hist.map(h => h.date), ...preds.map(p => p.date)];
  
  const lastHistVal = hist.length ? hist[hist.length-1].quantity : null;
  const lastHistIdx = hist.length - 1;
  
  const histData = hist.map(h => h.quantity).concat(new Array(preds.length).fill(null));
  const predData = new Array(hist.length).fill(null).concat(preds.map(p => p.predicted_qty));
  
  if (hist.length > 0 && preds.length > 0) {
    predData[lastHistIdx] = lastHistVal;
  }
  
  const baseData = new Array(hist.length).fill(null).concat(preds.map(p => p.base_qty));
  if (hist.length > 0 && preds.length > 0) {
    baseData[lastHistIdx] = lastHistVal;
  }

  charts.forecast = new Chart(document.getElementById('forecastChart'), { 
    type:'line', 
    data:{
      labels: allLabels,
      datasets:[
        { 
          label: 'Historical Actuals', 
          data: histData, 
          borderColor: '#10b981', 
          backgroundColor: 'rgba(16,185,129,0.1)', 
          fill: true, 
          tension: 0.4, 
          pointRadius: 3 
        },
        { 
          label: 'Base Prediction', 
          data: baseData, 
          borderColor: '#94a3b8', 
          borderDash: [5,5], 
          tension: 0.4, 
          pointRadius: 0 
        },
        { 
          label: 'Adjusted (with boosts)', 
          data: predData, 
          borderColor: '#8b5cf6', 
          backgroundColor: 'rgba(139,92,246,0.15)', 
          fill: true, 
          tension: 0.4, 
          pointRadius: 4,
          pointBackgroundColor: predData.map((_, i) => {
             if (i <= lastHistIdx) return '#10b981';
             const p = preds[i - hist.length];
             return p && p.boosts.length ? '#ec4899' : '#8b5cf6';
          })
        }
      ]
    }, 
    options: chartOpts() 
  });
}

// ─── Reports ──────────────────────────────────────────────────
async function loadReports() {
  const rep = await api('/api/reports');
  if (rep.error) return;
  if (rep.monthly_revenue?.length) {
    if (charts.revenue) charts.revenue.destroy();
    charts.revenue = new Chart(document.getElementById('revenueChart'), { type:'bar', data:{
      labels: rep.monthly_revenue.map(d=>d.month).reverse(),
      datasets:[{ label:'Revenue (₹)', data:rep.monthly_revenue.map(d=>d.revenue).reverse(),
        backgroundColor: rep.monthly_revenue.map((_,i)=>`hsl(${260+i*10},70%,60%)`) }]
    }, options: chartOpts('₹') });
  }
  const tp = document.getElementById('topProducts');
  if (rep.top_products?.length) {
    const max = Math.max(...rep.top_products.map(p=>p.total_revenue));
    tp.innerHTML = rep.top_products.map((p,i) => {
      const pct = (p.total_revenue/max*100).toFixed(0);
      return `<div style="margin-bottom:12px">
        <div style="display:flex;justify-content:space-between;font-size:13px;margin-bottom:4px">
          <!-- NEW-01: escapeHtml() prevents XSS from server-controlled product names -->
          <span>${i+1}. ${escapeHtml(p.name)}</span><span style="color:var(--success)">₹${fmt(p.total_revenue)}</span>
        </div>
        <div style="background:rgba(255,255,255,0.06);border-radius:6px;height:8px;overflow:hidden">
          <div style="width:${pct}%;height:100%;background:linear-gradient(90deg,var(--accent),var(--pink));border-radius:6px"></div>
        </div></div>`;
    }).join('');
  }
}

// ─── Festivals ────────────────────────────────────────────────
async function loadFestivals() {
  const res = await api('/api/festivals');
  if (res.error) return;
  const tn  = res.festivals.filter(f=>f.category==='Tamil Nadu');
  const nat = res.festivals.filter(f=>f.category!=='Tamil Nadu');
  document.getElementById('tnFestivals').innerHTML  = tn.map(festCard).join('');
  document.getElementById('natFestivals').innerHTML = nat.map(festCard).join('');
}

function festCard(f) {
  return `<div class="festival-card">
    <div class="mult-badge">${f.multiplier}x</div>
    <div><div class="fest-name">${escapeHtml(f.name)}</div><div class="fest-date">${escapeHtml(f.start)} to ${escapeHtml(f.end)} • <span class="tag tag-gold" style="font-size:10px">${escapeHtml(f.category)}</span></div></div>
  </div>`;
}

// ─── Admin Panel ──────────────────────────────────────────────
async function loadAdmin() {
  if (!canAccess('admin')) {
    toast('Admin access required', 'error');
    nav('dashboard');
    return;
  }
  await Promise.all([loadUsers(), loadAudit()]);
}

async function loadUsers() {
  const res = await api('/api/users');
  if (res.error) { document.getElementById('usersPanel').innerHTML = `<p style="color:var(--danger)">${escapeHtml(res.error)}</p>`; return; }
  const roleColors = { Admin:'tag-red', Manager:'tag-gold', Staff:'tag-green' };
  const usersPanel = document.getElementById('usersPanel');
  usersPanel.innerHTML = `
    <div class="table-responsive">
      <table><thead><tr><th>Username</th><th>Role</th><th>Status</th><th>Last Login</th><th>Action</th></tr></thead><tbody>
      ${res.users.map(u => `<tr>
        <td><strong>${escapeHtml(u.username)}</strong></td>
        <td><span class="tag ${roleColors[u.role]||'tag-purple'}">${escapeHtml(u.role)}</span></td>
        <td><span class="tag ${u.is_active?'tag-green':'tag-red'}">${u.is_active?'Active':'Disabled'}</span></td>
        <td style="font-size:11px;color:var(--text-dim)">${escapeHtml(u.last_login||'Never')}</td>
        <td>${escapeHtml(u.username)!==currentUser?.username
          ? `<button class="btn btn-sm" style="background:${u.is_active?'rgba(239,68,68,0.15)':'rgba(16,185,129,0.15)'};color:${u.is_active?'var(--red)':'var(--green)'}" data-toggle-user="${parseInt(u.id)}">${u.is_active?'Disable':'Enable'}</button>`
          : '<span style="font-size:11px;color:var(--text-dim)">Current</span>'
        }</td>
      </tr>`).join('')}
      </tbody></table>
    </div>`;
  usersPanel.onclick = function(e) {
    const btn = e.target.closest('[data-toggle-user]');
    if (btn) toggleUser(parseInt(btn.dataset.toggleUser, 10));
  };
}

async function toggleUser(uid) {
  const res = await api('/api/toggle-user', { method:'POST', body:{ user_id: uid } });
  if (res.error) return toast(res.error,'error');
  toast(`User ${res.user.is_active ? 'enabled' : 'disabled'}`);
  loadUsers();
}

async function createUser() {
  const username = document.getElementById('newUsername').value.trim();
  const password = document.getElementById('newPassword').value;
  const role     = document.getElementById('newRole').value;
  if (!username || !password) return toast('Username and password required','error');
  const res = await api('/api/create-user', { method:'POST', body:{ username, password, role } });
  if (res.error) return toast(res.error,'error');
  toast(`User "${username}" created as ${role}!`);
  document.getElementById('newUsername').value = '';
  document.getElementById('newPassword').value = '';
  loadUsers();
}

async function loadAudit() {
  const res = await api('/api/audit-log');
  if (res.error) return;
  document.getElementById('auditPanel').innerHTML = res.logs?.length
    ? `<div class="table-responsive">
         <table><thead><tr><th>User</th><th>Action</th><th>Details</th><th>Time</th></tr></thead><tbody>
         ${res.logs.map(l=>`<tr><td>${escapeHtml(l.username||'System')}</td><td>${escapeHtml(l.action)}</td><td>${escapeHtml(l.details||'-')}</td><td style="font-size:11px">${escapeHtml(l.created_at)}</td></tr>`).join('')}
         </tbody></table>
       </div>`
    : '<p style="color:var(--text-dim)">No audit logs yet</p>';
}

// ─── DB Status ────────────────────────────────────────────────
async function checkDB() {
  const res = await api('/api/db-status');
  const el = document.getElementById('dbStatus');
  const textEl = document.getElementById('dbStatusText');
  if (res.status === 'connected') {
    el.className = 'db-status';
    if (textEl) textEl.textContent = `MySQL · ${res.database || 'retail_sales_db'}`;
  } else {
    el.className = 'db-status off';
    if (textEl) textEl.textContent = 'Disconnected';
  }
}

// ─── Auto Initialization ──────────────────────────────────────
var _initialized = false;

function bindProductSearch() {
  const search = document.querySelector('.search-box input');
  if (!search || search.dataset.bound) return;
  search.dataset.bound = '1';
  search.addEventListener('keydown', async e => {
    if (e.key !== 'Enter') return;
    const q = search.value.trim().toLowerCase();
    if (!q) return;
    nav('inventory');
    const res = await api('/api/products');
    allProducts = res.products || [];
    filterInv(q);
    search.value = '';
  });
}

function initApp() {
  if (_initialized) return;
  _initialized = true;
  restoreSession();
  applyRoleUI();
  updateUserDisplay();
  bindProductSearch();
  console.log('[SmartRetail] Initializing app...');

  var navMap = {
    'nav-dashboard': 'dashboard',
    'nav-billing': 'billing',
    'nav-inventory': 'inventory',
    'nav-predictions': 'predictions',
    'nav-reports': 'reports',
    'nav-festivals': 'festivals',
    'nav-settings': 'settings',
    'nav-admin': 'admin',
  };

  Object.keys(navMap).forEach(function(elId) {
    var page = navMap[elId];
    var el = document.getElementById(elId);
    if (el) {
      el.removeAttribute('onclick');
      el.addEventListener('click', function(e) {
        e.preventDefault();
        e.stopPropagation();
        console.log('[SmartRetail] Nav click:', page);
        nav(page);
      });
      console.log('[SmartRetail] Bound nav:', elId, '->', page);
    }
  });

  var sidebarToggleBtn = document.querySelector('.sidebar-toggle');
  if (sidebarToggleBtn) {
    sidebarToggleBtn.removeAttribute('onclick');
    sidebarToggleBtn.addEventListener('click', function() { toggleSidebar(); });
  }

  var mobileToggle = document.getElementById('mobileMenuToggle');
  if (mobileToggle) {
    mobileToggle.removeAttribute('onclick');
    mobileToggle.addEventListener('click', function() { toggleSidebar(true); });
  }

  var sidebarOverlay = document.getElementById('sidebarOverlay');
  if (sidebarOverlay) {
    sidebarOverlay.removeAttribute('onclick');
    sidebarOverlay.addEventListener('click', function() { toggleSidebar(false); });
  }

  var refreshBtn = document.querySelector('.btn-refresh');
  if (refreshBtn) {
    refreshBtn.removeAttribute('onclick');
    refreshBtn.addEventListener('click', function() { loadDashboard(); });
  }

  var notifBell = document.getElementById('topbarNotification');
  if (notifBell) {
    notifBell.removeAttribute('onclick');
    notifBell.addEventListener('click', function() { nav('inventory'); });
  }

  var addCartBtn = document.querySelector('.btn-primary[onclick="addToCart()"]');
  if (addCartBtn) {
    addCartBtn.removeAttribute('onclick');
    addCartBtn.addEventListener('click', function() { addToCart(); });
  }
  var checkoutBtn = document.querySelector('.btn-success[onclick="checkout()"]');
  if (checkoutBtn) {
    checkoutBtn.removeAttribute('onclick');
    checkoutBtn.addEventListener('click', function() { checkout(); });
  }

  var invSearch = document.getElementById('invSearch');
  if (invSearch) {
    invSearch.removeAttribute('oninput');
    invSearch.addEventListener('input', function() { filterInv(this.value); });
  }

  var invCatFilter = document.getElementById('invCatFilter');
  if (invCatFilter) {
    invCatFilter.removeAttribute('onchange');
    invCatFilter.addEventListener('change', function() {
      filterInv(document.getElementById('invSearch').value);
    });
  }

  var addProdBtn = document.getElementById('btnAddProduct');
  if (addProdBtn) {
    addProdBtn.removeAttribute('onclick');
    addProdBtn.addEventListener('click', function() { showAddProduct(); });
  }

  var addProductModal = document.getElementById('addProductModal');
  if (addProductModal) {
    addProductModal.removeAttribute('onclick');
    addProductModal.addEventListener('click', function(e) {
      if (e.target === this) this.style.display = 'none';
    });
  }

  var submitProdBtns = document.querySelectorAll('[onclick="submitAddProduct()"]');
  submitProdBtns.forEach(function(btn) {
    btn.removeAttribute('onclick');
    btn.addEventListener('click', function() { submitAddProduct(); });
  });

  var cancelModalBtns = document.querySelectorAll('[onclick*="addProductModal"]');
  cancelModalBtns.forEach(function(btn) {
    btn.removeAttribute('onclick');
    btn.addEventListener('click', function() {
      document.getElementById('addProductModal').style.display = 'none';
    });
  });

  var dropZoneEl = document.getElementById('dropZone');
  if (dropZoneEl) {
    dropZoneEl.removeAttribute('onclick');
    dropZoneEl.addEventListener('click', function() { document.getElementById('csvFile').click(); });
    dropZoneEl.addEventListener('dragover', function(e) { e.preventDefault(); this.classList.add('dragover'); });
    dropZoneEl.addEventListener('dragleave', function() { this.classList.remove('dragover'); });
    dropZoneEl.addEventListener('drop', function(e) {
      e.preventDefault(); this.classList.remove('dragover');
      var f = e.dataTransfer.files[0];
      if (f) { document.getElementById('csvFile').files = e.dataTransfer.files; handleCSV(document.getElementById('csvFile')); }
    });
  }

  var csvFileInput = document.getElementById('csvFile');
  if (csvFileInput) {
    csvFileInput.removeAttribute('onchange');
    csvFileInput.addEventListener('change', function() { handleCSV(this); });
  }

  var predictBtns = document.querySelectorAll('[onclick="runPrediction(false)"]');
  predictBtns.forEach(function(btn) {
    btn.removeAttribute('onclick');
    btn.addEventListener('click', function() { runPrediction(false); });
  });
  var predictDBBtns = document.querySelectorAll('[onclick="runPrediction(true)"]');
  predictDBBtns.forEach(function(btn) {
    btn.removeAttribute('onclick');
    btn.addEventListener('click', function() { runPrediction(true); });
  });

  document.querySelectorAll('.pill-btn').forEach(function(btn) {
    btn.removeAttribute('onclick');
    btn.addEventListener('click', function() {
      var days = this.textContent.includes('30') ? 30 : 7;
      setForecastDays(days, this);
    });
  });

  document.querySelectorAll('.pill-tab').forEach(function(tab) {
    tab.addEventListener('click', function() {
      var mode = this.textContent.includes('Single') ? 'single' : 'range';
      setPredMode(mode, this);
    });
  });

  var createUserBtn = document.querySelector('[onclick="createUser()"]');
  if (createUserBtn) {
    createUserBtn.removeAttribute('onclick');
    createUserBtn.addEventListener('click', function() { createUser(); });
  }

  // MED-03: Wire all remaining buttons that previously had inline onclick=
  const btnLogoutEl = document.getElementById('btnLogout');
  if (btnLogoutEl) btnLogoutEl.addEventListener('click', doLogout);

  const btnAddToCartEl = document.getElementById('btnAddToCart');
  if (btnAddToCartEl) btnAddToCartEl.addEventListener('click', addToCart);

  const btnCheckoutEl = document.getElementById('btnCheckout');
  if (btnCheckoutEl) btnCheckoutEl.addEventListener('click', checkout);

  const btnSubmitEl = document.getElementById('btnSubmitAddProduct');
  if (btnSubmitEl) btnSubmitEl.addEventListener('click', submitAddProduct);

  const btnCancelEl = document.getElementById('btnCancelAddProduct');
  if (btnCancelEl) btnCancelEl.addEventListener('click', () => {
    document.getElementById('addProductModal').style.display = 'none';
  });

  const btnRunPredEl = document.getElementById('btnRunPrediction');
  if (btnRunPredEl) btnRunPredEl.addEventListener('click', () => runPrediction(false));

  const btnRunPredDBEl = document.getElementById('btnRunPredictionDB');
  if (btnRunPredDBEl) btnRunPredDBEl.addEventListener('click', () => runPrediction(true));

  const btnPredSingleEl = document.getElementById('btnPredSingle');
  if (btnPredSingleEl) btnPredSingleEl.addEventListener('click', function() { setPredMode('single', this); });

  const btnPredRangeEl = document.getElementById('btnPredRange');
  if (btnPredRangeEl) btnPredRangeEl.addEventListener('click', function() { setPredMode('range', this); });

  const btn7DaysEl = document.getElementById('btn7Days');
  if (btn7DaysEl) btn7DaysEl.addEventListener('click', function() { setForecastDays(7, this); });

  const btn30DaysEl = document.getElementById('btn30Days');
  if (btn30DaysEl) btn30DaysEl.addEventListener('click', function() { setForecastDays(30, this); });

  const btnSidebarToggleEl = document.getElementById('btnSidebarToggle');
  if (btnSidebarToggleEl) btnSidebarToggleEl.addEventListener('click', () => toggleSidebar());

  const btnCreateUserEl = document.getElementById('btnCreateUser');
  if (btnCreateUserEl) btnCreateUserEl.addEventListener('click', createUser);

  const btnCloseDailyEl = document.getElementById('btnCloseDailyAnalysis');
  if (btnCloseDailyEl) btnCloseDailyEl.addEventListener('click', closeDailyAnalysis);

  console.log('[SmartRetail] All event listeners bound successfully.');

  const loginBtn = document.getElementById('loginBtn');
  if (loginBtn) loginBtn.addEventListener('click', doLogin);

  updateDateTime();
  checkDB();
  loadDashboard();

  console.log('[SmartRetail] App initialized successfully.');
}

function boot() {
  restoreSession();
  const overlay = document.getElementById('loginOverlay');
  // CRIT-05: check in-memory token (no sessionStorage for JWT)
  if (overlay && overlay.dataset.requireAuth === '1' && !_tokenStore.get()) {
    overlay.classList.add('visible');
    const loginBtnEl = document.getElementById('loginBtn');
    if (loginBtnEl) loginBtnEl.addEventListener('click', doLogin);
    // Also wire password Enter key
    const pwdInput = document.getElementById('loginPassword');
    if (pwdInput) pwdInput.addEventListener('keydown', (e) => { if (e.key === 'Enter') doLogin(); });
    return;
  }
  initApp();
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', boot);
} else {
  boot();
}

// ── Daily Analysis Modal Functions ──
function openDailyAnalysis(dateStr) {
  if (!window.currentPredictions) return;
  const pData = window.currentPredictions.find(p => p.date === dateStr);
  if (!pData) return;
  
  document.getElementById('dailyAnalysisDate').textContent = `${pData.day}, ${pData.date}`;
  
  const tbody = document.getElementById('dailyAnalysisTableBody');
  if (pData.daily_breakdown && Object.keys(pData.daily_breakdown).length > 0) {
    const sorted = Object.entries(pData.daily_breakdown).sort((a, b) => b[1] - a[1]);
    tbody.innerHTML = sorted
      .filter(([k, v]) => v > 0)
      .map(([k, v]) => `<tr><td>${escapeHtml(k)}</td><td style="font-weight:bold;color:var(--accent)">${v} units</td></tr>`)
      .join('');
  } else {
    tbody.innerHTML = `<tr><td colspan="2" style="text-align:center">No breakdown data available for this date.</td></tr>`;
  }
  
  document.getElementById('dailyAnalysisModal').style.display = 'flex';
}

function closeDailyAnalysis() {
  document.getElementById('dailyAnalysisModal').style.display = 'none';
}

window.addEventListener('click', e => {
  if (e.target === document.getElementById('dailyAnalysisModal')) {
    closeDailyAnalysis();
  }
});
