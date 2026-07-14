const API = "";

let config = null;
let activeTab = location.hash.replace("#", "") || "overview";
let currentUser = JSON.parse(localStorage.getItem("vmsUser") || "null");
let logPage = 1;
let logPageSize = 20;

const baseTabs = [
  { id: "overview", title: "总体概览" },
  { id: "oa", title: "OA 审批" },
  { id: "guard", title: "门卫核验" },
  { id: "admin", title: "管理报表" },
  { id: "users", title: "账号创建", adminOnly: true },
  { id: "permissions", title: "菜单分配权限", adminOnly: true },
];

const nav = document.querySelector("#nav");
const view = document.querySelector("#view");
const title = document.querySelector("#page-title");
const message = document.querySelector("#message");
const refreshBtn = document.querySelector("#refresh-btn");
const todayPill = document.querySelector("#today-pill");
const appShell = document.querySelector("#app-shell");
const loginScreen = document.querySelector("#login-screen");

function showMessage(text, type = "success") {
  message.textContent = text;
  message.className = `message ${type}`;
  if (!text) message.className = "message hidden";
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function formatDateTime(value) {
  return (value || "").replace("T", " ");
}

async function api(path, options = {}) {
  const res = await fetch(API + path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const contentType = res.headers.get("content-type") || "";
  const data = contentType.includes("application/json") ? await res.json() : await res.text();
  if (!res.ok) {
    const msg = data.message || "请求失败";
    const details = Array.isArray(data.details) ? `：${data.details.join("；")}` : "";
    throw new Error(msg + details);
  }
  return data;
}

function userTabs() {
  if (!currentUser) return [];
  const permissions = new Set(currentUser.permissions || []);
  return baseTabs.filter((tab) => permissions.has(tab.id) && (!tab.adminOnly || currentUser.role === "admin"));
}

function statusPill(status) {
  let color = "";
  if (["已通过", "待来访", "待入厂", "已入厂", "已离厂"].includes(status)) color = "green";
  if (["审批中", "部分入厂", "部分离厂"].includes(status)) color = "orange";
  if (["已驳回", "已取消", "已过期"].includes(status)) color = "red";
  return `<span class="pill ${color}">${escapeHtml(status || "-")}</span>`;
}

function actionLabel(action) {
  const labels = {
    create_appointment: "创建预约",
    oa_approve: "OA审批同意",
    oa_reject: "OA审批驳回",
    oa_archive: "流程归档",
    get_qr: "获取二维码",
    guard_verify: "门卫核验",
    guard_checkin: "确认入厂",
    guard_checkout: "确认离厂",
    guard_rollback_checkin: "回退入厂",
    guard_rollback_checkout: "回退离厂",
    export_csv: "导出CSV",
    create_user: "创建账号",
    update_permissions: "分配菜单权限",
  };
  return labels[action] || action || "";
}

function renderLogin() {
  appShell.classList.add("hidden");
  loginScreen.classList.remove("hidden");
  loginScreen.innerHTML = `
    <video class="login-video" autoplay loop muted playsinline>
      <source src="/web/assets/login-bg.webm" type="video/webm" />
    </video>
    <div class="login-overlay">
      <form class="login-form" id="login-form">
        <h1>依视路陆逊梯卡松江工厂访客系统</h1>
        <div class="login-tabs"><span>密码登录</span></div>
        <input name="username" autocomplete="username" placeholder="请输入您的账号" />
        <input name="password" type="password" autocomplete="current-password" placeholder="请输入密码" />
        <button class="btn login-btn" type="submit">登录</button>
        <div class="login-error" id="login-error"></div>
      </form>
      <footer>© EssilorLuxottica SongJiang VMS. All Rights Reserved</footer>
    </div>
  `;
  document.querySelector("#login-form").onsubmit = async (event) => {
    event.preventDefault();
    const form = new FormData(event.target);
    try {
      const data = await api("/api/auth/login", {
        method: "POST",
        body: JSON.stringify({
          username: form.get("username").trim(),
          password: form.get("password"),
        }),
      });
      currentUser = data.user;
      localStorage.setItem("vmsUser", JSON.stringify(currentUser));
      loginScreen.classList.add("hidden");
      appShell.classList.remove("hidden");
      const first = userTabs()[0]?.id || "overview";
      activeTab = userTabs().some((tab) => tab.id === activeTab) ? activeTab : first;
      location.hash = activeTab;
      await render();
    } catch (error) {
      document.querySelector("#login-error").textContent = error.message;
    }
  };
}

function renderShell() {
  const tabs = userTabs();
  if (!tabs.some((tab) => tab.id === activeTab)) {
    activeTab = tabs[0]?.id || "overview";
    location.hash = activeTab;
  }
  nav.innerHTML = tabs.map((tab) => `<button type="button" data-tab="${tab.id}" class="${tab.id === activeTab ? "active" : ""}">${tab.title}</button>`).join("");
  nav.querySelectorAll("button").forEach((btn) => {
    btn.onclick = () => {
      activeTab = btn.dataset.tab;
      location.hash = activeTab;
      render();
    };
  });
  const found = tabs.find((tab) => tab.id === activeTab) || tabs[0];
  title.textContent = found?.title || "";
  todayPill.textContent = config ? `今日 ${config.today}` : "";
  document.querySelector("#current-user").textContent = currentUser ? `${currentUser.displayName}（${currentUser.username}）` : "";
}

async function renderOverview() {
  const all = await api(`/api/appointments?date=${encodeURIComponent(config.today)}`);
  const tasks = await api("/api/oa/tasks");
  const guards = await api(`/api/guard/today?date=${encodeURIComponent(config.today)}`);
  const visitorCount = guards.items.reduce((sum, item) => sum + item.visitors.length, 0);
  view.innerHTML = `
    <div class="grid three">
      <div class="metric"><span>今日预约</span><strong>${all.items.length}</strong></div>
      <div class="metric"><span>今日访客</span><strong>${visitorCount}</strong></div>
      <div class="metric"><span>OA 待办</span><strong>${tasks.items.length}</strong></div>
    </div>
    <div class="panel" style="margin-top:16px">
      <div class="panel-header"><h3>今日预约概览</h3></div>
      <div class="panel-body">${tableForAppointments(all.items, false)}</div>
    </div>
  `;
}

function tableForAppointments(items, withActions = false, options = {}) {
  if (!items.length) return `<div class="empty">暂无记录</div>`;
  const showVisitorCompany = Boolean(options.showVisitorCompany);
  return `
    <table>
      <thead><tr><th>申请单号</th><th>访客类型</th><th>访问日期</th><th>接洽人</th>${showVisitorCompany ? "<th>访客公司</th>" : ""}<th>访客</th><th>状态</th><th>操作</th></tr></thead>
      <tbody>
        ${items
          .map(
            (item) => `
              <tr>
                <td>${escapeHtml(item.applicationNo)}</td>
                <td>${escapeHtml(item.visitorType)}</td>
                <td>${escapeHtml(item.visitStartDate)} 至 ${escapeHtml(item.visitEndDate)}<br /><span class="muted">${escapeHtml(item.visitTimeSlot)}</span></td>
                <td>${escapeHtml(item.contactName)}<br /><span class="muted">${escapeHtml(item.contactDepartment)}</span></td>
                ${showVisitorCompany ? `<td>${item.visitors.map((v) => escapeHtml(v.company || item.applicantCompany || "-")).join("<br />")}</td>` : ""}
                <td>${item.visitors.map((v) => `${escapeHtml(v.name)}（${escapeHtml(v.qrStatus)}）`).join("<br />")}</td>
                <td>${statusPill(item.status)}</td>
                <td>${withActions ? `<button class="ghost" data-detail="${item.applicationNo}" type="button">详情</button>` : ""}</td>
              </tr>
            `,
          )
          .join("")}
      </tbody>
    </table>
  `;
}

function renderAppointmentDetail(item) {
  const visitors = item.visitors
    .map((v) => `<tr><td>${v.seq}</td><td>${escapeHtml(v.name)}</td><td>${escapeHtml(v.company)}</td><td>${escapeHtml(v.phone)}</td><td>${escapeHtml(v.idType)} ${escapeHtml(v.idNumberMasked)}</td><td>${statusPill(v.qrStatus)}</td><td>${formatDateTime(v.checkinTime) || "-"}</td><td>${formatDateTime(v.checkoutTime) || "-"}</td></tr>`)
    .join("");
  const approvals = item.approvalRecords.length
    ? item.approvalRecords.map((r) => `<tr><td>${escapeHtml(r.nodeName)}</td><td>${escapeHtml(r.approverName)}</td><td>${escapeHtml(actionLabel("oa_" + r.action) || r.action)}</td><td>${escapeHtml(r.opinion || "-")}</td><td>${formatDateTime(r.actionTime)}</td></tr>`).join("")
    : `<tr><td colspan="5" class="muted">暂无审批记录</td></tr>`;
  showModal(
    `${item.applicationNo} 详情`,
    `
      <div class="detail">
        <div>申请人</div><div>${escapeHtml(item.applicantName)}｜${escapeHtml(item.applicantCompany)}｜${escapeHtml(item.applicantPhone)}</div>
        <div>接洽人</div><div>${escapeHtml(item.contactName)}｜${escapeHtml(item.contactDepartment)}｜${escapeHtml(item.contactPhone)}</div>
        <div>访问时间</div><div>${escapeHtml(item.visitStartDate)} 至 ${escapeHtml(item.visitEndDate)}｜${escapeHtml(item.visitTimeSlot)}</div>
        <div>访问区域</div><div>${escapeHtml(item.visitAreas.join("、"))}</div>
        <div>访问目的</div><div>${escapeHtml(item.visitPurpose)}</div>
        <div>随身物品/特殊需求</div><div>${escapeHtml(item.specialRequest || "-")}</div>
        <div>车牌号</div><div>${escapeHtml(item.carPlate || "-")}</div>
      </div>
      <h4>访客信息</h4>
      <table><thead><tr><th>#</th><th>姓名</th><th>公司</th><th>手机</th><th>证件</th><th>状态</th><th>入厂时间</th><th>离厂时间</th></tr></thead><tbody>${visitors}</tbody></table>
      <h4>审批记录</h4>
      <table><thead><tr><th>节点</th><th>审批人</th><th>执行操作</th><th>意见</th><th>时间</th></tr></thead><tbody>${approvals}</tbody></table>
    `,
  );
}

function showModal(titleText, bodyHtml) {
  document.querySelector("#modal-root").innerHTML = `
    <div class="modal-mask">
      <div class="modal">
        <div class="modal-header"><h3>${escapeHtml(titleText)}</h3><button class="ghost" id="modal-close">关闭</button></div>
        <div class="modal-body">${bodyHtml}</div>
      </div>
    </div>
  `;
  document.querySelector("#modal-close").onclick = () => (document.querySelector("#modal-root").innerHTML = "");
}

async function renderOA() {
  const data = await api("/api/oa/tasks");
  view.innerHTML = `
    <div class="panel">
      <div class="panel-header"><h3>OA 待办审批</h3><span class="muted">审批动作会同步回预约系统</span></div>
      <div class="panel-body">
        ${
          data.items.length
            ? data.items
                .map(
                  (item) => `
                    <div class="sub-panel">
                      <div class="panel-header">
                        <h3>${escapeHtml(item.applicationNo)}｜${escapeHtml(item.currentNode.nodeName)}</h3>
                        ${statusPill(item.status)}
                      </div>
                      <div class="panel-body grid">
                        <div class="detail">
                          <div>申请人</div><div>${escapeHtml(item.applicantName)}｜${escapeHtml(item.applicantCompany)}｜${escapeHtml(item.applicantPhone)}</div>
                          <div>访客</div><div>${item.visitors.map((v) => `${escapeHtml(v.name)}｜${escapeHtml(v.company)}｜${escapeHtml(v.idType)} ${escapeHtml(v.idNumberMasked)}`).join("<br />")}</div>
                          <div>访问</div><div>${escapeHtml(item.visitStartDate)} 至 ${escapeHtml(item.visitEndDate)}｜${escapeHtml(item.visitAreas.join("、"))}｜${escapeHtml(item.visitPurpose)}</div>
                          <div>当前审批人</div><div>${escapeHtml(item.currentNode.approverName)}（${escapeHtml(item.currentNode.approverId)}）</div>
                        </div>
                        <textarea data-opinion="${item.applicationNo}" placeholder="审批意见；驳回时必填"></textarea>
                        <div class="actions">
                          <button class="btn" data-oa-action="approve" data-application="${item.applicationNo}" data-approver-id="${item.currentNode.approverId}" data-approver-name="${item.currentNode.approverName}">同意</button>
                          <button class="btn danger" data-oa-action="reject" data-application="${item.applicationNo}" data-approver-id="${item.currentNode.approverId}" data-approver-name="${item.currentNode.approverName}">驳回</button>
                        </div>
                      </div>
                    </div>
                  `,
                )
                .join("")
            : `<div class="empty">暂无 OA 待办</div>`
        }
      </div>
    </div>
  `;
  document.querySelectorAll("[data-oa-action]").forEach((btn) => {
    btn.onclick = async () => {
      const applicationNo = btn.dataset.application;
      const opinion = document.querySelector(`[data-opinion="${applicationNo}"]`).value.trim();
      try {
        await api(`/api/oa/tasks/${applicationNo}/action`, {
          method: "POST",
          body: JSON.stringify({
            action: btn.dataset.oaAction,
            opinion,
            approverId: btn.dataset.approverId,
            approverName: btn.dataset.approverName,
          }),
        });
        showMessage("OA 审批已处理。");
        await renderOA();
      } catch (err) {
        showMessage(err.message, "error");
      }
    };
  });
}

async function renderGuard() {
  view.innerHTML = `
    <div class="split">
      <div class="panel">
        <div class="panel-header"><h3>扫码核验</h3></div>
        <div class="panel-body grid">
          <div class="field"><label>二维码内容 / Token</label><input id="qr-token" placeholder="VMS:QR-..." /></div>
          <div class="field"><label>场景</label><select id="scan-scene"><option value="checkin">入厂</option><option value="checkout">离厂</option></select></div>
          <div class="field"><label>门岗</label><input id="gate-code" value="GATE-1" /></div>
          <div class="field"><label>保安工号</label><input id="guard-user" value="${escapeHtml(currentUser?.username || "guard01")}" /></div>
          <label class="check"><input type="checkbox" id="id-verified" checked /><span>证件核验一致</span></label>
          <div class="actions">
            <button class="btn" id="verify-btn" type="button">校验</button>
            <button class="btn warning" id="checkin-btn" type="button">确认入厂</button>
            <button class="btn danger" id="checkout-btn" type="button">确认离厂</button>
            <button class="ghost" id="rollback-checkin-btn" type="button">回退入厂</button>
            <button class="ghost" id="rollback-checkout-btn" type="button">回退离厂</button>
          </div>
          <div id="verify-result" class="muted"></div>
        </div>
      </div>
      <div class="panel">
        <div class="panel-header">
          <h3>访客预约列表</h3>
          <div class="actions">
            <input type="date" id="guard-date" value="${config.today}" />
            <input id="guard-name" placeholder="姓名" />
            <input id="guard-company" placeholder="公司" />
            <button class="ghost" id="guard-search">查询</button>
          </div>
        </div>
        <div class="panel-body" id="guard-list"></div>
      </div>
    </div>
  `;
  document.querySelector("#guard-search").onclick = loadGuardList;
  document.querySelector("#verify-btn").onclick = verifyQr;
  document.querySelector("#checkin-btn").onclick = guardCheckin;
  document.querySelector("#checkout-btn").onclick = guardCheckout;
  document.querySelector("#rollback-checkin-btn").onclick = () => guardRollback("checkin");
  document.querySelector("#rollback-checkout-btn").onclick = () => guardRollback("checkout");
  await loadGuardList();
}

async function loadGuardList() {
  const params = new URLSearchParams({
    date: document.querySelector("#guard-date")?.value || config.today,
    name: document.querySelector("#guard-name")?.value || "",
    company: document.querySelector("#guard-company")?.value || "",
  });
  const data = await api(`/api/guard/today?${params.toString()}`);
  const rows = [];
  data.items.forEach((item) => item.visitors.forEach((v) => rows.push({ item, v })));
  document.querySelector("#guard-list").innerHTML = rows.length
    ? `<table><thead><tr><th>访客申请单号</th><th>访客</th><th>访问</th><th>状态</th><th>访客申请二维码</th></tr></thead><tbody>${rows
        .map(
          ({ item, v }) => `
            <tr>
              <td><button class="link-button" data-guard-detail="${item.applicationNo}">${escapeHtml(item.applicationNo)}</button></td>
              <td>${escapeHtml(v.name)}<br /><span class="muted">${escapeHtml(v.company)}｜${escapeHtml(v.phone)}｜${escapeHtml(v.idNumberMasked)}</span></td>
              <td>${escapeHtml(item.visitStartDate)} 至 ${escapeHtml(item.visitEndDate)}<br /><span class="muted">${escapeHtml(item.contactName)}｜${escapeHtml(item.visitAreas.join("、"))}</span></td>
              <td>${statusPill(v.qrStatus)}</td>
              <td><button class="ghost" data-use-token="${escapeHtml(v.qrPayload || v.qrToken)}">填入</button><p class="qr-token">${escapeHtml(v.qrPayload || "-")}</p></td>
            </tr>
          `,
        )
        .join("")}</tbody></table>`
    : `<div class="empty">暂无可核验预约</div>`;
  document.querySelectorAll("[data-use-token]").forEach((btn) => {
    btn.onclick = () => (document.querySelector("#qr-token").value = btn.dataset.useToken);
  });
  document.querySelectorAll("[data-guard-detail]").forEach((btn) => {
    btn.onclick = async () => {
      const data = await api(`/api/appointments/${btn.dataset.guardDetail}`);
      renderAppointmentDetail(data.item);
    };
  });
}

async function verifyQr() {
  try {
    const data = await api("/api/guard/qr/verify", {
      method: "POST",
      body: JSON.stringify({
        qrToken: document.querySelector("#qr-token").value.trim(),
        guardUserId: document.querySelector("#guard-user").value.trim(),
        gateCode: document.querySelector("#gate-code").value.trim(),
        scanScene: document.querySelector("#scan-scene").value,
      }),
    });
    document.querySelector("#verify-result").innerHTML = `${data.valid ? "通过" : "不通过"}：${escapeHtml(data.message)}`;
  } catch (err) {
    showMessage(err.message, "error");
  }
}

async function guardCheckin() {
  if (document.querySelector("#scan-scene").value !== "checkin") return showMessage("当前场景是离厂，不能执行确认入厂。", "error");
  try {
    await api("/api/guard/checkin", {
      method: "POST",
      body: JSON.stringify({
        qrToken: document.querySelector("#qr-token").value.trim(),
        guardUserId: document.querySelector("#guard-user").value.trim(),
        gateCode: document.querySelector("#gate-code").value.trim(),
        scanScene: document.querySelector("#scan-scene").value,
        idVerified: document.querySelector("#id-verified").checked,
      }),
    });
    showMessage("入厂登记完成。");
    await loadGuardList();
  } catch (err) {
    showMessage(err.message, "error");
  }
}

async function guardCheckout() {
  if (document.querySelector("#scan-scene").value !== "checkout") return showMessage("当前场景是入厂，不能执行确认离厂。", "error");
  try {
    await api("/api/guard/checkout", {
      method: "POST",
      body: JSON.stringify({
        qrToken: document.querySelector("#qr-token").value.trim(),
        guardUserId: document.querySelector("#guard-user").value.trim(),
        gateCode: document.querySelector("#gate-code").value.trim(),
        scanScene: document.querySelector("#scan-scene").value,
      }),
    });
    showMessage("离厂登记完成，二维码已失效。");
    await loadGuardList();
  } catch (err) {
    showMessage(err.message, "error");
  }
}

async function guardRollback(action) {
  try {
    await api("/api/guard/rollback", {
      method: "POST",
      body: JSON.stringify({
        action,
        qrToken: document.querySelector("#qr-token").value.trim(),
        guardUserId: document.querySelector("#guard-user").value.trim(),
      }),
    });
    showMessage(action === "checkin" ? "已回退入厂操作。" : "已回退离厂操作。");
    await loadGuardList();
  } catch (err) {
    showMessage(err.message, "error");
  }
}

async function renderAdmin() {
  view.innerHTML = `
    <div class="panel">
      <div class="panel-header">
        <h3>来访记录与导出</h3>
        <div class="actions">
          <select id="admin-status"><option value="">全部状态</option>${config.statuses.map((s) => `<option>${s}</option>`).join("")}</select>
          <input type="date" id="admin-date" value="${config.today}" />
          <input id="admin-name" placeholder="接洽人姓名" />
          <input id="admin-company" placeholder="访客公司" />
          <button class="ghost" id="admin-search">筛选</button>
          <a class="btn secondary export-btn" id="export-link" href="/api/admin/export">导出 CSV</a>
        </div>
      </div>
      <div class="panel-body" id="admin-list"></div>
    </div>
    <div class="panel" style="margin-top:16px">
      <div class="panel-header">
        <h3>最近操作日志</h3>
        <div class="actions">
          <select id="log-page-size"><option>20</option><option>50</option><option>100</option><option>500</option></select>
          <button class="ghost" id="log-prev">上一页</button>
          <span class="muted" id="log-page-info"></span>
          <button class="ghost" id="log-next">下一页</button>
        </div>
      </div>
      <div class="panel-body" id="log-list"></div>
    </div>
  `;
  document.querySelector("#admin-search").onclick = loadAdmin;
  document.querySelector("#log-page-size").value = String(logPageSize);
  document.querySelector("#log-page-size").onchange = () => {
    logPageSize = Number(document.querySelector("#log-page-size").value);
    logPage = 1;
    loadLogs();
  };
  document.querySelector("#log-prev").onclick = () => {
    if (logPage > 1) {
      logPage -= 1;
      loadLogs();
    }
  };
  document.querySelector("#log-next").onclick = () => {
    logPage += 1;
    loadLogs();
  };
  await loadAdmin();
}

function adminParams() {
  return new URLSearchParams({
    status: document.querySelector("#admin-status")?.value || "",
    date: document.querySelector("#admin-date")?.value || "",
    contactName: document.querySelector("#admin-name")?.value || "",
    visitorCompany: document.querySelector("#admin-company")?.value || "",
  });
}

async function loadAdmin() {
  const params = adminParams();
  document.querySelector("#export-link").href = `/api/admin/export?${params.toString()}&user=${encodeURIComponent(currentUser?.username || "")}`;
  const data = await api(`/api/appointments?${params.toString()}`);
  document.querySelector("#admin-list").innerHTML = tableForAppointments(data.items, false, { showVisitorCompany: true });
  await loadLogs();
}

async function loadLogs() {
  const logs = await api(`/api/admin/logs?page=${logPage}&pageSize=${logPageSize}`);
  const totalPages = Math.max(Math.ceil(logs.total / logs.pageSize), 1);
  if (logPage > totalPages) {
    logPage = totalPages;
    return loadLogs();
  }
  document.querySelector("#log-page-info").textContent = `${logs.page} / ${totalPages}，共 ${logs.total} 条`;
  document.querySelector("#log-list").innerHTML = logs.items.length
    ? `<table><thead><tr><th>时间</th><th>执行操作</th><th>单号</th><th>用户</th></tr></thead><tbody>${logs.items
        .map((l) => `<tr><td>${escapeHtml(l.time)}</td><td>${escapeHtml(l.actionLabel || actionLabel(l.action))}</td><td>${escapeHtml(l.applicationNo || "-")}</td><td>${escapeHtml(l.user || "-")}</td></tr>`)
        .join("")}</tbody></table>`
    : `<div class="empty">暂无日志</div>`;
}

async function renderUsers() {
  const data = await api("/api/users");
  view.innerHTML = `
    <div class="grid two">
      <form class="panel" id="user-form">
        <div class="panel-header"><h3>创建账号</h3></div>
        <div class="panel-body grid">
          <div class="field"><label>账号</label><input name="username" placeholder="例如 guard02" /></div>
          <div class="field"><label>显示名称</label><input name="displayName" placeholder="例如 保安2号" /></div>
          <div class="field"><label>角色</label><select name="role"><option value="guard">保安</option><option value="admin">管理员</option></select></div>
          <div class="field"><label>默认密码</label><input name="password" value="admin" /></div>
          <button class="btn" type="submit">创建账号</button>
        </div>
      </form>
      <div class="panel">
        <div class="panel-header"><h3>账号列表</h3></div>
        <div class="panel-body">${userTable(data.items)}</div>
      </div>
    </div>
  `;
  document.querySelector("#user-form").onsubmit = async (event) => {
    event.preventDefault();
    const form = new FormData(event.target);
    try {
      await api("/api/users", {
        method: "POST",
        body: JSON.stringify({
          username: form.get("username").trim(),
          displayName: form.get("displayName").trim(),
          role: form.get("role"),
          password: form.get("password") || "admin",
          permissions: form.get("role") === "admin" ? baseTabs.map((tab) => tab.id) : ["overview", "oa", "guard", "admin"],
          operator: currentUser?.username || "",
        }),
      });
      showMessage("账号已创建。");
      await renderUsers();
    } catch (err) {
      showMessage(err.message, "error");
    }
  };
}

function userTable(items) {
  if (!items.length) return `<div class="empty">暂无账号</div>`;
  return `<table><thead><tr><th>账号</th><th>名称</th><th>角色</th><th>权限</th></tr></thead><tbody>${items
    .map((u) => `<tr><td>${escapeHtml(u.username)}</td><td>${escapeHtml(u.displayName)}</td><td>${escapeHtml(u.role)}</td><td>${escapeHtml((u.permissions || []).join("、"))}</td></tr>`)
    .join("")}</tbody></table>`;
}

async function renderPermissions() {
  const data = await api("/api/users");
  view.innerHTML = `
    <div class="panel">
      <div class="panel-header"><h3>菜单分配权限</h3></div>
      <div class="panel-body">
        <table>
          <thead><tr><th>账号</th><th>名称</th><th>菜单权限</th><th>操作</th></tr></thead>
          <tbody>
            ${data.items
              .map(
                (user) => `
                  <tr>
                    <td>${escapeHtml(user.username)}</td>
                    <td>${escapeHtml(user.displayName)}</td>
                    <td>
                      <div class="permission-grid" data-permissions="${user.username}">
                        ${baseTabs
                          .map((tab) => `<label class="check inline"><input type="checkbox" value="${tab.id}" ${user.permissions?.includes(tab.id) ? "checked" : ""} ${tab.adminOnly && user.role !== "admin" ? "disabled" : ""} /><span>${tab.title}</span></label>`)
                          .join("")}
                      </div>
                    </td>
                    <td><button class="btn" data-save-permissions="${user.username}">保存</button></td>
                  </tr>
                `,
              )
              .join("")}
          </tbody>
        </table>
      </div>
    </div>
  `;
  document.querySelectorAll("[data-save-permissions]").forEach((btn) => {
    btn.onclick = async () => {
      const username = btn.dataset.savePermissions;
      const permissions = [...document.querySelectorAll(`[data-permissions="${username}"] input:checked`)].map((input) => input.value);
      try {
        await api(`/api/users/${encodeURIComponent(username)}/permissions`, {
          method: "POST",
          body: JSON.stringify({ permissions, operator: currentUser?.username || "" }),
        });
        showMessage("权限已保存。");
        if (username === currentUser.username) {
          currentUser.permissions = permissions;
          localStorage.setItem("vmsUser", JSON.stringify(currentUser));
          renderShell();
        }
      } catch (err) {
        showMessage(err.message, "error");
      }
    };
  });
}

async function render() {
  if (!currentUser) {
    renderLogin();
    return;
  }
  loginScreen.classList.add("hidden");
  appShell.classList.remove("hidden");
  showMessage("");
  if (!config) config = await api("/api/config");
  renderShell();
  if (activeTab === "overview") await renderOverview();
  if (activeTab === "oa") await renderOA();
  if (activeTab === "guard") await renderGuard();
  if (activeTab === "admin") await renderAdmin();
  if (activeTab === "users") await renderUsers();
  if (activeTab === "permissions") await renderPermissions();
}

window.addEventListener("hashchange", () => {
  activeTab = location.hash.replace("#", "") || "overview";
  render();
});

refreshBtn.addEventListener("click", render);
document.querySelector("#logout-btn").addEventListener("click", () => {
  localStorage.removeItem("vmsUser");
  currentUser = null;
  renderLogin();
});

render().catch((err) => showMessage(err.message, "error"));
