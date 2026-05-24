// ─── SmartRetail AI — Frontend Logic ───────────────────────────
const API = '';
let products = [], cart = [], csvData = null, charts = {}, currentUser = { username: 'public', role: 'Admin' }, allProducts = [];

// ─── Role Permissions ──────────────────────────────────────────
const ROLES = {
  Admin:   ['dashboard','billing','inventory','predictions','reports','festivals','admin'],
  Manager: ['dashboard','billing','inventory','predictions','reports','festivals'],
  Staff:   ['dashboard','billing'],
};

// ─── Login ────────────────────────────────────────────────────
async function doLogin() {
  const username = document.getElementById('loginUser').value.trim();
  const password = document.getElementById('loginPass').value;
  const btn = document.getElementById('loginBtn');
  const err = document.getElementById('loginError');
  if (!username || !password) { showLoginError('Enter username and password'); return; }
  btn.textContent = 'Signing in...'; btn.disabled = true;
  const res = await api('/api/login', { method:'POST', body:{ username, password } });
  btn.textContent = '🔐 Sign In'; btn.disabled = false;
  if (res.error) { showLoginError(res.error); return; }
  // Store JWT token securely in sessionStorage
  if (res.token) sessionStorage.setItem('jwt_token', res.token);
  currentUser = res.user;
  document.getElementById('loginScreen').style.display = 'none';
  document.getElementById('appShell').classList.add('visible');
  applyRoleUI();
  checkDB();
  loadDashboard();
}

function showLoginError(msg) {
  const e = document.getElementById('loginError');
  e.textContent = msg; e.style.display = 'block';
  setTimeout(() => e.style.display = 'none', 4000);
}

function doLogout() {
  currentUser = null;
  // Clear JWT token from sessionStorage
  sessionStorage.removeItem('jwt_token');
  document.getElementById('appShell').classList.remove('visible');
  document.getElementById('loginScreen').style.display = 'flex';
  document.getElementById('loginUser').value = '';
  document.getElementById('loginPass').value = '';
  // Reset nav
  document.querySelectorAll('.nav-item').forEach(el => el.style.display = '');
}

function applyRoleUI() {
  if (!currentUser) return;
  const allowed = ROLES[currentUser.role] || [];
  // Show/hide nav items
  document.querySelectorAll('.nav-item').forEach(el => {
    const page = el.id?.replace('nav-','');
    el.style.display = allowed.includes(page) ? 'flex' : 'none';
  });
  // Manager+ can add products
  const canManage = currentUser.role === 'Admin' || currentUser.role === 'Manager';
  const addBtn = document.getElementById('btnAddProduct');
  if (addBtn) addBtn.style.display = canManage ? 'inline-flex' : 'none';
  // User info
  const roleColors = { Admin:'#ef4444', Manager:'#f59e0b', Staff:'#10b981' };
  const userInfoEl = document.getElementById('userInfo');
  if (userInfoEl) {
    userInfoEl.innerHTML =
      `<strong style="color:#fff">${currentUser.username}</strong><br>
       <span style="color:${roleColors[currentUser.role]}">${currentUser.role}</span>`;
  }
}

function canAccess(page) {
  if (!currentUser) return false;
  return (ROLES[currentUser.role] || []).includes(page);
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
  if (!canAccess(page)) { toast('Access denied for your role', 'error'); return; }
  document.querySelectorAll('.section').forEach(s => s.classList.remove('active'));
  document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
  document.getElementById('sec-' + page).classList.add('active');
  const navEl = document.getElementById('nav-' + page);
  if (navEl) navEl.classList.add('active');
  if (page === 'dashboard')   loadDashboard();
  if (page === 'inventory')   loadInventory();
  if (page === 'billing')     loadBillingProducts();
  if (page === 'reports')     loadReports();
  if (page === 'festivals')   loadFestivals();
  if (page === 'admin')       loadAdmin();
  toggleSidebar(false); // Automatically close slide-out sidebar on mobile select
}

