const API = "/api/v1";
let token = localStorage.getItem("token") || "";
let currentUser = readUser();
let currentRegisteredFilter = "";
let currentView = "";
let realtimeSource = null;
let autoRefreshInFlight = false;

const $ = (id) => document.getElementById(id);

function readUser() {
  try { return JSON.parse(localStorage.getItem("current_user") || "null"); }
  catch { return null; }
}

function saveSession(data) {
  token = data.access_token;
  currentUser = data.user;
  localStorage.setItem("token", token);
  localStorage.setItem("current_user", JSON.stringify(currentUser));
}

function headers() {
  const h = { "Content-Type": "application/json" };
  if (token) h.Authorization = "Bearer " + token;
  return h;
}

function isAdmin() {
  const role = String(currentUser?.role || "").toLowerCase();
  return role === "admin" || role === "dispatcher" || role === "manager" || role === "super_admin";
}

function isSuperAdmin() {
  return String(currentUser?.role || "").toLowerCase() === "super_admin";
}

function isCitizen() { return !isAdmin(); }

function openSidebar() { $("dashboardPage")?.classList.add("sidebar-open"); }
function closeSidebar() { $("dashboardPage")?.classList.remove("sidebar-open"); }
function toggleSidebar() { $("dashboardPage")?.classList.toggle("sidebar-open"); }
function closeSidebarOnMobile() { if (window.matchMedia("(max-width: 980px)").matches) closeSidebar(); }

function showToast(message) {
  const box = $("toast");
  box.textContent = message;
  box.classList.remove("hidden");
  clearTimeout(showToast.timer);
  showToast.timer = setTimeout(() => box.classList.add("hidden"), 2800);
}

function startAutoRefresh() {
  startRealtimeUpdates();
}

function stopAutoRefresh() {
  stopRealtimeUpdates();
  autoRefreshInFlight = false;
}

function startRealtimeUpdates() {
  stopRealtimeUpdates();
  if (!token || !currentUser || !window.EventSource) return;
  realtimeSource = new EventSource(`${API}/events?token=${encodeURIComponent(token)}`);
  realtimeSource.onmessage = (event) => {
    try {
      handleRealtimeEvent(JSON.parse(event.data));
    } catch (_) {
      // Ignore malformed realtime messages.
    }
  };
  realtimeSource.onerror = () => {
    // EventSource reconnects automatically. Keep the UI unchanged while reconnecting.
  };
}

function stopRealtimeUpdates() {
  if (realtimeSource) {
    realtimeSource.close();
    realtimeSource = null;
  }
}

async function refreshActiveViewFromRealtime() {
  if (!token || !currentUser || autoRefreshInFlight || document.hidden) return;
  if (document.activeElement && document.activeElement.matches("textarea.admin-reply, input, textarea, select")) return;
  autoRefreshInFlight = true;
  try {
    if (isAdmin() && currentView === "admin") await loadAdminRequests(true);
    else if (isAdmin() && currentView === "registered") await loadRegisteredRequests(currentRegisteredFilter, true);
    else if (isAdmin() && currentView === "statistics") await loadMonthlyStatistics(true);
    else if (isCitizen() && currentView === "myRequests") await loadMyRequests(true);
    else if (isCitizen() && currentView === "notifications") await loadNotifications(true);
  } catch (_) {
    // keep the UI stable during background refresh
  } finally {
    autoRefreshInFlight = false;
  }
}

function handleRealtimeEvent(message) {
  const type = message?.type || "";
  const payload = message?.payload || {};
  if (isAdmin() && type === "request_created") {
    if (currentView === "admin") refreshActiveViewFromRealtime();
    return;
  }
  if (isAdmin() && type === "request_updated") {
    if (currentView === "admin" || currentView === "registered" || currentView === "statistics") refreshActiveViewFromRealtime();
    return;
  }
  if (isCitizen() && Number(payload.user_id) === Number(currentUser?.id)) {
    if (type === "request_updated") {
      if (currentView === "myRequests" || currentView === "notifications") refreshActiveViewFromRealtime();
      showToast("وصل رد جديد على طلبك");
    } else if (type === "request_created" && currentView === "myRequests") {
      refreshActiveViewFromRealtime();
    }
  }
}

