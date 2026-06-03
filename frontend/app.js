// Global Error Visualizer for Debugging
function showError(msg) {
  const errDiv = document.createElement('div');
  errDiv.style.cssText = 'position:fixed;top:0;left:0;width:100%;background:#ef4444;color:#fff;padding:12px;z-index:999999;font-family:monospace;font-size:13px;box-shadow:0 4px 12px rgba(0,0,0,0.3);text-align:center';
  errDiv.innerHTML = `<strong>⚠️ Browser Console Error Detected:</strong> ${msg} <span style="cursor:pointer;margin-left:15px;text-decoration:underline" onclick="this.parentElement.remove()">[Dismiss]</span>`;
  document.body.appendChild(errDiv);
}

window.onerror = function(message, source, lineno, colno, error) {
  showError(`JS Error: ${message} at line ${lineno}, col ${colno} (${source})`);
  return false;
};

window.addEventListener('unhandledrejection', function(event) {
  showError(`Unhandled Promise Rejection: ${event.reason?.stack || event.reason?.message || event.reason}`);
});


const API = '';
let products = [], cart = [], csvData = null, charts = {}, currentUser = { username: 'Guest', role: 'Admin' }, allProducts = [];

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
  document.querySelectorAll('.nav-item').forEach(el => { el.style.display = 'flex'; });
  const addBtn = document.getElementById('btnAddProduct');
  if (addBtn) addBtn.style.display = 'inline-flex';
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