// ─── Toast ─────────────────────────────────────────────────────
function toast(msg, type = 'success') {
  const t = document.getElementById('toast');
  t.textContent = msg; t.className = 'toast ' + type; t.style.display = 'block';
  setTimeout(() => t.style.display = 'none', 3500);
}

// ─── API Helper (with JWT Auth & Error Handling) ──────────────
async function api(path, opts = {}) {
  try {
    const headers = { 'Content-Type': 'application/json' };
    // Attach JWT Bearer token if available
    const token = sessionStorage.getItem('jwt_token');
    if (token) headers['Authorization'] = 'Bearer ' + token;
    const r = await fetch(API + path, {
      headers, ...opts,
      body: opts.body ? JSON.stringify(opts.body) : undefined
    });
    // Handle 401 Unauthorized — session expired
    if (r.status === 401 && path !== '/api/login') {
      toast('Session expired. Please log in again.', 'error');
      doLogout();
      return { error: 'Session expired' };
    }
    // Handle 429 Too Many Requests — rate limited
    if (r.status === 429) {
      const data = await r.json().catch(() => ({}));
      toast(data.error || 'Too many requests. Please slow down.', 'warning');
      return { error: 'Rate limited' };
    }
    return await r.json();
  } catch (e) { return { error: e.message }; }
}

function fmt(n) { return Number(n||0).toLocaleString('en-IN', { maximumFractionDigits: 0 }); }

// ─── Dashboard ────────────────────────────────────────────────
async function loadDashboard() {
  const dateEl = document.getElementById('topbarDateTime') || document.getElementById('dateDisplay');
  if (dateEl) {
    dateEl.textContent =
      new Date().toLocaleDateString('en-IN', { weekday:'long', year:'numeric', month:'long', day:'numeric' });
  }
  const rep = await api('/api/reports');
  if (rep.error) return;
  const low = rep.stock_summary?.low || 0;
  document.getElementById('lowBadge').textContent = low;
  document.getElementById('kpiCards').innerHTML = `
    <div class="kpi-card revenue"><div class="label">Today's Revenue</div><div class="value">₹${fmt(rep.today_revenue)}</div><div class="sub">Today</div></div>
    <div class="kpi-card"><div class="label">Total Revenue</div><div class="value">₹${fmt(rep.total_revenue)}</div><div class="sub">All time</div></div>
    <div class="kpi-card"><div class="label">Active Products</div><div class="value">${rep.stock_summary?.total||0}</div><div class="sub">In database</div></div>
    <div class="kpi-card ${low>0?'danger':''}"><div class="label">Low Stock Alerts</div><div class="value">${low}</div><div class="sub">Need restock</div></div>`;
  const alerts = await api('/api/inventory-alerts');
  const ac = document.getElementById('alertsContainer');
  if (alerts.alerts?.length) {
    ac.innerHTML = alerts.alerts.map(a =>
      `<div class="alert-card"><div class="info"><h4>🚨 ${a.name} — LOW STOCK</h4><p>Current: <strong>${a.current_stock}</strong> | Min: ${a.min_stock_level} | Shortage: <strong>${a.min_stock_level - a.current_stock}</strong></p></div>
       <button class="btn btn-danger btn-sm" onclick="restock(${a.id})">⚠️ Restock +50</button></div>`
    ).join('');
  } else {
    ac.innerHTML = '<p style="color:var(--success)">✅ All stock levels healthy!</p>';
  }
  if (rep.monthly_revenue?.length) renderSalesChart(rep.monthly_revenue);
  if (rep.top_products?.length)    renderStockChart(rep.top_products);
}

function renderSalesChart(data) {
  if (charts.sales) charts.sales.destroy();
  charts.sales = new Chart(document.getElementById('salesChart'), { type:'line', data:{
    labels: data.map(d=>d.month).reverse(),
    datasets:[{ label:'Revenue (₹)', data:data.map(d=>d.revenue).reverse(),
      borderColor:'#8b5cf6', backgroundColor:'rgba(139,92,246,0.1)', fill:true, tension:0.4, pointRadius:4 }]
  }, options: chartOpts('₹') });
}