async function apiFetch(path, options = {}) {
  const response = await fetch(API + path, { ...options, headers: { ...headers(), ...(options.headers || {}) } });
  let data = null;
  try { data = await response.json(); } catch { data = {}; }
  if (!response.ok) {
    const detail = Array.isArray(data.detail) ? data.detail.map(x => x.msg || String(x)).join("، ") : (data.detail || "حدث خطأ في الاتصال");
    throw new Error(detail);
  }
  return data;
}


function getRequestDraft(prefix) {
  if (prefix === "complaint") {
    return {
      type: "complaint",
      title: $("complaintTitle").value.trim(),
      category: $("complaintCategory").value.trim(),
      description: $("complaintDescription").value.trim(),
      priority: $("complaintPriority")?.value || "normal",
      governorate: $("complaintGovernorate")?.value.trim() || currentUser?.city || "",
      area: $("complaintArea")?.value.trim() || "",
    };
  }
  return {
    type: "emergency",
    title: $("emergencyTitle").value.trim(),
    category: "Emergency",
    description: $("emergencyDescription").value.trim(),
    priority: $("emergencyPriority")?.value || "emergency",
    governorate: $("emergencyGovernorate")?.value.trim() || currentUser?.city || "",
    area: $("emergencyArea")?.value.trim() || "",
  };
}

async function analyzeTextWithAi(payload) {
  return apiFetch("/ai/analyze", { method: "POST", body: JSON.stringify(payload) });
}

function scoreBar(label, value, cssClass = "") {
  const score = Math.max(0, Math.min(100, Number(value || 0)));
  return `
    <div class="fuzzy-meter ${cssClass}">
      <div class="fuzzy-meter-row"><strong>${escapeHtml(label)}</strong><span>${score}%</span></div>
      <div class="fuzzy-track"><i style="width:${score}%"></i></div>
    </div>`;
}

function renderAiAnalysis(data, options = {}) {
  const keywords = Array.isArray(data.keywords) && data.keywords.length
    ? `<p class="ai-keywords"><strong>كلمات مؤثرة:</strong> ${data.keywords.map(escapeHtml).join("، ")}</p>`
    : "";
  const useReplyButton = options.replyTarget
    ? `<button class="primary-btn ai-use-reply" type="button" onclick="useAiSuggestedReply('${options.replyTarget}', ${JSON.stringify(data.suggested_reply || "").replace(/"/g, '&quot;')})">استخدام الرد المقترح</button>`
    : "";
  const applyButton = options.prefix
    ? `<button class="ghost-btn" type="button" onclick="applyAiSuggestion('${options.prefix}', '${escapeAttr(data.priority || '')}', '${escapeAttr(data.category || '')}')">اعتماد التصنيف المقترح</button>`
    : "";
  const fuzzyScores = `
    <div class="fuzzy-grid">
      ${scoreBar("درجة الخطورة النهائية", data.risk_score, data.priority || "normal")}
      ${scoreBar("درجة الاستعجال", data.urgency_score, "urgent")}
      ${scoreBar("تأثير الموقع/المنطقة", data.location_score, "location")}
      ${scoreBar("تأثير الخدمات الأساسية", data.service_score, "service")}
      ${scoreBar("درجة الثقة", data.confidence_score, "confidence")}
    </div>`;
  return `
    <div class="ai-card fuzzy-ai-card">
      <div class="ai-card-head">
        <span class="ai-badge">Fuzzy AI</span>
        <strong>تحليل بالمنطق العائم</strong>
        <span class="risk-chip ${escapeHtml(data.priority || 'normal')}">التصنيف: ${escapeHtml(data.priority_label || priorityAr(data.priority))}</span>
      </div>
      ${fuzzyScores}
      <p><strong>القسم المقترح:</strong> ${escapeHtml(data.category || "-")}</p>
      <p><strong>الملخص:</strong> ${escapeHtml(data.summary || "-")}</p>
      <p><strong>الثقة:</strong> ${escapeHtml(data.confidence_label || "-")}</p>
      <p><strong>سبب التحليل:</strong> ${escapeHtml(data.reason || "-")}</p>
      ${keywords}
      <div class="ai-actions">${applyButton}${useReplyButton}</div>
    </div>`;
}