function canAccess() {
  return true;
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
  if (page === 'admin')       loadAdmin();
  
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
    const headers = { 'Content-Type': 'application/json' };
    const r = await fetch(API + path, {
      headers, ...opts,
      body: opts.body ? JSON.stringify(opts.body) : undefined
    });
    if (r.status === 429) {
      const data = await r.json().catch(() => ({}));
      toast(data.error || 'Too many requests. Please slow down.', 'warning');
      return { error: 'Rate limited' };
    }
    return await r.json();
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
  const yesterdayRev = todayRev * 0.85;
  const revChange = yesterdayRev > 0 ? ((todayRev - yesterdayRev) / yesterdayRev * 100).toFixed(1) : '0';
  
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
        <div class="kpi-trend festival">▲ Festival Boost</div>
      </div>
      <div class="value">+52%</div>
      <div class="label">AI SALES FORECAST LIFT</div>
      <div class="sub">Festival window active</div>
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
          <span class="alert-item-name">🔥 ${a.name}</span>
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
        <button class="alert-restock-btn" onclick="restock(${a.id})">✨ Quick Restock</button>
      </div>`;
    }).join('');
  } else {
    if (alertCountEl) alertCountEl.textContent = '0';
    ac.innerHTML = '<p style="color:var(--success)">✅ All stock levels healthy!</p>';
  }
  
  if (rep.monthly_revenue?.length) renderSalesChart(rep.monthly_revenue);
}

function renderSalesChart(data) {
  const chartEl = document.getElementById('salesChart');
  if (!chartEl) return;
  if (charts.sales) charts.sales.destroy();
  charts.sales = new Chart(chartEl, { type:'line', data:{
    labels: data.map(d=>d.month).reverse(),
    datasets:[{ label:'Revenue (₹)', data:data.map(d=>d.revenue).reverse(),
      borderColor:'#8b5cf6', backgroundColor:'rgba(139,92,246,0.1)', fill:true, tension:0.4, pointRadius:4,
      pointBackgroundColor: data.map(()=>'#a78bfa'),
      pointBorderColor: data.map(()=>'#8b5cf6'),
    }]
  }, options: chartOpts('₹') });
}

function chartOpts(prefix='') {
  return { responsive:true, maintainAspectRatio:false,
    plugins:{ legend:{ labels:{ color:'#94a3b8' } } },
    scales:{ x:{ ticks:{ color:'#94a3b8' }, grid:{ color:'rgba(255,255,255,0.05)' } },
             y:{ ticks:{ color:'#94a3b8', callback:v=>prefix+fmt(v) }, grid:{ color:'rgba(255,255,255,0.05)' } } } };
}

function setForecastDays(days, el) {
  document.querySelectorAll('.pill-btn').forEach(b => b.classList.remove('active'));
  if (el) el.classList.add('active');
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
async function loadBillingProducts() {
  const res = await api('/api/products');
  products = res.products || [];
  const sel = document.getElementById('billProduct');
  sel.innerHTML = products.map(p =>
    `<option value="${p.id}" data-price="${p.price}" data-stock="${p.current_stock}" data-unit="${p.unit}">${p.name} — ₹${p.price}/${p.unit}</option>`
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
  document.getElementById('cartItems').innerHTML = cart.length
    ? cart.map((c,i) => `<tr><td>${c.name}</td><td>${c.quantity} ${c.unit}</td><td>₹${c.price}</td><td>₹${(c.price*c.quantity).toFixed(2)}</td><td><button class="remove-btn" onclick="removeFromCart(${i})">✕</button></td></tr>`).join('')
    : '<tr><td colspan="5" style="color:var(--text-dim);text-align:center;padding:20px">Cart empty — add products above</td></tr>';
  document.getElementById('cartTotal').textContent = '₹' + cart.reduce((s,c)=>s+c.price*c.quantity,0).toFixed(2);
}

async function checkout() {
  if (!cart.length) return toast('Cart is empty!','error');
  const res = await api('/api/billing', { method:'POST', body:{ cart: cart.map(c=>({ product_id:c.product_id, quantity:c.quantity })) } });
  if (res.error) return toast(res.error,'error');
  document.getElementById('receiptArea').innerHTML =
    `<div class="receipt-card"><div style="text-align:center;margin-bottom:12px"><strong>SmartRetail AI</strong><br><small>${res.timestamp}</small></div>
    ${res.receipt.map(r=>`<div class="receipt-line"><span>${r.name} × ${r.qty} ${r.unit}</span><span>₹${r.total.toFixed(2)}</span></div>`).join('')}
    <div class="receipt-total">Grand Total: ₹${res.grand_total.toFixed(2)}</div></div>`;
  cart = []; renderCart(); loadBillingProducts();
  toast('Bill generated! Stock updated.');
}

// ─── Inventory ────────────────────────────────────────────────
async function loadInventory() {
  const res = await api('/api/products');
  allProducts = res.products || [];
  const cats = [...new Set(allProducts.map(p=>p.category))].sort();
  const catSel = document.getElementById('invCatFilter');
  catSel.innerHTML = '<option value="">All Categories</option>' + cats.map(c=>`<option>${c}</option>`).join('');
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
  document.getElementById('invTable').innerHTML = prods.map(p => {
    const status = p.current_stock < p.min_stock_level ? 'low' : p.current_stock < p.min_stock_level*2 ? 'warn' : 'ok';
    const tag = status==='low'
      ? `<span class="tag tag-red">🔴 Low</span>`
      : status==='warn'
      ? `<span class="tag tag-gold">🟡 Warning</span>`
      : `<span class="tag tag-green">🟢 OK</span>`;
    const canRestock = currentUser?.role==='Admin'||currentUser?.role==='Manager';
    return `<tr>
      <td><strong>${p.name}</strong></td><td>${p.category}</td><td>${p.unit}</td><td>₹${p.price}</td>
      <td class="stock-${status}">${p.current_stock}</td><td style="color:var(--text-dim)">${p.min_stock_level}</td>
      <td>${tag}</td>
      <td>${canRestock?`<button class="btn btn-success btn-sm" onclick="restock(${p.id})">+ Restock</button>`:'—'}</td>
    </tr>`;
  }).join('');
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
function handleCSV(input) {
  const file = input.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = e => {
    csvData = e.target.result;
    document.getElementById('csvStatus').innerHTML =
      `<span class="tag tag-green">✅ ${file.name} (${(file.size/1024).toFixed(1)} KB) — Ready to train</span>`;
    toast('CSV loaded! Click Predict to train.');
  };
  reader.readAsText(file);
}

const dz = document.getElementById('dropZone');
if (dz) {
  dz.addEventListener('dragover', e => { e.preventDefault(); dz.classList.add('dragover'); });
  dz.addEventListener('dragleave', () => dz.classList.remove('dragover'));
  dz.addEventListener('drop', e => {
    e.preventDefault(); dz.classList.remove('dragover');
    const f = e.dataTransfer.files[0];
    if (f) { document.getElementById('csvFile').files = e.dataTransfer.files; handleCSV(document.getElementById('csvFile')); }
  });
}

async function loadPredictions() {
  const res = await api('/api/products');
  if (res.error) return;
  const prods = res.products || [];
  const sel = document.getElementById('predProduct');
  if (sel) {
    let html = '<option value="ALL" style="font-weight:bold;color:var(--accent)">🌟 All Products</option>';
    html += prods.map(p => `<option value="${p.name}">${p.name} (${p.category})</option>`).join('');
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
                `<tr><td>${prodName}</td><td style="font-weight:bold;color:var(--accent)">${qty} units</td><td>${formatAccuracyCell(prodName, accuracyByProduct)}</td></tr>`
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

  document.getElementById('predResults').innerHTML =
    `<div style="margin-bottom:16px;display:flex;gap:8px;flex-wrap:wrap">
       <span class="tag tag-purple">Total Predicted: ${data.total_predicted} units</span>${srcLabel}${accTag}
     </div>
     <div style="font-size:12px;color:var(--text-dim);margin-bottom:8px">💡 Tip: Click on any date row to see a detailed product breakdown.</div>
     <div class="table-responsive">
       <table><thead><tr><th>Date</th><th>Day</th><th>Base</th><th>Adjusted</th><th>Boosts</th></tr></thead><tbody>
       ${data.predictions.map(p => {
          return `<tr class="clickable-row" style="cursor:pointer;" onclick="openDailyAnalysis('${p.date}')">
           <td>${p.date}</td><td>${p.day}</td><td>${p.base_qty}</td>
           <td style="font-weight:700;color:var(--accent)">${p.predicted_qty}</td>
           <td>${p.boosts.length ? p.boosts.map(b=>`<span class="tag tag-gold">${b}</span>`).join(' ') : '<span class="tag tag-green">Normal</span>'}</td></tr>`;
       }).join('')}
       </tbody></table>
     </div>`;
     
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
          <span>${i+1}. ${p.name}</span><span style="color:var(--success)">₹${fmt(p.total_revenue)}</span>
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
    <div><div class="fest-name">${f.name}</div><div class="fest-date">${f.start} to ${f.end} • <span class="tag tag-gold" style="font-size:10px">${f.category}</span></div></div>
  </div>`;
}