function renderStockChart(data) {
  const chartEl = document.getElementById('stockChart');
  if (!chartEl) return;
  if (charts.stock) charts.stock.destroy();
  charts.stock = new Chart(chartEl, { type:'bar', data:{
    labels: data.slice(0,8).map(d=>d.name),
    datasets:[{ label:'Revenue (₹)', data:data.slice(0,8).map(d=>d.total_revenue),
      backgroundColor:['#8b5cf6','#ec4899','#06b6d4','#10b981','#f59e0b','#ef4444','#a78bfa','#f97316'] }]
  }, options: chartOpts('₹') });
}

function chartOpts(prefix='') {
  return { responsive:true, maintainAspectRatio:false,
    plugins:{ legend:{ labels:{ color:'#94a3b8' } } },
    scales:{ x:{ ticks:{ color:'#94a3b8' }, grid:{ color:'rgba(255,255,255,0.05)' } },
             y:{ ticks:{ color:'#94a3b8', callback:v=>prefix+fmt(v) }, grid:{ color:'rgba(255,255,255,0.05)' } } } };
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
    ? cart.map((c,i) => `<div class="cart-item"><span>${c.name} × ${c.quantity} ${c.unit}</span><span>₹${(c.price*c.quantity).toFixed(2)} <span class="remove" onclick="removeFromCart(${i})">✕</span></span></div>`).join('')
    : '<p style="color:var(--text-dim);text-align:center">Cart empty</p>';
  document.getElementById('cartTotal').textContent = '₹' + cart.reduce((s,c)=>s+c.price*c.quantity,0).toFixed(2);
}

async function checkout() {
  if (!cart.length) return toast('Cart is empty!','error');
  const res = await api('/api/billing', { method:'POST', body:{ cart: cart.map(c=>({ product_id:c.product_id, quantity:c.quantity })) } });
  if (res.error) return toast(res.error,'error');
  document.getElementById('receiptArea').innerHTML =
    `<div class="receipt"><div style="text-align:center;margin-bottom:12px"><strong>SmartRetail AI</strong><br><small>${res.timestamp}</small></div>
    ${res.receipt.map(r=>`<div class="line"><span>${r.name} × ${r.qty} ${r.unit}</span><span>₹${r.total.toFixed(2)}</span></div>`).join('')}
    <div class="total">Grand Total: ₹${res.grand_total.toFixed(2)}</div></div>`;
  cart = []; renderCart(); loadBillingProducts();
  toast('Bill generated! Stock updated.');
}

// ─── Inventory ────────────────────────────────────────────────
async function loadInventory() {
  const res = await api('/api/products');
  allProducts = res.products || [];
  // Populate category filter
  const cats = [...new Set(allProducts.map(p=>p.category))].sort();
  const catSel = document.getElementById('invCatFilter');
  catSel.innerHTML = '<option value="">All Categories</option>' + cats.map(c=>`<option>${c}</option>`).join('');
  // Show add product button for Manager/Admin
  const addBtn = document.getElementById('btnAddProduct');
  if (addBtn) addBtn.style.display = (currentUser?.role==='Admin'||currentUser?.role==='Manager') ? 'inline-flex' : 'none';
  renderInventoryTable(allProducts);
  renderLowStockBanner(allProducts);
}