function escapeAttr(value) {
  return String(value ?? "").replace(/[&<>'"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" }[c]));
}

function applyAiSuggestion(prefix, priority, category) {
  const priorityField = $(`${prefix}Priority`);
  if (priorityField && priority && Array.from(priorityField.options).some(o => o.value === priority)) {
    priorityField.value = priority;
  }
  if (prefix === "complaint" && $("complaintCategory") && category && !$("complaintCategory").value.trim()) {
    $("complaintCategory").value = category;
  }
  showToast("تم اعتماد اقتراح المساعد الذكي");
}

async function analyzeCitizenRequest(prefix) {
  const box = $(`${prefix}AiResult`);
  if (!box) return;
  try {
    const payload = getRequestDraft(prefix);
    if (!payload.description || payload.description.length < 3) throw new Error("اكتب وصف البلاغ أولاً حتى يستطيع المساعد الذكي تحليله");
    box.classList.remove("muted");
    box.innerHTML = '<p class="muted">جاري التحليل الذكي...</p>';
    const data = await analyzeTextWithAi(payload);
    box.innerHTML = renderAiAnalysis(data, { prefix });
  } catch (err) {
    box.innerHTML = `<p class="error">${escapeHtml(err.message)}</p>`;
  }
}

async function analyzeAdminRequest(button) {
  const card = button.closest(".admin-card");
  if (!card) return;
  const box = card.querySelector(".admin-ai-result");
  try {
    const payload = {
      type: card.dataset.type || "complaint",
      title: card.dataset.title || "",
      category: card.dataset.category || "",
      description: card.dataset.description || "",
    };
    if (box) box.innerHTML = '<p class="muted">جاري توليد الملخص والرد المقترح...</p>';
    const data = await analyzeTextWithAi(payload);
    const replyTarget = `adminReply${card.dataset.id}`;
    if (box) box.innerHTML = renderAiAnalysis(data, { replyTarget });
  } catch (err) {
    if (box) box.innerHTML = `<p class="error">${escapeHtml(err.message)}</p>`;
  }
}

function useAiSuggestedReply(textareaId, text) {
  const field = $(textareaId);
  if (!field) return;
  field.value = text || "";
  field.focus();
  showToast("تم وضع الرد المقترح داخل خانة رسالة الأدمن");
}

function setAuthMode(mode) {
  const login = mode === "login";
  $("loginTab").classList.toggle("active", login);
  $("registerTab").classList.toggle("active", !login);
  $("loginForm").classList.toggle("hidden", !login);
  $("registerForm").classList.toggle("hidden", login);
  $("authMsg").textContent = "";
}

function clearLoginFields() {
  ["loginPhone", "loginPassword"].forEach(id => { if ($(id)) $(id).value = ""; });
}

function clearRegisterFields() {
  ["registerName", "registerPhone", "registerCity", "registerPassword"].forEach(id => { if ($(id)) $(id).value = ""; });
}

function clearAddAdminFields() {
  ["newAdminName", "newAdminPhone", "newAdminCity", "newAdminPassword"].forEach(id => { if ($(id)) $(id).value = ""; });
  if ($("addAdminMsg")) $("addAdminMsg").textContent = "";
}





function showAuth() {
  stopAutoRefresh();
  closeSidebar();

  document.body.classList.add("auth-mode");
  document.body.classList.remove("dashboard-mode");

  $("authPage").classList.remove("hidden");
  $("dashboardPage").classList.add("hidden");
  $("dashboardPage").classList.remove("sidebar-open");

  clearLoginFields();
  clearRegisterFields();
  setAuthMode("login");
}

function showDashboard() {
  startAutoRefresh();
  closeSidebar();

  document.body.classList.remove("auth-mode");
  document.body.classList.add("dashboard-mode");

  $("authPage").classList.add("hidden");
  $("dashboardPage").classList.remove("hidden");
  $("dashboardPage").classList.remove("sidebar-open");

  renderUserPanel();
  renderNav();
  showView(isAdmin() ? "admin" : "complaint");
}







function roleLabel() { return isAdmin() ? "مدير النظام" : "مستخدم النظام"; }

function renderUserPanel() {
  const name = currentUser?.full_name || "مستخدم";
  $("userName").textContent = name;
  $("userAvatar").textContent = name.trim()[0]?.toUpperCase() || "U";
  $("userRoleText").textContent = roleLabel();
  $("roleBadge").textContent = isAdmin() ? "صلاحيات الأدمن" : "لوحة المستخدم";
}

function renderNav() {
  const nav = $("navMenu");
  const citizenItems = [
    ["complaint", "إرسال شكوى", "📝"],
    ["emergency", "بلاغ طارئ", "🚨"],
    ["myRequests", "طلباتي", "📋"],
    ["notifications", "الإشعارات", "🔔"],
  ];
  const adminItems = [
    ["admin", "استلام الشكاوي", "⚙️"],
    ["registered", "الطلبات المسجلة", "📋"],
    ["statistics", "الإحصائيات الشهرية", "📊"],
  ];
  if (isSuperAdmin()) adminItems.push(["addAdmin", "إضافة أدمن", "➕"]);
  const items = isAdmin() ? adminItems : citizenItems;
  nav.innerHTML = items.map(([view, label, icon]) => `<button class="nav-btn" data-view="${view}" type="button"><span>${label}</span><b>${icon}</b></button>`).join("");
  nav.querySelectorAll("button").forEach(btn => btn.addEventListener("click", () => { showView(btn.dataset.view); closeSidebarOnMobile(); }));
}

function setActiveNav(view) {
  document.querySelectorAll(".nav-btn").forEach(btn => btn.classList.toggle("active", btn.dataset.view === view));
}

function hideAllViews() { document.querySelectorAll(".view").forEach(v => v.classList.add("hidden")); }

function showView(view) {
  if (isCitizen() && ["admin", "registered", "statistics", "addAdmin", "home"].includes(view)) {
    showToast("هذه الصفحة غير متاحة للمستخدم العادي");
    view = "complaint";
  }
  if (isAdmin() && ["home", "complaint", "emergency", "myRequests", "notifications"].includes(view)) {
    showToast("هذه الصفحة غير متاحة لحساب الأدمن");
    view = "admin";
  }
  if (view === "addAdmin" && !isSuperAdmin()) {
    showToast("هذه الصفحة متاحة للأدمن الأساسي فقط");
    view = "admin";
  }

  hideAllViews();
  setActiveNav(view);

  const titles = {
    complaint: "إرسال شكوى",
    emergency: "بلاغ طارئ",
    myRequests: "طلباتي",
    notifications: "الإشعارات",
    admin: "استلام الشكاوي",
    registered: "الطلبات المسجلة",
    statistics: "الإحصائيات الشهرية",
    addAdmin: "إضافة أدمن",
  };
  const subtitles = {
    complaint: "",
    emergency: "",
    myRequests: "",
    notifications: "",
    admin: "",
    registered: "",
    statistics: "",
    addAdmin: "",
  };
  $("pageTitle").textContent = titles[view] || "";
  $("pageSubtitle").textContent = subtitles[view] || "";

  if (view === "home") { view = isAdmin() ? "admin" : "complaint"; }
  currentView = view;
  if (view === "myRequests") loadMyRequests();
  if (view === "notifications") loadNotifications();
  if (view === "admin") loadAdminRequests();
  if (view === "registered") loadRegisteredRequests(currentRegisteredFilter);
  if (view === "statistics") loadMonthlyStatistics();
  if (view === "addAdmin") clearAddAdminFields();
  $(`${view}View`)?.classList.remove("hidden");
}

function renderHome() {
  $("homeView").innerHTML = "";
}

function floatOrNull(value) {
  const clean = String(value || "").trim();
  if (!clean) return null;
  const n = Number(clean);
  if (!Number.isFinite(n)) throw new Error("إحداثيات GPS يجب أن تكون أرقامًا صحيحة");
  return n;
}

function ensureLocation(prefix) {
  const lat = floatOrNull($(`${prefix}Lat`).value);
  const lon = floatOrNull($(`${prefix}Lon`).value);
  if (lat === null || lon === null) throw new Error("يرجى جلب الموقع الحالي قبل الإرسال.");
  return { latitude: lat, longitude: lon };
}

function getLocationFor(prefix) {
  const status = $(`${prefix}LocationStatus`);
  if (!navigator.geolocation) {
    status.textContent = "المتصفح لا يدعم جلب الموقع. شغّل الموقع من المتصفح أو جرّب متصفحًا آخر.";
    status.classList.add("error");
    return;
  }
  status.textContent = "جاري جلب الموقع... وافق على إذن الموقع من المتصفح.";
  status.classList.remove("error");
  navigator.geolocation.getCurrentPosition(
    (pos) => {
      const lat = Number(pos.coords.latitude).toFixed(6);
      const lon = Number(pos.coords.longitude).toFixed(6);
      $(`${prefix}Lat`).value = lat;
      $(`${prefix}Lon`).value = lon;
      status.innerHTML = `تم تحديد موقعك بنجاح: <a target="_blank" rel="noopener" href="https://www.google.com/maps?q=${lat},${lon}">فتح الموقع على الخريطة</a>`;
    },
    (err) => {
      status.textContent = err.code === 1 ? "تم رفض إذن الموقع. يجب السماح للموقع من المتصفح حتى تستطيع الإرسال." : "تعذر جلب الموقع. حاول مرة ثانية.";
      status.classList.add("error");
    },
    { enableHighAccuracy: true, timeout: 15000, maximumAge: 0 }
  );
}

async function createRequest(payload) {
  if (!isCitizen()) {
    showToast("الأدمن لا يستطيع إرسال طلبات مستخدمين");
    return;
  }
  await apiFetch("/requests", { method: "POST", body: JSON.stringify(payload) });
  showToast("تم إرسال الطلب بنجاح");
  showView("complaint");
}

async function loadMyRequests(silent = false) {
  const box = $("myRequestsList");
  if (!silent) box.innerHTML = '<p class="muted">جاري التحميل...</p>';
  try {
    const items = await apiFetch("/requests");
    box.innerHTML = items.length ? items.map(renderRequestCard).join("") : '<p class="muted">لم ترسل أي طلبات بعد.</p>';
  } catch (e) { box.innerHTML = `<p class="error">${escapeHtml(e.message)}</p>`; }
}

async function loadNotifications(silent = false) {
  const box = $("notificationsList");
  if (!silent) box.innerHTML = '<p class="muted">جاري التحميل...</p>';
  try {
    const items = await apiFetch("/notifications");
    box.innerHTML = items.length ? items.map(n => `
      <article class="item-card">
        <h4>${escapeHtml(n.title || "إشعار")}</h4>
        <p>${escapeHtml(n.message || "")}</p>
        <small>${formatDate(n.created_at)}</small>
      </article>`).join("") : '<p class="muted">لا توجد إشعارات.</p>';
  } catch (e) { box.innerHTML = `<p class="error">${escapeHtml(e.message)}</p>`; }
}

async function loadAdminRequests(silent = false) {
  if (!isAdmin()) return showView("complaint");
  if (silent && document.activeElement && document.activeElement.matches("textarea.admin-reply")) return;
  const box = $("adminRequestsList");
  if (!silent) box.innerHTML = '<p class="muted">جاري التحميل...</p>';
  try {
    const items = await apiFetch("/admin/requests?status=submitted");
    box.innerHTML = items.length ? items.map(renderAdminRequestCard).join("") : '<p class="muted">لا توجد طلبات جديدة.</p>';
    bindAdminButtons();
  } catch (e) { box.innerHTML = `<p class="error">${escapeHtml(e.message)}</p>`; }
}

async function loadRegisteredRequests(filter = "", silent = false) {
  if (!isAdmin()) return showView("complaint");
  currentRegisteredFilter = filter || "";
  const box = $("registeredRequestsList");
  if (!silent) box.innerHTML = '<p class="muted">جاري التحميل...</p>';
  try {
    const query = filter ? `?status=${encodeURIComponent(filter)}` : "?scope=registered";
    const items = await apiFetch("/admin/requests" + query);
    box.innerHTML = items.length ? items.map(renderRegisteredRequestCard).join("") : '<p class="muted">لا توجد طلبات مسجلة.</p>';
  } catch (e) { box.innerHTML = `<p class="error">${escapeHtml(e.message)}</p>`; }
}

async function loadMonthlyStatistics(silent = false) {
  if (!isAdmin()) return showView("complaint");
  const box = $("monthlyStatsBox");
  if (!box) return;
  if (!silent) box.innerHTML = '<p class="muted">جاري تحميل الإحصائيات...</p>';
  try {
    const rows = await apiFetch("/admin/statistics/monthly");
    box.innerHTML = rows.length ? renderMonthlyStatsTable(rows) : '<p class="muted">لا توجد بيانات كافية للإحصائيات بعد.</p>';
  } catch (e) { box.innerHTML = `<p class="error">${escapeHtml(e.message)}</p>`; }
}

function renderMonthlyStatsTable(rows) {
  return `
    <div class="table-scroll">
      <table class="stats-table">
        <thead>
          <tr>
            <th>الشهر</th>
            <th>إجمالي الطلبات</th>
            <th>عادية</th>
            <th>طارئة</th>
            <th>مستعجلة</th>
            <th>خطرة</th>
            <th>مرتبطة بالأمان</th>
            <th>انقطاعات</th>
            <th>موارد أساسية</th>
            <th>مقبولة</th>
            <th>مرفوضة</th>
            <th>معلّقة</th>
            <th>مستوى الضغط</th>
          </tr>
        </thead>
        <tbody>
          ${rows.map(r => `
            <tr>
              <td><strong>${escapeHtml(r.month_label)}</strong></td>
              <td>${r.total}</td>
              <td>${r.normal}</td>
              <td>${r.emergency}</td>
              <td>${r.urgent}</td>
              <td>${r.dangerous}</td>
              <td>${r.safety_related}</td>
              <td>${r.outage_related}</td>
              <td>${r.essential_resources}</td>
              <td>${r.accepted}</td>
              <td>${r.rejected}</td>
              <td>${r.pending}</td>
              <td><span class="load-badge ${escapeHtml(r.load_level_key)}">${escapeHtml(r.load_level)}</span></td>
            </tr>`).join("")}
        </tbody>
      </table>
    </div>`;
}

function locationHtml(it) {
  if (it.latitude == null || it.longitude == null) return `<span class="location-missing">لا يوجد موقع</span>`;
  const lat = escapeHtml(it.latitude);
  const lon = escapeHtml(it.longitude);
  return `<a class="map-link" target="_blank" rel="noopener" href="https://www.google.com/maps?q=${lat},${lon}">فتح الموقع على الخريطة</a>`;
}

function citizenRequestMessage(it) {
  const reply = String(it.admin_reply || "").trim();
  if (reply) return reply;
  if (it.status === "accepted" || it.status === "resolved") return "تم قبول طلبك، وصلت الرسالة وبأقرب وقت سيتم مساعدتك.";
  if (it.status === "rejected") return "تم رفض الطلب. يجب أن يظهر سبب الرفض هنا.";
  return "طلبك قيد المراجعة لدى الإدارة.";
}

function renderRequestCard(it) {
  return `
    <article class="item-card request-card citizen-request-card">
      <div class="card-top"><h4>#${it.id} - ${escapeHtml(it.title)}</h4><span class="status ${it.status}">${statusAr(it.status)}</span></div>
      <p>${escapeHtml(it.description || "")}</p>
      <p class="meta">${typeAr(it.type)} | درجة الحالة: ${priorityAr(it.priority)} | ${formatDate(it.created_at)}</p>
      <p class="meta">الموقع: ${locationHtml(it)}</p>
      <div class="reply-box"><strong>حالة الطلب:</strong><p>${escapeHtml(citizenRequestMessage(it))}</p></div>
    </article>`;
}

function renderAdminRequestCard(it) {
  return `
    <article class="item-card request-card admin-card" data-id="${it.id}" data-type="${escapeAttr(it.type || '')}" data-title="${escapeAttr(it.title || '')}" data-category="${escapeAttr(it.category || '')}" data-description="${escapeAttr(it.description || '')}">
      <div class="card-top"><h4>#${it.id} - ${escapeHtml(it.title)}</h4><span class="status ${it.status}">${statusAr(it.status)}</span></div>
      <p>${escapeHtml(it.description || "")}</p>
      <p class="meta">${typeAr(it.type)} | درجة الحالة: ${priorityAr(it.priority)} | المواطن: ${escapeHtml(it.citizen_name || "-")} - ${escapeHtml(it.citizen_phone || "-")} | ${formatDate(it.created_at)}</p>
      <p class="meta">الموقع: ${locationHtml(it)}</p>
      <div class="ai-box admin-ai-box">
        <div class="section-row compact-row">
          <label>المساعد الذكي للأدمن</label>
          <button class="ghost-btn ai-admin-btn" type="button">تلخيص واقتراح رد</button>
        </div>
        <div class="admin-ai-result muted">اضغط التحليل ليظهر ملخص البلاغ والتوصية والرد المقترح.</div>
      </div>
      <textarea id="adminReply${it.id}" class="admin-reply" placeholder="رسالة للمستخدم. عند الرفض يجب كتابة سبب الرفض.">${escapeHtml(it.admin_reply || "")}</textarea>
      <div class="admin-actions admin-simple-actions">
        <button class="accept-btn" data-status="accepted">مقبول</button>
        <button class="reject-btn" data-status="rejected">مرفوض</button>
      </div>
    </article>`;
}

function renderRegisteredRequestCard(it) {
  return `
    <article class="item-card request-card registered-card">
      <div class="card-top"><h4>#${it.id} - ${escapeHtml(it.title)}</h4><span class="status ${it.status}">${statusAr(it.status)}</span></div>
      <p>${escapeHtml(it.description || "")}</p>
      <p class="meta">${typeAr(it.type)} | درجة الحالة: ${priorityAr(it.priority)} | المواطن: ${escapeHtml(it.citizen_name || "-")} - ${escapeHtml(it.citizen_phone || "-")} | ${formatDate(it.created_at)}</p>
      <p class="meta">الموقع: ${locationHtml(it)}</p>
      ${it.admin_reply ? `<div class="reply-box"><strong>رسالة الإدارة:</strong><p>${escapeHtml(it.admin_reply)}</p></div>` : ""}
    </article>`;
}

function bindAdminButtons() {
  document.querySelectorAll(".admin-card").forEach(card => {
    const id = card.dataset.id;
    card.querySelectorAll("[data-status]").forEach(btn => btn.addEventListener("click", () => updateRequest(id, btn.dataset.status, card.querySelector(".admin-reply").value)));
    const aiButton = card.querySelector(".ai-admin-btn");
    if (aiButton) aiButton.addEventListener("click", () => analyzeAdminRequest(aiButton));
  });
}

async function updateRequest(id, status, reply) {
  try {
    reply = String(reply || "").trim();
    if (status === "rejected" && !reply) {
      showToast("عند رفض الطلب يجب كتابة سبب الرفض");
      return;
    }
    await apiFetch(`/admin/requests/${id}`, { method: "PATCH", body: JSON.stringify({ status, admin_reply: reply, note: reply }) });
    showToast("تم إرسال الرد للمستخدم ونقل الطلب إلى الطلبات المسجلة");
    loadAdminRequests();
  } catch (e) { showToast(e.message); }
}

function logout() {
  token = "";
  currentUser = null;
  localStorage.removeItem("token");
  localStorage.removeItem("current_user");
  showAuth();
}

function formatDate(value) {
  if (!value) return "";
  try {
    const d = new Date(value);
    return d.toLocaleString("ar-SY");
  } catch { return ""; }
}
function statusAr(s) { return ({ submitted: "جديد", accepted: "مقبول", resolved: "مقبول", rejected: "مرفوض", triaged: "مستلم", in_progress: "قيد المعالجة", closed: "مغلق" })[s] || s || "-"; }
function priorityAr(p) { return ({ normal: "عادية", emergency: "طارئة", urgent: "مستعجلة", dangerous: "خطرة", high: "مستعجلة", critical: "خطرة", low: "عادية" })[p] || p || "-"; }
function typeAr(t) { return t === "emergency" ? "بلاغ طارئ" : "شكوى"; }
function escapeHtml(value) { return String(value ?? "").replace(/[&<>'"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" }[c])); }

$("loginTab").addEventListener("click", () => setAuthMode("login"));
$("registerTab").addEventListener("click", () => setAuthMode("register"));

$("loginForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  $("authMsg").textContent = "";
  try {
    const phone = $("loginPhone").value.trim();
    const password = $("loginPassword").value;
    if (!phone || !password) throw new Error("اكتب اسم الدخول وكلمة المرور");
    const data = await apiFetch("/auth/login", { method: "POST", body: JSON.stringify({ phone, password }) });
    clearRegisterFields();
    clearLoginFields();
    saveSession(data);
    showDashboard();
  } catch (err) { $("authMsg").textContent = err.message; }
});

$("registerForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  $("authMsg").textContent = "";
  try {
    const data = await apiFetch("/auth/register", { method: "POST", body: JSON.stringify({
      full_name: $("registerName").value.trim(),
      phone: $("registerPhone").value.trim(),
      city: $("registerCity").value.trim(),
      password: $("registerPassword").value,
    }) });
    clearRegisterFields();
    clearLoginFields();
    saveSession(data);
    showDashboard();
  } catch (err) { $("authMsg").textContent = err.message; }
});

$("complaintForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  try {
    const loc = ensureLocation("complaint");
    await createRequest({
      type: "complaint",
      title: $("complaintTitle").value.trim(),
      category: $("complaintCategory").value.trim() || null,
      description: $("complaintDescription").value.trim(),
      city: $("complaintGovernorate")?.value.trim() || currentUser?.city || null,
      ...loc,
      priority: $("complaintPriority").value || "normal",
    });
    e.target.reset();
    $("complaintLocationStatus").textContent = "";
  } catch (err) { showToast(err.message); }
});

$("emergencyForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  try {
    const loc = ensureLocation("emergency");
    await createRequest({
      type: "emergency",
      title: $("emergencyTitle").value.trim(),
      category: "Emergency",
      description: $("emergencyDescription").value.trim(),
      city: $("emergencyGovernorate")?.value.trim() || currentUser?.city || null,
      ...loc,
      priority: $("emergencyPriority").value || "emergency",
    });
    e.target.reset();
    $("emergencyLocationStatus").textContent = "";
  } catch (err) { showToast(err.message); }
});