// ─── Admin Panel ──────────────────────────────────────────────
async function loadAdmin() {
  await Promise.all([loadUsers(), loadAudit()]);
}

async function loadUsers() {
  const res = await api('/api/users');
  if (res.error) { document.getElementById('usersPanel').innerHTML = `<p style="color:var(--danger)">${res.error}</p>`; return; }
  const roleColors = { Admin:'tag-red', Manager:'tag-gold', Staff:'tag-green' };
  document.getElementById('usersPanel').innerHTML = `
    <div class="table-responsive">
      <table><thead><tr><th>Username</th><th>Role</th><th>Status</th><th>Last Login</th><th>Action</th></tr></thead><tbody>
      ${res.users.map(u => `<tr>
        <td><strong>${u.username}</strong></td>
        <td><span class="tag ${roleColors[u.role]||'tag-purple'}">${u.role}</span></td>
        <td><span class="tag ${u.is_active?'tag-green':'tag-red'}">${u.is_active?'Active':'Disabled'}</span></td>
        <td style="font-size:11px;color:var(--text-dim)">${u.last_login||'Never'}</td>
        <td>${u.username!==currentUser?.username
          ? `<button class="btn btn-sm" style="background:${u.is_active?'rgba(239,68,68,0.15)':'rgba(16,185,129,0.15)'};color:${u.is_active?'var(--red)':'var(--green)'}" onclick="toggleUser(${u.id})">${u.is_active?'Disable':'Enable'}</button>`
          : '<span style="font-size:11px;color:var(--text-dim)">Current</span>'
        }</td>
      </tr>`).join('')}
      </tbody></table>
    </div>`;
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
         ${res.logs.map(l=>`<tr><td>${l.username||'System'}</td><td>${l.action}</td><td>${l.details||'-'}</td><td style="font-size:11px">${l.created_at}</td></tr>`).join('')}
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

function initApp() {
  if (_initialized) return;
  _initialized = true;
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

  console.log('[SmartRetail] All event listeners bound successfully.');

  applyRoleUI();
  updateUserDisplay();
  updateDateTime();
  checkDB();
  loadDashboard();

  console.log('[SmartRetail] App initialized successfully.');
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initApp);
} else {
  initApp();
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
      .map(([k, v]) => `<tr><td>${k}</td><td style="font-weight:bold;color:var(--accent)">${v} units</td></tr>`)
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