function renderLowStockBanner(prods) {
  const low = prods.filter(p => p.current_stock < p.min_stock_level);
  const banner = document.getElementById('lowStockBanner');
  const list = document.getElementById('lowStockList');
  if (banner && list) {
    if (low.length) {
      banner.style.display = 'block';
      list.innerHTML = low.map(p =>
        `<div style="display:flex;justify-content:space-between;align-items:center;padding:8px 0;border-bottom:1px solid rgba(239,68,68,0.15)">
          <span><strong>${p.name}</strong> <span class="tag tag-red">Only ${p.current_stock} left</span></span>
          <button class="btn btn-danger btn-sm" onclick="restock(${p.id})">Restock +50</button>
        </div>`
      ).join('');
    } else {
      banner.style.display = 'none';
    }
  }
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

// Drag and drop
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

async function runPrediction(forceDB = false) {
  const product = document.getElementById('predProduct').value.trim();
  const start   = document.getElementById('predStart').value;
  const end     = document.getElementById('predEnd').value || start;
  if (!product || !start) return toast('Enter product name and start date','error');
  if (!forceDB && !csvData) return toast('Upload a CSV or click "Use DB Data"','error');
  document.getElementById('predResults').innerHTML = '<p style="color:var(--text-dim);text-align:center;padding:20px">Training model...</p>';
  // Train
  const trainBody = forceDB ? { product } : { csv_data: csvData, product };
  const train = await api('/api/train', { method:'POST', body: trainBody });
  if (!train.success) return toast(train.error || train.message, 'error');
  const src = train.source === 'database' ? '🗄️ Trained from database' : '📄 Trained from your CSV';
  document.getElementById('trainSource').textContent = `${src}: ${train.message}`;
  toast(train.message);
  // Predict
  const pred = await api('/api/predict', { method:'POST', body:{ product, start_date: start, end_date: end } });
  if (pred.error) return toast(pred.error,'error');
  renderPredictions(pred);
}

function renderPredictions(data) {
  const srcLabel = data.source === 'database'
    ? '<span class="tag tag-green">Source: Database</span>'
    : '<span class="tag tag-purple">Source: Your CSV</span>';
  document.getElementById('predResults').innerHTML =
    `<div style="margin-bottom:16px;display:flex;gap:8px;flex-wrap:wrap">
       <span class="tag tag-purple">Total Predicted: ${data.total_predicted} units</span>${srcLabel}
     </div>
     <div class="table-responsive">
       <table><thead><tr><th>Date</th><th>Day</th><th>Base</th><th>Adjusted</th><th>Boosts</th></tr></thead><tbody>
       ${data.predictions.map(p =>
         `<tr><td>${p.date}</td><td>${p.day}</td><td>${p.base_qty}</td>
          <td style="font-weight:700;color:var(--accent)">${p.predicted_qty}</td>
          <td>${p.boosts.length ? p.boosts.map(b=>`<span class="tag tag-gold">${b}</span>`).join(' ') : '<span class="tag tag-green">Normal</span>'}</td></tr>`
       ).join('')}
       </tbody></table>
     </div>`;
  if (charts.forecast) charts.forecast.destroy();
  charts.forecast = new Chart(document.getElementById('forecastChart'), { type:'line', data:{
    labels: data.predictions.map(p=>p.date),
    datasets:[
      { label:'Base Prediction', data:data.predictions.map(p=>p.base_qty), borderColor:'#94a3b8', borderDash:[5,5], tension:0.4, pointRadius:3 },
      { label:'Adjusted (with boosts)', data:data.predictions.map(p=>p.predicted_qty), borderColor:'#8b5cf6', backgroundColor:'rgba(139,92,246,0.1)', fill:true, tension:0.4, pointRadius:5,
        pointBackgroundColor: data.predictions.map(p=>p.boosts.length?'#ec4899':'#8b5cf6') }
    ]}, options: chartOpts() });
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
    <div class="mult">${f.multiplier}x</div>
    <div><div class="name">${f.name}</div><div class="date">${f.start} to ${f.end} • <span class="tag tag-gold" style="font-size:10px">${f.category}</span></div></div>
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
          ? `<button class="btn btn-sm" style="background:${u.is_active?'rgba(239,68,68,0.15)':'rgba(16,185,129,0.15)'};color:${u.is_active?'var(--danger)':'var(--success)'}" onclick="toggleUser(${u.id})">${u.is_active?'Disable':'Enable'}</button>`
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
  if (res.status === 'connected') { el.className='db-badge live'; el.textContent='● MySQL Live'; }
  else { el.className='db-badge off'; el.textContent='● Disconnected'; }
}

// ─── Auto Initialization ──────────────────────────────────────
applyRoleUI();
checkDB();
loadDashboard();