if ($("addAdminForm")) {
  $("addAdminForm").addEventListener("submit", async (e) => {
    e.preventDefault();
    if (!isSuperAdmin()) {
      showToast("إضافة الأدمن متاحة للأدمن الأساسي فقط");
      return;
    }
    if ($("addAdminMsg")) $("addAdminMsg").textContent = "";
    try {
      const payload = {
        full_name: $("newAdminName").value.trim(),
        phone: $("newAdminPhone").value.trim(),
        city: $("newAdminCity").value.trim(),
        password: $("newAdminPassword").value,
      };
      if (!payload.full_name || !payload.phone || !payload.password) throw new Error("اكتب اسم الأدمن واسم الدخول وكلمة المرور");
      await apiFetch("/admin/admins", { method: "POST", body: JSON.stringify(payload) });
      clearAddAdminFields();
      if ($("addAdminMsg")) $("addAdminMsg").textContent = "تم إنشاء حساب الأدمن بنجاح";
      showToast("تم إنشاء حساب الأدمن بنجاح");
    } catch (err) {
      if ($("addAdminMsg")) $("addAdminMsg").textContent = err.message;
      showToast(err.message);
    }
  });
}

document.addEventListener("keydown", (event) => { if (event.key === "Escape") closeSidebar(); });
window.addEventListener("resize", () => { if (!window.matchMedia("(max-width: 980px)").matches) closeSidebar(); });

(async function boot() {
  if (!token) return showAuth();
  try {
    currentUser = await apiFetch("/auth/me");
    localStorage.setItem("current_user", JSON.stringify(currentUser));
    showDashboard();
  } catch { logout(); }
})();
