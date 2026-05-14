(() => {
  "use strict";

  const root = document.getElementById("miniPanelApp");
  const params = new URLSearchParams(window.location.search);
  const companyId = params.get("company_id") || params.get("companyId") || "";
  const panelType = (params.get("type") || params.get("panel_type") || "sales").toLowerCase();
  const isLogin = window.location.pathname.includes("/login");
  const storageKey = `clonexa_mini_panel_token_${companyId}_${panelType}`;

  let timerHandle = null;
  let currentOperational = null;
  let currentModuleConfig = null;

  const TYPE_LABELS = {
    sales: "Ventas",
    store: "Tiendas",
    stores: "Tiendas",
    inventory: "Inventarios",
    logistics: "Logística",
    other: "Otros"
  };

  function h(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function labelType(value) {
    return TYPE_LABELS[value] || value || "Mini Panel";
  }

  function token() {
    return localStorage.getItem(storageKey) || "";
  }

  function authHeaders() {
    const value = token();
    return value ? { Authorization: `Bearer ${value}` } : {};
  }

  async function api(path, options = {}) {
    const response = await fetch(path, options);
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(data.detail || data.message || "Solicitud rechazada.");
    }
    return data;
  }

  function loginUrl() {
    return `/mini-panel/login?company_id=${encodeURIComponent(companyId)}&type=${encodeURIComponent(panelType)}`;
  }

  function shellUrl() {
    return `/mini-panel?company_id=${encodeURIComponent(companyId)}&type=${encodeURIComponent(panelType)}`;
  }

  function formatSeconds(total) {
    const safe = Math.max(0, Math.floor(Number(total || 0)));
    const h = String(Math.floor(safe / 3600)).padStart(2, "0");
    const m = String(Math.floor((safe % 3600) / 60)).padStart(2, "0");
    const s = String(safe % 60).padStart(2, "0");
    return `${h}:${m}:${s}`;
  }

  function formatMoney(value) {
    const number = Number(value || 0);
    try {
      return new Intl.NumberFormat("es-CO", {
        style: "currency",
        currency: "COP",
        maximumFractionDigits: 0
      }).format(number);
    } catch (_) {
      return `$${Math.round(number).toLocaleString("es-CO")}`;
    }
  }


  /* CLONEXA_020A_NOTES_CALENDAR_START */
/* CLONEXA_020C_NOTES_AGENDA_FULL_VISUAL_REBUILD: UI/UX reconstruida sin tocar backend */
  const NOTES_CODES_020A = new Set([
    "notes",
    "notas",
    "nota",
    "agenda",
    "notas_o_agenda",
    "recordatorio",
    "recordatorios",
    "reminder",
    "reminders",
    "calendar",
    "calendario"
  ]);

  let currentNotesSummary020A = null;

  function isNotesCode020A(code) {
    const normalized = normalizeModuleCode019H(code);
    return NOTES_CODES_020A.has(normalized);
  }

  function notesModuleEnabled020A(moduleConfig) {
    const config = moduleConfig || currentModuleConfig || {};
    const modules = Array.isArray(config.modules) ? config.modules : [];
    return modules.some((code) => isNotesCode020A(code));
  }

  function pad020A(value) {
    return String(value).padStart(2, "0");
  }

  function localDateIso020A(date = new Date()) {
    return `${date.getFullYear()}-${pad020A(date.getMonth() + 1)}-${pad020A(date.getDate())}`;
  }

  function parseIsoDate020A(iso) {
    const parts = String(iso || localDateIso020A()).split("-").map((part) => Number(part));
    const year = parts[0] || new Date().getFullYear();
    const month = Math.max(1, Math.min(12, parts[1] || 1));
    const day = Math.max(1, Math.min(31, parts[2] || 1));
    return new Date(year, month - 1, day);
  }

  function formatDateLabel020A(iso) {
    const date = parseIsoDate020A(iso);
    return `${pad020A(date.getDate())}/${pad020A(date.getMonth() + 1)}/${date.getFullYear()}`;
  }

  function formatLongDate020A(iso) {
    try {
      return new Intl.DateTimeFormat("es-CO", {
        weekday: "long",
        day: "2-digit",
        month: "long",
        year: "numeric"
      }).format(parseIsoDate020A(iso));
    } catch (_) {
      return formatDateLabel020A(iso);
    }
  }

  function formatMonthTitle020C(date) {
    try {
      return new Intl.DateTimeFormat("es-CO", { month: "long", year: "numeric" }).format(date);
    } catch (_) {
      return `${pad020A(date.getMonth() + 1)}/${date.getFullYear()}`;
    }
  }

  function noteDateIso020C(note) {
    const raw = note?.note_date || note?.date || note?.scheduled_date || note?.scheduled_at || "";
    return String(raw || "").slice(0, 10);
  }

  function noteStatusLabel020C(status) {
    const value = String(status || "active").toLowerCase();
    if (value === "done" || value === "completed") return "Completado";
    if (value === "archived") return "Archivado";
    return "Pendiente";
  }

  function noteTypeLabel020C(type) {
    const value = String(type || "reminder").toLowerCase();
    if (value === "note" || value === "nota") return "Nota";
    if (value === "event" || value === "evento") return "Evento";
    return "Recordatorio";
  }

  function formatNoteTime020A(note) {
    const raw = note?.display_time || note?.note_time || note?.time || "";
    return String(raw || "").slice(0, 5);
  }

  function defaultNoteTime020A() {
    const now = new Date();
    now.setMinutes(now.getMinutes() < 30 ? 30 : 60, 0, 0);
    return `${pad020A(now.getHours())}:${pad020A(now.getMinutes())}`;
  }

  function defaultNotesSummary020A() {
    const today = localDateIso020A();
    return {
      date: today,
      count: 0,
      label: `${formatDateLabel020A(today)} · 0 recordatorios`,
      next_label: "Sin próximos recordatorios",
      next: null,
      upcoming: []
    };
  }

  async function notesApi020A(path, options = {}) {
    if (!companyId) throw new Error("Falta company_id.");
    const headers = {
      ...authHeaders(),
      ...(options.headers || {})
    };
    return api(`/api/v1/mini-panel-notes/companies/${encodeURIComponent(companyId)}${path}`, {
      ...options,
      headers
    });
  }

  async function loadNotesSummary020A(moduleConfig = null) {
    if (!notesModuleEnabled020A(moduleConfig)) {
      return defaultNotesSummary020A();
    }
    const today = localDateIso020A();
    return notesApi020A(`/summary?panel_type=${encodeURIComponent(panelType)}&date=${encodeURIComponent(today)}`);
  }

  async function loadNotesDay020A(dateIso) {
    const date = dateIso || localDateIso020A();
    return notesApi020A(`?panel_type=${encodeURIComponent(panelType)}&date=${encodeURIComponent(date)}`);
  }

  async function createNote020A(payload) {
    return notesApi020A(`?panel_type=${encodeURIComponent(panelType)}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
  }

  async function completeNote020A(noteId) {
    return notesApi020A(`/${encodeURIComponent(noteId)}/complete?panel_type=${encodeURIComponent(panelType)}`, {
      method: "POST"
    });
  }

  async function archiveNote020A(noteId) {
    return notesApi020A(`/${encodeURIComponent(noteId)}?panel_type=${encodeURIComponent(panelType)}`, {
      method: "DELETE"
    });
  }

  function updateNotesCard020A(summary) {
    const safe = summary || defaultNotesSummary020A();
    const count = document.querySelector("[data-notes-card-count]");
    const next = document.querySelector("[data-notes-card-next]");
    if (count) count.textContent = safe.label || `${formatDateLabel020A(localDateIso020A())} · 0 recordatorios`;
    if (next) next.textContent = safe.next_label || "Sin próximos recordatorios";
  }

  function renderNotesList020A(items, emptyText = "No hay notas para mostrar.", mode = "compact") {
    const rows = Array.isArray(items) ? items : [];
    if (!rows.length) {
      return `<div class="mp-notes-empty-020a">${h(emptyText)}</div>`;
    }

    return rows.map((item) => {
      const status = String(item.status || "active").toLowerCase();
      const dateIso = noteDateIso020C(item);
      const showDate = mode === "upcoming" && dateIso;
      const timeLabel = formatNoteTime020A(item) || "--:--";
      const typeLabel = noteTypeLabel020C(item.note_type || item.type);
      return `
        <article class="mp-note-item-020a ${h(status)}" data-note-row="${h(item.id || "")}">
          <div class="mp-note-time-020c">
            <strong>${h(timeLabel)}</strong>
            ${showDate ? `<small>${h(formatDateLabel020A(dateIso))}</small>` : `<small>${h(typeLabel)}</small>`}
          </div>
          <div class="mp-note-body-020c">
            <div class="mp-note-title-line-020c">
              <strong>${h(item.title || "Nota")}</strong>
              <em>${h(noteStatusLabel020C(status))}</em>
            </div>
            <small>${h(item.description || "Sin detalle")}</small>
          </div>
          <div class="mp-note-actions-020a">
            ${status === "done" ? "" : `<button class="mp-button small secondary" type="button" data-note-complete="${h(item.id)}">Completar</button>`}
            <button class="mp-button small ghost" type="button" data-note-archive="${h(item.id)}">Archivar</button>
          </div>
        </article>
      `;
    }).join("");
  }

  function renderCalendarGrid020A(selectedDate, viewMonthIso, eventDateSet = new Set()) {
    const view = parseIsoDate020A(viewMonthIso || selectedDate);
    const year = view.getFullYear();
    const month = view.getMonth();
    const first = new Date(year, month, 1);
    const startOffset = (first.getDay() + 6) % 7;
    const cursor = new Date(year, month, 1 - startOffset);
    const todayIso = localDateIso020A();

    const weekdays = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"].map((day) => `<span>${day}</span>`).join("");
    let days = "";

    for (let index = 0; index < 42; index += 1) {
      const date = new Date(cursor.getFullYear(), cursor.getMonth(), cursor.getDate() + index);
      const iso = localDateIso020A(date);
      const hasEvent = eventDateSet.has(iso);
      const classes = [
        "mp-calendar-day-020a",
        date.getMonth() === month ? "" : "outside",
        iso === selectedDate ? "selected" : "",
        iso === todayIso ? "today" : "",
        hasEvent ? "has-event" : ""
      ].filter(Boolean).join(" ");

      days += `
        <button class="${classes}" type="button" data-note-date="${h(iso)}" aria-label="${h(formatDateLabel020A(iso))}">
          <span>${date.getDate()}</span>
          ${hasEvent ? `<i></i>` : ""}
        </button>
      `;
    }

    return `
      <div class="mp-calendar-head-020a">
        <button class="mp-button small secondary" type="button" data-notes-month="-1" aria-label="Mes anterior">‹</button>
        <strong>${h(formatMonthTitle020C(view))}</strong>
        <button class="mp-button small secondary" type="button" data-notes-month="1" aria-label="Mes siguiente">›</button>
      </div>
      <div class="mp-calendar-weekdays-020a">${weekdays}</div>
      <div class="mp-calendar-grid-020a">${days}</div>
    `;
  }

  async function openNotesCalendar020A(session) {
    if (!notesModuleEnabled020A(currentModuleConfig)) {
      const msg = root.querySelector("[data-panel-message]");
      if (msg) {
        msg.classList.remove("ok");
        msg.textContent = "Notas no está asignado a este mini panel.";
      }
      return;
    }

    let selectedDate = localDateIso020A();
    let viewMonthIso = `${selectedDate.slice(0, 7)}-01`;

    const overlay = document.createElement("div");
    overlay.className = "mp-modal mp-notes-modal-020a";
    overlay.innerHTML = `
      <div class="mp-modal-backdrop" data-notes-close></div>
      <section class="mp-modal-card mp-notes-card-020a" role="dialog" aria-modal="true" aria-label="Notas y agenda">
        <header class="mp-notes-top-020a">
          <div class="mp-notes-title-zone-020c">
            <div class="mp-kicker">Notas / Recordatorios</div>
            <h2>Calendario operativo</h2>
            <p>${h(session?.company?.name || "Empresa")} · ${h(labelType(panelType))}</p>
          </div>
          <button class="mp-button small secondary mp-notes-close-020c" type="button" data-notes-close>Cerrar</button>
        </header>
        <div class="mp-notes-content-020a" data-notes-content>
          <div class="mp-notes-empty-020a">Cargando calendario...</div>
        </div>
      </section>
    `;
    document.body.appendChild(overlay);

    const content = overlay.querySelector("[data-notes-content]");

    async function refresh() {
      if (!content) return;
      content.innerHTML = `
        <div class="mp-notes-loading-020c">
          <div></div>
          <strong>Cargando agenda...</strong>
          <small>Sincronizando recordatorios del mini panel.</small>
        </div>
      `;

      try {
        const data = await loadNotesDay020A(selectedDate);
        const dayItems = Array.isArray(data.items) ? data.items : [];
        const upcoming = Array.isArray(data.upcoming) ? data.upcoming : [];
        const eventDateSet = new Set(
          [...dayItems, ...upcoming]
            .map((item) => noteDateIso020C(item))
            .filter(Boolean)
        );

        const nextItem = upcoming[0] || null;
        const todayIso = localDateIso020A();
        const todayLabel = formatDateLabel020A(todayIso);

        content.innerHTML = `
          <div class="mp-notes-hero-020c">
            <div>
              <span>Agenda activa</span>
              <strong>${h(formatLongDate020A(selectedDate))}</strong>
              <small>Gestiona notas, llamadas, seguimientos y recordatorios del panel de ventas.</small>
            </div>
            <div class="mp-notes-hero-stats-020c">
              <article>
                <span>Día seleccionado</span>
                <strong>${dayItems.length}</strong>
                <small>recordatorios</small>
              </article>
              <article>
                <span>Próximos</span>
                <strong>${upcoming.length}</strong>
                <small>eventos</small>
              </article>
              <article>
                <span>Hoy</span>
                <strong>${h(todayLabel)}</strong>
                <small>operación</small>
              </article>
            </div>
          </div>

          <div class="mp-notes-board-020c">
            <aside class="mp-notes-panel-020a mp-notes-calendar-020a">
              <div class="mp-notes-panel-head-020c">
                <span>Calendario</span>
                <strong>Selecciona un día</strong>
              </div>
              ${renderCalendarGrid020A(selectedDate, viewMonthIso, eventDateSet)}
            </aside>

            <section class="mp-notes-panel-020a mp-notes-create-020c">
              <div class="mp-notes-panel-head-020c">
                <span>Nuevo recordatorio</span>
                <strong>${h(formatLongDate020A(selectedDate))}</strong>
              </div>

              <form class="mp-notes-form-020a" data-notes-form>
                <div class="mp-notes-form-grid-020a">
                  <div class="mp-field">
                    <label>Día</label>
                    <input type="date" name="note_date" value="${h(selectedDate)}" data-note-date-input required />
                  </div>
                  <div class="mp-field">
                    <label>Hora</label>
                    <input type="time" name="note_time" value="${h(defaultNoteTime020A())}" required />
                  </div>
                  <div class="mp-field">
                    <label>Tipo</label>
                    <select name="note_type">
                      <option value="reminder">Recordatorio</option>
                      <option value="note">Nota</option>
                    </select>
                  </div>
                </div>

                <div class="mp-field">
                  <label>Título</label>
                  <input name="title" maxlength="180" placeholder="Ej: llamar cliente, confirmar pedido..." required />
                </div>

                <div class="mp-field">
                  <label>Detalle</label>
                  <textarea name="description" rows="4" placeholder="Detalle interno opcional"></textarea>
                </div>

                <button class="mp-button mp-notes-save-020c" type="submit">Guardar nota</button>
                <div class="mp-message ok" data-notes-message></div>
              </form>
            </section>

            <aside class="mp-notes-panel-020a mp-notes-upcoming-020c">
              <div class="mp-notes-panel-head-020c">
                <span>Próximos 5</span>
                <strong>Eventos y notas</strong>
              </div>
              ${nextItem ? `
                <div class="mp-notes-next-020c">
                  <span>Siguiente</span>
                  <strong>${h(formatNoteTime020A(nextItem) || "--:--")} · ${h(nextItem.title || "Nota")}</strong>
                  <small>${h(nextItem.description || "Sin detalle")}</small>
                </div>
              ` : ""}
              <div class="mp-notes-list-020a">
                ${renderNotesList020A(upcoming, "No hay próximos recordatorios.", "upcoming")}
              </div>
            </aside>

            <section class="mp-notes-panel-020a mp-notes-day-020c">
              <div class="mp-notes-panel-head-020c">
                <span>Día seleccionado</span>
                <strong>${h(formatDateLabel020A(selectedDate))} · ${dayItems.length} recordatorios</strong>
              </div>
              <div class="mp-notes-list-020a">
                ${renderNotesList020A(dayItems, "No hay recordatorios en este día.", "day")}
              </div>
            </section>
          </div>
        `;
      } catch (error) {
        content.innerHTML = `<div class="mp-notes-empty-020a error">${h(error.message || "No fue posible cargar Notas.")}</div>`;
      }
    }

    overlay.addEventListener("click", async (event) => {
      const target = event.target;

      if (target.closest("[data-notes-close]")) {
        overlay.remove();
        return;
      }

      const monthButton = target.closest("[data-notes-month]");
      if (monthButton) {
        const direction = Number(monthButton.getAttribute("data-notes-month") || 0);
        const view = parseIsoDate020A(viewMonthIso);
        view.setMonth(view.getMonth() + direction);
        viewMonthIso = `${view.getFullYear()}-${pad020A(view.getMonth() + 1)}-01`;
        await refresh();
        return;
      }

      const dateButton = target.closest("[data-note-date]");
      if (dateButton) {
        selectedDate = dateButton.getAttribute("data-note-date") || selectedDate;
        viewMonthIso = `${selectedDate.slice(0, 7)}-01`;
        await refresh();
        return;
      }

      const completeButton = target.closest("[data-note-complete]");
      if (completeButton) {
        await completeNote020A(completeButton.getAttribute("data-note-complete"));
        currentNotesSummary020A = await loadNotesSummary020A(currentModuleConfig).catch(() => defaultNotesSummary020A());
        updateNotesCard020A(currentNotesSummary020A);
        await refresh();
        return;
      }

      const archiveButton = target.closest("[data-note-archive]");
      if (archiveButton) {
        await archiveNote020A(archiveButton.getAttribute("data-note-archive"));
        currentNotesSummary020A = await loadNotesSummary020A(currentModuleConfig).catch(() => defaultNotesSummary020A());
        updateNotesCard020A(currentNotesSummary020A);
        await refresh();
      }
    });

    overlay.addEventListener("change", async (event) => {
      const input = event.target.closest("[data-note-date-input]");
      if (!input) return;
      selectedDate = input.value || selectedDate;
      viewMonthIso = `${selectedDate.slice(0, 7)}-01`;
      await refresh();
    });

    overlay.addEventListener("submit", async (event) => {
      const form = event.target.closest("[data-notes-form]");
      if (!form) return;

      event.preventDefault();
      const formData = new FormData(form);
      const msg = form.querySelector("[data-notes-message]");

      if (msg) {
        msg.classList.add("ok");
        msg.textContent = "Guardando nota...";
      }

      try {
        await createNote020A({
          title: String(formData.get("title") || "").trim(),
          description: String(formData.get("description") || "").trim(),
          note_date: String(formData.get("note_date") || selectedDate),
          note_time: String(formData.get("note_time") || defaultNoteTime020A()),
          note_type: String(formData.get("note_type") || "reminder")
        });

        selectedDate = String(formData.get("note_date") || selectedDate);
        viewMonthIso = `${selectedDate.slice(0, 7)}-01`;
        currentNotesSummary020A = await loadNotesSummary020A(currentModuleConfig).catch(() => defaultNotesSummary020A());
        updateNotesCard020A(currentNotesSummary020A);
        await refresh();
      } catch (error) {
        if (msg) {
          msg.classList.remove("ok");
          msg.textContent = error.message || "No fue posible guardar la nota.";
        }
      }
    });

    await refresh();
  }
/* CLONEXA_020A_NOTES_CALENDAR_END */


  function clearTimer() {
    if (timerHandle) {
      window.clearInterval(timerHandle);
      timerHandle = null;
    }
  }

  function setShellMode(enabled) {
    document.body.classList.toggle("mp-shell-body", Boolean(enabled));
  }

  function renderError(message) {
    clearTimer();
    setShellMode(false);
    root.innerHTML = `
      <section class="mp-card">
        <div class="mp-kicker">CLONEXA</div>
        <h1>Mini Panel</h1>
        <p>${h(message || "No fue posible cargar el mini panel.")}</p>
        <button class="mp-button secondary" type="button" data-retry>Reintentar</button>
      </section>
    `;
    root.querySelector("[data-retry]")?.addEventListener("click", () => window.location.reload());
  }

  function renderLogin(message = "") {
    clearTimer();
    setShellMode(false);
    root.innerHTML = `
      <section class="mp-card">
        <div class="mp-kicker">Acceso operativo</div>
        <h1>${h(labelType(panelType))}</h1>
        <p>Ingresa con el usuario y clave generados desde el panel de la empresa.</p>

        <form class="mp-form" id="miniPanelLoginForm">
          <div class="mp-field">
            <label>Usuario</label>
            <input id="miniPanelUsername" autocomplete="username" placeholder="usuario.ventas" required />
          </div>

          <div class="mp-field">
            <label>Clave</label>
            <input id="miniPanelPassword" type="password" autocomplete="current-password" required />
          </div>

          <button class="mp-button" type="submit">Entrar</button>
          <div class="mp-message" id="miniPanelMessage">${h(message)}</div>
        </form>
      </section>
    `;

    const form = document.getElementById("miniPanelLoginForm");
    const msg = document.getElementById("miniPanelMessage");

    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      msg.textContent = "Validando acceso...";
      msg.classList.add("ok");

      try {
        if (!companyId) throw new Error("Falta company_id en el enlace.");
        const username = document.getElementById("miniPanelUsername").value.trim();
        const password = document.getElementById("miniPanelPassword").value;

        const data = await api(`/api/v1/companies/${encodeURIComponent(companyId)}/mini-panel-login`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ username, password, panel_type: panelType })
        });

        localStorage.setItem(storageKey, data.access_token);
        localStorage.setItem("clonexa_mini_panel_last_session", JSON.stringify({
          company_id: companyId,
          type: panelType,
          at: new Date().toISOString()
        }));

        window.location.href = shellUrl();
      } catch (error) {
        msg.classList.remove("ok");
        msg.textContent = error.message || "No fue posible iniciar sesión.";
      }
    });
  }

  function liveValue(kind) {
    if (!currentOperational) return 0;
    const base = Number(currentOperational[`${kind}_seconds`] || 0);
    const syncedAt = Number(currentOperational._synced_at || Date.now());
    const elapsed = Math.max(0, Math.floor((Date.now() - syncedAt) / 1000));

    if (kind === "active" && currentOperational.status === "active") {
      return base + elapsed;
    }
    if (kind === "break" && currentOperational.status === "break") {
      return base + elapsed;
    }
    return base;
  }

  function updateTimers() {
    const activeEl = document.querySelector("[data-active-timer]");
    const breakEl = document.querySelector("[data-break-timer]");
    const paidEl = document.querySelector("[data-paid-timer]");
    const statusEl = document.querySelector("[data-operational-status]");

    if (activeEl) activeEl.textContent = formatSeconds(liveValue("active"));
    if (breakEl) breakEl.textContent = formatSeconds(liveValue("break"));
    if (paidEl) paidEl.textContent = formatSeconds(liveValue("active"));
    if (statusEl && currentOperational) {
      statusEl.textContent = operationalLabel(currentOperational.status);
      statusEl.className = `mp-status-pill ${currentOperational.status || "active"}`;
    }
  }

  function startTimers(operational) {
    clearTimer();
    currentOperational = {
      ...(operational || {}),
      _synced_at: Date.now()
    };
    updateTimers();
    timerHandle = window.setInterval(updateTimers, 1000);
  }

  function operationalLabel(status) {
    if (status === "break") return "En pausa";
    if (status === "finished") return "Finalizado";
    return "Activo";
  }

  async function loadOperationalSession() {
    return api(`/api/v1/companies/${encodeURIComponent(companyId)}/mini-panel-operational-session?panel_type=${encodeURIComponent(panelType)}`, {
      headers: authHeaders()
    });
  }

  async function operationalAction(action) {
    return api(`/api/v1/companies/${encodeURIComponent(companyId)}/mini-panel-operational-session/${action}?panel_type=${encodeURIComponent(panelType)}`, {
      method: "POST",
      headers: authHeaders()
    });
  }


  // CLONEXA_019F_R1_PASSWORD_HELPERS_START
  async function changePasswordRequest(currentPassword, newPassword, confirmPassword) {
    return api(`/api/v1/companies/${encodeURIComponent(companyId)}/mini-panel-change-password?panel_type=${encodeURIComponent(panelType)}`, {
      method: "POST",
      headers: {
        ...authHeaders(),
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        current_password: currentPassword,
        new_password: newPassword,
        confirm_password: confirmPassword
      })
    });
  }
  // CLONEXA_019F_R1_PASSWORD_HELPERS_END


  /* CLONEXA_019H_R1_SAFE_DYNAMIC_MODULES_START */
  const PANEL_TYPE_ALIASES_019H = {
    "sales": "sales",
    "venta": "sales",
    "ventas": "sales",
    "store": "store",
    "stores": "store",
    "tienda": "store",
    "tiendas": "store",
    "inventory": "inventory",
    "inventario": "inventory",
    "logistics": "logistics",
    "logistica": "logistics",
    "field": "logistics",
    "other": "other"
  };

  const MODULE_DEFS_019H = {
    "cotizacion": { title: "Cotizaciones", description: "Crear cotizaciones para clientes.", tag: "COT" },
    "cotizaciones": { title: "Cotizaciones", description: "Crear cotizaciones para clientes.", tag: "COT" },
    "quote": { title: "Cotizaciones", description: "Crear cotizaciones para clientes.", tag: "COT" },
    "quotes": { title: "Cotizaciones", description: "Crear cotizaciones para clientes.", tag: "COT" },

    "notas_o_agenda": { title: "Notas", description: "Registrar notas de seguimiento.", tag: "NOT" },
    "notes": { title: "Notas", description: "Registrar notas de seguimiento.", tag: "NOT" },
    "notas": { title: "Notas", description: "Registrar notas de seguimiento.", tag: "NOT" },

    "registro_venta": { title: "Registro ventas", description: "Reportar ventas cerradas.", tag: "VEN" },
    "registro_ventas": { title: "Registro ventas", description: "Reportar ventas cerradas.", tag: "VEN" },
    "sales_register": { title: "Registro ventas", description: "Reportar ventas cerradas.", tag: "VEN" },
    "sales": { title: "Registro ventas", description: "Reportar ventas cerradas.", tag: "VEN" },

    "day_closing": { title: "Realizar cierre", description: "Enviar cierre diario del vendedor.", tag: "CIE" },
    "cierre_dia": { title: "Realizar cierre", description: "Enviar cierre diario del vendedor.", tag: "CIE" },
    "cierre_de_dia": { title: "Realizar cierre", description: "Enviar cierre diario del vendedor.", tag: "CIE" },
    "commercial_closing": { title: "Realizar cierre", description: "Enviar cierre diario del vendedor.", tag: "CIE" },

    "kpis": { title: "KPIs", description: "Consultar indicadores asignados.", tag: "KPI" },
    "requests": { title: "Solicitudes", description: "Crear y consultar solicitudes operativas.", tag: "REQ" },
    "stores": { title: "Tiendas", description: "Operación asignada a tiendas.", tag: "STR" },
    "inventory": { title: "Inventario", description: "Consultar y registrar movimientos de inventario.", tag: "INV" },
    "materials": { title: "Materiales", description: "Gestionar materiales asignados.", tag: "MAT" },
    "reports": { title: "Reportes", description: "Consultar reportes operativos asignados.", tag: "REP" },
    "workforce": { title: "Personal", description: "Consultar personal operativo asignado.", tag: "WRK" },
    "gps": { title: "GPS", description: "Consultar ubicación y control operativo.", tag: "GPS" },
    "crm": { title: "CRM Campo", description: "Consultar operación en campo.", tag: "CRM" },
    "field": { title: "Operación en campo", description: "Consultar actividades en campo.", tag: "FLD" },
    "bots": { title: "Bots", description: "Consultar canales automatizados.", tag: "BOT" }
  };

  function normalizePanelType019H(value) {
    const raw = String(value || "")
      .toLowerCase()
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .replace(/[^a-z0-9]+/g, "_")
      .replace(/^_+|_+$/g, "");
    return PANEL_TYPE_ALIASES_019H[raw] || raw || "sales";
  }

  function normalizeModuleCode019H(value) {
    return String(value || "")
      .toLowerCase()
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .replace(/[^a-z0-9]+/g, "_")
      .replace(/^_+|_+$/g, "");
  }

  function titleFromCode019H(code, moduleNames = {}) {
    const normalized = normalizeModuleCode019H(code);
    const rawName = moduleNames[code] || moduleNames[normalized] || "";
    const clean = String(rawName || normalized || "Módulo").replace(/_/g, " ").trim();
    return clean.replace(/\w\S*/g, (part) => part.charAt(0).toUpperCase() + part.slice(1).toLowerCase());
  }

  function moduleDefinition019H(code, moduleNames = {}) {
    const normalized = normalizeModuleCode019H(code);
    const def = MODULE_DEFS_019H[normalized];
    if (def) return { ...def, code: normalized };

    const title = titleFromCode019H(normalized, moduleNames);
    return {
      code: normalized,
      title,
      description: "Módulo asignado desde Admin V2.",
      tag: normalized.slice(0, 3).toUpperCase() || "MOD"
    };
  }

  function extractMiniPanelSettings019H(companyModules) {
    const rows = Array.isArray(companyModules) ? companyModules : [];
    const miniRow = rows.find((row) => {
      const code = normalizeModuleCode019H(row?.module?.code || row?.code || row?.module_code || "");
      const name = normalizeModuleCode019H(row?.module?.name || row?.name || "");
      return code === "mini_panel" || name.includes("mini_panel") || name.includes("creacion_mini");
    });

    const settings = miniRow && typeof miniRow.settings === "object" && miniRow.settings ? miniRow.settings : {};

    if (settings.mini_panel_modules && typeof settings.mini_panel_modules === "object") {
      return settings.mini_panel_modules;
    }

    if (settings.panels && typeof settings.panels === "object") {
      return settings;
    }

    return { enabled: false, panels: {}, module_names: {} };
  }

  function panelConfig019H(config, typeValue) {
    const type = normalizePanelType019H(typeValue);
    const panels = config && typeof config.panels === "object" && config.panels ? config.panels : {};
    return panels[type] || panels[`${type}s`] || panels[type === "stores" ? "store" : ""] || {};
  }

  function assignedModuleCodes019H(config, typeValue) {
    const panel = panelConfig019H(config, typeValue);
    const modules = Array.isArray(panel.modules) ? panel.modules : [];
    return modules
      .map((code) => normalizeModuleCode019H(code))
      .filter(Boolean)
      .filter((code, index, arr) => arr.indexOf(code) === index);
  }

  async function loadMiniPanelModuleConfig019H() {
    const empty = { enabled: false, modules: [], module_names: {}, raw: null };
    try {
      if (!companyId) return empty;

      const data = await api(`/api/v1/companies/${encodeURIComponent(companyId)}/modules?enabled_only=true`, {
        headers: authHeaders()
      });

      const config = extractMiniPanelSettings019H(data);
      const panel = panelConfig019H(config, panelType);
      const codes = assignedModuleCodes019H(config, panelType);
      const moduleNames = config && typeof config.module_names === "object" && config.module_names ? config.module_names : {};

      return {
        enabled: config.enabled === true || panel.enabled === true || codes.length > 0,
        selected_panel: normalizePanelType019H(panelType),
        modules: codes,
        module_names: moduleNames,
        raw: config
      };
    } catch (error) {
      console.warn("CLONEXA 019H-R1 modules fallback:", error);
      return {
        ...empty,
        error: error && error.message ? error.message : String(error)
      };
    }
  }

  function buildDynamicMiniPanelModules019H(moduleConfig) {
    const config = moduleConfig || {};
    const codes = Array.isArray(config.modules) ? config.modules : [];
    return codes
      .map((code) => moduleDefinition019H(code, config.module_names || {}))
      .filter((item) => item && item.code);
  }

  function renderDynamicModulesHtml019H(dynamicModules) {
    if (!dynamicModules.length) {
      return `
        <div class="mp-modules-empty-019h">
          <strong>No hay módulos asignados a este mini panel.</strong>
          <small>Agrega módulos desde Admin V2 - Empresa - Módulos - Módulos para Mini Panel.</small>
        </div>
      `;
    }

    return dynamicModules.map((item) => moduleCard(item.title, item.description, item.tag, item.code)).join("");
  }
  /* CLONEXA_019H_R1_SAFE_DYNAMIC_MODULES_END */



function moduleCard(title, description, tag, code = "") {
    return `
      <button class="mp-module-card" type="button" data-module="${h(code || tag)}" data-module-title="${h(title)}">
        <span>${h(tag)}</span>
        <strong>${h(title)}</strong>
        <small>${h(description)}</small>
      </button>
    `;
  }

  function renderShell(session, operational, moduleConfig = null) {
    setShellMode(true);

    const company = session.company || {};
    const user = session.user || {};
    const employee = session.employee || {};
    const mini = session.mini_panel || {};
    const kpis = operational.kpis || {};
    const employeeName = employee.full_name || user.full_name || "usuario";
    const employeeRole = employee.role || user.role || "operador";
    const companyName = company.name || company.slug || "Empresa";
    const locationLabel = operational.location_label || "Trabajo";
    const salesTotal = Number(kpis.monthly_sales_total || 0);
    const goal = Number(kpis.monthly_goal || 0);
    const goalPct = goal > 0 ? Math.min(100, Math.round((salesTotal / goal) * 100)) : 0;
    const isFinished = operational.status === "finished";
    const dynamicModules019H = buildDynamicMiniPanelModules019H(moduleConfig || currentModuleConfig);
    const modulesHtml019H = renderDynamicModulesHtml019H(dynamicModules019H);

    const notesEnabled020A = notesModuleEnabled020A(moduleConfig || currentModuleConfig);
    const notesSummary020A = currentNotesSummary020A || defaultNotesSummary020A();
    const notesCardHtml020A = notesEnabled020A ? `
            <article class="mp-kpi-card notes mp-notes-info-card-020a" data-notes-card role="button" tabindex="0">
              <span>Notas</span>
              <strong data-notes-card-count>${h(notesSummary020A.label || `${formatDateLabel020A(localDateIso020A())} · 0 recordatorios`)}</strong>
              <small data-notes-card-next>${h(notesSummary020A.next_label || "Sin próximos recordatorios")}</small>
            </article>
    ` : "";

    root.innerHTML = `
      <section class="mp-sales-dashboard mp-sales-dashboard-r1 mp-sales-dashboard-r2 mp-sales-dashboard-r3">
        <header class="mp-sales-header mp-sales-header-r1 mp-sales-header-r2 mp-sales-header-r3">
          <section class="mp-header-main mp-header-main-r1 mp-header-main-r2 mp-header-main-r3">
            <div class="mp-kicker">Mini Panel ${h(mini.type_label || labelType(panelType))}</div>
            <h1>${h(companyName)}</h1>
            <p>Portal operativo personalizado para ${h(employeeName)}.</p>

            <div class="mp-meta compact">
              <span class="mp-chip">Vendedor: ${h(employeeName)}</span>
              <span class="mp-chip">Rol: ${h(employeeRole)}</span>
              <span class="mp-chip">Empresa: ${h(company.slug || companyName)}</span>
              <span class="mp-chip">Ubicación: ${h(locationLabel)}</span>
              <span class="mp-chip">Usuario: ${h(mini.username || user.email || "—")}</span>
            </div>
          </section>

          <section class="mp-time-panel-r3">
            <div class="mp-mini-panel-title-r3">
              <span>Tiempos</span>
              <strong data-operational-status class="mp-status-pill ${h(operational.status || "active")}">${h(operationalLabel(operational.status))}</strong>
            </div>

            <div class="mp-time-stack-r3">
              <article class="mp-time-card-r3">
                <span>Activo</span>
                <strong data-active-timer>${h(formatSeconds(operational.active_seconds || 0))}</strong>
              </article>

              <article class="mp-time-card-r3 pause">
                <span>Pausa</span>
                <strong data-break-timer>${h(formatSeconds(operational.break_seconds || 0))}</strong>
              </article>
            </div>
          </section>

          <section class="mp-action-panel-r3">
            <div class="mp-mini-panel-title-r3">
              <span>Acciones</span>
            </div>

            <div class="mp-action-stack-r3">
              <button class="mp-button small" type="button" data-action="pause" ${operational.status === "active" ? "" : "disabled"}>Pausa</button>
              <button class="mp-button small secondary" type="button" data-action="resume" ${operational.status === "break" ? "" : "disabled"}>Retomar labores</button>
              <button class="mp-button small danger" type="button" data-action="finish" ${isFinished ? "disabled" : ""}>Finalizar turno</button>
              <button class="mp-button small ghost" type="button" data-change-password>Cambiar contraseña</button>
            </div>
          </section>
        </header>

        <section class="mp-dashboard-section">
          <div class="mp-section-title">
            <div>
              <div class="mp-kicker">KPIs</div>
              <h2>Ventas y meta</h2>
            </div>
          </div>

          <div class="mp-kpi-grid mp-kpi-grid-r3">
            <article class="mp-kpi-card">
              <span>Total ventas mes</span>
              <strong>${h(formatMoney(salesTotal))}</strong>
              <small>Sumatoria de registros de venta</small>
            </article>

            <article class="mp-kpi-card">
              <span>Llevas vs meta</span>
              <strong>${h(formatMoney(salesTotal))} / ${h(formatMoney(goal))}</strong>
              <div class="mp-progress"><i style="width:${goalPct}%"></i></div>
              <small>${goalPct}% de cumplimiento</small>
            </article>
            ${notesCardHtml020A}
<article class="mp-kpi-card wide">
              <span>Promociones / mensaje</span>
              <strong>Sin promociones activas</strong>
              <small>Este espacio recibirá campañas enviadas desde el CRM madre Mundo Case.</small>
            </article>
          </div>
        </section>

        <section class="mp-dashboard-section mp-modules-section-r1 mp-modules-section-r3">
          <div class="mp-section-title">
            <div>
              <div class="mp-kicker">Módulos</div>
              <h2>Acciones operativas</h2>
            </div>
          </div>

          <div class="mp-modules-grid mp-modules-grid-r3">
            ${modulesHtml019H}
          </div>

          <div class="mp-message ok" data-panel-message></div>
        </section>

        <div class="mp-modal" data-password-modal hidden>
          <div class="mp-modal-backdrop" data-password-close></div>
          <section class="mp-modal-card">
            <div class="mp-kicker">Seguridad</div>
            <h2>Cambiar contraseña</h2>
            <p>Actualiza tu clave de acceso al mini panel.</p>

            <form class="mp-form" id="miniPanelPasswordForm">
              <div class="mp-field">
                <label>Clave actual</label>
                <input id="mpCurrentPassword" type="password" autocomplete="current-password" required />
              </div>

              <div class="mp-field">
                <label>Nueva clave</label>
                <input id="mpNewPassword" type="password" autocomplete="new-password" minlength="8" required />
              </div>

              <div class="mp-field">
                <label>Confirmar nueva clave</label>
                <input id="mpConfirmPassword" type="password" autocomplete="new-password" minlength="8" required />
              </div>

              <div class="mp-modal-actions">
                <button class="mp-button secondary" type="button" data-password-close>Cancelar</button>
                <button class="mp-button" type="submit">Guardar contraseña</button>
              </div>

              <div class="mp-message" id="miniPanelPasswordMessage"></div>
            </form>
          </section>
        </div>
      </section>
    `;

    startTimers(operational);

    root.querySelector("[data-action='pause']")?.addEventListener("click", async () => {
      await runOperationalAction("pause", session);
    });

    root.querySelector("[data-action='resume']")?.addEventListener("click", async () => {
      await runOperationalAction("resume", session);
    });

    root.querySelector("[data-action='finish']")?.addEventListener("click", async () => {
      const msg = root.querySelector("[data-panel-message]");
      try {
        const updated = await operationalAction("finish");
        startTimers(updated.operational_session || updated);
        if (msg) msg.textContent = "Turno finalizado.";
        window.setTimeout(() => {
          clearTimer();
          localStorage.removeItem(storageKey);
          window.location.href = loginUrl();
        }, 900);
      } catch (error) {
        if (msg) {
          msg.classList.remove("ok");
          msg.textContent = error.message || "No fue posible finalizar el turno.";
        }
      }
    });

    const modal = root.querySelector("[data-password-modal]");
    const passwordForm = root.querySelector("#miniPanelPasswordForm");
    const passwordMsg = root.querySelector("#miniPanelPasswordMessage");

    function closePasswordModal() {
      if (modal) modal.hidden = true;
      if (passwordForm) passwordForm.reset();
      if (passwordMsg) {
        passwordMsg.classList.remove("ok");
        passwordMsg.textContent = "";
      }
    }

    root.querySelector("[data-change-password]")?.addEventListener("click", () => {
      if (modal) modal.hidden = false;
    });

    root.querySelectorAll("[data-password-close]").forEach((button) => {
      button.addEventListener("click", closePasswordModal);
    });

    passwordForm?.addEventListener("submit", async (event) => {
      event.preventDefault();
      const currentPassword = root.querySelector("#mpCurrentPassword")?.value || "";
      const newPassword = root.querySelector("#mpNewPassword")?.value || "";
      const confirmPassword = root.querySelector("#mpConfirmPassword")?.value || "";

      if (passwordMsg) {
        passwordMsg.classList.add("ok");
        passwordMsg.textContent = "Actualizando contraseña...";
      }

      try {
        await changePasswordRequest(currentPassword, newPassword, confirmPassword);
        if (passwordMsg) {
          passwordMsg.classList.add("ok");
          passwordMsg.textContent = "Contraseña actualizada.";
        }
        window.setTimeout(closePasswordModal, 900);
      } catch (error) {
        if (passwordMsg) {
          passwordMsg.classList.remove("ok");
          passwordMsg.textContent = error.message || "No fue posible cambiar la contraseña.";
        }
      }
    });

    root.querySelector("[data-notes-card]")?.addEventListener("click", async () => {
      await openNotesCalendar020A(session);
    });

    root.querySelector("[data-notes-card]")?.addEventListener("keydown", async (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        await openNotesCalendar020A(session);
      }
    });

    root.querySelectorAll("[data-module]").forEach((button) => {
      button.addEventListener("click", async () => {
        const moduleCode = button.getAttribute("data-module") || "";
        if (isNotesCode020A(moduleCode)) {
          await openNotesCalendar020A(session);
          return;
        }

        const msg = root.querySelector("[data-panel-message]");
        if (msg) {
          msg.classList.add("ok");
          msg.textContent = "Módulo listo para activar en la siguiente fase.";
        }
      });
    });
  }


  async function runOperationalAction(action, session) {
    const msg = root.querySelector("[data-panel-message]");
    try {
      const updated = await operationalAction(action);
      const op = updated.operational_session || updated;
      renderShell(session, op, currentModuleConfig);
    } catch (error) {
      if (msg) {
        msg.classList.remove("ok");
        msg.textContent = error.message || "No fue posible actualizar la sesión.";
      }
    }
  }

  async function bootShell() {
    if (!companyId) {
      renderError("El enlace no contiene company_id.");
      return;
    }

    const savedToken = token();
    if (!savedToken) {
      window.location.href = loginUrl();
      return;
    }

    try {
      const session = await api(`/api/v1/companies/${encodeURIComponent(companyId)}/mini-panel-session?panel_type=${encodeURIComponent(panelType)}`, {
        headers: { Authorization: `Bearer ${savedToken}` }
      });

      const operational = await loadOperationalSession();
      currentModuleConfig = await loadMiniPanelModuleConfig019H().catch((error) => {
        console.warn("CLONEXA 019H-R1 config fallback:", error);
        return { enabled: false, modules: [], module_names: {}, error: error?.message || String(error) };
      });
      currentNotesSummary020A = await loadNotesSummary020A(currentModuleConfig).catch((error) => {
        console.warn("CLONEXA 020A notes summary fallback:", error);
        return defaultNotesSummary020A();
      });
      renderShell(session, operational.operational_session || operational, currentModuleConfig);
    } catch (error) {
      localStorage.removeItem(storageKey);
      renderLogin(error.message || "Sesión expirada. Ingresa de nuevo.");
    }
  }

  if (isLogin) {
    renderLogin();
  } else {
    bootShell();
  }
})();
// CLONEXA_FORCE_BUILD_019H_R1_20260513224440
