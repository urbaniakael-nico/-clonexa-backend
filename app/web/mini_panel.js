(() => {
  "use strict";

  const root = document.getElementById("miniPanelApp");
  const params = new URLSearchParams(window.location.search);
  const companyId = params.get("company_id") || params.get("companyId") || "";
  const panelType = (params.get("type") || params.get("panel_type") || "sales").toLowerCase();
  const isLogin = window.location.pathname.includes("/login");
  const storageKey = `clonexa_mini_panel_token_${companyId}_${panelType}`;
  const legacyStorageKey024B = storageKey;

  let timerHandle = null;
  let storeTeamTimer023W = null;
  let currentOperational = null;
  let currentModuleConfig = null;
  let currentQuoteReferences021C = [];
  let currentStoreTeam023W = null;
  let selectedStoreEmployee023W = "";

  const TYPE_LABELS = {
    sales: "Ventas",
    store: "Tiendas",
    stores: "Tiendas",
    inventory: "Inventarios",
    call_center: "Call Center",
    external: "Externo",
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

  /* CLONEXA_024B_STORE_ADMIN_SESSION_ISOLATION_TOKEN_START */
  function token() {
    return sessionStorage.getItem(storageKey) || "";
  }

  function clearMiniPanelToken024B() {
    sessionStorage.removeItem(storageKey);
    localStorage.removeItem(legacyStorageKey024B);
  }
  /* CLONEXA_024B_STORE_ADMIN_SESSION_ISOLATION_TOKEN_END */

  function authHeaders() {
    const value = token();
    return value ? { Authorization: `Bearer ${value}` } : {};
  }

  function authQueryParam(prefix = "&") {
    const value = token();
    return value ? `${prefix}access_token=${encodeURIComponent(value)}` : "";
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
    "notas_agenda",
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
        ${storeActorStripHtml023W("notas")}
        <div class="mp-notes-content-020a" data-notes-content>
          <div class="mp-notes-empty-020a">Cargando calendario...</div>
        </div>
      </section>
    `;
    document.body.appendChild(overlay);
    bindStoreActorSelector023W(overlay);

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
              <small>Gestiona notas, seguimientos, eventos y recordatorios de ${h(session?.company?.name || "la empresa")}.</small>
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
                      <option value="event">Evento</option>
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
          note_type: String(formData.get("note_type") || "reminder"),
          ...storeActorPayload023W()
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

  /* CLONEXA_021A_QUOTES_MODULE_START */
  const QUOTE_CODES_021A = new Set([
    "cotizacion",
    "cotizaciones",
    "cotizar",
    "quote",
    "quotes",
    "quotation",
    "quotations",
    "presupuesto",
    "presupuestos"
  ]);

  let currentQuotesSummary021A = null;

  function isQuotesCode021A(code) {
    const normalized = normalizeModuleCode019H(code);
    return QUOTE_CODES_021A.has(normalized);
  }

  function quotesModuleEnabled021A(moduleConfig) {
    const config = moduleConfig || currentModuleConfig || {};
    const modules = Array.isArray(config.modules) ? config.modules : [];
    return modules.some((code) => isQuotesCode021A(code));
  }

  function defaultQuotesSummary021A() {
    return {
      active_count: 0,
      total_amount: 0,
      latest: null
    };
  }

  async function quotesApi021A(path = "", options = {}) {
    const base = `/api/v1/mini-panel-quotes/companies/${encodeURIComponent(companyId)}`;
    const separator = path.includes("?") ? "&" : "?";
    const url = `${base}${path}${separator}panel_type=${encodeURIComponent(panelType)}`;
    const headers = {
      ...authHeaders(),
      ...(options.headers || {})
    };

    const response = await fetch(url, {
      ...options,
      headers
    });

    if (options.raw === true) {
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || errorData.message || "Solicitud rechazada.");
      }
      return response;
    }

    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(data.detail || data.message || "Solicitud rechazada.");
    }
    return data;
  }

  async function loadQuotesSummary021A(moduleConfig) {
    if (!quotesModuleEnabled021A(moduleConfig)) return defaultQuotesSummary021A();
    return quotesApi021A("/summary");
  }

  function quoteStatusLabel021A(value) {
    const status = String(value || "").toLowerCase();
    if (status === "archived") return "Archivada";
    if (status === "converted") return "Cuenta de cobro";
    if (status === "draft") return "Borrador";
    return "Emitida";
  }

  function quoteStatusClass021A(value) {
    const status = String(value || "").toLowerCase();
    if (status === "archived") return "archived";
    if (status === "converted") return "converted";
    if (status === "draft") return "draft";
    return "issued";
  }

  function quoteDocumentType021B(quote) {
    const explicit = String(quote?.document_type || "").toLowerCase();
    if (explicit === "account") return "account";
    return String(quote?.status || "").toLowerCase() === "converted" ? "account" : "quote";
  }

  function quoteAccountNumber021B(quote) {
    const raw = String(quote?.account_number || quote?.document_number || quote?.quote_number || "").trim();
    if (raw.toUpperCase().startsWith("CB-")) return raw;
    const original = String(quote?.quote_number || raw || "").trim();
    if (!original) return "CB";
    return "CB-" + original.replace(/^(COT-|CT-|CB-)/i, "");
  }

  function quoteDisplayNumber021B(quote, forcedType = "") {
    const docType = forcedType || quoteDocumentType021B(quote);
    if (docType === "account") return quoteAccountNumber021B(quote);
    return String(quote?.quote_number || quote?.document_number || "CT").trim();
  }

  function quotePdfLabel021B(quote, forcedType = "") {
    const docType = forcedType || quoteDocumentType021B(quote);
    return docType === "account" ? "PDF cuenta de cobro" : "PDF cotización";
  }

  function renderQuoteSignaturePreview021B(container, dataUrl) {
    const preview = container?.querySelector("[data-quote-signature-preview]");
    if (!preview) return;
    if (!dataUrl) {
      preview.innerHTML = "<span>Sin firma adjunta.</span>";
      return;
    }
    preview.innerHTML = `<img src="${h(dataUrl)}" alt="Firma adjunta" />`;
  }

  function formatQuoteDate021A(value) {
    const raw = String(value || "");
    if (!raw) return "—";
    const date = raw.slice(0, 10);
    if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) return raw.slice(0, 16);
    const [year, month, day] = date.split("-");
    return `${day}/${month}/${year}`;
  }

  function parseQuoteMoney021A(value) {
    const raw = String(value ?? "")
      .replace(/[^\d,.-]/g, "")
      .replace(/\./g, "")
      .replace(",", ".");
    const number = Number(raw);
    return Number.isFinite(number) ? Math.max(0, number) : 0;
  }

  function quoteMoney021A(value) {
    return formatMoney(Number(value || 0));
  }

  function quoteCleanText021C(value) {
    let text = String(value ?? "");
    for (let i = 0; i < 2 && /[ÃÂ]/.test(text); i += 1) {
      try {
        const repaired = decodeURIComponent(escape(text));
        if (!repaired || repaired === text) break;
        text = repaired;
      } catch (_) {
        break;
      }
    }
    return text;
  }

  async function loadQuoteReferences021C() {
    try {
      const response = await fetch(`/api/v1/references-v1/companies/${encodeURIComponent(companyId)}`, {
        headers: authHeaders(),
      });
      if (!response.ok) return [];
      const data = await response.json().catch(() => ({}));
      const rows = Array.isArray(data?.items)
        ? data.items
        : Array.isArray(data?.references)
          ? data.references
          : Array.isArray(data)
            ? data
            : [];
      return rows
        .filter((item) => item && item.archived !== true)
        .map((item) => ({
          id: String(item.id || ""),
          name: quoteCleanText021C(item.name || item.reference_name || ""),
          category: quoteCleanText021C(item.category || item.reference_category || ""),
          size: quoteCleanText021C(item.size || item.reference_size || ""),
          color: quoteCleanText021C(item.color || item.reference_color || ""),
          sku: quoteCleanText021C(item.sku || item.code || ""),
          unit_price: Number(item.unit_price ?? item.price ?? 0) || 0,
        }))
        .filter((item) => item.name);
    } catch (_) {
      return [];
    }
  }

  function quoteReferenceLabel021C(ref = {}) {
    return [ref.name, ref.size, ref.color, ref.sku ? `SKU ${ref.sku}` : ""].filter(Boolean).join(" · ");
  }

  function quoteReferenceOptions021C(selectedId = "") {
    const options = currentQuoteReferences021C.map((ref) => `
      <option
        value="${h(ref.id)}"
        data-ref-name="${h(ref.name)}"
        data-ref-label="${h(quoteReferenceLabel021C(ref))}"
        data-ref-price="${h(ref.unit_price)}"
        data-ref-sku="${h(ref.sku)}"
        ${String(selectedId || "") === String(ref.id || "") ? "selected" : ""}
      >${h(quoteReferenceLabel021C(ref))}</option>
    `).join("");
    return `<option value="">Manual / sin referencia</option>${options}`;
  }

  function applyQuoteReference021C(select) {
    const option = select?.selectedOptions?.[0];
    const row = select?.closest("[data-quote-item-row]");
    if (!option || !row || !option.value) return;
    const description = row.querySelector("[name='item_description']");
    const unitPrice = row.querySelector("[name='item_unit_price']");
    if (description) description.value = option.dataset.refLabel || option.dataset.refName || option.textContent || "";
    if (unitPrice) unitPrice.value = String(Number(option.dataset.refPrice || 0) || 0);
  }

  function updateQuotesCard021A(summary) {
    const data = summary || defaultQuotesSummary021A();
    const count = document.querySelector("[data-quotes-card-count]");
    const total = document.querySelector("[data-quotes-card-total]");
    const latest = document.querySelector("[data-quotes-card-latest]");

    if (count) count.textContent = `${Number(data.active_count || 0)} activas`;
    if (total) total.textContent = `${quoteMoney021A(data.total_amount || 0)} cotizado`;

    const latestQuote = data.latest || null;
    if (latest) {
      latest.textContent = latestQuote
        ? `Última: ${latestQuote.quote_number || "cotización"} · ${latestQuote.client_name || "cliente"}`
        : "Sin cotizaciones registradas";
    }
  }

  function quotePayloadFromForm021A(form, signatureData) {
    const itemRows = Array.from(form.querySelectorAll("[data-quote-item-row]"));
    const items = itemRows
      .map((row) => {
        const refSelect = row.querySelector("[data-quote-reference-select]");
        const refOption = refSelect?.selectedOptions?.[0];
        return {
          description: row.querySelector("[name='item_description']")?.value || "",
          quantity: parseQuoteMoney021A(row.querySelector("[name='item_quantity']")?.value || "0"),
          unit_price: parseQuoteMoney021A(row.querySelector("[name='item_unit_price']")?.value || "0"),
          reference_id: String(refSelect?.value || ""),
          sku: String(refOption?.dataset?.refSku || "")
        };
      })
      .filter((item) => item.description.trim());

    const discountRows = Array.from(form.querySelectorAll("[data-quote-discount-row]"));
    const discounts = discountRows.map((row) => {
      const kind = row.getAttribute("data-quote-discount-kind") || "discount";
      const percent = parseQuoteMoney021A(row.querySelector("[name='discount_percent']")?.value || row.querySelector("[name='discount_value']")?.value || "0");
      return {
        type: kind,
        kind,
        affects_total: kind !== "retention",
        name: row.querySelector("[name='discount_name']")?.value || (kind === "retention" ? "Retención" : ""),
        description: row.querySelector("[name='discount_description']")?.value || "",
        value: kind === "retention" ? percent : parseQuoteMoney021A(row.querySelector("[name='discount_value']")?.value || "0"),
        percent: kind === "retention" ? percent : null
      };
    });

    return {
      client_name: form.querySelector("[name='client_name']")?.value || "",
      client_document: form.querySelector("[name='client_document']")?.value || "",
      client_address: form.querySelector("[name='client_address']")?.value || "",
      client_phone: form.querySelector("[name='client_phone']")?.value || "",
      client_email: form.querySelector("[name='client_email']")?.value || "",
      items,
      discounts,
      payment: {
        detail: form.querySelector("[name='payment_detail']")?.value || "",
        name: form.querySelector("[name='payment_name']")?.value || "",
        method: form.querySelector("[name='payment_method']")?.value || "transferencia",
        data: form.querySelector("[name='payment_data']")?.value || ""
      },
      notes: form.querySelector("[name='quote_notes']")?.value || "",
      signature_data_url: signatureData || ""
    };
  }

  function renderQuoteItemRow021A(item = {}) {
    return `
      <div class="mp-quote-item-row-021a" data-quote-item-row>
        <div class="mp-field concept">
          <label>Concepto</label>
          <select data-quote-reference-select>
            ${quoteReferenceOptions021C(item.reference_id || item.id || "")}
          </select>
          <input name="item_description" value="${h(item.description || "")}" placeholder="Ej: servicio, producto, referencia..." required />
        </div>
        <div class="mp-field qty">
          <label>Cantidad</label>
          <input name="item_quantity" type="number" min="0" step="0.01" value="${h(item.quantity ?? 1)}" data-quote-calc />
        </div>
        <div class="mp-field money">
          <label>Valor unitario</label>
          <input name="item_unit_price" type="number" min="0" step="0.01" value="${h(item.unit_price ?? 0)}" data-quote-calc />
        </div>
        <div class="mp-quote-line-total-021a">
          <span>Total</span>
          <strong data-line-total>${h(quoteMoney021A((Number(item.quantity || 1) * Number(item.unit_price || 0))))}</strong>
        </div>
        <button class="mp-button ghost danger mini" type="button" data-remove-quote-item>Quitar</button>
      </div>
    `;
  }

  function renderQuoteDiscountRow021A(index, discount = {}) {
    const storedKind = String(discount.kind || discount.type || "").toLowerCase();
    const kind = index === 2 || storedKind === "retention" || storedKind === "retencion" ? "retention" : "discount";
    const value = kind === "retention" ? (discount.percent ?? discount.value ?? 0) : (discount.value || 0);
    return `
      <div class="mp-quote-discount-row-021a" data-quote-discount-row data-quote-discount-kind="${h(kind)}">
        <div class="mp-field">
          <label>${kind === "retention" ? "Retención" : "Descuento"} · Nombre</label>
          <input name="discount_name" value="${h(discount.name || (kind === "retention" ? "Retención" : ""))}" placeholder="${kind === "retention" ? "Ej: retefuente" : "Ej: pronto pago"}" />
        </div>
        <div class="mp-field">
          <label>Descripción</label>
          <input name="discount_description" value="${h(discount.description || "")}" placeholder="${kind === "retention" ? "Detalle de la retención" : "Detalle del descuento"}" />
        </div>
        <div class="mp-field">
          <label>${kind === "retention" ? "Porcentaje retención" : "Valor descuento"}</label>
          <input name="${kind === "retention" ? "discount_percent" : "discount_value"}" type="number" min="0" ${kind === "retention" ? "max=\"100\"" : ""} step="0.01" value="${h(value)}" data-quote-calc />
        </div>
      </div>
    `;
  }

  function recalcQuoteTotals021A(container) {
    let subtotal = 0;

    container.querySelectorAll("[data-quote-item-row]").forEach((row) => {
      const qty = parseQuoteMoney021A(row.querySelector("[name='item_quantity']")?.value || 0);
      const unit = parseQuoteMoney021A(row.querySelector("[name='item_unit_price']")?.value || 0);
      const total = qty * unit;
      subtotal += total;
      const lineTotal = row.querySelector("[data-line-total]");
      if (lineTotal) lineTotal.textContent = quoteMoney021A(total);
    });

    let discounts = 0;
    let retention = 0;
    container.querySelectorAll("[data-quote-discount-row]").forEach((row) => {
      const kind = row.getAttribute("data-quote-discount-kind") || "discount";
      if (kind === "retention") {
        const percent = Math.min(100, Math.max(0, parseQuoteMoney021A(row.querySelector("[name='discount_percent']")?.value || 0)));
        retention += Math.max(0, subtotal) * percent / 100;
      } else {
        discounts += parseQuoteMoney021A(row.querySelector("[name='discount_value']")?.value || 0);
      }
    });

    discounts = Math.min(discounts, subtotal);
    const total = Math.max(0, subtotal - discounts);

    const subtotalNode = container.querySelector("[data-quote-subtotal]");
    const discountsNode = container.querySelector("[data-quote-discounts]");
    const retentionNode = container.querySelector("[data-quote-retention]");
    const totalNode = container.querySelector("[data-quote-total]");

    if (subtotalNode) subtotalNode.textContent = quoteMoney021A(subtotal);
    if (discountsNode) discountsNode.textContent = quoteMoney021A(discounts);
    if (retentionNode) retentionNode.textContent = quoteMoney021A(retention);
    if (totalNode) totalNode.textContent = quoteMoney021A(total);
  }

  function renderQuotesList021A(items = []) {
    if (!items.length) {
      return `
        <div class="mp-quotes-empty-021a">
          <strong>No hay documentos para mostrar.</strong>
          <small>Crea una cotización desde el formulario superior o ajusta el filtro.</small>
        </div>
      `;
    }

    return items.map((quote) => {
      const docType = quoteDocumentType021B(quote);
      const displayNumber = quoteDisplayNumber021B(quote, docType);
      const converted = docType === "account";
      return `
        <article class="mp-quote-row-021a ${h(quoteStatusClass021A(quote.status))}" data-quote-row="${h(quote.id)}">
          <div>
            <span>${h(displayNumber)}</span>
            <strong>${h(quote.client_name || "Cliente")}</strong>
            <small>${h(formatQuoteDate021A(quote.created_at))} · ${h(converted ? "Cuenta de cobro" : "Cotización")}</small>
          </div>
          <div class="mp-quote-row-amount-021a">${h(quoteMoney021A(quote.total || 0))}</div>
          <div class="mp-quote-row-actions-021a">
            <button class="mp-button secondary mini" type="button" data-quote-detail="${h(quote.id)}">Detalle</button>
            <button class="mp-button mini" type="button" data-quote-pdf="${h(quote.id)}" data-quote-doc-type="${h(docType)}" data-quote-number="${h(displayNumber)}">${h(quotePdfLabel021B(quote, docType))}</button>
            ${converted ? `<button class="mp-button ghost mini" type="button" data-quote-pdf="${h(quote.id)}" data-quote-doc-type="quote" data-quote-number="${h(quoteDisplayNumber021B(quote, "quote"))}">PDF cotización</button>` : `<button class="mp-button ghost mini" type="button" data-quote-convert="${h(quote.id)}">Pasar a cuenta de cobro</button>`}
            <button class="mp-button ghost danger mini" type="button" data-quote-archive="${h(quote.id)}">Archivar</button>
          </div>
        </article>
      `;
    }).join("");
  }

  function initQuoteSignature021A(overlay, state) {
    const canvas = overlay.querySelector("[data-quote-signature]");
    const clear = overlay.querySelector("[data-clear-signature]");
    const attach = overlay.querySelector("[data-attach-signature]");
    const fileInput = overlay.querySelector("[data-quote-signature-file]");
    const previewBox = overlay.querySelector("[data-quote-signature-preview]");
    if (!canvas) return;

    const ctx = canvas.getContext("2d");
    let drawing = false;
    let hasInk = false;

    function resize() {
      const ratio = Math.max(window.devicePixelRatio || 1, 1);
      const rect = canvas.getBoundingClientRect();
      canvas.width = Math.max(420, Math.floor(rect.width * ratio));
      canvas.height = Math.max(150, Math.floor(rect.height * ratio));
      ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
      ctx.lineWidth = 2.5;
      ctx.lineCap = "round";
      ctx.lineJoin = "round";
      ctx.strokeStyle = "#ffffff";
    }

    function point(event) {
      const rect = canvas.getBoundingClientRect();
      return {
        x: event.clientX - rect.left,
        y: event.clientY - rect.top
      };
    }

    function saveSignature() {
      state.signatureData = hasInk ? canvas.toDataURL("image/png") : (state.signatureData || "");
      renderQuoteSignaturePreview021B(overlay, state.signatureData);
    }

    function clearCanvas() {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      hasInk = false;
    }

    resize();
    renderQuoteSignaturePreview021B(overlay, state.signatureData);

    canvas.addEventListener("pointerdown", (event) => {
      drawing = true;
      hasInk = true;
      state.signatureData = "";
      renderQuoteSignaturePreview021B(overlay, "");
      canvas.setPointerCapture(event.pointerId);
      const p = point(event);
      ctx.beginPath();
      ctx.moveTo(p.x, p.y);
    });

    canvas.addEventListener("pointermove", (event) => {
      if (!drawing) return;
      const p = point(event);
      ctx.lineTo(p.x, p.y);
      ctx.stroke();
      saveSignature();
    });

    canvas.addEventListener("pointerup", (event) => {
      drawing = false;
      try { canvas.releasePointerCapture(event.pointerId); } catch (_) {}
      saveSignature();
    });

    canvas.addEventListener("pointerleave", () => {
      drawing = false;
      saveSignature();
    });

    attach?.addEventListener("click", () => fileInput?.click());

    fileInput?.addEventListener("change", () => {
      const file = fileInput.files?.[0];
      if (!file) return;
      if (!file.type.startsWith("image/")) {
        alert("Adjunta una imagen de firma válida.");
        fileInput.value = "";
        return;
      }

      const reader = new FileReader();
      reader.onload = () => {
        clearCanvas();
        state.signatureData = String(reader.result || "");
        if (previewBox) {
          previewBox.innerHTML = `<img src="${h(state.signatureData)}" alt="Firma adjunta" />`;
        }
      };
      reader.readAsDataURL(file);
    });

    clear?.addEventListener("click", () => {
      clearCanvas();
      state.signatureData = "";
      if (fileInput) fileInput.value = "";
      renderQuoteSignaturePreview021B(overlay, "");
    });

    window.setTimeout(resize, 60);
  }

  async function downloadQuotePdf021A(quoteId, quoteNumber, documentType = "quote") {
    const suffix = documentType === "account" ? "account" : "quote";
    const response = await quotesApi021A(`/${encodeURIComponent(quoteId)}/pdf?document_type=${encodeURIComponent(suffix)}`, { raw: true });
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${quoteNumber || (suffix === "account" ? "cuenta-cobro" : "cotizacion")}.pdf`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 2000);
  }

  function fillQuoteForm021A(form, quote, state) {
    if (!form || !quote) return;

    state.editingId = quote.id || null;
    state.signatureData = quote.signature_data_url || "";

    form.querySelector("[name='client_name']").value = quote.client_name || "";
    form.querySelector("[name='client_document']").value = quote.client_document || "";
    form.querySelector("[name='client_address']").value = quote.client_address || "";
    form.querySelector("[name='client_phone']").value = quote.client_phone || "";
    form.querySelector("[name='client_email']").value = quote.client_email || "";
    form.querySelector("[name='payment_detail']").value = quote.payment?.detail || "";
    form.querySelector("[name='payment_name']").value = quote.payment?.name || "";
    form.querySelector("[name='payment_method']").value = quote.payment?.method || "transferencia";
    form.querySelector("[name='payment_data']").value = quote.payment?.data || "";
    form.querySelector("[name='quote_notes']").value = quote.notes || "";

    const itemsBox = form.querySelector("[data-quote-items]");
    if (itemsBox) {
      const items = Array.isArray(quote.items) && quote.items.length ? quote.items : [{ description: "", quantity: 1, unit_price: 0 }];
      itemsBox.innerHTML = items.map((item) => renderQuoteItemRow021A(item)).join("");
    }

    const discountsBox = form.querySelector("[data-quote-discounts-box]");
    if (discountsBox) {
      const discounts = Array.isArray(quote.discounts) ? quote.discounts : [];
      discountsBox.innerHTML = [0, 1].map((_, index) => renderQuoteDiscountRow021A(index + 1, discounts[index] || {})).join("");
    }

    const editingLabel = form.querySelector("[data-quote-editing]");
    if (editingLabel) editingLabel.textContent = `Editando ${quote.quote_number || "cotización"}`;

    renderQuoteSignaturePreview021B(form, state.signatureData);
    recalcQuoteTotals021A(form);
    form.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function resetQuoteForm021A(form, state) {
    state.editingId = null;
    state.signatureData = "";
    form.reset();
    const itemsBox = form.querySelector("[data-quote-items]");
    if (itemsBox) itemsBox.innerHTML = renderQuoteItemRow021A();
    const discountsBox = form.querySelector("[data-quote-discounts-box]");
    if (discountsBox) discountsBox.innerHTML = [1, 2].map((index) => renderQuoteDiscountRow021A(index)).join("");
    const editingLabel = form.querySelector("[data-quote-editing]");
    if (editingLabel) editingLabel.textContent = "Nueva cotización";
    const canvas = form.querySelector("[data-quote-signature]");
    const ctx = canvas?.getContext("2d");
    if (canvas && ctx) ctx.clearRect(0, 0, canvas.width, canvas.height);
    const fileInput = form.querySelector("[data-quote-signature-file]");
    if (fileInput) fileInput.value = "";
    renderQuoteSignaturePreview021B(form, "");
    recalcQuoteTotals021A(form);
  }

  async function openQuotesModule021A(session) {
    if (!quotesModuleEnabled021A(currentModuleConfig)) {
      alert("Cotizaciones no está asignado a este mini panel.");
      return;
    }

    const company = session.company || {};
    const state = { editingId: null, signatureData: "" };
    currentQuoteReferences021C = await loadQuoteReferences021C();

    const overlay = document.createElement("div");
    overlay.className = "mp-modal mp-quotes-modal-021a";
    overlay.innerHTML = `
      <div class="mp-modal-backdrop" data-quotes-close></div>
      <section class="mp-quotes-card-021a">
        <header class="mp-quotes-header-021a">
          <div>
            <div class="mp-kicker">Cotizaciones</div>
            <h2>Generador comercial</h2>
            <p>${h(company.name || company.slug || "Empresa")} · ${h(labelType(panelType))}</p>
          </div>
          <button class="mp-button secondary" type="button" data-quotes-close>Cerrar</button>
        </header>

        ${storeActorStripHtml023W("cotizaciones")}

        <div class="mp-quotes-content-021a">
          <section class="mp-quotes-form-panel-021a">
            <div class="mp-quotes-section-head-021a">
              <div>
                <span data-quote-editing>Nueva cotización</span>
                <strong>Formulario de cotización</strong>
              </div>
              <div class="mp-quotes-total-pill-021a">
                <small>Total</small>
                <b data-quote-total>${h(quoteMoney021A(0))}</b>
              </div>
            </div>

            <form class="mp-quotes-form-021a" data-quotes-form>
              <div class="mp-quotes-client-grid-021a">
                <div class="mp-field wide">
                  <label>Tu nombre o razón social</label>
                  <input name="client_name" placeholder="Cliente / empresa" required />
                </div>
                <div class="mp-field">
                  <label>CC / NIT</label>
                  <input name="client_document" placeholder="Documento" />
                </div>
                <div class="mp-field">
                  <label>Teléfono</label>
                  <input name="client_phone" placeholder="Teléfono" />
                </div>
                <div class="mp-field wide">
                  <label>Dirección</label>
                  <input name="client_address" placeholder="Dirección del cliente" />
                </div>
                <div class="mp-field">
                  <label>Correo</label>
                  <input name="client_email" type="email" placeholder="correo@cliente.com" />
                </div>
              </div>

              <div class="mp-quotes-subsection-021a">
                <div class="mp-quotes-subtitle-021a">
                  <strong>Conceptos</strong>
                  <button class="mp-button secondary mini" type="button" data-add-quote-item>Agregar línea</button>
                </div>
                <div data-quote-items>
                  ${renderQuoteItemRow021A()}
                </div>
              </div>

              <div class="mp-quotes-discounts-021a" data-quote-discounts-box>
                ${renderQuoteDiscountRow021A(1)}
                ${renderQuoteDiscountRow021A(2)}
              </div>

              <div class="mp-quotes-payment-grid-021a">
                <div class="mp-field">
                  <label>Detalle pago 1</label>
                  <input name="payment_detail" placeholder="Ej: anticipo, saldo, contado..." />
                </div>
                <div class="mp-field">
                  <label>Nombre</label>
                  <input name="payment_name" placeholder="Responsable / banco / referencia" />
                </div>
                <div class="mp-field">
                  <label>Forma</label>
                  <select name="payment_method">
                    <option value="efectivo">Efectivo</option>
                    <option value="transferencia" selected>Transferencia</option>
                    <option value="cheque">Cheque</option>
                    <option value="otro">Otro</option>
                  </select>
                </div>
                <div class="mp-field wide">
                  <label>Datos de pago</label>
                  <textarea name="payment_data" rows="3" placeholder="Cuenta, referencia, condiciones, vencimiento..."></textarea>
                </div>
              </div>

              <div class="mp-field">
                <label>Observaciones / condiciones</label>
                <textarea name="quote_notes" rows="3" placeholder="Validez de oferta, tiempos de entrega, garantías..."></textarea>
              </div>

              <div class="mp-quotes-signature-wrap-021a">
                <div class="mp-quotes-signature-head-021b">
                  <div>
                    <strong>Firma digital</strong>
                    <small>Firma sobre el recuadro o adjunta una imagen de firma para incluirla en el PDF.</small>
                  </div>
                  <div class="mp-quotes-signature-actions-021b">
                    <button class="mp-button secondary mini" type="button" data-attach-signature>Adjuntar firma</button>
                    <button class="mp-button ghost mini" type="button" data-clear-signature>Limpiar firma</button>
                  </div>
                </div>
                <input type="file" accept="image/*" data-quote-signature-file hidden />
                <canvas data-quote-signature></canvas>
                <div class="mp-quotes-signature-preview-021b" data-quote-signature-preview>
                  <span>Sin firma adjunta.</span>
                </div>
              </div>

              <footer class="mp-quotes-form-footer-021a">
                <div class="mp-quotes-totals-021a">
                  <span>Subtotal: <b data-quote-subtotal>${h(quoteMoney021A(0))}</b></span>
                  <span>Descuentos: <b data-quote-discounts>${h(quoteMoney021A(0))}</b></span>
                  <span>Retención: <b data-quote-retention>${h(quoteMoney021A(0))}</b></span>
                  <span>Total: <b data-quote-total>${h(quoteMoney021A(0))}</b></span>
                </div>
                <div class="mp-quotes-actions-021a">
                  <button class="mp-button secondary" type="button" data-reset-quote>Nuevo</button>
                  <button class="mp-button" type="submit">Guardar cotización</button>
                </div>
              </footer>

              <div class="mp-message" data-quotes-message></div>
            </form>
          </section>

          <section class="mp-quotes-list-panel-021a">
            <div class="mp-quotes-section-head-021a">
              <div>
                <span>Historial</span>
                <strong>Buscar cotizaciones</strong>
              </div>
            </div>
            <div class="mp-quotes-search-021a">
              <input data-quotes-search placeholder="Buscar por nombre, NIT, correo, número, cotización o cuenta de cobro..." />
              <select data-quotes-type-filter title="Filtrar documentos">
                <option value="">Todos</option>
                <option value="quote">Cotizaciones</option>
                <option value="account">Cuentas de cobro</option>
              </select>
              <button class="mp-button secondary mini" type="button" data-quotes-refresh>Buscar</button>
            </div>
            <div class="mp-quotes-summary-strip-021a">
              <article>
                <span>Activas</span>
                <strong data-quotes-summary-count>0</strong>
              </article>
              <article>
                <span>Monto</span>
                <strong data-quotes-summary-total>${h(quoteMoney021A(0))}</strong>
              </article>
            </div>
            <div class="mp-quotes-list-021a" data-quotes-list>
              <div class="mp-quotes-empty-021a">Cargando cotizaciones...</div>
            </div>
          </section>
        </div>
      </section>
    `;

    document.body.appendChild(overlay);
    bindStoreActorSelector023W(overlay);
    initQuoteSignature021A(overlay, state);

    const form = overlay.querySelector("[data-quotes-form]");
    const listBox = overlay.querySelector("[data-quotes-list]");
    const msg = overlay.querySelector("[data-quotes-message]");
    const search = overlay.querySelector("[data-quotes-search]");
    const typeFilter = overlay.querySelector("[data-quotes-type-filter]");

    function setMsg(text, ok = true) {
      if (!msg) return;
      msg.classList.toggle("ok", ok);
      msg.textContent = text || "";
    }

    async function refreshSummary() {
      try {
        currentQuotesSummary021A = await loadQuotesSummary021A(currentModuleConfig);
        updateQuotesCard021A(currentQuotesSummary021A);
        const count = overlay.querySelector("[data-quotes-summary-count]");
        const total = overlay.querySelector("[data-quotes-summary-total]");
        if (count) count.textContent = String(currentQuotesSummary021A.active_count || 0);
        if (total) total.textContent = quoteMoney021A(currentQuotesSummary021A.total_amount || 0);
      } catch (error) {
        console.warn("No fue posible cargar resumen de cotizaciones", error);
      }
    }

    async function refreshList() {
      if (!listBox) return;
      listBox.innerHTML = `<div class="mp-quotes-empty-021a">Cargando cotizaciones...</div>`;
      try {
        const q = search?.value || "";
        const documentType = typeFilter?.value || "";
        const data = await quotesApi021A(`?q=${encodeURIComponent(q)}&document_type=${encodeURIComponent(documentType)}`);
        listBox.innerHTML = renderQuotesList021A(Array.isArray(data.items) ? data.items : []);
      } catch (error) {
        listBox.innerHTML = `<div class="mp-quotes-empty-021a">No fue posible cargar cotizaciones: ${h(error.message || "error")}</div>`;
      }
    }

    overlay.querySelectorAll("[data-quotes-close]").forEach((button) => {
      button.addEventListener("click", () => overlay.remove());
    });

    overlay.addEventListener("input", (event) => {
      if (event.target && event.target.matches("[data-quote-calc]")) {
        recalcQuoteTotals021A(form);
      }
    });

    overlay.addEventListener("change", (event) => {
      const target = event.target;
      if (target instanceof HTMLElement && target.matches("[data-quote-reference-select]")) {
        applyQuoteReference021C(target);
        recalcQuoteTotals021A(form);
      }
    });

    overlay.querySelector("[data-add-quote-item]")?.addEventListener("click", () => {
      const box = overlay.querySelector("[data-quote-items]");
      if (box) {
        box.insertAdjacentHTML("beforeend", renderQuoteItemRow021A());
        recalcQuoteTotals021A(form);
      }
    });

    overlay.addEventListener("click", async (event) => {
      const target = event.target;
      if (!(target instanceof HTMLElement)) return;

      if (target.matches("[data-remove-quote-item]")) {
        const rows = overlay.querySelectorAll("[data-quote-item-row]");
        if (rows.length > 1) {
          target.closest("[data-quote-item-row]")?.remove();
          recalcQuoteTotals021A(form);
        }
        return;
      }

      if (target.matches("[data-reset-quote]")) {
        resetQuoteForm021A(form, state);
        setMsg("");
        return;
      }

      if (target.matches("[data-quotes-refresh]")) {
        await refreshList();
        return;
      }

      const detailId = target.getAttribute("data-quote-detail");
      if (detailId) {
        try {
          const data = await quotesApi021A(`/${encodeURIComponent(detailId)}`);
          fillQuoteForm021A(form, data.quote, state);
          setMsg("Cotización cargada en el formulario.", true);
        } catch (error) {
          setMsg(error.message || "No fue posible cargar el detalle.", false);
        }
        return;
      }

      const pdfId = target.getAttribute("data-quote-pdf");
      if (pdfId) {
        try {
          target.disabled = true;
          await downloadQuotePdf021A(pdfId, target.getAttribute("data-quote-number") || "cotizacion", target.getAttribute("data-quote-doc-type") || "quote");
        } catch (error) {
          setMsg(error.message || "No fue posible generar PDF.", false);
        } finally {
          target.disabled = false;
        }
        return;
      }

      const archiveId = target.getAttribute("data-quote-archive");
      if (archiveId) {
        if (!confirm("¿Archivar esta cotización?")) return;
        try {
          await quotesApi021A(`/${encodeURIComponent(archiveId)}/archive`, { method: "POST" });
          await refreshSummary();
          await refreshList();
          setMsg("Cotización archivada.", true);
        } catch (error) {
          setMsg(error.message || "No fue posible archivar.", false);
        }
        return;
      }

      const convertId = target.getAttribute("data-quote-convert");
      if (convertId) {
        try {
          const converted = await quotesApi021A(`/${encodeURIComponent(convertId)}/convert`, { method: "POST" });
          const convertedQuote = converted.quote || {};
          await refreshSummary();
          await refreshList();
          setMsg("Cuenta de cobro generada. Descargando PDF...", true);
          await downloadQuotePdf021A(convertId, quoteDisplayNumber021B(convertedQuote, "account"), "account");
        } catch (error) {
          setMsg(error.message || "No fue posible pasar a cuenta de cobro.", false);
        }
      }
    });

    search?.addEventListener("keydown", async (event) => {
      if (event.key === "Enter") {
        event.preventDefault();
        await refreshList();
      }
    });

    typeFilter?.addEventListener("change", async () => {
      await refreshList();
    });

    form?.addEventListener("submit", async (event) => {
      event.preventDefault();
      setMsg("Guardando cotización...", true);

      try {
        const payload = {
          ...quotePayloadFromForm021A(form, state.signatureData),
          ...storeActorPayload023W()
        };
        const method = state.editingId ? "PATCH" : "POST";
        const path = state.editingId ? `/${encodeURIComponent(state.editingId)}` : "";
        const data = await quotesApi021A(path, {
          method,
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload)
        });

        const quote = data.quote || {};
        setMsg(`Cotización ${quote.quote_number || ""} guardada.`, true);
        resetQuoteForm021A(form, state);
        await refreshSummary();
        await refreshList();
      } catch (error) {
        setMsg(error.message || "No fue posible guardar la cotización.", false);
      }
    });

    recalcQuoteTotals021A(form);
    await refreshSummary();
    await refreshList();
  }
  /* CLONEXA_021A_QUOTES_MODULE_END */

  function clearTimer() {
    if (timerHandle) {
      window.clearInterval(timerHandle);
      timerHandle = null;
    }
    if (storeTeamTimer023W) {
      window.clearInterval(storeTeamTimer023W);
      storeTeamTimer023W = null;
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

        sessionStorage.setItem(storageKey, data.access_token);
        localStorage.removeItem(legacyStorageKey024B);
        sessionStorage.setItem("clonexa_mini_panel_current_session_024B", JSON.stringify({
          company_id: companyId,
          type: panelType,
          user_id: data?.user?.id || data?.mini_panel_user?.id || "",
          employee_id: data?.mini_panel?.employee_id || data?.employee?.id || data?.mini_panel_user?.employee_id || "",
          username: data?.mini_panel?.username || data?.mini_panel_user?.username || "",
          at: new Date().toISOString()
        }));
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
    "call": "call_center",
    "calls": "call_center",
    "call_center": "call_center",
    "callcenter": "call_center",
    "llamadas": "call_center",
    "transport_calls": "call_center",
    "external": "external",
    "externo": "external",
    "externos": "external",
    "other": "other"
  };

  const MODULE_DEFS_019H = {
    "cotizacion": { title: "Cotizaciones", description: "Crear cotizaciones para clientes.", tag: "COT" },
    "cotizaciones": { title: "Cotizaciones", description: "Crear cotizaciones para clientes.", tag: "COT" },
    "quote": { title: "Cotizaciones", description: "Crear cotizaciones para clientes.", tag: "COT" },
    "quotes": { title: "Cotizaciones", description: "Crear cotizaciones para clientes.", tag: "COT" },
    "transport_quotes_tickets": { title: "Cotizaciones / Tickets", description: "Crear ordenes de servicio y revisar checks por rol.", tag: "TKT" },
    "transport_tickets": { title: "Cotizaciones / Tickets", description: "Crear ordenes de servicio y revisar checks por rol.", tag: "TKT" },
    "cotizaciones_tickets": { title: "Cotizaciones / Tickets", description: "Crear ordenes de servicio y revisar checks por rol.", tag: "TKT" },
    "tickets_cotizaciones": { title: "Cotizaciones / Tickets", description: "Crear ordenes de servicio y revisar checks por rol.", tag: "TKT" },
    "transport_payments": { title: "Tesoreria / Pagos", description: "Revisar checks, pagos y facturacion de tickets.", tag: "TES" },
    "notas_agenda": { title: "Notas / Agenda", description: "Notas, eventos y recordatorios operativos.", tag: "NOT" },
    "notas_o_agenda": { title: "Notas / Agenda", description: "Notas, eventos y recordatorios operativos.", tag: "NOT" },
    "notes": { title: "Notas / Agenda", description: "Notas, eventos y recordatorios operativos.", tag: "NOT" },
    "notas": { title: "Notas / Agenda", description: "Notas, eventos y recordatorios operativos.", tag: "NOT" },

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
    "request": { title: "Solicitudes", description: "Crear y consultar solicitudes operativas.", tag: "REQ" },
    "solicitudes": { title: "Solicitudes", description: "Crear y consultar solicitudes operativas.", tag: "REQ" },
    "solicitud": { title: "Solicitudes", description: "Crear y consultar solicitudes operativas.", tag: "REQ" },
    "store_shift_control": { title: "Control de turno", description: "Inicio, pausas y cierre para nomina.", tag: "LOG" },
    "login": { title: "Control de turno", description: "Inicio, pausas y cierre para nomina.", tag: "LOG" },
    "control_turno": { title: "Control de turno", description: "Inicio, pausas y cierre para nomina.", tag: "LOG" },
    "turnos": { title: "Control de turno", description: "Inicio, pausas y cierre para nomina.", tag: "LOG" },
    "stores": { title: "Tiendas", description: "Operación asignada a tiendas.", tag: "STR" },
    "inventory": { title: "Inventario", description: "Consultar y registrar movimientos de inventario.", tag: "INV" },
    "materials": { title: "Materiales", description: "Gestionar materiales asignados.", tag: "MAT" },
    "reports": { title: "Reportes", description: "Consultar reportes operativos asignados.", tag: "REP" },
    "workforce": { title: "Personal", description: "Consultar personal operativo asignado.", tag: "WRK" },
    "gps": { title: "GPS", description: "Consultar ubicación y control operativo.", tag: "GPS" },
    "crm": { title: "CRM Campo", description: "Consultar operación en campo.", tag: "CRM" },
    "field": { title: "Operación en campo", description: "Consultar actividades en campo.", tag: "FLD" },
    "cal": { title: "Call Center / Llamadas", description: "Registrar llamadas, rutas, cotizaciones y tickets.", tag: "CALL" },
    "transport_calls": { title: "Call Center / Llamadas", description: "Registrar llamadas, rutas, cotizaciones y tickets.", tag: "CALL" },
    "transport_call": { title: "Call Center / Llamadas", description: "Registrar llamadas, rutas, cotizaciones y tickets.", tag: "CALL" },
    "call_center": { title: "Call Center / Llamadas", description: "Registrar llamadas, rutas, cotizaciones y tickets.", tag: "CALL" },
    "call_center_llamada": { title: "Call Center / Llamadas", description: "Registrar llamadas, rutas, cotizaciones y tickets.", tag: "CALL" },
    "call_center_llamadas": { title: "Call Center / Llamadas", description: "Registrar llamadas, rutas, cotizaciones y tickets.", tag: "CALL" },
    "callcenter": { title: "Call Center / Llamadas", description: "Registrar llamadas, rutas, cotizaciones y tickets.", tag: "CALL" },
    "call": { title: "Call Center / Llamadas", description: "Registrar llamadas, rutas, cotizaciones y tickets.", tag: "CALL" },
    "calls": { title: "Call Center / Llamadas", description: "Registrar llamadas, rutas, cotizaciones y tickets.", tag: "CALL" },
    "llamada": { title: "Call Center / Llamadas", description: "Registrar llamadas, rutas, cotizaciones y tickets.", tag: "CALL" },
    "llamadas": { title: "Call Center / Llamadas", description: "Registrar llamadas, rutas, cotizaciones y tickets.", tag: "CALL" },
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

  // CLONEXA_022A_HIERARCHY_SOURCE_OF_TRUTH_START
  // Canonicaliza alias para que un módulo exista una sola vez por panel.
  // Importante: Mini Panel NO hereda automáticamente módulos activos de empresa.
  // Solo renderiza los módulos asignados explícitamente a su panel_type.
  const MODULE_ALIAS_CANONICAL_022A = {
    "cotizacion": "cotizacion",
    "cotizaciones": "cotizacion",
    "cotizar": "cotizacion",
    "quote": "cotizacion",
    "quotes": "cotizacion",
    "quotation": "cotizacion",
    "quotations": "cotizacion",
    "presupuesto": "cotizacion",
    "presupuestos": "cotizacion",
    "transport_quotes_tickets": "transport_quotes_tickets",
    "transport_tickets": "transport_quotes_tickets",
    "cotizaciones_tickets": "transport_quotes_tickets",
    "tickets_cotizaciones": "transport_quotes_tickets",
    "cotizacion_ticket": "transport_quotes_tickets",
    "cotizacion_tickets": "transport_quotes_tickets",
    "quotes_tickets": "transport_quotes_tickets",
    "quote_ticket": "transport_quotes_tickets",
    "ticket_quote": "transport_quotes_tickets",
    "ticket_quotes": "transport_quotes_tickets",
    "tickets": "transport_quotes_tickets",
    "transport_payments": "transport_payments",
    "tesoreria": "transport_payments",
    "pagos": "transport_payments",
    "facturacion": "transport_payments",
    "nota": "notas",
    "notas": "notas",
    "notes": "notas",
    "agenda": "notas",
    "recordatorio": "notas",
    "recordatorios": "notas",
    "notas_agenda": "notas",
    "notas_o_agenda": "notas",

    "registro_venta": "registro_venta",
    "registro_ventas": "registro_venta",
    "sales_register": "registro_venta",

    "cierre_dia": "day_closing",
    "cierre_de_dia": "day_closing",
    "day_closing": "day_closing",
    "commercial_closing": "day_closing",

    "request": "requests",
    "requests": "requests",
    "solicitud": "requests",
    "solicitudes": "requests",
    "stock_request": "requests",
    "stock_requests": "requests",

    "login": "store_shift_control",
    "control_turno": "store_shift_control",
    "control_de_turno": "store_shift_control",
    "turno": "store_shift_control",
    "turnos": "store_shift_control",
    "shift": "store_shift_control",
    "shift_control": "store_shift_control",
    "store_shift": "store_shift_control",
    "store_shift_control": "store_shift_control",

    "cal": "transport_calls",
    "call": "transport_calls",
    "calls": "transport_calls",
    "call_center": "transport_calls",
    "callcenter": "transport_calls",
    "call_center_llamada": "transport_calls",
    "call_center_llamadas": "transport_calls",
    "llamada": "transport_calls",
    "llamadas": "transport_calls",
    "transport_call": "transport_calls",
    "transport_calls": "transport_calls"
  };

  function canonicalModuleCode022A(value) {
    const normalized = normalizeModuleCode019H(value);
    return MODULE_ALIAS_CANONICAL_022A[normalized] || normalized;
  }
  // CLONEXA_022A_HIERARCHY_SOURCE_OF_TRUTH_END

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
      .map((code) => canonicalModuleCode022A(code))
      .filter(Boolean)
      .filter((code, index, arr) => arr.indexOf(code) === index);
  }

  /* CLONEXA_022A_MINIPANEL_STRICT_ASSIGNMENT_START */
  function activeUniversalModuleCodes021D(_companyModules) {
    // 022A: módulo activo en empresa = capacidad disponible, NO asignación automática al mini panel.
    // Se conserva la función por compatibilidad con patches previos, pero no agrega módulos heredados.
    return [];
  }

  function mergeUniversalMiniPanelCodes021D(panelCodes, _companyModules) {
    const base = Array.isArray(panelCodes) ? panelCodes : [];
    return base
      .map((code) => canonicalModuleCode022A(code))
      .filter(Boolean)
      .filter((code, index, arr) => arr.indexOf(code) === index);
  }
  /* CLONEXA_022A_MINIPANEL_STRICT_ASSIGNMENT_END */

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

      const effectiveCodes022A = mergeUniversalMiniPanelCodes021D(codes, data);

      return {
        enabled: config.enabled === true || panel.enabled === true || effectiveCodes022A.length > 0,
        selected_panel: normalizePanelType019H(panelType),
        modules: effectiveCodes022A,
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
    const seen = new Set();

    return codes
      .map((code) => canonicalModuleCode022A(code))
      .filter((code) => {
        if (!code || seen.has(code)) return false;
        seen.add(code);
        return true;
      })
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
  /* CLONEXA_023W_STORE_TEAM_MINI_PANEL_START */
  const CX_STORE_SHIFT_CONTROL_CODES_023W = new Set([
    "store_shift_control",
    "login",
    "control_turno",
    "control_de_turno",
    "turno",
    "turnos",
    "shift",
    "shift_control",
    "store_shift"
  ]);

  function isStorePanel023W() {
    return normalizePanelType019H(panelType) === "store";
  }

  function isStoreShiftControlCode023W(code) {
    return CX_STORE_SHIFT_CONTROL_CODES_023W.has(canonicalModuleCode022A(code));
  }

  /* CLONEXA_024B_STORE_ADMIN_SESSION_ISOLATION_ACTOR_START */
  function storeActorKey023W() {
    const store = currentStoreTeam023W?.store || {};
    const slotId = String(store.id || store.store_id || store.store_slot_id || "store_current").trim() || "store_current";
    const adminId = String(store.admin_employee_id || store.current_employee_id || store.leader_employee_id || "current").trim() || "current";
    return `clonexa_store_actor_${companyId}_${panelType}_${slotId}_${adminId}`;
  }
  /* CLONEXA_024B_STORE_ADMIN_SESSION_ISOLATION_ACTOR_END */

  function storeTeamAuthKey023W(employeeId) {
    return `clonexa_store_member_auth_${companyId}_${panelType}_${employeeId}`;
  }

  function storeTeamStyles023W() {
    if (document.getElementById("cxStoreTeamStyles023W")) return;
    const style = document.createElement("style");
    style.id = "cxStoreTeamStyles023W";
    style.textContent = `
      .st-actor-023w{margin:16px 0;padding:16px;border:1px solid rgba(255,255,255,.14);border-radius:22px;background:rgba(255,255,255,.075);display:grid;grid-template-columns:minmax(220px,.55fr) minmax(260px,1fr);gap:12px;align-items:end}
      .st-actor-023w label{display:block;font-size:11px;font-weight:950;letter-spacing:.16em;text-transform:uppercase;color:rgba(255,255,255,.68);margin-bottom:7px}
      .st-actor-023w select{width:100%;box-sizing:border-box;border:1px solid rgba(255,255,255,.16);border-radius:16px;background:rgba(4,7,23,.72);color:#fff;padding:13px 14px;font-weight:900}
      .st-actor-023w small{display:block;color:rgba(255,255,255,.65);font-weight:800}
      .st-shell-023w{min-height:100vh;padding:28px;background:radial-gradient(circle at 8% 8%,rgba(255,35,187,.24),transparent 28%),radial-gradient(circle at 90% 12%,rgba(55,170,255,.20),transparent 30%),linear-gradient(135deg,#12091f,#071329 58%,#101326);color:#fff}
      .st-card-023w{border:1px solid rgba(255,255,255,.15);border-radius:28px;background:linear-gradient(145deg,rgba(255,255,255,.105),rgba(255,255,255,.045));box-shadow:0 28px 88px rgba(0,0,0,.36);backdrop-filter:blur(18px)}
      .st-hero-023w{padding:28px;margin-bottom:18px;display:flex;justify-content:space-between;gap:18px;align-items:flex-start}
      .st-kicker-023w{font-size:11px;font-weight:950;letter-spacing:.32em;text-transform:uppercase;color:#ff42d4}
      .st-title-023w{font-size:44px;line-height:1;margin:9px 0 8px;font-weight:950}
      .st-muted-023w{color:rgba(255,255,255,.70);font-weight:800}
      .st-btn-023w{border:0;border-radius:17px;padding:12px 16px;background:linear-gradient(135deg,#ff25bb,#7154ff);color:#fff;font-weight:950;cursor:pointer}
      .st-btn-023w.secondary{background:rgba(255,255,255,.11);border:1px solid rgba(255,255,255,.16)}
      .st-btn-023w.danger{background:rgba(255,70,125,.18);border:1px solid rgba(255,70,125,.38)}
      .st-grid-023w{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}
      .st-member-023w{padding:20px;display:grid;gap:14px}
      .st-member-head-023w{display:flex;justify-content:space-between;gap:12px;align-items:flex-start}
      .st-member-head-023w strong{font-size:22px}
      .st-pill-023w{display:inline-flex;border-radius:999px;padding:7px 10px;border:1px solid rgba(255,255,255,.15);background:rgba(255,255,255,.10);font-size:12px;font-weight:950}
      .st-pill-023w.admin{border-color:rgba(255,66,212,.36);background:rgba(255,66,212,.16)}
      .st-pill-023w.live{border-color:rgba(62,255,193,.35);background:rgba(62,255,193,.13);color:#9bffe4}
      .st-pill-023w.break{border-color:rgba(255,207,107,.35);background:rgba(255,207,107,.12);color:#ffe3a7}
      .st-metrics-023w{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px}
      .st-mini-023w{border:1px solid rgba(255,255,255,.10);border-radius:16px;background:rgba(0,0,0,.18);padding:12px}
      .st-mini-023w span{display:block;font-size:10px;font-weight:950;letter-spacing:.12em;text-transform:uppercase;color:rgba(255,255,255,.58)}
      .st-mini-023w strong{display:block;margin-top:5px}
      .st-progress-023w{height:9px;border-radius:999px;background:rgba(0,0,0,.28);overflow:hidden}
      .st-progress-023w i{display:block;height:100%;border-radius:inherit;background:linear-gradient(90deg,#ff25bb,#55e6ff)}
      .st-login-023w{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr) auto;gap:10px;align-items:end}
      .st-field-023w label{display:block;font-size:11px;font-weight:950;letter-spacing:.12em;text-transform:uppercase;color:rgba(255,255,255,.62);margin-bottom:7px}
      .st-field-023w input{width:100%;box-sizing:border-box;border:1px solid rgba(255,255,255,.15);border-radius:15px;background:rgba(4,7,23,.66);color:#fff;padding:12px 13px;font-weight:850}
      .st-actions-023w{display:flex;gap:10px;flex-wrap:wrap}
      .st-msg-023w{font-weight:900;color:#8fffd8}
      @media(max-width:980px){.st-grid-023w,.st-actor-023w,.st-login-023w{grid-template-columns:1fr}.st-title-023w{font-size:36px}.st-metrics-023w{grid-template-columns:1fr}}
    `;
    document.head.appendChild(style);
  }

  function normalizeStoreTeam023W(data) {
    const team = data && data.team ? data.team : data;
    const members = Array.isArray(team?.members) ? team.members : [];
    return {
      ...(team || {}),
      members: members.map((member) => ({
        ...member,
        session: member.session ? { ...member.session, _synced_at: Date.now() } : null
      }))
    };
  }

  async function loadStoreTeam023W(force = false) {
    if (!isStorePanel023W()) return null;
    if (currentStoreTeam023W && !force) return currentStoreTeam023W;
    const data = await api(`/api/v1/companies/${encodeURIComponent(companyId)}/mini-panel-store-team?panel_type=${encodeURIComponent(panelType)}`, {
      headers: authHeaders()
    });
    currentStoreTeam023W = normalizeStoreTeam023W(data);
    const members = Array.isArray(currentStoreTeam023W.members) ? currentStoreTeam023W.members : [];
    const saved = sessionStorage.getItem(storeActorKey023W()) || "";
    const fallback = members.find((item) => item.is_current)?.employee_id || members[0]?.employee_id || "";
    selectedStoreEmployee023W = members.some((item) => item.employee_id === saved) ? saved : fallback;
    if (selectedStoreEmployee023W) sessionStorage.setItem(storeActorKey023W(), selectedStoreEmployee023W);
    return currentStoreTeam023W;
  }

  function selectedStoreMember023W() {
    const members = Array.isArray(currentStoreTeam023W?.members) ? currentStoreTeam023W.members : [];
    return members.find((item) => item.employee_id === selectedStoreEmployee023W) || members.find((item) => item.is_current) || members[0] || null;
  }

  function storeActorPayload023W() {
    if (!isStorePanel023W()) return {};
    const member = selectedStoreMember023W();
    if (!member) return {};
    const store = currentStoreTeam023W?.store || {};
    return {
      store_employee_id: member.employee_id || "",
      store_employee_name: member.full_name || "",
      store_user_id: member.user_id || "",
      store_slot_id: store.id || "",
      store_slot_name: store.name || ""
    };
  }

  function storeActorStripHtml023W(context = "module") {
    if (!isStorePanel023W()) return "";
    storeTeamStyles023W();
    const team = currentStoreTeam023W || {};
    const members = Array.isArray(team.members) ? team.members : [];
    if (!members.length) return "";
    const selectedId = selectedStoreEmployee023W || members.find((item) => item.is_current)?.employee_id || members[0]?.employee_id || "";
    const selected = members.find((item) => item.employee_id === selectedId) || members[0];
    const store = team.store || {};
    return `
      <section class="st-actor-023w" data-store-actor-shell-023w="${h(context)}">
        <div>
          <label>Colaborador del registro</label>
          <select data-store-actor-023w>
            ${members.map((member) => `<option value="${h(member.employee_id)}" ${member.employee_id === selectedId ? "selected" : ""}>${h(member.full_name || "Colaborador")}${member.is_admin ? " - admin tienda" : ""}</option>`).join("")}
          </select>
        </div>
        <small>
          Tienda: ${h(store.name || "Tienda actual")}<br>
          Los registros de este modulo quedaran asignados a ${h(selected?.full_name || "el colaborador seleccionado")}.
        </small>
      </section>
    `;
  }

  function bindStoreActorSelector023W(scope = root) {
    const host = scope || root || document;
    host.querySelectorAll("[data-store-actor-023w]").forEach((select) => {
      if (select.dataset.storeActorBound023w === "1") return;
      select.dataset.storeActorBound023w = "1";
      select.addEventListener("change", () => {
        selectedStoreEmployee023W = select.value || "";
        if (selectedStoreEmployee023W) sessionStorage.setItem(storeActorKey023W(), selectedStoreEmployee023W);
      });
    });
  }

  function storeMemberAuthenticated023W(member) {
    return Boolean(member?.is_current || sessionStorage.getItem(storeTeamAuthKey023W(member?.employee_id || "")) === "1");
  }

  function storeTeamLiveValue023W(member, kind) {
    const session = member?.session || {};
    const base = Number(session[`${kind}_seconds`] || 0);
    const syncedAt = Number(session._synced_at || Date.now());
    const elapsed = Math.max(0, Math.floor((Date.now() - syncedAt) / 1000));
    if (kind === "active" && session.status === "active") return base + elapsed;
    if (kind === "break" && session.status === "break") return base + elapsed;
    return base;
  }

  function updateStoreTeamTimers023W() {
    root.querySelectorAll("[data-store-member-card-023w]").forEach((card) => {
      const employeeId = card.getAttribute("data-store-member-card-023w") || "";
      const member = (currentStoreTeam023W?.members || []).find((item) => item.employee_id === employeeId);
      const active = card.querySelector("[data-store-active-023w]");
      const pause = card.querySelector("[data-store-break-023w]");
      if (active) active.textContent = formatSeconds(storeTeamLiveValue023W(member, "active"));
      if (pause) pause.textContent = formatSeconds(storeTeamLiveValue023W(member, "break"));
    });
  }

  function startStoreTeamTimers023W() {
    if (storeTeamTimer023W) window.clearInterval(storeTeamTimer023W);
    updateStoreTeamTimers023W();
    storeTeamTimer023W = window.setInterval(updateStoreTeamTimers023W, 1000);
  }

  function storeMemberCard023W(member) {
    const session = member.session || {};
    const status = session.status || "closed";
    const authenticated = storeMemberAuthenticated023W(member);
    const goal = Number(member.monthly_goal || 0);
    const sales = Number(member.sales_total || 0);
    const pct = goal > 0 ? Math.min(100, Math.round((sales / goal) * 100)) : 0;
    const statusLabel = status === "break" ? "En pausa" : (status === "active" ? "Activo" : "Sin turno");
    const canStart = authenticated && status !== "active" && status !== "break";
    const canPause = authenticated && status === "active";
    const canResume = authenticated && status === "break";
    const canFinish = authenticated && (status === "active" || status === "break");
    return `
      <article class="st-card-023w st-member-023w" data-store-member-card-023w="${h(member.employee_id)}">
        <div class="st-member-head-023w">
          <div>
            <strong>${h(member.full_name || "Colaborador")}</strong>
            <div class="st-muted-023w">${h(member.role || "cajero")} ${member.phone ? `- ${h(member.phone)}` : ""}</div>
          </div>
          <div style="display:flex;gap:8px;flex-wrap:wrap;justify-content:flex-end">
            ${member.is_admin ? `<span class="st-pill-023w admin">Admin tienda</span>` : ""}
            <span class="st-pill-023w ${status === "break" ? "break" : (status === "active" ? "live" : "")}">${h(statusLabel)}</span>
          </div>
        </div>

        <div class="st-metrics-023w">
          <div class="st-mini-023w"><span>Activo</span><strong data-store-active-023w>${h(formatSeconds(session.active_seconds || 0))}</strong></div>
          <div class="st-mini-023w"><span>Pausa</span><strong data-store-break-023w>${h(formatSeconds(session.break_seconds || 0))}</strong></div>
          <div class="st-mini-023w"><span>Ventas/meta</span><strong>${h(formatMoney(sales))} / ${h(formatMoney(goal))}</strong></div>
        </div>
        <div class="st-progress-023w"><i style="width:${pct}%"></i></div>
        <div class="st-muted-023w">${h(pct)}% de cumplimiento - ${h(member.sales_count || 0)} venta(s)</div>

        ${member.has_login ? (authenticated ? `
          <div class="st-actions-023w">
            <button class="st-btn-023w" type="button" data-store-action-023w="start" data-store-employee-023w="${h(member.employee_id)}" ${canStart ? "" : "disabled"}>Inicio de turno</button>
            <button class="st-btn-023w secondary" type="button" data-store-action-023w="pause" data-store-employee-023w="${h(member.employee_id)}" ${canPause ? "" : "disabled"}>Pausa</button>
            <button class="st-btn-023w secondary" type="button" data-store-action-023w="resume" data-store-employee-023w="${h(member.employee_id)}" ${canResume ? "" : "disabled"}>Retorno</button>
            <button class="st-btn-023w danger" type="button" data-store-action-023w="finish" data-store-employee-023w="${h(member.employee_id)}" ${canFinish ? "" : "disabled"}>Finalizar turno</button>
          </div>
        ` : `
          <div class="st-login-023w">
            <div class="st-field-023w"><label>Usuario</label><input data-store-login-user-023w value="${h(member.username || "")}" placeholder="usuario tienda"></div>
            <div class="st-field-023w"><label>Clave</label><input data-store-login-pass-023w type="password" placeholder="Clave del colaborador"></div>
            <button class="st-btn-023w" type="button" data-store-login-023w="${h(member.employee_id)}">Ingresar login</button>
          </div>
        `) : `<div class="st-msg-023w">Genera la clave de este colaborador desde el modulo Login tiendas.</div>`}
      </article>
    `;
  }

  async function storeTeamLogin023W(employeeId, username, password) {
    const data = await api(`/api/v1/companies/${encodeURIComponent(companyId)}/mini-panel-store-team/${encodeURIComponent(employeeId)}/login?panel_type=${encodeURIComponent(panelType)}`, {
      method: "POST",
      headers: { ...authHeaders(), "Content-Type": "application/json" },
      body: JSON.stringify({ username, password })
    });
    sessionStorage.setItem(storeTeamAuthKey023W(employeeId), "1");
    currentStoreTeam023W = normalizeStoreTeam023W(data.team || data);
    return currentStoreTeam023W;
  }

  async function storeTeamAction023W(employeeId, action, options = {}) {
    const params = new URLSearchParams({ panel_type: panelType });
    if (options.cascadeTeam) params.set("cascade_team", "1");
    const data = await api(`/api/v1/companies/${encodeURIComponent(companyId)}/mini-panel-store-team/${encodeURIComponent(employeeId)}/session/${encodeURIComponent(action)}?${params.toString()}`, {
      method: "POST",
      headers: authHeaders()
    });
    currentStoreTeam023W = normalizeStoreTeam023W(data.team || data);
    return data;
  }

  async function openStoreShiftControlModule023W(session) {
    storeTeamStyles023W();
    const msgId = "storeTeamMsg023W";
    let loadError = "";
    try {
      await loadStoreTeam023W(true);
    } catch (error) {
      loadError = error.message || "No se pudo cargar el equipo de tienda.";
      currentStoreTeam023W = { store: {}, members: [] };
    }
    const store = currentStoreTeam023W?.store || {};
    const members = Array.isArray(currentStoreTeam023W?.members) ? currentStoreTeam023W.members : [];
    root.innerHTML = `
      <main class="st-shell-023w">
        <header class="st-card-023w st-hero-023w">
          <div>
            <div class="st-kicker-023w">Control de turno</div>
            <h1 class="st-title-023w">${h(store.name || "Tienda")}</h1>
            <p class="st-muted-023w">Loguea colaboradores, controla pausas y envia tiempos a CRM Campo y Nomina.</p>
          </div>
          <div class="st-actions-023w">
            <button class="st-btn-023w secondary" type="button" data-store-refresh-023w>Actualizar</button>
            <button class="st-btn-023w secondary" type="button" data-store-back-023w>Dashboard</button>
          </div>
        </header>
        ${storeActorStripHtml023W("turnos")}
        <section class="st-grid-023w">
          ${members.map(storeMemberCard023W).join("") || `<div class="st-card-023w st-member-023w">No hay colaboradores asignados a esta tienda desde Login tiendas.</div>`}
        </section>
        <div class="st-msg-023w" id="${msgId}">${h(loadError)}</div>
      </main>
    `;
    bindStoreActorSelector023W();
    startStoreTeamTimers023W();

    root.querySelector("[data-store-back-023w]")?.addEventListener("click", () => bootShell());
    root.querySelector("[data-store-refresh-023w]")?.addEventListener("click", () => openStoreShiftControlModule023W(session));
    root.querySelectorAll("[data-store-login-023w]").forEach((button) => {
      button.addEventListener("click", async () => {
        const employeeId = button.getAttribute("data-store-login-023w") || "";
        const card = button.closest("[data-store-member-card-023w]");
        const username = card?.querySelector("[data-store-login-user-023w]")?.value || "";
        const password = card?.querySelector("[data-store-login-pass-023w]")?.value || "";
        const msg = root.querySelector(`#${msgId}`);
        try {
          if (msg) msg.textContent = "Validando login...";
          await storeTeamLogin023W(employeeId, username, password);
          await openStoreShiftControlModule023W(session);
        } catch (error) {
          if (msg) msg.textContent = error.message || "Login invalido.";
        }
      });
    });
    root.querySelectorAll("[data-store-action-023w]").forEach((button) => {
      button.addEventListener("click", async () => {
        const employeeId = button.getAttribute("data-store-employee-023w") || "";
        const action = button.getAttribute("data-store-action-023w") || "";
        const member = members.find((item) => item.employee_id === employeeId) || {};
        const msg = root.querySelector(`#${msgId}`);
        try {
          if (msg) msg.textContent = "Actualizando turno...";
          await storeTeamAction023W(employeeId, action);
          if (action === "finish" && member.is_admin) {
            clearMiniPanelToken024B();
            window.location.href = loginUrl();
            return;
          }
          await openStoreShiftControlModule023W(session);
        } catch (error) {
          if (msg) msg.textContent = error.message || "No se pudo actualizar el turno.";
        }
      });
    });
  }
  /* CLONEXA_023W_STORE_TEAM_MINI_PANEL_END */

  /* CLONEXA_028L_TRANSPORT_CALLS_MINIPANEL_START */
  const CX_TRANSPORT_CALL_CODES_028L = new Set([
    "transport_calls",
    "call_center",
    "callcenter",
    "llamadas",
    "llamada",
    "calls",
    "call"
  ]);

  const TRANSPORT_CITIES_CO_028L = [
    "Bogota D.C.",
    "Medellin",
    "Cali",
    "Barranquilla",
    "Cartagena",
    "Cucuta",
    "Bucaramanga",
    "Pereira",
    "Santa Marta",
    "Ibague",
    "Manizales",
    "Pasto",
    "Neiva",
    "Villavicencio",
    "Armenia",
    "Monteria",
    "Sincelejo",
    "Valledupar",
    "Popayan",
    "Tunja",
    "Riohacha",
    "Quibdo",
    "Florencia",
    "Yopal",
    "Arauca",
    "Mocoa",
    "San Andres",
    "Leticia",
    "Inirida",
    "Puerto Carreno",
    "Mitu",
    "Soacha",
    "Bello",
    "Itagui",
    "Envigado",
    "Rionegro",
    "Dosquebradas",
    "Palmira",
    "Buenaventura",
    "Tulua",
    "Buga",
    "Cartago",
    "Jamundi",
    "Yumbo",
    "Chia",
    "Cajica",
    "Zipaquira",
    "Fusagasuga",
    "Facatativa",
    "Madrid",
    "Mosquera",
    "Funza",
    "Cota",
    "Girardot",
    "Duitama",
    "Sogamoso",
    "Floridablanca",
    "Giron",
    "Piedecuesta",
    "Barrancabermeja",
    "Ocana",
    "Pamplona",
    "Soledad",
    "Malambo",
    "Apartado",
    "Turbo",
    "Caucasia",
    "Magangue",
    "Cerete",
    "Sahagun",
    "Lorica",
    "Aguachica",
    "Ipiales",
    "Tumaco",
    "Santander de Quilichao",
    "Pitalito",
    "Garzon",
    "La Dorada",
    "Honda",
    "Espinal",
    "Melgar",
    "Mariquita",
    "Acacias",
    "Granada",
    "Aguazul"
  ];

  function isTransportCallsCode028L(code) {
    const normalized = normalizeModuleCode019H(code);
    return CX_TRANSPORT_CALL_CODES_028L.has(normalized);
  }

  async function transportCallsApi028L(path, options = {}) {
    if (!companyId) throw new Error("Falta company_id.");
    const headers = {
      ...authHeaders(),
      ...(options.headers || {})
    };
    if (options.body && !headers["Content-Type"]) {
      headers["Content-Type"] = "application/json";
    }
    return api(`/api/v1/transport-calls/companies/${encodeURIComponent(companyId)}${path}`, {
      ...options,
      headers
    });
  }

  async function transportTelephonyApi029A(path, options = {}) {
    if (!companyId) throw new Error("Falta company_id.");
    const headers = { ...authHeaders(), ...(options.headers || {}) };
    if (options.body && !headers["Content-Type"]) headers["Content-Type"] = "application/json";
    return api(`/api/v1/transport-telephony/companies/${encodeURIComponent(companyId)}${path}`, {
      ...options,
      headers
    });
  }

  function transportCallsStyles028L() {
    if (document.getElementById("cxTransportCallsStyles028L")) return;
    const style = document.createElement("style");
    style.id = "cxTransportCallsStyles028L";
    style.textContent = `
      .tc-card-028l{width:min(1180px,calc(100vw - 28px));max-height:calc(100vh - 28px);overflow:auto}
      .tc-head-028l{display:flex;justify-content:space-between;gap:14px;align-items:flex-start;margin-bottom:18px}
      .tc-head-028l h2{margin:6px 0 6px;font-size:34px;line-height:1}
      .tc-head-028l p{margin:0;color:rgba(255,255,255,.68);font-weight:800}
      .tc-advisor-kpis-028l{display:grid;grid-template-columns:1.4fr repeat(4,minmax(120px,1fr));gap:10px;margin:0 0 16px}
      .tc-advisor-kpis-028l article{min-height:78px;border:1px solid rgba(255,255,255,.12);border-radius:18px;background:rgba(255,255,255,.06);padding:13px}
      .tc-advisor-kpis-028l span{display:block;margin-bottom:7px;color:rgba(255,255,255,.58);font-size:10px;letter-spacing:.12em;text-transform:uppercase;font-weight:950}
      .tc-advisor-kpis-028l strong{display:block;font-size:22px;line-height:1;color:#fff}
      .tc-advisor-kpis-028l small{display:block;margin-top:7px;color:rgba(255,255,255,.62);font-weight:800}
      .tc-grid-028l{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px}
      .tc-grid-028l .wide{grid-column:span 2}
      .tc-grid-028l .full{grid-column:1/-1}
      .tc-field-028l label{display:block;margin:0 0 7px;font-size:11px;letter-spacing:.14em;text-transform:uppercase;font-weight:950;color:rgba(255,255,255,.66)}
      .tc-field-028l input,.tc-field-028l select,.tc-field-028l textarea{width:100%;box-sizing:border-box;border:1px solid rgba(255,255,255,.15);border-radius:16px;background:rgba(4,7,23,.72);color:#fff;padding:13px 14px;font-weight:850;outline:none}
      .tc-field-028l input[readonly]{color:#8fffd8;border-color:rgba(63,255,190,.28);background:rgba(63,255,190,.08)}
      .tc-checks-028l{display:flex;gap:14px;flex-wrap:wrap;align-items:center;margin:6px 0 0}
      .tc-checks-028l label{display:inline-flex;gap:8px;align-items:center;font-weight:950;color:#fff}
      .tc-actions-028l{display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin-top:16px}
      .tc-panel-028l{margin-top:18px;padding:16px;border:1px solid rgba(255,255,255,.13);border-radius:22px;background:rgba(255,255,255,.06)}
      .tc-panel-028l h3{margin:0 0 12px;font-size:20px}
      .tc-table-028l{width:100%;border-collapse:collapse;font-weight:800}
      .tc-table-028l th,.tc-table-028l td{padding:11px 10px;border-bottom:1px solid rgba(255,255,255,.09);text-align:left;vertical-align:top}
      .tc-table-028l th{font-size:10px;letter-spacing:.12em;text-transform:uppercase;color:rgba(255,255,255,.58)}
      .tc-chip-028l{display:inline-flex;border-radius:999px;padding:6px 9px;background:rgba(255,255,255,.11);border:1px solid rgba(255,255,255,.14);font-size:12px;font-weight:950}
      .tc-chip-028l.twilio{color:#8fffd8;border-color:rgba(63,255,190,.28);background:rgba(63,255,190,.10)}
      .tc-softphone-029a{grid-column:1/-1;display:grid;grid-template-columns:minmax(220px,1fr) repeat(3,auto);gap:10px;align-items:center;padding:14px;border:1px solid rgba(63,255,190,.28);border-radius:18px;background:rgba(63,255,190,.07)}
      .tc-softphone-state-029a span{display:block;color:rgba(255,255,255,.58);font-size:10px;letter-spacing:.12em;text-transform:uppercase;font-weight:950}
      .tc-softphone-state-029a strong{display:block;margin-top:5px;color:#8fffd8;font-size:18px}
      .tc-call-btn-029a{border:0;border-radius:14px;padding:12px 18px;font-weight:950;cursor:pointer;background:#28e889;color:#07140f}
      .tc-call-btn-029a.hangup{background:#ff4f87;color:#fff}
      .tc-call-btn-029a.secondary{background:rgba(255,255,255,.11);color:#fff;border:1px solid rgba(255,255,255,.15)}
      .tc-call-btn-029a:disabled{opacity:.45;cursor:not-allowed}
      .tc-monitor-card-028n{width:calc(100vw - 32px);height:calc(100vh - 32px);max-height:none;overflow:hidden;display:flex;flex-direction:column;padding:22px}
      .tc-monitor-card-028n .tc-head-028l{flex:0 0 auto;margin-bottom:12px}
      .tc-monitor-toolbar-028n{display:flex;gap:10px;flex-wrap:wrap;align-items:center;justify-content:space-between;margin:14px 0}
      .tc-monitor-kpis-028n{display:grid;grid-template-columns:repeat(8,minmax(118px,1fr));gap:10px;margin:8px 0 12px;flex:0 0 auto}
      .tc-monitor-kpi-028n{padding:12px;border:1px solid rgba(255,255,255,.12);border-radius:16px;background:rgba(255,255,255,.06);min-height:72px}
      .tc-monitor-kpi-028n span{display:block;margin-bottom:8px;color:rgba(255,255,255,.58);font-size:10px;letter-spacing:.12em;text-transform:uppercase;font-weight:950}
      .tc-monitor-kpi-028n strong{display:block;font-size:24px;line-height:1;color:#fff}
      .tc-monitor-kpi-028n.alert strong{color:#ff8ebd}
      .tc-monitor-settings-028n{display:grid;grid-template-columns:repeat(4,minmax(150px,1fr));gap:10px;align-items:end;margin:8px 0 12px;padding:12px;border:1px solid rgba(255,255,255,.10);border-radius:18px;background:rgba(255,255,255,.045);flex:0 0 auto}
      .tc-monitor-table-panel-028n{flex:1 1 auto;min-height:0;margin-top:0;display:flex;flex-direction:column}
      .tc-monitor-table-panel-028n h3{flex:0 0 auto}
      .tc-monitor-table-wrap-028n{flex:1 1 auto;min-height:0;overflow:auto;border-radius:18px;border:1px solid rgba(255,255,255,.08)}
      .tc-monitor-table-wrap-028n .tc-table-028l{min-width:1040px}
      .tc-monitor-table-wrap-028n thead th{position:sticky;top:0;z-index:2;background:rgba(22,20,47,.98);backdrop-filter:blur(10px)}
      .tc-monitor-table-wrap-028n tbody tr:nth-child(even){background:rgba(255,255,255,.025)}
      .tc-monitor-table-wrap-028n tbody tr:hover{background:rgba(41,255,187,.045)}
      .tc-monitor-status-028n{display:inline-flex;align-items:center;gap:7px;border-radius:999px;padding:7px 10px;font-size:12px;font-weight:950;border:1px solid rgba(255,255,255,.15);background:rgba(255,255,255,.10)}
      .tc-monitor-status-028n:before{content:"";width:8px;height:8px;border-radius:50%;background:rgba(255,255,255,.45)}
      .tc-monitor-status-028n.in_call{color:#8fffd8;border-color:rgba(63,255,190,.35);background:rgba(63,255,190,.12)}
      .tc-monitor-status-028n.in_call:before{background:#28ff92}
      .tc-monitor-status-028n.available{color:#b4ffcf;border-color:rgba(111,255,86,.28);background:rgba(111,255,86,.10)}
      .tc-monitor-status-028n.available:before{background:#67ff3f}
      .tc-monitor-status-028n.break{color:#ffd493;border-color:rgba(255,174,64,.30);background:rgba(255,174,64,.12)}
      .tc-monitor-status-028n.break:before{background:#ffb340}
      .tc-monitor-status-028n.offline{color:rgba(255,255,255,.62)}
      .tc-monitor-alerts-028n{display:flex;gap:6px;flex-wrap:wrap}
      .tc-monitor-alert-028n{display:inline-flex;border-radius:999px;padding:6px 8px;background:rgba(255,44,126,.14);border:1px solid rgba(255,44,126,.28);color:#ffc0d8;font-size:11px;font-weight:950}
      .tc-monitor-empty-028n{padding:24px;border:1px dashed rgba(255,255,255,.18);border-radius:18px;color:rgba(255,255,255,.68);font-weight:850}
      .tc-monitor-muted-028n{color:rgba(255,255,255,.58);font-size:12px;font-weight:850}
      @media(max-width:900px){.tc-grid-028l,.tc-advisor-kpis-028l{grid-template-columns:1fr}.tc-grid-028l .wide{grid-column:auto}.tc-head-028l{flex-direction:column}.tc-card-028l{width:calc(100vw - 18px)}.tc-softphone-029a{grid-template-columns:1fr 1fr}.tc-softphone-state-029a{grid-column:1/-1}}
      @media(max-width:1200px){.tc-monitor-kpis-028n{grid-template-columns:repeat(4,minmax(0,1fr))}}
      @media(max-width:900px){.tc-monitor-kpis-028n,.tc-monitor-settings-028n{grid-template-columns:1fr}.tc-monitor-card-028n{width:calc(100vw - 12px);height:calc(100vh - 12px);padding:14px}.tc-monitor-table-wrap-028n .tc-table-028l{min-width:940px}}
    `;
    document.head.appendChild(style);
  }

  function normalizeTransportLookup028L(value) {
    return String(value || "")
      .toLowerCase()
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .replace(/\s+/g, " ")
      .trim();
  }

  function transportToken028N(value) {
    return normalizeTransportLookup028L(value)
      .replace(/[^a-z0-9]+/g, "_")
      .replace(/^_+|_+$/g, "");
  }

  function transportRoleTokens028N(session) {
    const employee = session?.employee || {};
    const user = session?.user || {};
    const mini = session?.mini_panel || {};
    const source = [
      employee.role,
      employee.employee_type,
      user.role,
      mini.type,
      panelType
    ];
    const tokens = new Set();
    source.forEach((value) => {
      const token = transportToken028N(value);
      if (!token) return;
      tokens.add(token);
      tokens.add(token.replaceAll("_", ""));
      token.split("_").forEach((part) => {
        if (part) tokens.add(part);
      });
    });
    return tokens;
  }

  function transportCallsViewMode028N(session) {
    const tokens = transportRoleTokens028N(session);
    if (tokens.has("supervisor") || tokens.has("supervisora")) return "supervisor";
    const managementTokens = [
      "gerencia",
      "gerente",
      "manager",
      "admin",
      "admin_empresa",
      "adminempresa",
      "company_admin",
      "companyadmin",
      "tesoreria"
    ];
    return managementTokens.some((item) => tokens.has(item)) ? "management" : "advisor";
  }

  async function transportMonitorApi028N(path = "", options = {}) {
    if (!companyId) throw new Error("Falta company_id.");
    const suffix = `${path || ""}${String(path || "").includes("?") ? "&" : "?"}panel_type=${encodeURIComponent(panelType)}`;
    const headers = {
      ...authHeaders(),
      ...(options.headers || {})
    };
    if (options.body && !headers["Content-Type"]) {
      headers["Content-Type"] = "application/json";
    }
    return api(`/api/v1/companies/${encodeURIComponent(companyId)}/mini-panel-agent-monitor${suffix}`, {
      ...options,
      headers
    });
  }

  function transportMonitorStatusLabel028N(value) {
    const status = String(value || "offline").toLowerCase();
    if (status === "in_call") return "En llamada";
    if (status === "break") return "En pausa";
    if (status === "available") return "Disponible";
    return "Sin sesion";
  }

  function transportMonitorAlertLabel028N(value) {
    const reason = String(value || "");
    if (reason === "llamada_larga") return "Llamada larga";
    if (reason === "pausa_larga") return "Pausa larga";
    return reason || "Alerta";
  }

  function transportMonitorDate028N(value) {
    if (!value) return "-";
    return String(value).slice(0, 16).replace("T", " ");
  }

  function transportMonitorKpis028N(payload) {
    const summary = payload?.summary || {};
    const cards = [
      ["Agentes", summary.agents_total || 0, ""],
      ["Disponibles", summary.agents_available || 0, ""],
      ["En llamada", summary.agents_in_call || 0, ""],
      ["Pausa", summary.agents_paused || 0, ""],
      ["Alertas", summary.alerts || 0, "alert"],
      ["Llamadas hoy", summary.calls_today || 0, ""],
      ["Duracion hoy", formatSeconds(summary.duration_today || 0), ""],
      ["Tickets / cotiz.", `${Number(summary.tickets_today || 0)} / ${Number(summary.quotes_today || 0)}`, ""]
    ];
    return cards.map(([label, value, extra]) => `
      <article class="tc-monitor-kpi-028n ${h(extra)}">
        <span>${h(label)}</span>
        <strong>${h(value)}</strong>
      </article>
    `).join("");
  }

  function transportMonitorAgentRows028N(payload) {
    const agents = Array.isArray(payload?.agents) ? payload.agents : [];
    if (!agents.length) {
      return `<tr><td colspan="8"><div class="tc-monitor-empty-028n">No hay agentes activos para este segmento.</div></td></tr>`;
    }
    return agents.map((agent) => {
      const latest = agent.latest_call || {};
      const route = latest.origin || latest.destination ? `${latest.origin || "-"} -> ${latest.destination || "-"}` : "Sin ruta reciente";
      const alerts = Array.isArray(agent.alert_reasons) && agent.alert_reasons.length
        ? `<div class="tc-monitor-alerts-028n">${agent.alert_reasons.map((item) => `<span class="tc-monitor-alert-028n">${h(transportMonitorAlertLabel028N(item))}</span>`).join("")}</div>`
        : `<span class="tc-monitor-muted-028n">OK</span>`;
      const canForce = Boolean(agent.can_force_logout && agent.user_id);
      return `
        <tr>
          <td><strong>${h(agent.full_name || "Agente")}</strong><br><small>${h(agent.role || "rol sin definir")}${agent.username ? ` / ${h(agent.username)}` : ""}</small></td>
          <td><span class="tc-monitor-status-028n ${h(agent.live_status || "offline")}">${h(transportMonitorStatusLabel028N(agent.live_status))}</span></td>
          <td><strong>${h(formatSeconds(agent.current_call_seconds || 0))}</strong><br><small>${h(String(agent.call_status || "none") === "none" ? "Sin llamada" : transportCallStatusLabel028L(agent.call_status))}</small></td>
          <td>${h(formatSeconds(agent.active_seconds || 0))}</td>
          <td>${h(formatSeconds(agent.break_seconds || 0))}</td>
          <td><strong>${h(route)}</strong><br><small>${h(transportMonitorDate028N(latest.created_at || agent.last_seen_at))}</small></td>
          <td>${alerts}</td>
          <td>
            ${canForce ? `<button class="mp-button small danger" type="button" data-transport-force-logout="${h(agent.user_id)}">Desloguear</button>` : `<span class="tc-monitor-muted-028n">Solo lectura</span>`}
          </td>
        </tr>
      `;
    }).join("");
  }

  function transportMonitorSettingsHtml028N(settings = {}) {
    return `
      <form class="tc-monitor-settings-028n" data-transport-monitor-settings>
        <div class="tc-field-028l">
          <label>Alerta llamada min</label>
          <input name="call_alert_minutes" type="number" min="1" max="240" value="${h(settings.call_alert_minutes || 10)}" />
        </div>
        <div class="tc-field-028l">
          <label>Alerta pausa min</label>
          <input name="break_alert_minutes" type="number" min="1" max="240" value="${h(settings.break_alert_minutes || 15)}" />
        </div>
        <div class="tc-field-028l">
          <label>Inactividad min</label>
          <input name="idle_alert_minutes" type="number" min="1" max="240" value="${h(settings.idle_alert_minutes || 30)}" />
        </div>
        <button class="mp-button" type="submit">Guardar alertas</button>
      </form>
    `;
  }

  function transportMonitorBodyHtml028N(payload, viewMode) {
    const settings = payload?.settings || {};
    const title = viewMode === "management" ? "Panel gerencial de llamadas" : "Control de agentes";
    const subtitle = viewMode === "management"
      ? "Vision consolidada de llamadas, agentes, tickets y cotizaciones."
      : "Estados en vivo, duracion de llamada, pausas y cierre de sesiones pegadas.";
    return `
      <div class="tc-head-028l">
        <div>
          <div class="mp-kicker">${viewMode === "management" ? "Panel gerencial" : "Mini panel supervisor"}</div>
          <h2>${h(title)}</h2>
          <p>${h(subtitle)}</p>
        </div>
        <div class="tc-monitor-toolbar-028n">
          <button class="mp-button secondary" type="button" data-transport-monitor-refresh>Actualizar</button>
          <button class="mp-button secondary" type="button" data-transport-close>Cerrar</button>
        </div>
      </div>

      <div class="tc-monitor-kpis-028n">${transportMonitorKpis028N(payload)}</div>
      ${transportMonitorSettingsHtml028N(settings)}

      <section class="tc-panel-028l tc-monitor-table-panel-028n">
        <h3>${viewMode === "management" ? "Agentes y supervision" : "Agentes monitoreados"}</h3>
        <div class="tc-monitor-table-wrap-028n">
          <table class="tc-table-028l">
            <thead>
              <tr>
                <th>Agente</th>
                <th>Estado</th>
                <th>Llamada</th>
                <th>Activo</th>
                <th>Pausa</th>
                <th>Ultima gestion</th>
                <th>Alertas</th>
                <th>Acciones</th>
              </tr>
            </thead>
            <tbody>${transportMonitorAgentRows028N(payload)}</tbody>
          </table>
        </div>
      </section>
      <div class="mp-message ok" data-transport-monitor-message></div>
    `;
  }

  async function openTransportMonitorModule028N(session, viewMode) {
    transportCallsStyles028L();
    const overlay = document.createElement("div");
    overlay.className = "mp-modal";
    overlay.innerHTML = `
      <div class="mp-modal-backdrop" data-transport-close></div>
      <section class="mp-modal-card tc-monitor-card-028n" role="dialog" aria-modal="true" aria-label="Monitor Call Center">
        <div class="tc-panel-028l">Cargando monitor de agentes...</div>
      </section>
    `;
    document.body.appendChild(overlay);

    const card = overlay.querySelector(".tc-monitor-card-028n");
    let timer = null;
    let closed = false;

    const close = () => {
      closed = true;
      if (timer) window.clearInterval(timer);
      overlay.remove();
    };

    const bindMonitorActions = () => {
      card?.querySelector("[data-transport-monitor-refresh]")?.addEventListener("click", () => {
        loadMonitor();
      });

      card?.querySelector("[data-transport-monitor-settings]")?.addEventListener("submit", async (event) => {
        event.preventDefault();
        const form = event.currentTarget;
        const message = card.querySelector("[data-transport-monitor-message]");
        const payload = {
          call_alert_minutes: Number(form.elements.call_alert_minutes?.value || 10),
          break_alert_minutes: Number(form.elements.break_alert_minutes?.value || 15),
          idle_alert_minutes: Number(form.elements.idle_alert_minutes?.value || 30)
        };
        try {
          if (message) {
            message.classList.add("ok");
            message.textContent = "Guardando alertas...";
          }
          const data = await transportMonitorApi028N("/settings", {
            method: "PUT",
            body: JSON.stringify(payload)
          });
          if (!closed && card) {
            card.innerHTML = transportMonitorBodyHtml028N(data.monitor || data, viewMode);
            bindMonitorActions();
          }
        } catch (error) {
          if (message) {
            message.classList.remove("ok");
            message.textContent = error.message || "No fue posible guardar alertas.";
          }
        }
      });

      card?.querySelectorAll("[data-transport-force-logout]").forEach((button) => {
        button.addEventListener("click", async () => {
          const userId = button.getAttribute("data-transport-force-logout") || "";
          if (!userId) return;
          if (!window.confirm("Deseas desloguear este agente y cerrar su sesion activa?")) return;
          button.disabled = true;
          button.textContent = "Cerrando...";
          try {
            const data = await transportMonitorApi028N(`/${encodeURIComponent(userId)}/force-logout`, {
              method: "POST"
            });
            if (!closed && card) {
              card.innerHTML = transportMonitorBodyHtml028N(data.monitor || data, viewMode);
              bindMonitorActions();
            }
          } catch (error) {
            button.disabled = false;
            button.textContent = "Desloguear";
            const message = card.querySelector("[data-transport-monitor-message]");
            if (message) {
              message.classList.remove("ok");
              message.textContent = error.message || "No fue posible cerrar la sesion.";
            }
          }
        });
      });
    };

    async function loadMonitor() {
      try {
        const data = await transportMonitorApi028N("", { method: "GET" });
        if (!closed && card) {
          card.innerHTML = transportMonitorBodyHtml028N(data, viewMode);
          bindMonitorActions();
        }
      } catch (error) {
        if (!closed && card) {
          card.innerHTML = `
            <div class="tc-head-028l">
              <div>
                <div class="mp-kicker">Call Center</div>
                <h2>No se pudo cargar el monitor</h2>
                <p>${h(error.message || "Revisa permisos del mini panel.")}</p>
              </div>
              <button class="mp-button secondary" type="button" data-transport-close>Cerrar</button>
            </div>
          `;
        }
      }
    }

    overlay.addEventListener("click", (event) => {
      if (event.target.closest("[data-transport-close]")) close();
    });

    await loadMonitor();
    timer = window.setInterval(loadMonitor, 15000);
  }

  function transportCustomerKeyMap028L(customers) {
    const map = new Map();
    (Array.isArray(customers) ? customers : []).forEach((item) => {
      [item.customer_name, item.phone, item.contract_code].forEach((value) => {
        const key = normalizeTransportLookup028L(value);
        if (key && !map.has(key)) map.set(key, item);
      });
    });
    return map;
  }

  function transportCustomerOptions028L(customers) {
    return (Array.isArray(customers) ? customers : [])
      .map((item) => {
        const batch = item.batch_file_name ? `Base: ${item.batch_file_name}${item.row_number ? ` #${item.row_number}` : ""}` : "";
        const fare = Number(item.ticket_value || 0) > 0 ? `Valor: ${formatMoney(item.ticket_value || 0)}` : "";
        const label = [item.phone, item.contract_code, item.account_code, item.transporter, fare, batch].filter(Boolean).join(" / ");
        return `<option value="${h(item.customer_name || item.phone || item.contract_code || "")}" label="${h(label)}"></option>`;
      })
      .join("");
  }

  function transportCityOptions028L() {
    return TRANSPORT_CITIES_CO_028L.map((city) => `<option value="${h(city)}"></option>`).join("");
  }

  function transportAdvisorCallMatches028L(item, employeeName) {
    const advisor = normalizeTransportLookup028L(item?.advisor_name || "");
    const target = normalizeTransportLookup028L(employeeName || "");
    return !target || !advisor || advisor === target;
  }

  function transportAdvisorKpis028L(calls, employeeName, selectedCustomer = null) {
    const rows = (Array.isArray(calls) ? calls : []).filter((item) => transportAdvisorCallMatches028L(item, employeeName));
    const quoteCount = rows.filter((item) => item.quote_requested || String(item.result || "") === "quoted").length;
    const ticketCount = rows.filter((item) => item.ticket_requested || String(item.result || "") === "ticket_created").length;
    const selected = selectedCustomer?.customer_name || selectedCustomer?.phone || selectedCustomer?.contract_code || "Sin cliente seleccionado";
    return `
      <section class="tc-advisor-kpis-028l">
        <article>
          <span>Mensajes internos</span>
          <strong>Sin mensajes</strong>
          <small>Supervision, gerencia o tesoreria apareceran aqui.</small>
        </article>
        <article>
          <span>Llamadas gestionadas</span>
          <strong>${h(rows.length)}</strong>
          <small>Ultimos registros visibles</small>
        </article>
        <article>
          <span>Cotizaciones</span>
          <strong>${h(quoteCount)}</strong>
          <small>Generadas o marcadas</small>
        </article>
        <article>
          <span>Tickets</span>
          <strong>${h(ticketCount)}</strong>
          <small>Generados o marcados</small>
        </article>
        <article>
          <span>Cliente activo</span>
          <strong data-transport-selected-client>${h(selected)}</strong>
          <small>Seleccion desde base cargada</small>
        </article>
      </section>
    `;
  }

  function transportCallStatusLabel028L(value) {
    const status = String(value || "completed").toLowerCase();
    if (status === "missed") return "Perdida";
    if (status === "pending") return "En proceso";
    return "Completada";
  }

  function transportCallDirectionLabel028L(value) {
    return String(value || "inbound").toLowerCase() === "outbound" ? "Saliente" : "Entrante";
  }

  function transportCallsRows028L(calls, employeeName = "") {
    const rows = (Array.isArray(calls) ? calls : []).filter((item) => transportAdvisorCallMatches028L(item, employeeName));
    if (!rows.length) {
      return `<tr><td colspan="7">Sin llamadas registradas todavia.</td></tr>`;
    }
    return rows.slice(0, 10).map((item) => `
      <tr>
        <td>${h(String(item.created_at || "").slice(0, 16).replace("T", " "))}</td>
        <td><strong>${h(item.customer_name || "Cliente sin nombre")}</strong><br><small>${h(item.phone || item.contract_code || "")}</small></td>
        <td>${h(item.contract_code || "Sin contrato")}</td>
        <td>${h(item.origin || "-")} -> ${h(item.destination || "-")}</td>
        <td>${h(transportCallDirectionLabel028L(item.call_direction))}</td>
        <td><span class="tc-chip-028l">${h(transportCallStatusLabel028L(item.call_status))}</span></td>
        <td>${h(formatSeconds(item.duration_seconds || 0))}</td>
      </tr>
    `).join("");
  }

  async function loadTransportCustomers028L(search = "", session = null) {
    const employeeId = session?.employee?.id || session?.employee_id || session?.mini_panel?.employee_id || "";
    const suffix = `?limit=80&search=${encodeURIComponent(search || "")}&employee_id=${encodeURIComponent(employeeId || "")}`;
    const data = await transportCallsApi028L(`/customers${suffix}`, { method: "GET" });
    return Array.isArray(data.customers) ? data.customers : [];
  }

  async function loadTransportCalls028L() {
    const data = await transportCallsApi028L("/calls?limit=40", { method: "GET" });
    return Array.isArray(data.calls) ? data.calls : [];
  }

  function setTransportField028L(form, name, value) {
    const field = form?.elements?.[name];
    if (field) field.value = value == null ? "" : value;
  }

  function fillTransportCustomer028L(form, customer) {
    if (!form || !customer) return;
    setTransportField028L(form, "customer_name", customer.customer_name || "");
    setTransportField028L(form, "customer_type", customer.customer_type || "person");
    setTransportField028L(form, "phone", customer.phone || "");
    setTransportField028L(form, "contract_code", customer.contract_code || "");
    setTransportField028L(form, "email", customer.email || "");
    setTransportField028L(form, "document_id", customer.document_id || "");
    setTransportField028L(form, "account_code", customer.account_code || "");
    setTransportField028L(form, "origin", customer.origin || "");
    setTransportField028L(form, "destination", customer.destination || "");
    setTransportField028L(form, "trip_type", customer.trip_type || "");
    setTransportField028L(form, "transporter", customer.transporter || "");
    setTransportField028L(form, "ticket_value", customer.ticket_value || "");
    setTransportField028L(form, "batch_row_id", customer.batch_row_id || "");
    setTransportField028L(form, "campaign_code", customer.campaign_code || "");
    setTransportField028L(form, "phone_type", customer.phone_type || "unknown");
    setTransportField028L(form, "consent_status", customer.consent_status || "unknown");
    if (form.elements.do_not_call) form.elements.do_not_call.checked = Boolean(customer.do_not_call);
    if (customer.notes && form.elements.notes && !form.elements.notes.value) form.elements.notes.value = customer.notes;
  }

  async function openTransportCallsModule028L(session) {
    const viewMode028N = transportCallsViewMode028N(session);
    if (viewMode028N === "supervisor" || viewMode028N === "management") {
      await openTransportMonitorModule028N(session, viewMode028N);
      return;
    }

    transportCallsStyles028L();
    const employee = session?.employee || {};
    const user = session?.user || {};
    const employeeName = employee.full_name || user.full_name || "asesor";
    const uid = `tc028l_${Date.now()}`;
    let customers = [];
    let calls = [];
    try {
      [customers, calls] = await Promise.all([
        loadTransportCustomers028L("", session),
        loadTransportCalls028L()
      ]);
    } catch (error) {
      console.warn("CLONEXA 028L transport calls load:", error);
    }

    let customerMap = transportCustomerKeyMap028L(customers);
    const overlay = document.createElement("div");
    overlay.className = "mp-modal";
    overlay.innerHTML = `
      <div class="mp-modal-backdrop" data-transport-close></div>
      <section class="mp-modal-card tc-card-028l" role="dialog" aria-modal="true" aria-label="Call Center">
        <div class="tc-head-028l">
          <div>
            <div class="mp-kicker">Mini panel asesor</div>
            <h2>Call Center / Llamadas</h2>
            <p>Registro operativo de cliente, ruta, contrato, cotizacion y ticket.</p>
          </div>
          <button class="mp-button secondary" type="button" data-transport-close>Cerrar</button>
        </div>

        <div data-transport-kpis>${transportAdvisorKpis028L(calls, employeeName)}</div>

        <form class="mp-form" data-transport-form>
          <datalist id="${h(uid)}_customers">${transportCustomerOptions028L(customers)}</datalist>
          <datalist id="${h(uid)}_cities">${transportCityOptions028L()}</datalist>
          <input type="hidden" name="call_direction" value="inbound" />
          <input type="hidden" name="call_status" value="completed" />
          <input type="hidden" name="duration_seconds" value="0" />
          <input type="hidden" name="source" value="mini_panel" />
          <input type="hidden" name="twilio_parent_call_sid" value="" />
          <input type="hidden" name="batch_row_id" value="" />
          <input type="hidden" name="email" value="" />
          <input type="hidden" name="document_id" value="" />
          <input type="hidden" name="account_code" value="" />
          <input type="hidden" name="transporter" value="" />
          <input type="hidden" name="ticket_value" value="0" />

          <div class="tc-grid-028l">
            <div class="tc-softphone-029a">
              <div class="tc-softphone-state-029a">
                <span>Softphone web</span>
                <strong data-telephony-state>Listo para llamar</strong>
              </div>
              <button class="tc-call-btn-029a" type="button" data-telephony-call>Llamar</button>
              <button class="tc-call-btn-029a hangup" type="button" data-telephony-hangup disabled>Colgar</button>
              <button class="tc-call-btn-029a secondary" type="button" data-telephony-mute disabled>Silenciar</button>
            </div>
            <div class="tc-field-028l wide">
              <label>Cliente</label>
              <input name="customer_name" list="${h(uid)}_customers" placeholder="Nombre, telefono o contrato" autocomplete="off" required />
            </div>
            <div class="tc-field-028l">
              <label>Tipo cliente</label>
              <select name="customer_type">
                <option value="person">Persona</option>
                <option value="company">Empresa</option>
                <option value="contract">Contrato</option>
              </select>
            </div>
            <div class="tc-field-028l">
              <label>Telefono</label>
              <input name="phone" placeholder="+57..." autocomplete="off" />
            </div>
            <div class="tc-field-028l">
              <label>Tipo de linea</label>
              <input name="phone_type" value="unknown" readonly />
            </div>
            <div class="tc-field-028l">
              <label>Campana</label>
              <input name="campaign_code" placeholder="Campana o base asignada" autocomplete="off" />
            </div>
            <div class="tc-field-028l">
              <label>Consentimiento</label>
              <select name="consent_status">
                <option value="unknown">Sin confirmar</option>
                <option value="granted">Autorizado</option>
                <option value="denied">No autorizado</option>
                <option value="revoked">Revocado</option>
              </select>
            </div>
            <div class="tc-field-028l">
              <label>No llamar</label>
              <label class="tc-chip-028l"><input type="checkbox" name="do_not_call" /> Bloquear llamadas</label>
            </div>
            <div class="tc-field-028l">
              <label># contrato / aval</label>
              <input name="contract_code" placeholder="Contrato o aval" autocomplete="off" />
            </div>
            <div class="tc-field-028l">
              <label>Origen</label>
              <input name="origin" list="${h(uid)}_cities" placeholder="Ciudad origen" autocomplete="off" />
            </div>
            <div class="tc-field-028l">
              <label>Destino</label>
              <input name="destination" list="${h(uid)}_cities" placeholder="Ciudad destino" autocomplete="off" />
            </div>
            <div class="tc-field-028l">
              <label>Tipo viaje</label>
              <input name="trip_type" placeholder="Ruta, expreso, aeropuerto..." autocomplete="off" />
            </div>
            <div class="tc-field-028l">
              <label>Resultado</label>
              <select name="result">
                <option value="follow_up">Seguimiento</option>
                <option value="quoted">Cotizacion</option>
                <option value="ticket_created">Ticket generado</option>
                <option value="not_interested">No interesado</option>
                <option value="no_contact">No contacto</option>
              </select>
            </div>
            <div class="tc-field-028l">
              <label>Opcion 2</label>
              <select name="typification_2">
                <option value="">Sin seleccion</option>
                <option value="requiere_confirmacion">Requiere confirmacion</option>
                <option value="requiere_autorizacion">Requiere autorizacion</option>
                <option value="requiere_pago">Requiere pago</option>
                <option value="datos_incompletos">Datos incompletos</option>
              </select>
            </div>
            <div class="tc-field-028l">
              <label>Opcion 3</label>
              <select name="typification_3">
                <option value="">Sin seleccion</option>
                <option value="cliente_indica_llamar">Cliente indica llamar</option>
                <option value="cliente_indica_whatsapp">Cliente indica WhatsApp</option>
                <option value="cliente_indica_correo">Cliente indica correo</option>
                <option value="cliente_indica_no_contactar">Cliente indica no contactar</option>
              </select>
            </div>
            <div class="tc-field-028l">
              <label>Direccion llamada</label>
              <input name="call_direction_display" value="Saliente por Twilio" readonly />
            </div>
            <div class="tc-field-028l">
              <label>Estado llamada</label>
              <input name="call_status_display" value="Sin iniciar" readonly />
            </div>
            <div class="tc-field-028l">
              <label>Duracion</label>
              <input name="duration_display" value="00:00:00" readonly />
            </div>
            <div class="tc-field-028l">
              <label>ID llamada</label>
              <input name="twilio_call_sid" placeholder="Twilio automatico" readonly />
            </div>
            <div class="tc-field-028l full">
              <label>Notas</label>
              <textarea name="notes" rows="3" placeholder="Resumen, ruta solicitada, aprobaciones o pendientes..."></textarea>
            </div>
          </div>

          <div class="tc-checks-028l">
            <label><input type="checkbox" name="quote_requested" /> Genero cotizacion</label>
            <label><input type="checkbox" name="ticket_requested" /> Genero ticket</label>
            <span class="tc-chip-028l twilio">Twilio automatico</span>
          </div>

          <div class="tc-actions-028l">
            <button class="mp-button" type="submit">Guardar llamada</button>
            <button class="mp-button secondary" type="button" data-transport-next>Siguiente llamada</button>
            <button class="mp-button secondary" type="button" data-transport-refresh>Actualizar base</button>
            <span class="tc-chip-028l" data-transport-queue></span>
            <span class="mp-message ok" data-transport-message></span>
          </div>
        </form>

        <section class="tc-panel-028l">
          <h3>Ultimas llamadas</h3>
          <div style="overflow:auto">
            <table class="tc-table-028l">
              <thead>
                <tr>
                  <th>Fecha</th>
                  <th>Cliente</th>
                  <th>Contrato</th>
                  <th>Ruta</th>
                  <th>Dir.</th>
                  <th>Estado</th>
                  <th>Duracion</th>
                </tr>
              </thead>
              <tbody data-transport-rows>${transportCallsRows028L(calls, employeeName)}</tbody>
            </table>
          </div>
        </section>
      </section>
    `;
    document.body.appendChild(overlay);

    const form = overlay.querySelector("[data-transport-form]");
    const message = overlay.querySelector("[data-transport-message]");
    const rowsTarget = overlay.querySelector("[data-transport-rows]");
    const kpisTarget = overlay.querySelector("[data-transport-kpis]");
    const customerDatalist = overlay.querySelector(`#${uid}_customers`);
    const telephonyState = overlay.querySelector("[data-telephony-state]");
    const callButton = overlay.querySelector("[data-telephony-call]");
    const hangupButton = overlay.querySelector("[data-telephony-hangup]");
    const muteButton = overlay.querySelector("[data-telephony-mute]");
    const nextButton = overlay.querySelector("[data-transport-next]");
    const queueStatus = overlay.querySelector("[data-transport-queue]");
    let selectedCustomer = null;
    let telephonyDevice = null;
    let activeCall = null;
    let callStartedAt = 0;
    let callTimer = null;
    let callMuted = false;

    const setTelephonyState029A = (label, status = "") => {
      if (telephonyState) telephonyState.textContent = label;
      if (form?.elements?.call_status_display && status) form.elements.call_status_display.value = status;
    };
    const blockedCallMessage029A = (preflight = {}) => {
      const consent = preflight?.consent || {};
      const consentStatus = String(consent.consent_status || form?.elements?.consent_status?.value || "unknown");
      if (Boolean(consent.do_not_call) || Boolean(form?.elements?.do_not_call?.checked)) {
        return "Llamada bloqueada: el contacto esta marcado como No llamar";
      }
      if (["denied", "revoked"].includes(consentStatus)) {
        return "Llamada bloqueada: el contacto no autorizo llamadas";
      }
      if (consentStatus !== "granted") {
        return "Llamada bloqueada: selecciona Autorizado en Consentimiento";
      }
      return "Llamada bloqueada por la politica de contacto";
    };
    const updateCallTimer029A = () => {
      const seconds = callStartedAt ? Math.max(0, Math.floor((Date.now() - callStartedAt) / 1000)) : 0;
      setTransportField028L(form, "duration_seconds", seconds);
      setTransportField028L(form, "duration_display", formatSeconds(seconds));
    };
    const stopCallTimer029A = () => {
      if (callTimer) window.clearInterval(callTimer);
      callTimer = null;
      updateCallTimer029A();
    };
    const setCallControls029A = (inCall) => {
      if (callButton) callButton.disabled = inCall;
      if (hangupButton) hangupButton.disabled = !inCall;
      if (muteButton) muteButton.disabled = !inCall;
    };
    const finishSoftphoneCall029A = (statusLabel = "Completada") => {
      stopCallTimer029A();
      setTransportField028L(form, "call_status", statusLabel === "Completada" ? "completed" : "missed");
      setTelephonyState029A("Llamada finalizada", statusLabel);
      activeCall = null;
      callMuted = false;
      if (muteButton) muteButton.textContent = "Silenciar";
      setCallControls029A(false);
    };

    const renderAdvisorKpis = () => {
      if (kpisTarget) kpisTarget.innerHTML = transportAdvisorKpis028L(calls, employeeName, selectedCustomer);
    };

    const updateQueueStatus028L = () => {
      if (!queueStatus) return;
      if (!customers.length) {
        queueStatus.textContent = "Sin registros pendientes";
        return;
      }
      const currentId = String(selectedCustomer?.batch_row_id || "");
      const currentIndex = customers.findIndex((customer) => String(customer.batch_row_id || "") === currentId);
      queueStatus.textContent = currentIndex >= 0
        ? `Registro ${currentIndex + 1} de ${customers.length}`
        : `${customers.length} registros pendientes`;
    };

    const selectTransportCustomer028L = (customer, resetForm = true) => {
      if (resetForm) form?.reset();
      selectedCustomer = customer || null;
      if (selectedCustomer) {
        fillTransportCustomer028L(form, selectedCustomer);
        setTransportField028L(form, "call_status_display", "Sin iniciar");
        setTransportField028L(form, "duration_display", "00:00:00");
        setTelephonyState029A(
          `Listo para llamar: ${selectedCustomer.customer_name || selectedCustomer.phone || "cliente"}`,
          "Sin iniciar"
        );
      } else {
        setTransportField028L(form, "phone_type", "unknown");
        setTransportField028L(form, "call_status_display", "Sin iniciar");
        setTransportField028L(form, "duration_display", "00:00:00");
        setTelephonyState029A("Sin registros pendientes", "Sin iniciar");
      }
      renderAdvisorKpis();
      updateQueueStatus028L();
    };

    const refreshLists = async (search = "", autoSelect = false) => {
      try {
        const previousId = String(selectedCustomer?.batch_row_id || "");
        const nextCustomers = await loadTransportCustomers028L(search, session);
        customers = nextCustomers;
        customerMap = transportCustomerKeyMap028L(customers);
        if (customerDatalist) customerDatalist.innerHTML = transportCustomerOptions028L(customers);
        calls = await loadTransportCalls028L();
        if (rowsTarget) rowsTarget.innerHTML = transportCallsRows028L(calls, employeeName);
        const preservedCustomer = customers.find((customer) => String(customer.batch_row_id || "") === previousId);
        if (preservedCustomer) selectTransportCustomer028L(preservedCustomer);
        else if (autoSelect || !selectedCustomer) selectTransportCustomer028L(customers[0] || null);
        else {
          selectedCustomer = null;
          renderAdvisorKpis();
          updateQueueStatus028L();
        }
      } catch (error) {
        if (message) {
          message.classList.remove("ok");
          message.textContent = error.message || "No se pudo actualizar.";
        }
      }
    };

    form?.elements?.customer_name?.addEventListener("input", (event) => {
      const value = event.target.value || "";
      const match = customerMap.get(normalizeTransportLookup028L(value));
      if (match) {
        selectTransportCustomer028L(match);
      }
    });

    selectTransportCustomer028L(customers[0] || null);

    callButton?.addEventListener("click", async () => {
      const phone = String(form?.elements?.phone?.value || "").trim();
      if (!phone) {
        setTelephonyState029A("Selecciona un cliente con telefono", "Sin iniciar");
        return;
      }
      if (!window.Twilio?.Device) {
        setTelephonyState029A("No se cargo el softphone Twilio", "Error");
        return;
      }
      try {
        setTelephonyState029A("Validando consentimiento...", "Validando");
        const consentPayload = {
          consent_status: String(form.elements.consent_status?.value || "unknown"),
          do_not_call: Boolean(form.elements.do_not_call?.checked),
          source: "mini_panel",
          notes: `Registrado por ${employeeName}`
        };
        await transportTelephonyApi029A(`/consents/${encodeURIComponent(phone)}`, {
          method: "PUT",
          body: JSON.stringify(consentPayload)
        });
        const preflight = await transportTelephonyApi029A("/preflight", {
          method: "POST",
          body: JSON.stringify({
            phone,
            batch_row_id: String(form.elements.batch_row_id?.value || ""),
            campaign_code: String(form.elements.campaign_code?.value || "")
          })
        });
        setTransportField028L(form, "phone", preflight.phone || phone);
        setTransportField028L(form, "phone_type", preflight.phone_type || "unknown");
        setTransportField028L(form, "campaign_code", preflight.campaign_code || "General");
        if (!preflight.allowed) {
          setTelephonyState029A(blockedCallMessage029A(preflight), "Bloqueada");
          return;
        }
        const tokenData = await transportTelephonyApi029A("/token", { method: "GET" });
        if (telephonyDevice) telephonyDevice.destroy();
        telephonyDevice = new window.Twilio.Device(tokenData.token, {
          logLevel: 1,
          closeProtection: true
        });
        telephonyDevice.on("error", (error) => {
          console.error("CLONEXA Twilio Device:", error);
          setTelephonyState029A(error?.message || "Error de telefonia", "Error");
          setCallControls029A(false);
        });
        setTelephonyState029A("Conectando llamada...", "Marcando");
        setCallControls029A(true);
        activeCall = await telephonyDevice.connect({ params: {
          To: preflight.phone,
          CompanyId: String(companyId),
          CustomerName: String(form.elements.customer_name?.value || ""),
          CampaignCode: String(preflight.campaign_code || "General"),
          BatchRowId: String(form.elements.batch_row_id?.value || "")
        }});
        activeCall.on("accept", () => {
          const parentSid = String(activeCall?.parameters?.CallSid || "");
          setTransportField028L(form, "twilio_parent_call_sid", parentSid);
          setTransportField028L(form, "twilio_call_sid", parentSid);
          setTransportField028L(form, "call_direction", "outbound");
          setTransportField028L(form, "call_status", "pending");
          setTelephonyState029A("En llamada", "En llamada");
          stopCallTimer029A();
          callStartedAt = Date.now();
          callTimer = window.setInterval(updateCallTimer029A, 1000);
        });
        activeCall.on("disconnect", () => finishSoftphoneCall029A("Completada"));
        activeCall.on("cancel", () => finishSoftphoneCall029A("No contestada"));
        activeCall.on("reject", () => finishSoftphoneCall029A("No contestada"));
        activeCall.on("error", (error) => {
          console.error("CLONEXA Twilio Call:", error);
          finishSoftphoneCall029A("Fallida");
          setTelephonyState029A(error?.message || "La llamada fallo", "Fallida");
        });
      } catch (error) {
        console.error("CLONEXA softphone:", error);
        setTelephonyState029A(error?.message || "No se pudo iniciar la llamada", "Error");
        setCallControls029A(false);
      }
    });

    hangupButton?.addEventListener("click", () => activeCall?.disconnect());
    muteButton?.addEventListener("click", () => {
      if (!activeCall) return;
      callMuted = !callMuted;
      activeCall.mute(callMuted);
      muteButton.textContent = callMuted ? "Activar audio" : "Silenciar";
    });

    nextButton?.addEventListener("click", () => {
      if (activeCall) {
        if (message) {
          message.classList.remove("ok");
          message.textContent = "Finaliza la llamada antes de avanzar.";
        }
        return;
      }
      if (!customers.length) {
        if (message) {
          message.classList.add("ok");
          message.textContent = "No hay registros pendientes en la base.";
        }
        return;
      }
      const currentId = String(selectedCustomer?.batch_row_id || "");
      const currentIndex = customers.findIndex((customer) => String(customer.batch_row_id || "") === currentId);
      const nextIndex = currentIndex >= 0 ? currentIndex + 1 : 0;
      if (nextIndex >= customers.length) {
        if (message) {
          message.classList.add("ok");
          message.textContent = "Estas en el ultimo registro pendiente. Guarda la gestion para continuar.";
        }
        return;
      }
      selectTransportCustomer028L(customers[nextIndex]);
      if (message) {
        message.classList.add("ok");
        message.textContent = "Siguiente llamada cargada.";
      }
    });

    overlay.querySelector("[data-transport-refresh]")?.addEventListener("click", async () => {
      if (message) {
        message.classList.add("ok");
        message.textContent = "Actualizando...";
      }
      await refreshLists("", true);
      if (message) {
        message.classList.add("ok");
        message.textContent = "Base actualizada.";
      }
    });

    form?.addEventListener("submit", async (event) => {
      event.preventDefault();
      if (activeCall) {
        if (message) {
          message.classList.remove("ok");
          message.textContent = "Finaliza la llamada antes de guardar la tipificacion.";
        }
        return;
      }
      const data = new FormData(form);
      const baseNotes = String(data.get("notes") || "").trim();
      const typificationNotes = [
        data.get("typification_2") ? `Opcion 2: ${data.get("typification_2")}` : "",
        data.get("typification_3") ? `Opcion 3: ${data.get("typification_3")}` : "",
        data.get("email") ? `Correo base: ${data.get("email")}` : "",
        data.get("account_code") ? `Cuenta base: ${data.get("account_code")}` : "",
        data.get("transporter") ? `Transportadora base: ${data.get("transporter")}` : "",
        Number(data.get("ticket_value") || 0) > 0 ? `Valor ticket base: ${data.get("ticket_value")}` : ""
      ].filter(Boolean);
      const payload = {
        advisor_name: employeeName,
        advisor_status: "available",
        customer_name: String(data.get("customer_name") || "").trim(),
        customer_type: String(data.get("customer_type") || "person").trim(),
        phone: String(data.get("phone") || "").trim(),
        origin: String(data.get("origin") || "").trim(),
        destination: String(data.get("destination") || "").trim(),
        trip_type: String(data.get("trip_type") || "").trim(),
        call_direction: String(data.get("call_direction") || "inbound").trim(),
        call_status: String(data.get("call_status") || "completed").trim(),
        result: String(data.get("result") || "follow_up").trim(),
        duration_seconds: Number(data.get("duration_seconds") || 0),
        quote_requested: data.has("quote_requested"),
        ticket_requested: data.has("ticket_requested"),
        contract_code: String(data.get("contract_code") || "").trim(),
        source: String(data.get("twilio_call_sid") || "").trim() ? "twilio" : "mini_panel",
        twilio_call_sid: "",
        twilio_parent_call_sid: String(data.get("twilio_parent_call_sid") || data.get("twilio_call_sid") || "").trim(),
        batch_row_id: String(data.get("batch_row_id") || "").trim(),
        campaign_code: String(data.get("campaign_code") || "").trim(),
        phone_type: String(data.get("phone_type") || "unknown").trim(),
        consent_status: String(data.get("consent_status") || "unknown").trim(),
        do_not_call: data.has("do_not_call"),
        notes: [baseNotes, ...typificationNotes].filter(Boolean).join("\n")
      };

      if (!payload.customer_name && !payload.phone && !payload.contract_code) {
        if (message) {
          message.classList.remove("ok");
          message.textContent = "Agrega cliente, telefono o contrato.";
        }
        return;
      }

      try {
        if (message) {
          message.classList.add("ok");
          message.textContent = "Guardando llamada...";
        }
        await transportCallsApi028L("/calls", {
          method: "POST",
          body: JSON.stringify(payload)
        });
        form.reset();
        selectedCustomer = null;
        await refreshLists("", true);
        if (message) {
          message.classList.add("ok");
          message.textContent = customers.length
            ? "Llamada guardada. Siguiente registro cargado."
            : "Llamada guardada. Base completada.";
        }
      } catch (error) {
        if (message) {
          message.classList.remove("ok");
          message.textContent = error.message || "No se pudo guardar la llamada.";
        }
      }
    });

    const closeTransportModal028L = () => {
      document.removeEventListener("keydown", onTransportKeydown028L);
      stopCallTimer029A();
      if (activeCall) activeCall.disconnect();
      if (telephonyDevice) telephonyDevice.destroy();
      overlay.remove();
    };
    const onTransportKeydown028L = (event) => {
      if (event.key === "Escape") closeTransportModal028L();
    };
    document.addEventListener("keydown", onTransportKeydown028L);
    overlay.addEventListener("click", (event) => {
      if (event.target.closest("[data-transport-close]")) closeTransportModal028L();
    });
  }
  /* CLONEXA_028L_TRANSPORT_CALLS_MINIPANEL_END */


  /* CLONEXA_028O_TRANSPORT_QUOTES_TICKETS_MINIPANEL_START */
  const CX_TRANSPORT_QUOTES_TICKETS_CODES_028O = new Set([
    "transport_quotes_tickets",
    "transport_tickets",
    "cotizaciones_tickets",
    "tickets_cotizaciones",
    "cotizacion_ticket",
    "cotizacion_tickets",
    "quotes_tickets",
    "quote_ticket",
    "ticket_quote",
    "ticket_quotes",
    "tickets"
  ]);

  function isTransportQuotesTicketsCode028O(code) {
    const normalized = canonicalModuleCode022A(code);
    return CX_TRANSPORT_QUOTES_TICKETS_CODES_028O.has(normalized) || normalized === "transport_quotes_tickets";
  }

  function isTransportQuotesPanel028O(session) {
    const type = normalizePanelType019H(panelType);
    if (type === "call_center" || type === "external") return true;
    const tokens = typeof transportRoleTokens028N === "function" ? transportRoleTokens028N(session) : new Set();
    return ["agente_call", "agentecall", "agente_externo", "agenteexterno", "supervisor", "tesoreria", "gerencia", "gerente"].some((item) => tokens.has(item));
  }

  async function openQuotesEntry028O(session, moduleCode = "") {
    if (isTransportQuotesTicketsCode028O(moduleCode) || (isTransportQuotesPanel028O(session) && isQuotesCode021A(moduleCode || "cotizacion"))) {
      await openTransportQuotesTicketsModule028O(session);
      return;
    }
    await openQuotesModule021A(session);
  }

  function transportQuoteRole028O(session) {
    const tokens = typeof transportRoleTokens028N === "function" ? transportRoleTokens028N(session) : new Set();
    if (tokens.has("supervisor") || tokens.has("supervisora")) return "supervisor";
    if (tokens.has("tesoreria") || tokens.has("tesorero") || tokens.has("treasury")) return "tesoreria";
    if (tokens.has("gerencia") || tokens.has("gerente") || tokens.has("manager") || tokens.has("admin") || tokens.has("admin_empresa")) return "gerencia";
    if (tokens.has("agente_externo") || tokens.has("agenteexterno") || tokens.has("external") || tokens.has("externo")) return "agente_externo";
    return "agente_call";
  }

  function transportQuoteCanCheckSupervisor028O(session) {
    return transportQuoteRole028O(session) === "supervisor";
  }

  function transportQuoteCanCheckTreasury028O(session) {
    return transportQuoteRole028O(session) === "tesoreria";
  }

  async function transportQuoteApi028O(path, options = {}) {
    if (!companyId) throw new Error("Falta company_id.");
    const headers = {
      ...authHeaders(),
      ...(options.headers || {})
    };
    if (options.body && !headers["Content-Type"]) {
      headers["Content-Type"] = "application/json";
    }
    return api(`/api/v1/transport-quotes-tickets/companies/${encodeURIComponent(companyId)}${path}`, {
      ...options,
      headers
    });
  }

  function transportQuotePdfUrl028O(id, inline = true) {
    return `/api/v1/transport-quotes-tickets/companies/${encodeURIComponent(companyId)}/documents/${encodeURIComponent(id)}/print.pdf?inline=${inline ? "true" : "false"}${authQueryParam()}`;
  }

  function transportQuoteMoneyValue028O(value) {
    try {
      const raw = String(value || "0").trim();
      const clean = raw.replace(/[^0-9,.-]/g, "");
      if (clean.includes(",") && clean.includes(".")) {
        return Number(clean.lastIndexOf(",") > clean.lastIndexOf(".") ? clean.replaceAll(".", "").replace(",", ".") : clean.replaceAll(",", "")) || 0;
      }
      if ((clean.match(/\./g) || []).length === 1 && clean.split(".").pop().length === 3) return Number(clean.replaceAll(".", "")) || 0;
      if ((clean.match(/,/g) || []).length === 1 && clean.split(",").pop().length === 3) return Number(clean.replaceAll(",", "")) || 0;
      if ((clean.match(/\./g) || []).length > 1) return Number(clean.replaceAll(".", "")) || 0;
      if ((clean.match(/,/g) || []).length > 1) return Number(clean.replaceAll(",", "")) || 0;
      return Number(clean.replace(",", ".")) || 0;
    } catch (_) {
      return 0;
    }
  }

  function transportQuoteTypeLabel028O(value) {
    return String(value || "quote") === "ticket" ? "Ticket / orden" : "Cotizacion";
  }

  function transportQuoteStatusLabel028O(value) {
    const labels = {
      pending: "Pendiente",
      approved: "Aprobada",
      rejected: "Rechazada",
      converted: "Convertida",
      scheduled: "Programada",
      in_route: "En ruta",
      completed: "Completada",
      cancelled: "Cancelada",
      billed: "Facturada"
    };
    return labels[String(value || "pending")] || "Pendiente";
  }

  function transportQuoteCheckChips028O(item) {
    return `
      <div class="tqt-checks-028o">
        <span class="tqt-chip-028o ${item?.supervisor_check ? "ok" : "pending"}">${item?.supervisor_check ? "Supervisor OK" : "Supervisor pendiente"}</span>
        <span class="tqt-chip-028o ${item?.treasury_check ? "ok" : "pending"}">${item?.treasury_check ? "Tesoreria OK" : "Tesoreria pendiente"}</span>
        ${item?.charged_to_contract ? `<span class="tqt-chip-028o ok">Cargado a contrato</span>` : `<span class="tqt-chip-028o pending">Sin cargar a contrato</span>`}
      </div>
    `;
  }

  function transportQuoteRows028O(documents, session) {
    const rows = Array.isArray(documents) ? documents : [];
    const canSupervisor = transportQuoteCanCheckSupervisor028O(session);
    const canTreasury = transportQuoteCanCheckTreasury028O(session);
    if (!rows.length) {
      return `<tr><td colspan="6"><div class="tc-monitor-empty-028n">No hay cotizaciones o tickets para revisar.</div></td></tr>`;
    }
    return rows.map((item) => {
      const id = String(item.id || "");
      const isQuote = String(item.document_type || "quote") === "quote";
      return `
        <tr>
          <td><strong>${h(item.document_number || "-")}</strong><br><small>${h(transportQuoteTypeLabel028O(item.document_type))}</small><br><span class="tc-chip-028l">${h(transportQuoteStatusLabel028O(item.status))}</span></td>
          <td><strong>${h(item.client_name || "Cliente")}</strong><br><small>${h(item.contract_code || "Sin contrato")} ${item.account_code ? ` / ${h(item.account_code)}` : ""}</small><br><small>${h(item.phone || "")}</small></td>
          <td><strong>${h(item.origin || "-")} -> ${h(item.destination || "-")}</strong><br><small>${h(item.route_detail || "Ruta sin detalle")}</small><br><small>Servicio: ${h(item.service_date || "-")}</small></td>
          <td><strong>${h(formatMoney(item.total_amount || 0))}</strong><br><small>Tiquetes: ${h(item.ticket_count || 0)}</small><br><small>Vigencia: ${h(item.validity_date || "-")}</small></td>
          <td>${transportQuoteCheckChips028O(item)}</td>
          <td>
            <div class="tqt-actions-028o">
              <button class="mp-button small" type="button" data-tqt-print-028o="${h(id)}">Imprimir</button>
              <button class="mp-button small secondary" type="button" data-tqt-download-028o="${h(id)}">PDF</button>
              ${isQuote ? `<button class="mp-button small secondary" type="button" data-tqt-convert-028o="${h(id)}">Convertir a ticket</button>` : ""}
              ${canSupervisor && !item.supervisor_check ? `<button class="mp-button small" type="button" data-tqt-check-028o="${h(id)}" data-tqt-check-field-028o="supervisor_check">Check supervisor</button>` : ""}
              ${canTreasury && !item.treasury_check ? `<button class="mp-button small" type="button" data-tqt-check-028o="${h(id)}" data-tqt-check-field-028o="treasury_check">Check tesoreria</button>` : ""}
            </div>
          </td>
        </tr>
      `;
    }).join("");
  }

  function transportQuoteStyles028O() {
    transportCallsStyles028L();
    if (document.getElementById("cxTransportQuotesTicketsStyles028O")) return;
    const style = document.createElement("style");
    style.id = "cxTransportQuotesTicketsStyles028O";
    style.textContent = `
      .tqt-card-028o{width:min(1320px,calc(100vw - 28px));max-height:calc(100vh - 28px);overflow:auto}
      .tqt-layout-028o{display:grid;grid-template-columns:minmax(0,1.08fr) minmax(360px,.72fr);gap:16px;align-items:start}
      .tqt-side-028o{position:sticky;top:0}
      .tqt-summary-028o{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin:12px 0 18px}
      .tqt-summary-028o article{border:1px solid rgba(255,255,255,.12);border-radius:18px;background:rgba(255,255,255,.06);padding:13px}
      .tqt-summary-028o span{display:block;font-size:10px;letter-spacing:.12em;text-transform:uppercase;color:rgba(255,255,255,.58);font-weight:950;margin-bottom:6px}
      .tqt-summary-028o strong{display:block;font-size:24px;color:#fff}
      .tqt-checks-028o{display:flex;gap:6px;flex-wrap:wrap}
      .tqt-chip-028o{display:inline-flex;border-radius:999px;padding:6px 9px;border:1px solid rgba(255,255,255,.14);background:rgba(255,255,255,.10);font-size:11px;font-weight:950;color:rgba(255,255,255,.74)}
      .tqt-chip-028o.ok{background:rgba(41,255,187,.14);border-color:rgba(41,255,187,.34);color:#8fffd8}
      .tqt-chip-028o.pending{background:rgba(255,255,255,.08)}
      .tqt-actions-028o{display:flex;gap:8px;flex-wrap:wrap;min-width:250px}
      .mp-button.small{padding:9px 11px;border-radius:13px;font-size:12px}
      @media(max-width:980px){.tqt-layout-028o,.tqt-summary-028o{grid-template-columns:1fr}.tqt-side-028o{position:static}.tqt-card-028o{width:calc(100vw - 18px)}}
    `;
    document.head.appendChild(style);
  }

  async function loadTransportQuoteDocuments028O(filters = {}) {
    const query = new URLSearchParams({
      limit: "160",
      document_type: filters.type || "all",
      status: filters.status || "all",
      search: filters.search || ""
    });
    const data = await transportQuoteApi028O(`/documents?${query.toString()}`, { method: "GET" });
    return Array.isArray(data.documents) ? data.documents : [];
  }

  function transportQuoteTransporterOptions028O(customers, documents = []) {
    const values = new Set();
    [...(Array.isArray(customers) ? customers : []), ...(Array.isArray(documents) ? documents : [])].forEach((item) => {
      const value = String(item?.transporter || "").trim();
      if (value) values.add(value);
    });
    return [...values].sort((a, b) => a.localeCompare(b)).map((item) => `<option value="${h(item)}"></option>`).join("");
  }

  function fillTransportQuoteCustomer028O(form, customer) {
    if (!form || !customer) return;
    const setValue = (name, value) => {
      const field = form.elements?.[name];
      if (field) field.value = value == null ? "" : value;
    };
    setValue("client_name", customer.customer_name || "");
    setValue("client_type", customer.customer_type || "person");
    setValue("phone", customer.phone || "");
    setValue("email", customer.email || "");
    setValue("document_id", customer.document_id || "");
    setValue("contract_code", customer.contract_code || "");
    setValue("account_code", customer.account_code || "");
    setValue("origin", customer.origin || "");
    setValue("destination", customer.destination || "");
    setValue("route_detail", customer.trip_type || "");
    setValue("transporter", customer.transporter || "");
    const unit = transportQuoteMoneyValue028O(customer.ticket_value);
    if (unit > 0) setValue("unit_amount", unit);
    transportQuoteRecalculateTotals028O(form);
  }

  function transportQuoteRecalculateTotals028O(form) {
    if (!form) return;
    const ticketCount = Math.max(1, Math.round(transportQuoteMoneyValue028O(form.elements?.ticket_count?.value) || 1));
    const unitAmount = transportQuoteMoneyValue028O(form.elements?.unit_amount?.value || form.elements?.value_amount?.value);
    const discountAmount = transportQuoteMoneyValue028O(form.elements?.discount_amount?.value);
    const valueAmount = Math.max(0, ticketCount * unitAmount);
    const totalAmount = Math.max(0, valueAmount - discountAmount);
    if (form.elements?.ticket_count) form.elements.ticket_count.value = ticketCount;
    if (form.elements?.value_amount) form.elements.value_amount.value = valueAmount ? String(valueAmount) : "";
    if (form.elements?.total_amount) form.elements.total_amount.value = totalAmount ? String(totalAmount) : "";
  }

  async function openTransportQuotesTicketsModule028O(session) {
    transportQuoteStyles028O();
    const employee = session?.employee || {};
    const user = session?.user || {};
    const role = transportQuoteRole028O(session);
    const advisorName = employee.full_name || user.full_name || user.email || "Mini panel";
    const uid = `tqt028o_${Date.now()}`;
    const overlay = document.createElement("div");
    overlay.className = "mp-modal";
    overlay.innerHTML = `
      <div class="mp-modal-backdrop" data-tqt-close-028o></div>
      <section class="mp-modal-card tqt-card-028o" role="dialog" aria-modal="true" aria-label="Cotizaciones y Tickets">
        <div class="tc-head-028l">
          <div>
            <div class="mp-kicker">Vertical transporte</div>
            <h2>Cotizaciones / Tickets</h2>
            <p>${role === "supervisor" ? "Revisa y aprueba documentos como supervisor." : role === "tesoreria" ? "Revisa y aprueba documentos de tesoreria." : "Crea cotizaciones y tickets; los checks los hacen supervisor y tesoreria."}</p>
          </div>
          <div class="tc-actions-028l" style="margin-top:0">
            <button class="mp-button secondary" type="button" data-tqt-refresh-028o>Actualizar</button>
            <button class="mp-button secondary" type="button" data-tqt-close-028o>Cerrar</button>
          </div>
        </div>
        <div class="tc-panel-028l">Cargando cotizaciones y tickets...</div>
      </section>
    `;
    document.body.appendChild(overlay);
    const card = overlay.querySelector(".tqt-card-028o");

    async function renderBody(filters = {}) {
      let summary = {};
      let documents = [];
      let customers = [];
      let loadError = "";
      try {
        const [summaryResponse, docs, loadedCustomers] = await Promise.all([
          transportQuoteApi028O("/summary", { method: "GET" }),
          loadTransportQuoteDocuments028O(filters),
          loadTransportCustomers028L("", session)
        ]);
        summary = summaryResponse.summary || {};
        documents = docs;
        customers = loadedCustomers;
      } catch (error) {
        loadError = error.message || "No se pudo cargar cotizaciones y tickets.";
      }
      const customerMap = transportCustomerKeyMap028L(customers);

      const canReview = role === "supervisor" || role === "tesoreria" || role === "gerencia";
      card.innerHTML = `
        <div class="tc-head-028l">
          <div>
            <div class="mp-kicker">Vertical transporte</div>
            <h2>Cotizaciones / Tickets</h2>
            <p>${role === "supervisor" ? "Solo tu rol puede dar Check supervisor." : role === "tesoreria" ? "Solo tu rol puede dar Check tesoreria." : "Los checks quedan visibles en verde cuando supervisor y tesoreria los aprueban."}</p>
          </div>
          <div class="tc-actions-028l" style="margin-top:0">
            <button class="mp-button secondary" type="button" data-tqt-refresh-028o>Actualizar</button>
            <button class="mp-button secondary" type="button" data-tqt-close-028o>Cerrar</button>
          </div>
        </div>

        <div class="tqt-summary-028o">
          <article><span>Cotizaciones</span><strong>${h(summary.quote_count || 0)}</strong></article>
          <article><span>Tickets</span><strong>${h(summary.ticket_count || 0)}</strong></article>
          <article><span>Pendientes</span><strong>${h(summary.pending_count || 0)}</strong></article>
          <article><span>Valor total</span><strong>${h(formatMoney(summary.total_amount || 0))}</strong></article>
        </div>
        ${loadError ? `<div class="mp-message">${h(loadError)}</div>` : ""}

        <div class="tqt-layout-028o">
          <form class="mp-form tc-panel-028l" data-tqt-form-028o>
            <div class="mp-kicker">Nuevo documento</div>
            <h3>${canReview ? "Crear o consultar" : "Crear cotizacion o ticket"}</h3>
            <datalist id="${h(uid)}_customers">${transportCustomerOptions028L(customers)}</datalist>
            <datalist id="${h(uid)}_cities">${transportCityOptions028L()}</datalist>
            <datalist id="${h(uid)}_transporters">${transportQuoteTransporterOptions028O(customers, documents)}</datalist>
            <div class="tc-grid-028l">
              <div class="tc-field-028l"><label>Tipo</label><select name="document_type"><option value="quote">Cotizacion</option><option value="ticket">Ticket / orden</option></select></div>
              <div class="tc-field-028l"><label>Estado</label><select name="status"><option value="approved">Aprobada</option><option value="scheduled">Programada</option><option value="completed">Completada</option><option value="cancelled">Cancelada</option></select></div>
              <div class="tc-field-028l wide"><label>Cliente</label><input name="client_name" list="${h(uid)}_customers" placeholder="Empresa o persona" autocomplete="off" required></div>
              <div class="tc-field-028l"><label>Tipo cliente</label><select name="client_type"><option value="company">Empresa</option><option value="person">Persona</option><option value="agency">Agencia</option></select></div>
              <div class="tc-field-028l"><label>Telefono</label><input name="phone" placeholder="+57..."></div>
              <div class="tc-field-028l"><label>Correo</label><input name="email" placeholder="correo@empresa.com"></div>
              <div class="tc-field-028l"><label>Documento / NIT</label><input name="document_id" placeholder="NIT, CC o ID"></div>
              <div class="tc-field-028l"><label># contrato / aval</label><input name="contract_code" placeholder="Contrato o aval"></div>
              <div class="tc-field-028l"><label>Cuenta</label><input name="account_code" placeholder="Cuenta K..."></div>
              <div class="tc-field-028l"><label>Vigencia</label><input name="validity_date" type="date"></div>
              <div class="tc-field-028l"><label>Fecha servicio</label><input name="service_date" type="date"></div>
              <div class="tc-field-028l"><label>Origen</label><input name="origin" list="${h(uid)}_cities" placeholder="Ciudad origen" required></div>
              <div class="tc-field-028l"><label>Destino</label><input name="destination" list="${h(uid)}_cities" placeholder="Ciudad destino" required></div>
              <div class="tc-field-028l"><label>Tipo viaje / ruta</label><input name="route_detail" placeholder="Ruta, expreso, aeropuerto..."></div>
              <div class="tc-field-028l"><label>Transportadora</label><input name="transporter" list="${h(uid)}_transporters" placeholder="Transportadora"></div>
              <div class="tc-field-028l"><label>Persona autorizada</label><input name="person_name" placeholder="Nombre autorizado"></div>
              <div class="tc-field-028l"><label>ID autorizado</label><input name="person_document" placeholder="Documento autorizado"></div>
              <div class="tc-field-028l"><label>Tiquetes</label><input name="ticket_count" inputmode="numeric" value="1"></div>
              <div class="tc-field-028l"><label>Autorizado</label><input name="approval_code" placeholder="Codigo autorizacion"></div>
              <div class="tc-field-028l"><label>Valor x ticket</label><input name="unit_amount" inputmode="decimal" placeholder="0"></div>
              <div class="tc-field-028l"><label>Valor</label><input name="value_amount" inputmode="decimal" placeholder="0" readonly></div>
              <div class="tc-field-028l"><label>Descuento</label><input name="discount_amount" inputmode="decimal" placeholder="0"></div>
              <div class="tc-field-028l"><label>Total</label><input name="total_amount" inputmode="decimal" placeholder="0" readonly></div>
              <div class="tc-field-028l"><label>Asesor</label><input name="advisor_name" value="${h(advisorName)}"></div>
              <div class="tc-field-028l full"><label>Notas</label><textarea name="notes" rows="3" placeholder="Observaciones, aprobaciones, pendientes o condiciones"></textarea></div>
            </div>
            <div class="tc-checks-028l">
              <label><input type="checkbox" name="charged_to_contract"> Cargar a contrato</label>
              <span class="tqt-chip-028o pending">Supervisor pendiente</span>
              <span class="tqt-chip-028o pending">Tesoreria pendiente</span>
            </div>
            <div class="tc-actions-028l">
              <button class="mp-button" type="submit">Crear documento</button>
              <span class="mp-message ok" data-tqt-message-028o></span>
            </div>
          </form>

          <section class="tc-panel-028l tqt-side-028o">
            <div class="mp-kicker">Buscar y revisar</div>
            <h3>${role === "supervisor" ? "Pendientes de supervisor" : role === "tesoreria" ? "Pendientes de tesoreria" : "Historial"}</h3>
            <div class="tc-grid-028l" style="grid-template-columns:1fr 150px 150px auto">
              <div class="tc-field-028l"><label>Buscar</label><input data-tqt-search-028o value="${h(filters.search || "")}" placeholder="Cliente, contrato, ruta"></div>
              <div class="tc-field-028l"><label>Tipo</label><select data-tqt-type-028o><option value="all" ${filters.type === "all" || !filters.type ? "selected" : ""}>Todos</option><option value="quote" ${filters.type === "quote" ? "selected" : ""}>Cotizaciones</option><option value="ticket" ${filters.type === "ticket" ? "selected" : ""}>Tickets</option></select></div>
              <div class="tc-field-028l"><label>Estado</label><select data-tqt-status-028o><option value="all" ${filters.status === "all" || !filters.status ? "selected" : ""}>Todos</option><option value="pending" ${filters.status === "pending" ? "selected" : ""}>Pendientes</option><option value="approved" ${filters.status === "approved" ? "selected" : ""}>Aprobadas</option><option value="scheduled" ${filters.status === "scheduled" ? "selected" : ""}>Programadas</option><option value="billed" ${filters.status === "billed" ? "selected" : ""}>Facturadas</option></select></div>
              <button class="mp-button" type="button" data-tqt-apply-028o style="align-self:end">Buscar</button>
            </div>
          </section>
        </div>

        <section class="tc-panel-028l">
          <h3>Cotizaciones y tickets generados</h3>
          <div style="overflow:auto">
            <table class="tc-table-028l" style="min-width:1180px">
              <thead>
                <tr><th>Documento</th><th>Cliente</th><th>Ruta</th><th>Valor</th><th>Checks</th><th>Acciones</th></tr>
              </thead>
              <tbody>${transportQuoteRows028O(documents, session)}</tbody>
            </table>
          </div>
        </section>
      `;
      bindActions(filters, customerMap);
    }

    function nextFilters() {
      return {
        search: card.querySelector("[data-tqt-search-028o]")?.value || "",
        type: card.querySelector("[data-tqt-type-028o]")?.value || "all",
        status: card.querySelector("[data-tqt-status-028o]")?.value || "all"
      };
    }

    function bindActions(currentFilters = {}, customerMap = new Map()) {
      card.querySelector("[data-tqt-refresh-028o]")?.addEventListener("click", () => renderBody(currentFilters));
      card.querySelector("[data-tqt-apply-028o]")?.addEventListener("click", () => renderBody(nextFilters()));
      card.querySelector("[data-tqt-search-028o]")?.addEventListener("keydown", (event) => {
        if (event.key === "Enter") renderBody(nextFilters());
      });
      const quoteForm = card.querySelector("[data-tqt-form-028o]");
      quoteForm?.elements?.client_name?.addEventListener("input", (event) => {
        const match = customerMap.get(normalizeTransportLookup028L(event.target.value || ""));
        if (match) fillTransportQuoteCustomer028O(quoteForm, match);
      });
      ["ticket_count", "unit_amount", "discount_amount"].forEach((name) => {
        quoteForm?.elements?.[name]?.addEventListener("input", () => transportQuoteRecalculateTotals028O(quoteForm));
      });
      card.querySelector("[data-tqt-form-028o]")?.addEventListener("submit", async (event) => {
        event.preventDefault();
        const form = event.currentTarget;
        const data = new FormData(form);
        const ticketCount = Math.max(1, Math.round(transportQuoteMoneyValue028O(data.get("ticket_count")) || 1));
        const unitAmount = transportQuoteMoneyValue028O(data.get("unit_amount") || data.get("value_amount"));
        const valueAmount = Math.max(0, ticketCount * unitAmount);
        const discountAmount = transportQuoteMoneyValue028O(data.get("discount_amount"));
        const totalAmount = Math.max(0, valueAmount - discountAmount);
        const documentType = String(data.get("document_type") || "quote");
        const payload = {
          document_type: documentType,
          status: String(data.get("status") || (documentType === "ticket" ? "scheduled" : "approved")),
          client_name: String(data.get("client_name") || "").trim(),
          client_type: String(data.get("client_type") || "company"),
          phone: String(data.get("phone") || "").trim(),
          email: String(data.get("email") || "").trim(),
          document_id: String(data.get("document_id") || "").trim(),
          contract_code: String(data.get("contract_code") || "").trim(),
          account_code: String(data.get("account_code") || "").trim(),
          validity_date: String(data.get("validity_date") || "").trim(),
          origin: String(data.get("origin") || "").trim(),
          destination: String(data.get("destination") || "").trim(),
          route_detail: String(data.get("route_detail") || "").trim(),
          service_date: String(data.get("service_date") || "").trim(),
          ticket_count: ticketCount,
          authorized_people: [{
            document_id: String(data.get("person_document") || data.get("document_id") || "").trim(),
            name: String(data.get("person_name") || data.get("client_name") || "").trim(),
            ticket_count: ticketCount
          }],
          transporter: String(data.get("transporter") || "").trim(),
          value_amount: valueAmount,
          discount_amount: discountAmount,
          total_amount: totalAmount,
          charged_to_contract: data.has("charged_to_contract"),
          approval_code: String(data.get("approval_code") || "").trim(),
          advisor_name: String(data.get("advisor_name") || advisorName || "").trim(),
          supervisor_check: false,
          treasury_check: false,
          notes: String(data.get("notes") || "").trim()
        };
        const message = card.querySelector("[data-tqt-message-028o]");
        if (!payload.client_name || !payload.origin || !payload.destination) {
          if (message) {
            message.classList.remove("ok");
            message.textContent = "Cliente, origen y destino son obligatorios.";
          }
          return;
        }
        try {
          if (message) {
            message.classList.add("ok");
            message.textContent = "Creando documento...";
          }
          const created = await transportQuoteApi028O("/documents", { method: "POST", body: JSON.stringify(payload) });
          await renderBody(currentFilters);
          const nextMessage = card.querySelector("[data-tqt-message-028o]");
          const delivery = created?.whatsapp_delivery || {};
          if (nextMessage) {
            nextMessage.classList.toggle("ok", delivery.status !== "send_failed" && delivery.status !== "phone_missing");
            nextMessage.textContent = delivery.ok
              ? "Documento creado y enviado por WhatsApp."
              : delivery.status === "phone_missing"
                ? "Documento creado. El cliente no tiene telefono para WhatsApp."
                : delivery.status === "send_failed"
                  ? "Documento creado. WhatsApp no pudo enviarlo; queda disponible para reintento."
                  : "Documento creado correctamente.";
          }
        } catch (error) {
          if (message) {
            message.classList.remove("ok");
            message.textContent = error.message || "No se pudo crear el documento.";
          }
        }
      });
      card.querySelectorAll("[data-tqt-print-028o]").forEach((button) => {
        button.addEventListener("click", () => window.open(transportQuotePdfUrl028O(button.getAttribute("data-tqt-print-028o") || "", true), "_blank", "noopener"));
      });
      card.querySelectorAll("[data-tqt-download-028o]").forEach((button) => {
        button.addEventListener("click", () => window.open(transportQuotePdfUrl028O(button.getAttribute("data-tqt-download-028o") || "", false), "_blank", "noopener"));
      });
      card.querySelectorAll("[data-tqt-convert-028o]").forEach((button) => {
        button.addEventListener("click", async () => {
          const id = button.getAttribute("data-tqt-convert-028o") || "";
          if (!id) return;
          button.disabled = true;
          button.textContent = "Convirtiendo...";
          try {
            await transportQuoteApi028O(`/documents/${encodeURIComponent(id)}/convert-ticket`, { method: "POST" });
            await renderBody(currentFilters);
          } catch (error) {
            button.disabled = false;
            button.textContent = "Convertir a ticket";
            alert(error.message || "No se pudo convertir a ticket.");
          }
        });
      });
      card.querySelectorAll("[data-tqt-check-028o]").forEach((button) => {
        button.addEventListener("click", async () => {
          const id = button.getAttribute("data-tqt-check-028o") || "";
          const field = button.getAttribute("data-tqt-check-field-028o") || "";
          const allowed = (field === "supervisor_check" && transportQuoteCanCheckSupervisor028O(session)) || (field === "treasury_check" && transportQuoteCanCheckTreasury028O(session));
          if (!id || !allowed) return;
          button.disabled = true;
          button.textContent = "Validando...";
          try {
            await transportQuoteApi028O(`/documents/${encodeURIComponent(id)}`, {
              method: "PATCH",
              body: JSON.stringify({ [field]: true })
            });
            await renderBody(currentFilters);
          } catch (error) {
            button.disabled = false;
            button.textContent = field === "supervisor_check" ? "Check supervisor" : "Check tesoreria";
            alert(error.message || "No se pudo aplicar el check.");
          }
        });
      });
    }

    const closeTransportQuotesModal028O = () => {
      document.removeEventListener("keydown", onTransportQuotesKeydown028O);
      overlay.remove();
    };
    const onTransportQuotesKeydown028O = (event) => {
      if (event.key === "Escape") closeTransportQuotesModal028O();
    };
    document.addEventListener("keydown", onTransportQuotesKeydown028O);
    overlay.addEventListener("click", (event) => {
      if (event.target.closest("[data-tqt-close-028o]")) closeTransportQuotesModal028O();
    });

    await renderBody({ search: "", type: "all", status: "all" });
  }
  /* CLONEXA_028O_TRANSPORT_QUOTES_TICKETS_MINIPANEL_END */
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
    const storeTotals024A_R1 = (typeof isStorePanel023W === "function" && isStorePanel023W() && typeof storeTeamTotals024A_R1 === "function")
      ? storeTeamTotals024A_R1()
      : null;
    const hasStoreTotals024A_R1 = Boolean(storeTotals024A_R1 && typeof storeTeamMembers024A_R1 === "function" && storeTeamMembers024A_R1().length);
    const salesTotal = hasStoreTotals024A_R1 ? Number(storeTotals024A_R1.sales || 0) : Number(kpis.monthly_sales_total || 0);
    const goal = hasStoreTotals024A_R1 ? Number(storeTotals024A_R1.goal || 0) : Number(kpis.monthly_goal || 0);
    const goalPct = goal > 0 ? Math.min(100, Math.round((salesTotal / goal) * 100)) : 0;
    const promotions = Array.isArray(kpis.promotions) ? kpis.promotions.filter((item) => item && (item.message || item.title)) : [];
    const activePromotion = promotions[0] || null;
    const isFinished = operational.status === "finished";
    const dynamicModules019H = buildDynamicMiniPanelModules019H(moduleConfig || currentModuleConfig);
    const modulesHtml019H = renderDynamicModulesHtml019H(dynamicModules019H);

    const quotesEnabled021A = quotesModuleEnabled021A(moduleConfig || currentModuleConfig);
    const quotesSummary021A = currentQuotesSummary021A || defaultQuotesSummary021A();
    const quotesCardHtml021A = quotesEnabled021A ? `
            <article class="mp-kpi-card quotes" data-quotes-card role="button" tabindex="0">
              <span>Cotizaciones</span>
              <strong data-quotes-card-count>${h(`${Number(quotesSummary021A.active_count || 0)} activas`)}</strong>
              <small data-quotes-card-total>${h(`${quoteMoney021A(quotesSummary021A.total_amount || 0)} cotizado`)}</small>
              <small data-quotes-card-latest>${h(quotesSummary021A.latest ? `Última: ${quotesSummary021A.latest.quote_number || "cotización"} · ${quotesSummary021A.latest.client_name || "cliente"}` : "Sin cotizaciones registradas")}</small>
            </article>
    ` : "";

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

        ${storeActorStripHtml023W("dashboard")}

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
            ${quotesCardHtml021A}
            ${notesCardHtml020A}
<article class="mp-kpi-card wide">
              <span>Promociones / mensaje</span>
              <strong>${h(activePromotion ? (activePromotion.title || "Mensaje de ventas") : "Sin promociones activas")}</strong>
              <small>${h(activePromotion ? (activePromotion.message || "") : "Este espacio recibira campanas enviadas desde la consola de ventas.")}</small>
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
    bindStoreActorSelector023W();

    root.querySelector("[data-action='pause']")?.addEventListener("click", async () => {
      await runOperationalAction("pause", session);
    });

    root.querySelector("[data-action='resume']")?.addEventListener("click", async () => {
      await runOperationalAction("resume", session);
    });

    root.querySelector("[data-action='finish']")?.addEventListener("click", async () => {
      const msg = root.querySelector("[data-panel-message]");
      try {
        const updated = (typeof finishStoreTeamFromDashboard024A_R1 === "function")
          ? await finishStoreTeamFromDashboard024A_R1()
          : await operationalAction("finish");
        startTimers(updated.operational_session || updated);
        if (msg) msg.textContent = "Turno finalizado.";
        window.setTimeout(() => {
          clearTimer();
          clearMiniPanelToken024B();
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

    root.querySelector("[data-quotes-card]")?.addEventListener("click", async () => {
      await openQuotesEntry028O(session, "cotizacion");
    });

    root.querySelector("[data-quotes-card]")?.addEventListener("keydown", async (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        await openQuotesEntry028O(session, "cotizacion");
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
        if (typeof isTransportQuotesTicketsCode028O === "function" && isTransportQuotesTicketsCode028O(moduleCode)) {
          await openTransportQuotesTicketsModule028O(session);
          return;
        }

        if (isQuotesCode021A(moduleCode)) {
          await openQuotesEntry028O(session, moduleCode);
          return;
        }
        if (isNotesCode020A(moduleCode)) {
          await openNotesCalendar020A(session);
          return;
        }

        if (typeof isSalesRegisterCode022F === "function" && isSalesRegisterCode022F(moduleCode)) {
          await openSalesRegisterModule022F(session);
          return;
        }

        if (typeof isDayClosingCode023E === "function" && isDayClosingCode023E(moduleCode)) {
          await openDayClosingModule023E(session);
          return;
        }

        if (typeof isRequestsCode023T === "function" && isRequestsCode023T(moduleCode)) {
          await openRequestsModule023T(session);
          return;
        }

        if (typeof isFieldOpsCode024A_R1 === "function" && isFieldOpsCode024A_R1(moduleCode)) {
          await openFieldOpsMiniPanel024A_R1(session);
          return;
        }

        if (typeof isStoreShiftControlCode023W === "function" && isStoreShiftControlCode023W(moduleCode)) {
          await openStoreShiftControlModule023W(session);
          return;
        }

        if (typeof isTransportCallsCode028L === "function" && isTransportCallsCode028L(moduleCode)) {
          await openTransportCallsModule028L(session);
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

  /* CLONEXA_022F_REGISTRO_VENTA_DINAMICO_REFERENCIAS_START */
  const CX_SALES_REGISTER_CODES_022F = new Set([
    "registro_venta",
    "registro_ventas",
    "registro_de_venta",
    "registro_ventas",
    "sales_register",
    "register_sale",
    "register_sales",
    "venta",
    "ventas"
  ]);

  function isSalesRegisterCode022F(code) {
    return CX_SALES_REGISTER_CODES_022F.has(normalizeModuleCode019H(code));
  }

  function salesRegisterStyles022F() {
    if (document.getElementById("cxSalesRegisterStyles022F")) return;
    const style = document.createElement("style");
    style.id = "cxSalesRegisterStyles022F";
    style.textContent = `
      .sr-shell-022f{min-height:100vh;padding:28px;background:radial-gradient(circle at top left,rgba(255,44,200,.25),transparent 34%),linear-gradient(135deg,#14081f,#07142b);color:#fff}
      .sr-card-022f{background:rgba(255,255,255,.08);border:1px solid rgba(255,255,255,.16);border-radius:28px;box-shadow:0 24px 80px rgba(0,0,0,.35);backdrop-filter:blur(18px)}
      .sr-hero-022f{padding:28px;margin-bottom:18px;display:flex;align-items:flex-start;justify-content:space-between;gap:16px}
      .sr-kicker-022f{font-size:11px;font-weight:900;letter-spacing:.34em;text-transform:uppercase;color:#ff39d0}
      .sr-title-022f{font-size:42px;line-height:1;margin:10px 0 6px;font-weight:950}
      .sr-muted-022f{color:rgba(255,255,255,.72);font-weight:700}
      .sr-btn-022f{border:0;border-radius:18px;padding:13px 18px;color:#fff;background:linear-gradient(135deg,#ff25bb,#6d4cff);font-weight:900;cursor:pointer}
      .sr-btn-022f.secondary{background:rgba(255,255,255,.12);border:1px solid rgba(255,255,255,.16)}
      .sr-grid-022f{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:16px}
      .sr-category-022f{min-height:170px;text-align:left;padding:20px;border-radius:24px;border:1px solid rgba(255,255,255,.18);background:linear-gradient(135deg,rgba(255,255,255,.11),rgba(255,255,255,.04));color:#fff;cursor:pointer;box-shadow:0 18px 50px rgba(0,0,0,.25)}
      .sr-category-022f:hover{transform:translateY(-2px);border-color:rgba(255,57,208,.65)}
      .sr-icon-022f{width:70px;height:70px;border-radius:24px;display:grid;place-items:center;font-size:34px;background:radial-gradient(circle at 20% 20%,rgba(255,57,208,.7),rgba(46,166,255,.35))}
      .sr-category-022f strong{display:block;font-size:22px;margin-top:18px}
      .sr-category-022f small{display:block;margin-top:6px;color:rgba(255,255,255,.68);font-weight:800}
      .sr-layout-022f{display:grid;grid-template-columns:minmax(0,1.2fr) minmax(360px,.8fr);gap:18px}
      .sr-panel-022f{padding:22px}
      .sr-field-022f label{display:block;font-size:11px;letter-spacing:.14em;text-transform:uppercase;font-weight:950;color:rgba(255,255,255,.72);margin:0 0 7px}
      .sr-field-022f input,.sr-field-022f select,.sr-field-022f textarea{width:100%;box-sizing:border-box;border:1px solid rgba(255,255,255,.16);border-radius:16px;background:rgba(4,7,23,.52);color:#fff;padding:14px 15px;font-weight:800;outline:none}
      .sr-form-grid-022f{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}
      .sr-ref-list-022f{display:grid;gap:10px;max-height:360px;overflow:auto;margin-top:14px}
      .sr-ref-022f{width:100%;text-align:left;border:1px solid rgba(255,255,255,.13);background:rgba(255,255,255,.07);color:#fff;border-radius:18px;padding:13px 14px;cursor:pointer}
      .sr-ref-022f.active{border-color:#ff39d0;background:rgba(255,57,208,.16)}
      .sr-sales-list-022f{display:grid;gap:10px;margin-top:14px}
      .sr-sale-022f{border:1px solid rgba(255,255,255,.12);border-radius:18px;background:rgba(255,255,255,.07);padding:14px}
      .sr-sale-022f strong{display:flex;justify-content:space-between;gap:12px}
      .sr-badge-022f{display:inline-flex;border-radius:999px;background:rgba(255,57,208,.22);padding:7px 10px;font-weight:950;font-size:12px}
      .sr-message-022f{margin-top:12px;font-weight:900;color:#76ffd5}
      @media(max-width:980px){.sr-grid-022f,.sr-layout-022f{grid-template-columns:1fr}.sr-title-022f{font-size:34px}}
    `;
    document.head.appendChild(style);
  }

  async function salesApi022F(path, options = {}) {
    const headers = {
      ...authHeaders(),
      "Content-Type": "application/json",
      ...(options.headers || {})
    };
    return api(`/api/v1/mini-panel-sales/companies/${encodeURIComponent(companyId)}${path}`, {
      ...options,
      headers
    });
  }

  function categoryIcon022F(item) {
    return item?.icon || "✨";
  }

  async function openSalesRegisterModule022F(session) {
    salesRegisterStyles022F();
    let categories = [];
    let sales = [];
    let config = {};
    let loadError = "";

    try {
      config = await salesApi022F(`/config`);
      const cats = await salesApi022F(`/categories?panel_type=${encodeURIComponent(panelType)}`);
      categories = Array.isArray(cats.items) ? cats.items : [];
      const salesData = await salesApi022F(`/sales?panel_type=${encodeURIComponent(panelType)}`);
      sales = Array.isArray(salesData.items) ? salesData.items : [];
    } catch (error) {
      loadError = error.message || "No se pudo cargar Registro Venta.";
    }

    const totalAmount = sales.filter((item) => item.status !== "archived").reduce((sum, item) => sum + Number(item.total || 0), 0);

    root.innerHTML = `
      <main class="sr-shell-022f">
        <header class="sr-card-022f sr-hero-022f">
          <div>
            <div class="sr-kicker-022f">Registro venta</div>
            <h1 class="sr-title-022f">Venta operativa</h1>
            <p class="sr-muted-022f">${h(session?.company?.name || "Empresa")} · ${h(labelType(panelType))} · ${h(session?.employee?.full_name || session?.user?.full_name || "usuario")}</p>
          </div>
          <button class="sr-btn-022f secondary" type="button" data-sr-back-022f>Volver</button>
        </header>

        ${storeActorStripHtml023W("ventas")}

        <section class="sr-layout-022f">
          <div class="sr-card-022f sr-panel-022f">
            <div class="sr-kicker-022f">Categorías</div>
            <h2>Selecciona una categoría</h2>
            <p class="sr-muted-022f">Las referencias salen del módulo Referencias con canal Sistema o Ambos.</p>
            ${loadError ? `<div class="sr-message-022f" style="color:#ff9aae">${h(loadError)}</div>` : ""}
            <div class="sr-grid-022f">
              ${categories.map((item) => `
                <button class="sr-category-022f" type="button" data-sr-category-022f="${h(item.category || "")}">
                  <div class="sr-icon-022f">${h(categoryIcon022F(item))}</div>
                  <strong>${h(item.category || "Categoria")}</strong>
                  <small>${Number(item.count || 0)} referencias</small>
                </button>
              `).join("") || `<div class="sr-muted-022f">No hay categorías disponibles. Crea referencias con canal Sistema o Ambos.</div>`}
            </div>
          </div>

          <aside class="sr-card-022f sr-panel-022f">
            <div class="sr-kicker-022f">Mis ventas</div>
            <h2>${sales.length} registros</h2>
            <p class="sr-muted-022f">${h(formatMoney(totalAmount))} registrado por este usuario.</p>
            <div class="sr-sales-list-022f">
              ${sales.slice(0, 8).map((item) => `
                <article class="sr-sale-022f">
                  <strong><span>${h(item.reference_name)}</span><span>${h(formatMoney(item.total))}</span></strong>
                  <small>${h(item.reference_category || "Sin categoria")} · ${h(item.quantity)} und · ${h(item.payment_method || "")}</small>
                </article>
              `).join("") || `<div class="sr-muted-022f">Aún no tienes ventas registradas.</div>`}
            </div>
          </aside>
        </section>
      </main>
    `;

    bindStoreActorSelector023W();

    root.querySelector("[data-sr-back-022f]")?.addEventListener("click", () => bootShell());
    root.querySelectorAll("[data-sr-category-022f]").forEach((button) => {
      button.addEventListener("click", async () => {
        await renderSalesRegisterCategory022F(session, button.getAttribute("data-sr-category-022f") || "");
      });
    });
  }

  async function renderSalesRegisterCategory022F(session, category, search = "") {
    salesRegisterStyles022F();
    let refs = [];
    let sales = [];
    let selected = null;
    let loadError = "";

    async function loadRefs(q = "") {
      const params = new URLSearchParams();
      if (category) params.set("category", category);
      if (q) params.set("q", q);
      const data = await salesApi022F(`/references?${params.toString()}`);
      return Array.isArray(data.items) ? data.items : [];
    }

    try {
      refs = await loadRefs(search);
      const salesData = await salesApi022F(`/sales?panel_type=${encodeURIComponent(panelType)}`);
      sales = Array.isArray(salesData.items) ? salesData.items : [];
    } catch (error) {
      loadError = error.message || "No se pudieron cargar referencias.";
    }

    function renderRefButtons(items) {
      return (items || []).map((item) => `
        <button class="sr-ref-022f" type="button"
          data-sr-ref-022f="${h(item.id || "")}"
          data-sr-ref-name="${h(item.name || "")}"
          data-sr-ref-category="${h(item.category || category || "")}"
          data-sr-ref-size="${h(item.size || "")}"
          data-sr-ref-color="${h(item.color || "")}">
          <strong>${h(item.name || "Referencia")}</strong><br>
          <small>${h([item.category, item.size, item.color].filter(Boolean).join(" · "))}</small>
        </button>
      `).join("") || `<div class="sr-muted-022f">Sin referencias para esta categoría.</div>`;
    }

    root.innerHTML = `
      <main class="sr-shell-022f">
        <header class="sr-card-022f sr-hero-022f">
          <div>
            <div class="sr-kicker-022f">Registro venta</div>
            <h1 class="sr-title-022f">${h(category || "Categoría")}</h1>
            <p class="sr-muted-022f">Busca la referencia y registra la venta.</p>
          </div>
          <div style="display:flex;gap:10px;flex-wrap:wrap">
            <button class="sr-btn-022f secondary" type="button" data-sr-categories-022f>Categorías</button>
            <button class="sr-btn-022f secondary" type="button" data-sr-back-022f>Dashboard</button>
          </div>
        </header>

        <section class="sr-layout-022f">
          <section class="sr-card-022f sr-panel-022f">
            <div class="sr-kicker-022f">Referencia</div>
            <div class="sr-field-022f">
              <label>Filtro inteligente</label>
              <input id="srSearch022F" value="${h(search)}" placeholder="Escribe referencia, talla, color..." />
            </div>
            <div class="sr-ref-list-022f" id="srRefList022F">
              ${renderRefButtons(refs)}
            </div>
          </section>

          <aside class="sr-card-022f sr-panel-022f">
            <div class="sr-kicker-022f">Captura</div>
            <h2>Nueva venta</h2>
            <div class="sr-message-022f" id="srSelected022F">Selecciona una referencia.</div>
            <form id="srForm022F" style="margin-top:14px">
              <input type="hidden" id="srRefId022F" />
              <input type="hidden" id="srRefName022F" />
              <input type="hidden" id="srRefCategory022F" />
              <input type="hidden" id="srRefSize022F" />
              <input type="hidden" id="srRefColor022F" />

              <div class="sr-form-grid-022f">
                <div class="sr-field-022f">
                  <label>Cantidad</label>
                  <input id="srQty022F" type="number" min="0" step="1" value="1" />
                </div>
                <div class="sr-field-022f">
                  <label>Valor unitario</label>
                  <input id="srUnit022F" type="number" min="0" step="100" value="0" />
                </div>
                <div class="sr-field-022f">
                  <label>Forma de pago</label>
                  <select id="srPay022F">
                    <option value="efectivo">Efectivo</option>
                    <option value="transferencia">Transferencia</option>
                    <option value="tarjeta">Tarjeta</option>
                    <option value="cheque">Cheque</option>
                    <option value="otro">Otro</option>
                  </select>
                </div>
                <div class="sr-field-022f">
                  <label>Total</label>
                  <input id="srTotal022F" readonly value="${h(formatMoney(0))}" />
                </div>
              </div>
              <div class="sr-field-022f" style="margin-top:14px">
                <label>Observación</label>
                <textarea id="srNotes022F" rows="3" placeholder="Opcional"></textarea>
              </div>
              <button class="sr-btn-022f" type="submit" style="margin-top:14px;width:100%">Guardar venta</button>
              <div class="sr-message-022f" id="srMsg022F">${loadError ? h(loadError) : ""}</div>
            </form>

            <div class="sr-sales-list-022f">
              ${sales.slice(0, 5).map((item) => `
                <article class="sr-sale-022f">
                  <strong><span>${h(item.reference_name)}</span><span>${h(formatMoney(item.total))}</span></strong>
                  <small>${h(item.reference_category || "")} · ${h(item.quantity)} und</small>
                </article>
              `).join("")}
            </div>
          </aside>
        </section>
      </main>
    `;

    const backBtn = root.querySelector("[data-sr-back-022f]");
    if (backBtn) backBtn.addEventListener("click", () => bootShell());

    root.querySelector("[data-sr-categories-022f]")?.addEventListener("click", async () => {
      await openSalesRegisterModule022F(session);
    });

    const searchInput = root.querySelector("#srSearch022F");
    let searchTimer = null;
    searchInput?.addEventListener("input", () => {
      clearTimeout(searchTimer);
      searchTimer = setTimeout(async () => {
        try {
          const nextRefs = await loadRefs(searchInput.value || "");
          const list = root.querySelector("#srRefList022F");
          if (list) list.innerHTML = renderRefButtons(nextRefs);
          bindRefs();
        } catch (error) {
          const msg = root.querySelector("#srMsg022F");
          if (msg) msg.textContent = error.message || "No se pudo buscar.";
        }
      }, 280);
    });

    function updateTotal() {
      const qty = Number(root.querySelector("#srQty022F")?.value || 0);
      const unit = Number(root.querySelector("#srUnit022F")?.value || 0);
      const total = Math.max(0, qty) * Math.max(0, unit);
      const totalInput = root.querySelector("#srTotal022F");
      if (totalInput) totalInput.value = formatMoney(total);
    }

    root.querySelector("#srQty022F")?.addEventListener("input", updateTotal);
    root.querySelector("#srUnit022F")?.addEventListener("input", updateTotal);

    function bindRefs() {
      root.querySelectorAll("[data-sr-ref-022f]").forEach((button) => {
        button.addEventListener("click", () => {
          root.querySelectorAll("[data-sr-ref-022f]").forEach((item) => item.classList.remove("active"));
          button.classList.add("active");
          selected = {
            id: button.getAttribute("data-sr-ref-022f") || "",
            name: button.getAttribute("data-sr-ref-name") || "",
            category: button.getAttribute("data-sr-ref-category") || "",
            size: button.getAttribute("data-sr-ref-size") || "",
            color: button.getAttribute("data-sr-ref-color") || ""
          };
          root.querySelector("#srRefId022F").value = selected.id;
          root.querySelector("#srRefName022F").value = selected.name;
          root.querySelector("#srRefCategory022F").value = selected.category;
          root.querySelector("#srRefSize022F").value = selected.size;
          root.querySelector("#srRefColor022F").value = selected.color;
          const selectedBox = root.querySelector("#srSelected022F");
          if (selectedBox) selectedBox.textContent = `${selected.name} · ${[selected.size, selected.color].filter(Boolean).join(" · ")}`;
        });
      });
    }
    bindRefs();

    root.querySelector("#srForm022F")?.addEventListener("submit", async (event) => {
      event.preventDefault();
      const msg = root.querySelector("#srMsg022F");
      const referenceName = root.querySelector("#srRefName022F")?.value || "";
      if (!referenceName) {
        if (msg) msg.textContent = "Selecciona una referencia antes de guardar.";
        return;
      }
      try {
        if (msg) msg.textContent = "Guardando venta...";
        await salesApi022F(`/sales?panel_type=${encodeURIComponent(panelType)}`, {
          method: "POST",
          body: JSON.stringify({
            reference_id: root.querySelector("#srRefId022F")?.value || "",
            reference_name: referenceName,
            reference_category: root.querySelector("#srRefCategory022F")?.value || category || "",
            reference_size: root.querySelector("#srRefSize022F")?.value || "",
            reference_color: root.querySelector("#srRefColor022F")?.value || "",
            quantity: Number(root.querySelector("#srQty022F")?.value || 0),
            unit_price: Number(root.querySelector("#srUnit022F")?.value || 0),
            payment_method: root.querySelector("#srPay022F")?.value || "efectivo",
            notes: root.querySelector("#srNotes022F")?.value || ""
          })
        });
        if (msg) msg.textContent = "Venta registrada.";
        await renderSalesRegisterCategory022F(session, category, searchInput?.value || "");
      } catch (error) {
        if (msg) msg.textContent = error.message || "No se pudo guardar la venta.";
      }
    });
  }

  /* CLONEXA_022G_SALES_PIPELINE_ALISTAMIENTO_SOPORTES_GUIA_START */
  function salesPipelineStyles022G() {
    salesRegisterStyles022F();
    if (document.getElementById("cxSalesPipelineStyles022G")) return;
    const style = document.createElement("style");
    style.id = "cxSalesPipelineStyles022G";
    style.textContent = `
      .sr-pipeline-022g{display:flex;gap:8px;flex-wrap:wrap;margin-top:10px}
      .sr-pill-022g{display:inline-flex;align-items:center;gap:6px;border-radius:999px;padding:7px 10px;background:rgba(255,255,255,.10);border:1px solid rgba(255,255,255,.14);font-size:12px;font-weight:950;color:#fff}
      .sr-pill-022g.ok{background:rgba(41,255,187,.14);border-color:rgba(41,255,187,.34);color:#90ffd9}
      .sr-pill-022g.warn{background:rgba(255,208,86,.13);border-color:rgba(255,208,86,.32);color:#ffd980}
      .sr-file-label-022g{display:inline-flex;align-items:center;justify-content:center;border-radius:14px;padding:10px 12px;background:rgba(255,255,255,.10);border:1px solid rgba(255,255,255,.16);font-weight:950;cursor:pointer;font-size:12px}
      .sr-file-label-022g input{display:none}
      .sr-mini-actions-022g{display:flex;gap:8px;flex-wrap:wrap;margin-top:12px}
      .sr-mini-actions-022g button{border:0;border-radius:14px;padding:10px 12px;color:#fff;background:rgba(255,255,255,.12);border:1px solid rgba(255,255,255,.14);font-weight:950;cursor:pointer}
      .sr-mini-actions-022g button.primary{background:linear-gradient(135deg,#ff25bb,#6d4cff);border:0}
      .sr-mini-actions-022g button.danger{background:rgba(255,74,124,.17);border-color:rgba(255,74,124,.45)}
    `;
    document.head.appendChild(style);
  }

  function salesPipelineStatusLabel022G(item) {
    const status = String(item?.pipeline_status || item?.status || "active").toLowerCase();
    if (status === "archived") return "Archivada";
    if (item?.has_guide || status === "guide_attached") return "Guía recibida";
    if (item?.has_support || status === "support_attached") return "Soporte adjunto";
    if (item?.is_prepared || status === "prepared") return "Alistado";
    return "Registrada";
  }

  function salesFileToDataUrl022G(file) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result || ""));
      reader.onerror = () => reject(new Error("No se pudo leer el archivo."));
      reader.readAsDataURL(file);
    });
  }

  function salesOpenFile022G(file) {
    if (!file?.file_data) return;
    const win = window.open("", "_blank");
    if (!win) return;
    const safeType = String(file.file_type || "");
    const src = file.file_data;
    if (safeType.includes("pdf")) {
      win.document.write(`<iframe src="${src}" style="width:100%;height:100vh;border:0"></iframe>`);
    } else {
      win.document.write(`<img src="${src}" style="max-width:100%;height:auto;display:block;margin:auto" />`);
    }
  }

  function salesDownloadFile022G(file, fallbackName = "archivo") {
    if (!file?.file_data) return;
    const a = document.createElement("a");
    a.href = file.file_data;
    a.download = file.file_name || fallbackName;
    document.body.appendChild(a);
    a.click();
    a.remove();
  }

  function salesPrintFile022G(file) {
    if (!file?.file_data) return;
    const win = window.open("", "_blank");
    if (!win) return;
    const src = file.file_data;
    const isPdf = String(file.file_type || "").includes("pdf");
    win.document.write(isPdf
      ? `<iframe src="${src}" style="width:100%;height:100vh;border:0"></iframe><script>setTimeout(()=>print(),900)<\/script>`
      : `<img src="${src}" style="max-width:100%;height:auto;display:block;margin:auto" onload="print()" />`);
  }

  function salesCardHtml022G(item) {
    const support = item?.support || null;
    const guide = item?.guide || null;
    const archived = String(item?.status || "").toLowerCase() === "archived";
    return `
      <article class="sr-sale-022f">
        <strong><span>${h(item.reference_name || "Venta")}</span><span>${h(formatMoney(item.total || 0))}</span></strong>
        <small>${h(item.reference_category || "Sin categoria")} · ${h(item.quantity)} und · ${h(item.payment_method || "")}</small>
        <div class="sr-pipeline-022g">
          <span class="sr-pill-022g ok">Venta registrada</span>
          <span class="sr-pill-022g ${item.is_prepared ? "ok" : "warn"}">${item.is_prepared ? "Pedido alistado" : "Pendiente alistar"}</span>
          <span class="sr-pill-022g ${item.has_support ? "ok" : "warn"}">${item.has_support ? "Soporte adjunto" : "Sin soporte"}</span>
          <span class="sr-pill-022g ${item.has_guide ? "ok" : "warn"}">${item.has_guide ? "Guía recibida" : "Sin guía"}</span>
        </div>
        <div class="sr-mini-actions-022g">
          ${!item.is_prepared && !archived ? `<button class="primary" type="button" data-sr-prepare-022g="${h(item.id)}">Marcar alistado</button>` : ""}
          ${support ? `
            <button type="button" data-sr-open-support-022g="${h(item.id)}">Ver soporte</button>
            <button type="button" data-sr-download-support-022g="${h(item.id)}">Descargar soporte</button>
          ` : (!archived ? `
            <label class="sr-file-label-022g">Adjuntar factura/comprobante
              <input type="file" accept="image/*,.pdf" data-sr-support-file-022g="${h(item.id)}">
            </label>
          ` : "")}
          ${guide ? `
            <button class="primary" type="button" data-sr-open-guide-022g="${h(item.id)}">Ver guía</button>
            <button type="button" data-sr-download-guide-022g="${h(item.id)}">Descargar guía</button>
            <button type="button" data-sr-print-guide-022g="${h(item.id)}">Imprimir guía</button>
          ` : ""}
          ${!archived ? `<button class="danger" type="button" data-sr-archive-022g="${h(item.id)}">Guardar / archivar</button>` : `<span class="sr-pill-022g">Archivada</span>`}
        </div>
      </article>
    `;
  }

  function bindSalesPipelineActions022G(session, sales, refreshFn) {
    const salesById = new Map((sales || []).map((item) => [String(item.id), item]));

    root.querySelectorAll("[data-sr-prepare-022g]").forEach((button) => {
      button.addEventListener("click", async () => {
        const id = button.getAttribute("data-sr-prepare-022g");
        button.disabled = true;
        await salesApi022F(`/sales/${encodeURIComponent(id)}/prepared?panel_type=${encodeURIComponent(panelType)}`, {
          method: "POST",
          body: JSON.stringify({ prepared: true })
        });
        await refreshFn();
      });
    });

    root.querySelectorAll("[data-sr-support-file-022g]").forEach((input) => {
      input.addEventListener("change", async () => {
        const file = input.files && input.files[0];
        const id = input.getAttribute("data-sr-support-file-022g");
        if (!file || !id) return;
        const dataUrl = await salesFileToDataUrl022G(file);
        await salesApi022F(`/sales/${encodeURIComponent(id)}/support?panel_type=${encodeURIComponent(panelType)}`, {
          method: "POST",
          body: JSON.stringify({
            file_name: file.name || "soporte",
            file_type: file.type || "application/octet-stream",
            file_data: dataUrl
          })
        });
        await refreshFn();
      });
    });

    root.querySelectorAll("[data-sr-open-support-022g]").forEach((button) => {
      button.addEventListener("click", () => salesOpenFile022G(salesById.get(button.getAttribute("data-sr-open-support-022g"))?.support));
    });

    root.querySelectorAll("[data-sr-download-support-022g]").forEach((button) => {
      button.addEventListener("click", () => salesDownloadFile022G(salesById.get(button.getAttribute("data-sr-download-support-022g"))?.support, "soporte"));
    });

    root.querySelectorAll("[data-sr-open-guide-022g]").forEach((button) => {
      button.addEventListener("click", () => salesOpenFile022G(salesById.get(button.getAttribute("data-sr-open-guide-022g"))?.guide));
    });

    root.querySelectorAll("[data-sr-download-guide-022g]").forEach((button) => {
      button.addEventListener("click", () => salesDownloadFile022G(salesById.get(button.getAttribute("data-sr-download-guide-022g"))?.guide, "guia_envio"));
    });

    root.querySelectorAll("[data-sr-print-guide-022g]").forEach((button) => {
      button.addEventListener("click", () => salesPrintFile022G(salesById.get(button.getAttribute("data-sr-print-guide-022g"))?.guide));
    });

    root.querySelectorAll("[data-sr-archive-022g]").forEach((button) => {
      button.addEventListener("click", async () => {
        const id = button.getAttribute("data-sr-archive-022g");
        if (!id) return;
        if (!confirm("Archivar esta venta? Saldrá de la vista principal y quedará consultable por búsqueda.")) return;
        button.disabled = true;
        await salesApi022F(`/sales/${encodeURIComponent(id)}/archive?panel_type=${encodeURIComponent(panelType)}`, {
          method: "POST",
          body: JSON.stringify({})
        });
        await refreshFn();
      });
    });
  }

  async function openSalesRegisterModule022F(session) {
    salesPipelineStyles022G();
    let categories = [];
    let sales = [];
    let loadError = "";

    try {
      const cats = await salesApi022F(`/categories?panel_type=${encodeURIComponent(panelType)}`);
      categories = Array.isArray(cats.items) ? cats.items : [];
      const salesData = await salesApi022F(`/sales?panel_type=${encodeURIComponent(panelType)}`);
      sales = Array.isArray(salesData.items) ? salesData.items : [];
    } catch (error) {
      loadError = error.message || "No se pudo cargar Registro Venta.";
    }

    const activeSales = sales.filter((item) => item.status !== "archived");
    const totalAmount = activeSales.reduce((sum, item) => sum + Number(item.total || 0), 0);

    root.innerHTML = `
      <main class="sr-shell-022f">
        <header class="sr-card-022f sr-hero-022f">
          <div>
            <div class="sr-kicker-022f">Registro venta</div>
            <h1 class="sr-title-022f">Venta operativa</h1>
            <p class="sr-muted-022f">${h(session?.company?.name || "Empresa")} · ${h(labelType(panelType))} · ${h(session?.employee?.full_name || session?.user?.full_name || "usuario")}</p>
          </div>
          <button class="sr-btn-022f secondary" type="button" data-sr-back-022f>Volver</button>
        </header>

        <section class="sr-layout-022f">
          <div class="sr-card-022f sr-panel-022f">
            <div class="sr-kicker-022f">Categorías</div>
            <h2>Selecciona una categoría</h2>
            <p class="sr-muted-022f">Las referencias salen del módulo Referencias con canal Sistema o Ambos.</p>
            ${loadError ? `<div class="sr-message-022f" style="color:#ff9aae">${h(loadError)}</div>` : ""}
            <div class="sr-grid-022f">
              ${categories.map((item) => `
                <button class="sr-category-022f" type="button" data-sr-category-022f="${h(item.category || "")}">
                  <div class="sr-icon-022f">${h(categoryIcon022F(item))}</div>
                  <strong>${h(item.category || "Categoria")}</strong>
                  <small>${Number(item.count || 0)} referencias</small>
                </button>
              `).join("") || `<div class="sr-muted-022f">No hay categorías disponibles. Crea referencias con canal Sistema o Ambos.</div>`}
            </div>
          </div>

          <aside class="sr-card-022f sr-panel-022f">
            <div class="sr-kicker-022f">Mis ventas</div>
            <h2>${activeSales.length} activas</h2>
            <p class="sr-muted-022f">${h(formatMoney(totalAmount))} registrado por este usuario.</p>
            <div class="sr-sales-list-022f">
              ${activeSales.slice(0, 10).map(salesCardHtml022G).join("") || `<div class="sr-muted-022f">Aún no tienes ventas activas.</div>`}
            </div>
          </aside>
        </section>
      </main>
    `;

    root.querySelector("[data-sr-back-022f]")?.addEventListener("click", () => bootShell());
    root.querySelectorAll("[data-sr-category-022f]").forEach((button) => {
      button.addEventListener("click", async () => {
        await renderSalesRegisterCategory022F(session, button.getAttribute("data-sr-category-022f") || "");
      });
    });
    bindSalesPipelineActions022G(session, activeSales, () => openSalesRegisterModule022F(session));
  }

  async function renderSalesRegisterCategory022F(session, category, search = "") {
    salesPipelineStyles022G();
    let refs = [];
    let sales = [];
    let selected = null;
    let loadError = "";

    async function loadRefs(q = "") {
      const params = new URLSearchParams();
      if (category) params.set("category", category);
      if (q) params.set("q", q);
      const data = await salesApi022F(`/references?${params.toString()}`);
      return Array.isArray(data.items) ? data.items : [];
    }

    try {
      refs = await loadRefs(search);
      const salesData = await salesApi022F(`/sales?panel_type=${encodeURIComponent(panelType)}`);
      sales = Array.isArray(salesData.items) ? salesData.items : [];
    } catch (error) {
      loadError = error.message || "No se pudieron cargar referencias.";
    }

    const activeSales = sales.filter((item) => item.status !== "archived");

    function renderRefButtons(items) {
      return (items || []).map((item) => `
        <button class="sr-ref-022f" type="button"
          data-sr-ref-022f="${h(item.id || "")}"
          data-sr-ref-name="${h(item.name || "")}"
          data-sr-ref-category="${h(item.category || category || "")}"
          data-sr-ref-size="${h(item.size || "")}"
          data-sr-ref-color="${h(item.color || "")}">
          <strong>${h(item.name || "Referencia")}</strong><br>
          <small>${h([item.category, item.size, item.color].filter(Boolean).join(" · "))}</small>
        </button>
      `).join("") || `<div class="sr-muted-022f">Sin referencias para esta categoría.</div>`;
    }

    root.innerHTML = `
      <main class="sr-shell-022f">
        <header class="sr-card-022f sr-hero-022f">
          <div>
            <div class="sr-kicker-022f">Registro venta</div>
            <h1 class="sr-title-022f">${h(category || "Categoría")}</h1>
            <p class="sr-muted-022f">Busca la referencia, registra la venta y completa el flujo operativo.</p>
          </div>
          <div style="display:flex;gap:10px;flex-wrap:wrap">
            <button class="sr-btn-022f secondary" type="button" data-sr-categories-022f>Categorías</button>
            <button class="sr-btn-022f secondary" type="button" data-sr-back-022f>Dashboard</button>
          </div>
        </header>

        <section class="sr-layout-022f">
          <section class="sr-card-022f sr-panel-022f">
            <div class="sr-kicker-022f">Referencia</div>
            <div class="sr-field-022f">
              <label>Filtro inteligente</label>
              <input id="srSearch022F" value="${h(search)}" placeholder="Escribe referencia, talla, color..." />
            </div>
            <div class="sr-ref-list-022f" id="srRefList022F">
              ${renderRefButtons(refs)}
            </div>
          </section>

          <aside class="sr-card-022f sr-panel-022f">
            <div class="sr-kicker-022f">Captura</div>
            <h2>Nueva venta</h2>
            <div class="sr-message-022f" id="srSelected022F">Selecciona una referencia.</div>
            <form id="srForm022F" style="margin-top:14px">
              <input type="hidden" id="srRefId022F" />
              <input type="hidden" id="srRefName022F" />
              <input type="hidden" id="srRefCategory022F" />
              <input type="hidden" id="srRefSize022F" />
              <input type="hidden" id="srRefColor022F" />

              <div class="sr-form-grid-022f">
                <div class="sr-field-022f">
                  <label>Cantidad</label>
                  <input id="srQty022F" type="number" min="0" step="1" value="1" />
                </div>
                <div class="sr-field-022f">
                  <label>Valor unitario</label>
                  <input id="srUnit022F" type="number" min="0" step="100" value="0" />
                </div>
                <div class="sr-field-022f">
                  <label>Forma de pago</label>
                  <select id="srPay022F">
                    <option value="efectivo">Efectivo</option>
                    <option value="transferencia">Transferencia</option>
                    <option value="tarjeta">Tarjeta</option>
                    <option value="cheque">Cheque</option>
                    <option value="otro">Otro</option>
                  </select>
                </div>
                <div class="sr-field-022f">
                  <label>Total</label>
                  <input id="srTotal022F" readonly value="${h(formatMoney(0))}" />
                </div>
              </div>
              <div class="sr-field-022f" style="margin-top:14px">
                <label>Observación</label>
                <textarea id="srNotes022F" rows="3" placeholder="Opcional"></textarea>
              </div>
              <button class="sr-btn-022f" type="submit" style="margin-top:14px;width:100%">Guardar venta</button>
              <div class="sr-message-022f" id="srMsg022F">${loadError ? h(loadError) : ""}</div>
            </form>
          </aside>
        </section>

        <section class="sr-card-022f sr-panel-022f" style="margin-top:18px">
          <div class="sr-kicker-022f">Mis ventas activas</div>
          <div class="sr-sales-list-022f">
            ${activeSales.slice(0, 12).map(salesCardHtml022G).join("") || `<div class="sr-muted-022f">Sin ventas activas.</div>`}
          </div>
        </section>
      </main>
    `;

    root.querySelector("[data-sr-back-022f]")?.addEventListener("click", () => bootShell());
    root.querySelector("[data-sr-categories-022f]")?.addEventListener("click", async () => {
      await openSalesRegisterModule022F(session);
    });

    const searchInput = root.querySelector("#srSearch022F");
    let searchTimer = null;
    searchInput?.addEventListener("input", () => {
      clearTimeout(searchTimer);
      searchTimer = setTimeout(async () => {
        try {
          const nextRefs = await loadRefs(searchInput.value || "");
          const list = root.querySelector("#srRefList022F");
          if (list) list.innerHTML = renderRefButtons(nextRefs);
          bindRefs();
        } catch (error) {
          const msg = root.querySelector("#srMsg022F");
          if (msg) msg.textContent = error.message || "No se pudo buscar.";
        }
      }, 280);
    });

    function updateTotal() {
      const qty = Number(root.querySelector("#srQty022F")?.value || 0);
      const unit = Number(root.querySelector("#srUnit022F")?.value || 0);
      const total = Math.max(0, qty) * Math.max(0, unit);
      const totalInput = root.querySelector("#srTotal022F");
      if (totalInput) totalInput.value = formatMoney(total);
    }

    root.querySelector("#srQty022F")?.addEventListener("input", updateTotal);
    root.querySelector("#srUnit022F")?.addEventListener("input", updateTotal);

    function bindRefs() {
      root.querySelectorAll("[data-sr-ref-022f]").forEach((button) => {
        button.addEventListener("click", () => {
          root.querySelectorAll("[data-sr-ref-022f]").forEach((item) => item.classList.remove("active"));
          button.classList.add("active");
          selected = {
            id: button.getAttribute("data-sr-ref-022f") || "",
            name: button.getAttribute("data-sr-ref-name") || "",
            category: button.getAttribute("data-sr-ref-category") || "",
            size: button.getAttribute("data-sr-ref-size") || "",
            color: button.getAttribute("data-sr-ref-color") || ""
          };
          root.querySelector("#srRefId022F").value = selected.id;
          root.querySelector("#srRefName022F").value = selected.name;
          root.querySelector("#srRefCategory022F").value = selected.category;
          root.querySelector("#srRefSize022F").value = selected.size;
          root.querySelector("#srRefColor022F").value = selected.color;
          const selectedBox = root.querySelector("#srSelected022F");
          if (selectedBox) selectedBox.textContent = `${selected.name} · ${[selected.size, selected.color].filter(Boolean).join(" · ")}`;
        });
      });
    }
    bindRefs();

    root.querySelector("#srForm022F")?.addEventListener("submit", async (event) => {
      event.preventDefault();
      const msg = root.querySelector("#srMsg022F");
      const referenceName = root.querySelector("#srRefName022F")?.value || "";
      if (!referenceName) {
        if (msg) msg.textContent = "Selecciona una referencia antes de guardar.";
        return;
      }
      try {
        if (msg) msg.textContent = "Guardando venta...";
        await salesApi022F(`/sales?panel_type=${encodeURIComponent(panelType)}`, {
          method: "POST",
          body: JSON.stringify({
            reference_id: root.querySelector("#srRefId022F")?.value || "",
            reference_name: referenceName,
            reference_category: root.querySelector("#srRefCategory022F")?.value || category || "",
            reference_size: root.querySelector("#srRefSize022F")?.value || "",
            reference_color: root.querySelector("#srRefColor022F")?.value || "",
            quantity: Number(root.querySelector("#srQty022F")?.value || 0),
            unit_price: Number(root.querySelector("#srUnit022F")?.value || 0),
            payment_method: root.querySelector("#srPay022F")?.value || "efectivo",
            notes: root.querySelector("#srNotes022F")?.value || ""
          })
        });
        if (msg) msg.textContent = "Venta registrada.";
        await renderSalesRegisterCategory022F(session, category, searchInput?.value || "");
      } catch (error) {
        if (msg) msg.textContent = error.message || "No se pudo guardar la venta.";
      }
    });

    bindSalesPipelineActions022G(session, activeSales, () => renderSalesRegisterCategory022F(session, category, searchInput?.value || ""));
  }
  /* CLONEXA_022G_SALES_PIPELINE_ALISTAMIENTO_SOPORTES_GUIA_END */

  /* CLONEXA_022H_REGISTRO_VENTA_FACTURA_MULTIITEM_SCANNER_PRINT_START */
  let salesInvoiceCart022H = {
    items: [],
    payment_method: "efectivo",
    notes: ""
  };

  function salesInvoiceTotal022H() {
    return salesInvoiceCart022H.items.reduce((sum, item) => sum + (Number(item.quantity || 0) * Number(item.unit_price || 0)), 0);
  }

  function salesInvoiceCount022H() {
    return salesInvoiceCart022H.items.reduce((sum, item) => sum + Number(item.quantity || 0), 0);
  }

  function salesResetInvoice022H() {
    salesInvoiceCart022H = { items: [], payment_method: "efectivo", notes: "" };
  }

  function salesNormalizeItem022H(item) {
    const qty = Math.max(0, Number(item.quantity || 0));
    const unit = Math.max(0, Number(item.unit_price || 0));
    return {
      reference_id: String(item.reference_id || item.id || ""),
      reference_name: String(item.reference_name || item.name || "Referencia"),
      reference_category: String(item.reference_category || item.category || ""),
      reference_size: String(item.reference_size || item.size || ""),
      reference_color: String(item.reference_color || item.color || ""),
      quantity: qty,
      unit_price: unit,
      total: qty * unit,
      barcode: String(item.barcode || item.code || item.sku || "")
    };
  }

  function salesCartRowsHtml022H() {
    if (!salesInvoiceCart022H.items.length) {
      return `<div class="sr-muted-022f">Factura actual vacía. Agrega artículos desde cualquier categoría.</div>`;
    }

    return salesInvoiceCart022H.items.map((item, index) => `
      <article class="sr-invoice-line-022h" data-sr-cart-line="${index}">
        <div>
          <strong>${h(item.reference_name)}</strong>
          <small>${h([item.reference_category, item.reference_size, item.reference_color].filter(Boolean).join(" · "))}</small>
        </div>
        <input type="number" min="0" step="1" value="${h(item.quantity)}" data-sr-cart-qty="${index}" title="Cantidad">
        <input type="number" min="0" step="100" value="${h(item.unit_price)}" data-sr-cart-unit="${index}" title="Valor unitario">
        <strong data-sr-cart-total="${index}">${h(formatMoney(Number(item.quantity || 0) * Number(item.unit_price || 0)))}</strong>
        <button type="button" data-sr-cart-remove="${index}">Quitar</button>
      </article>
    `).join("");
  }

  function salesRefreshCartTotals022H() {
    salesInvoiceCart022H.items = salesInvoiceCart022H.items.map(salesNormalizeItem022H);
    document.querySelectorAll("[data-sr-cart-total]").forEach((node) => {
      const index = Number(node.getAttribute("data-sr-cart-total") || 0);
      const item = salesInvoiceCart022H.items[index];
      if (item) node.textContent = formatMoney(Number(item.quantity || 0) * Number(item.unit_price || 0));
    });
    const total = salesInvoiceTotal022H();
    const count = salesInvoiceCount022H();
    const totalNode = document.getElementById("srInvoiceTotal022H");
    const countNode = document.getElementById("srInvoiceCount022H");
    if (totalNode) totalNode.textContent = formatMoney(total);
    if (countNode) countNode.textContent = String(count);
  }

  function salesPrintInvoiceDraft022H(session, sale = null) {
    const items = sale?.items || salesInvoiceCart022H.items;
    if (!items || !items.length) {
      alert("No hay artículos para imprimir.");
      return;
    }

    const total = items.reduce((sum, item) => sum + (Number(item.quantity || 0) * Number(item.unit_price || 0)), 0);
    const invoiceNumber = sale?.invoice_number || "Factura actual";
    const seller = sale?.source_user_label || session?.employee?.full_name || session?.user?.full_name || "Vendedor";
    const company = session?.company?.name || "Empresa";
    const rows = items.map((item) => `
      <tr>
        <td>${h(item.reference_name || "")}<br><small>${h([item.reference_category, item.reference_size, item.reference_color].filter(Boolean).join(" · "))}</small></td>
        <td style="text-align:center">${h(item.quantity || 0)}</td>
        <td style="text-align:right">${h(formatMoney(item.unit_price || 0))}</td>
        <td style="text-align:right">${h(formatMoney((Number(item.quantity || 0) * Number(item.unit_price || 0))))}</td>
      </tr>
    `).join("");

    const win = window.open("", "_blank");
    if (!win) return;
    win.document.write(`
      <html>
        <head>
          <title>${h(invoiceNumber)}</title>
          <style>
            body{font-family:Arial,sans-serif;padding:28px;color:#111}
            h1{margin:0 0 4px;font-size:28px}
            .muted{color:#555;margin-bottom:22px}
            table{width:100%;border-collapse:collapse;margin-top:18px}
            th{background:#111;color:#fff;text-align:left;padding:10px}
            td{border-bottom:1px solid #ddd;padding:10px;vertical-align:top}
            .total{font-size:24px;font-weight:900;text-align:right;margin-top:18px}
            .footer{margin-top:40px;color:#555;font-size:12px;text-align:center}
          </style>
        </head>
        <body>
          <h1>${h(company)}</h1>
          <div class="muted">${h(invoiceNumber)} · Vendedor: ${h(seller)} · ${new Date().toLocaleString()}</div>
          <table>
            <thead><tr><th>Artículo</th><th>Cant.</th><th>Valor unit.</th><th>Total</th></tr></thead>
            <tbody>${rows}</tbody>
          </table>
          <div class="total">TOTAL ${h(formatMoney(total))}</div>
          <div class="footer">Registro venta generado por CLONEXA</div>
          <script>setTimeout(()=>print(),500)<\/script>
        </body>
      </html>
    `);
    win.document.close();
  }

  async function salesScanCode022H(searchInput, onSearch) {
    const fallbackPrompt = async () => {
      const code = prompt("Escanea o escribe código, SKU, nombre, talla o color:");
      if (code && searchInput) {
        searchInput.value = code.trim();
        await onSearch(code.trim(), true);
      }
    };

    if (!("BarcodeDetector" in window) || !navigator.mediaDevices?.getUserMedia) {
      await fallbackPrompt();
      return;
    }

    let stream = null;
    const overlay = document.createElement("div");
    overlay.style.cssText = "position:fixed;inset:0;background:rgba(0,0,0,.86);z-index:99999;display:flex;align-items:center;justify-content:center;flex-direction:column;gap:14px;color:#fff";
    overlay.innerHTML = `
      <video autoplay playsinline style="width:min(92vw,520px);border-radius:18px;border:1px solid rgba(255,255,255,.25)"></video>
      <div style="font-weight:900">Apunta al código de barras o QR</div>
      <button type="button" style="border:0;border-radius:14px;padding:12px 18px;font-weight:900">Cancelar</button>
    `;
    document.body.appendChild(overlay);

    const video = overlay.querySelector("video");
    const cancel = overlay.querySelector("button");
    let stopped = false;
    const stop = () => {
      stopped = true;
      try { stream?.getTracks()?.forEach((track) => track.stop()); } catch {}
      overlay.remove();
    };
    cancel.addEventListener("click", stop);

    try {
      stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" } });
      video.srcObject = stream;
      const detector = new BarcodeDetector({ formats: ["qr_code", "ean_13", "ean_8", "code_128", "code_39", "upc_a", "upc_e"] });

      const started = Date.now();
      const scanLoop = async () => {
        if (stopped) return;
        try {
          const codes = await detector.detect(video);
          if (codes && codes.length) {
            const raw = String(codes[0].rawValue || "").trim();
            stop();
            if (raw && searchInput) {
              searchInput.value = raw;
              await onSearch(raw, true);
            }
            return;
          }
        } catch {}
        if (Date.now() - started > 20000) {
          stop();
          await fallbackPrompt();
          return;
        }
        requestAnimationFrame(scanLoop);
      };
      requestAnimationFrame(scanLoop);
    } catch {
      stop();
      await fallbackPrompt();
    }
  }

  function salesCardHtml022G(item) {
    const support = item?.support || null;
    const guide = item?.guide || null;
    const archived = String(item?.status || "").toLowerCase() === "archived";
    const items = Array.isArray(item?.items) ? item.items : [];
    const itemSummary = items.length > 1
      ? `${items.length} artículos · ${Number(item.quantity || 0)} und · ${h(item.payment_method || "")}`
      : `${h(item.reference_category || "Sin categoria")} · ${h(item.quantity)} und · ${h(item.payment_method || "")}`;
    // CLONEXA_022K_R2_SAVE_SALES_ADJUSTMENT_SAFE: show persisted adjustment on saved invoices without touching categories/references.
    const adjustment = item?.adjustment || null;
    const adjustmentType = String(adjustment?.type || "none").toLowerCase();
    const adjustmentSign = (adjustmentType === "discount" || adjustmentType === "retention") ? "- " : "";
    const adjustmentHtml = adjustment && adjustmentType !== "none"
      ? `<div class="sr-muted-022f">${h(adjustment.label || "Ajuste")} ${h(adjustment.percent || 0)}% · ${adjustmentSign}${h(formatMoney(adjustment.adjustment_amount || 0))} · Total a pagar ${h(formatMoney(adjustment.total_payable ?? item.total ?? 0))}</div>`
      : "";
    return `
      <article class="sr-sale-022f">
        <strong><span>${h(item.invoice_number || item.reference_name || "Factura")}</span><span>${h(formatMoney(item.total || 0))}</span></strong>
        <small>${itemSummary}</small>
        ${adjustmentHtml}
        ${items.length > 1 ? `<div class="sr-muted-022f">${items.slice(0, 4).map((line) => `${h(line.reference_name || "")} x ${h(line.quantity || 0)}`).join(" · ")}${items.length > 4 ? " · ..." : ""}</div>` : ""}
        <div class="sr-pipeline-022g">
          <span class="sr-pill-022g ok">Venta registrada</span>
          <span class="sr-pill-022g ${item.is_prepared ? "ok" : "warn"}">${item.is_prepared ? "Pedido alistado" : "Pendiente alistar"}</span>
          <span class="sr-pill-022g ${item.has_support ? "ok" : "warn"}">${item.has_support ? "Soporte adjunto" : "Sin soporte"}</span>
          <span class="sr-pill-022g ${item.has_guide ? "ok" : "warn"}">${item.has_guide ? "Guía recibida" : "Sin guía"}</span>
        </div>
        <div class="sr-mini-actions-022g">
          <button type="button" data-sr-print-invoice-022h="${h(item.id)}">Imprimir factura</button>
          ${!item.is_prepared && !archived ? `<button class="primary" type="button" data-sr-prepare-022g="${h(item.id)}">Marcar alistado</button>` : ""}
          ${support ? `
            <button type="button" data-sr-open-support-022g="${h(item.id)}">Ver soporte</button>
            <button type="button" data-sr-download-support-022g="${h(item.id)}">Descargar soporte</button>
          ` : (!archived ? `
            <label class="sr-file-label-022g">Adjuntar factura/comprobante
              <input type="file" accept="image/*,.pdf" data-sr-support-file-022g="${h(item.id)}">
            </label>
          ` : "")}
          ${guide ? `
            <button class="primary" type="button" data-sr-open-guide-022g="${h(item.id)}">Ver guía</button>
            <button type="button" data-sr-download-guide-022g="${h(item.id)}">Descargar guía</button>
            <button type="button" data-sr-print-guide-022g="${h(item.id)}">Imprimir guía</button>
          ` : ""}
          ${!archived ? `<button class="danger" type="button" data-sr-archive-022g="${h(item.id)}">Guardar / archivar</button>` : `<span class="sr-pill-022g">Archivada</span>`}
        </div>
      </article>
    `;
  }

  function bindSalesPipelineActions022G(session, sales, refreshFn) {
    const salesById = new Map((sales || []).map((item) => [String(item.id), item]));

    root.querySelectorAll("[data-sr-print-invoice-022h]").forEach((button) => {
      button.addEventListener("click", () => salesPrintInvoiceDraft022H(session, salesById.get(button.getAttribute("data-sr-print-invoice-022h"))));
    });

    root.querySelectorAll("[data-sr-prepare-022g]").forEach((button) => {
      button.addEventListener("click", async () => {
        const id = button.getAttribute("data-sr-prepare-022g");
        button.disabled = true;
        await salesApi022F(`/sales/${encodeURIComponent(id)}/prepared?panel_type=${encodeURIComponent(panelType)}`, {
          method: "POST",
          body: JSON.stringify({ prepared: true })
        });
        await refreshFn();
      });
    });

    root.querySelectorAll("[data-sr-support-file-022g]").forEach((input) => {
      input.addEventListener("change", async () => {
        const id = input.getAttribute("data-sr-support-file-022g");
        const file = input.files && input.files[0];
        if (!id || !file) return;
        const dataUrl = await salesFileToDataUrl022G(file);
        await salesApi022F(`/sales/${encodeURIComponent(id)}/support?panel_type=${encodeURIComponent(panelType)}`, {
          method: "POST",
          body: JSON.stringify({
            file_name: file.name || "soporte",
            file_type: file.type || "application/octet-stream",
            file_data: dataUrl
          })
        });
        await refreshFn();
      });
    });

    root.querySelectorAll("[data-sr-open-support-022g]").forEach((button) => {
      button.addEventListener("click", () => salesOpenFile022G(salesById.get(button.getAttribute("data-sr-open-support-022g"))?.support));
    });

    root.querySelectorAll("[data-sr-download-support-022g]").forEach((button) => {
      button.addEventListener("click", () => salesDownloadFile022G(salesById.get(button.getAttribute("data-sr-download-support-022g"))?.support, "soporte"));
    });

    root.querySelectorAll("[data-sr-open-guide-022g]").forEach((button) => {
      button.addEventListener("click", () => salesOpenFile022G(salesById.get(button.getAttribute("data-sr-open-guide-022g"))?.guide));
    });

    root.querySelectorAll("[data-sr-download-guide-022g]").forEach((button) => {
      button.addEventListener("click", () => salesDownloadFile022G(salesById.get(button.getAttribute("data-sr-download-guide-022g"))?.guide, "guia_envio"));
    });

    root.querySelectorAll("[data-sr-print-guide-022g]").forEach((button) => {
      button.addEventListener("click", () => salesPrintFile022G(salesById.get(button.getAttribute("data-sr-print-guide-022g"))?.guide));
    });

    root.querySelectorAll("[data-sr-archive-022g]").forEach((button) => {
      button.addEventListener("click", async () => {
        const id = button.getAttribute("data-sr-archive-022g");
        if (!id) return;
        if (!confirm("Archivar esta venta? Saldrá de la vista principal y quedará consultable por búsqueda.")) return;
        button.disabled = true;
        await salesApi022F(`/sales/${encodeURIComponent(id)}/archive?panel_type=${encodeURIComponent(panelType)}`, {
          method: "POST",
          body: JSON.stringify({})
        });
        await refreshFn();
      });
    });
  }

  async function renderSalesRegisterCategory022F(session, category, search = "") {
    salesPipelineStyles022G();
    if (!document.getElementById("cxSalesInvoiceStyles022H")) {
      const style = document.createElement("style");
      style.id = "cxSalesInvoiceStyles022H";
      style.textContent = `
        .sr-invoice-layout-022h{display:grid;grid-template-columns:minmax(0,1.05fr) minmax(360px,.95fr);gap:18px}
        .sr-invoice-box-022h{display:grid;gap:10px}
        .sr-invoice-line-022h{display:grid;grid-template-columns:minmax(0,1fr) 82px 110px 110px 72px;gap:8px;align-items:center;padding:12px;border-radius:16px;background:rgba(255,255,255,.08);border:1px solid rgba(255,255,255,.12)}
        .sr-invoice-line-022h small{display:block;color:rgba(255,255,255,.62);font-weight:800;margin-top:3px}
        .sr-invoice-line-022h input{width:100%;border:1px solid rgba(255,255,255,.15);background:rgba(5,7,22,.65);color:#fff;border-radius:12px;padding:10px;font-weight:900}
        .sr-invoice-line-022h button{border:0;border-radius:12px;background:rgba(255,74,124,.22);border:1px solid rgba(255,74,124,.42);color:#fff;padding:10px;font-weight:900;cursor:pointer}
        .sr-toolbar-022h{display:flex;gap:10px;flex-wrap:wrap;margin-top:12px}
        .sr-toolbar-022h button{border:0;border-radius:14px;padding:12px 14px;color:#fff;background:rgba(255,255,255,.12);border:1px solid rgba(255,255,255,.14);font-weight:950;cursor:pointer}
        .sr-toolbar-022h button.primary{background:linear-gradient(135deg,#ff25bb,#6d4cff);border:0}
        .sr-total-box-022h{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;margin-top:12px}
        .sr-total-pill-022h{border-radius:16px;padding:14px;background:rgba(255,255,255,.09);border:1px solid rgba(255,255,255,.13);font-weight:950}
        @media(max-width:960px){.sr-invoice-layout-022h{grid-template-columns:1fr}.sr-invoice-line-022h{grid-template-columns:1fr 70px 90px}.sr-invoice-line-022h strong[data-sr-cart-total]{grid-column:1/3}.sr-invoice-line-022h button{grid-column:3/4}}
      `;
      document.head.appendChild(style);
    }

    let refs = [];
    let sales = [];
    let selected = null;
    let loadError = "";

    async function loadRefs(q = "") {
      const params = new URLSearchParams();
      if (category) params.set("category", category);
      if (q) params.set("q", q);
      const data = await salesApi022F(`/references?${params.toString()}`);
      return Array.isArray(data.items) ? data.items : [];
    }

    function renderRefButtons(items) {
      return (items || []).map((item) => `
        <button class="sr-ref-022f" type="button"
          data-sr-ref-022f="${h(item.id || "")}"
          data-sr-ref-name="${h(item.name || "")}"
          data-sr-ref-category="${h(item.category || category || "")}"
          data-sr-ref-size="${h(item.size || "")}"
          data-sr-ref-color="${h(item.color || "")}"
          data-sr-ref-barcode="${h(item.barcode || item.code || item.sku || item.id || "")}"
          data-sr-ref-unit-price="${h(item.unit_price ?? item.price ?? 0)}">
          <strong>${h(item.name || "Referencia")}</strong><br>
          <small>${h([item.category, item.size, item.color].filter(Boolean).join(" · "))}</small>
        </button>
      `).join("") || `<div class="sr-muted-022f">Sin referencias para esta búsqueda.</div>`;
    }

    try {
      refs = await loadRefs(search);
      const salesData = await salesApi022F(`/sales?panel_type=${encodeURIComponent(panelType)}`);
      sales = Array.isArray(salesData.items) ? salesData.items : [];
    } catch (error) {
      loadError = error.message || "No se pudieron cargar referencias.";
    }

    const activeSales = sales.filter((item) => item.status !== "archived");

    root.innerHTML = `
      <main class="sr-shell-022f">
        <header class="sr-card-022f sr-hero-022f">
          <div>
            <div class="sr-kicker-022f">Registro venta</div>
            <h1 class="sr-title-022f">${h(category || "Categoría")}</h1>
            <p class="sr-muted-022f">Agrega varios artículos, cambia de categoría y guarda una sola factura.</p>
          </div>
          <div style="display:flex;gap:10px;flex-wrap:wrap">
            <button class="sr-btn-022f secondary" type="button" data-sr-categories-022f>Categorías</button>
            <button class="sr-btn-022f secondary" type="button" data-sr-new-invoice-022h>Nueva factura</button>
            <button class="sr-btn-022f secondary" type="button" data-sr-print-draft-022h>Imprimir factura</button>
            <button class="sr-btn-022f secondary" type="button" data-sr-back-022f>Dashboard</button>
          </div>
        </header>

        ${storeActorStripHtml023W("ventas")}

        <section class="sr-invoice-layout-022h">
          <section class="sr-card-022f sr-panel-022f">
            <div class="sr-kicker-022f">Referencia</div>
            <div class="sr-field-022f">
              <label>Filtro inteligente</label>
              <input id="srSearch022F" value="${h(search)}" placeholder="Escribe o escanea referencia, código, talla, color..." />
            </div>
            <div class="sr-toolbar-022h">
              <button class="primary" type="button" data-sr-scan-022h>Escanear código</button>
              <button type="button" data-sr-clear-search-022h>Limpiar búsqueda</button>
            </div>
            <div class="sr-ref-list-022f" id="srRefList022F" style="margin-top:14px">
              ${renderRefButtons(refs)}
            </div>
          </section>

          <aside class="sr-card-022f sr-panel-022f">
            <div class="sr-kicker-022f">Factura actual</div>
            <h2>Carrito operativo</h2>
            <div class="sr-message-022f" id="srSelected022F">Selecciona una referencia y agrégala a la factura.</div>

            <div class="sr-form-grid-022f" style="margin-top:14px">
              <div class="sr-field-022f">
                <label>Cantidad</label>
                <input id="srQty022F" type="number" min="0" step="1" value="1" />
              </div>
              <div class="sr-field-022f">
                <label>Valor unitario</label>
                <input id="srUnit022F" type="number" min="0" step="100" value="0" />
              </div>
            </div>

            <div class="sr-toolbar-022h">
              <button class="primary" type="button" data-sr-add-line-022h>Agregar a factura actual</button>
            </div>

            <div class="sr-invoice-box-022h" id="srCartRows022H" style="margin-top:14px">
              ${salesCartRowsHtml022H()}
            </div>

            <div class="sr-total-box-022h">
              <div class="sr-total-pill-022h">Artículos<br><span id="srInvoiceCount022H">${h(salesInvoiceCount022H())}</span></div>
              <div class="sr-total-pill-022h">Total<br><span id="srInvoiceTotal022H">${h(formatMoney(salesInvoiceTotal022H()))}</span></div>
            </div>

            <div class="sr-form-grid-022f" style="margin-top:14px">
              <div class="sr-field-022f">
                <label>Forma de pago</label>
                <select id="srPay022F">
                  <option value="efectivo" ${salesInvoiceCart022H.payment_method === "efectivo" ? "selected" : ""}>Efectivo</option>
                  <option value="transferencia" ${salesInvoiceCart022H.payment_method === "transferencia" ? "selected" : ""}>Transferencia</option>
                  <option value="tarjeta" ${salesInvoiceCart022H.payment_method === "tarjeta" ? "selected" : ""}>Tarjeta</option>
                  <option value="cheque" ${salesInvoiceCart022H.payment_method === "cheque" ? "selected" : ""}>Cheque</option>
                  <option value="otro" ${salesInvoiceCart022H.payment_method === "otro" ? "selected" : ""}>Otro</option>
                </select>
              </div>
              <div class="sr-field-022f">
                <label>Observación factura</label>
                <input id="srNotes022F" value="${h(salesInvoiceCart022H.notes || "")}" placeholder="Opcional" />
              </div>
            </div>

            <button class="sr-btn-022f" type="button" data-sr-save-invoice-022h style="margin-top:14px;width:100%">Guardar factura / venta</button>
            <div class="sr-message-022f" id="srMsg022F">${loadError ? h(loadError) : ""}</div>
          </aside>
        </section>

        <section class="sr-card-022f sr-panel-022f" style="margin-top:18px">
          <div class="sr-kicker-022f">Mis ventas activas</div>
          <div class="sr-sales-list-022f">
            ${activeSales.slice(0, 12).map(salesCardHtml022G).join("") || `<div class="sr-muted-022f">Sin ventas activas.</div>`}
          </div>
        </section>
      </main>
    `;

    const searchInput = root.querySelector("#srSearch022F");
    bindStoreActorSelector023W();

    async function updateRefList(q = "", autoPick = false) {
      const nextRefs = await loadRefs(q);
      const list = root.querySelector("#srRefList022F");
      if (list) list.innerHTML = renderRefButtons(nextRefs);
      bindRefs();
      if (autoPick && nextRefs.length) {
        const firstBtn = root.querySelector("[data-sr-ref-022f]");
        firstBtn?.click();
      }
    }

    function bindRefs() {
      root.querySelectorAll("[data-sr-ref-022f]").forEach((button) => {
        button.addEventListener("click", () => {
          root.querySelectorAll("[data-sr-ref-022f]").forEach((item) => item.classList.remove("active"));
          button.classList.add("active");
          selected = {
            reference_id: button.getAttribute("data-sr-ref-022f") || "",
            reference_name: button.getAttribute("data-sr-ref-name") || "",
            reference_category: button.getAttribute("data-sr-ref-category") || "",
            reference_size: button.getAttribute("data-sr-ref-size") || "",
            reference_color: button.getAttribute("data-sr-ref-color") || "",
            barcode: button.getAttribute("data-sr-ref-barcode") || "",
            unit_price: Number(button.getAttribute("data-sr-ref-unit-price") || 0) || 0
          };
          const unitInput = root.querySelector("#srUnit022F");
          if (unitInput && selected.unit_price > 0) unitInput.value = String(selected.unit_price);
          const selectedBox = root.querySelector("#srSelected022F");
          if (selectedBox) selectedBox.textContent = `${selected.reference_name} · ${[selected.reference_size, selected.reference_color].filter(Boolean).join(" · ")}`;
        });
      });
    }

    function bindCartInputs() {
      root.querySelectorAll("[data-sr-cart-qty]").forEach((input) => {
        input.addEventListener("input", () => {
          const index = Number(input.getAttribute("data-sr-cart-qty") || 0);
          if (salesInvoiceCart022H.items[index]) {
            salesInvoiceCart022H.items[index].quantity = Number(input.value || 0);
            salesRefreshCartTotals022H();
          }
        });
      });

      root.querySelectorAll("[data-sr-cart-unit]").forEach((input) => {
        input.addEventListener("input", () => {
          const index = Number(input.getAttribute("data-sr-cart-unit") || 0);
          if (salesInvoiceCart022H.items[index]) {
            salesInvoiceCart022H.items[index].unit_price = Number(input.value || 0);
            salesRefreshCartTotals022H();
          }
        });
      });

      root.querySelectorAll("[data-sr-cart-remove]").forEach((button) => {
        button.addEventListener("click", async () => {
          const index = Number(button.getAttribute("data-sr-cart-remove") || 0);
          salesInvoiceCart022H.items.splice(index, 1);
          await renderSalesRegisterCategory022F(session, category, searchInput?.value || "");
        });
      });
    }

    let searchTimer = null;
    searchInput?.addEventListener("input", () => {
      clearTimeout(searchTimer);
      searchTimer = setTimeout(async () => {
        try {
          await updateRefList(searchInput.value || "", false);
        } catch (error) {
          const msg = root.querySelector("#srMsg022F");
          if (msg) msg.textContent = error.message || "No se pudo buscar.";
        }
      }, 260);
    });

    root.querySelector("[data-sr-back-022f]")?.addEventListener("click", () => bootShell());
    root.querySelector("[data-sr-categories-022f]")?.addEventListener("click", async () => openSalesRegisterModule022F(session));
    root.querySelector("[data-sr-clear-search-022h]")?.addEventListener("click", async () => {
      if (searchInput) searchInput.value = "";
      await updateRefList("", false);
    });
    root.querySelector("[data-sr-scan-022h]")?.addEventListener("click", async () => salesScanCode022H(searchInput, updateRefList));
    root.querySelector("[data-sr-new-invoice-022h]")?.addEventListener("click", async () => {
      if (salesInvoiceCart022H.items.length && !confirm("Crear nueva factura y limpiar la actual?")) return;
      salesResetInvoice022H();
      await renderSalesRegisterCategory022F(session, category, searchInput?.value || "");
    });
    root.querySelector("[data-sr-print-draft-022h]")?.addEventListener("click", () => salesPrintInvoiceDraft022H(session));

    root.querySelector("[data-sr-add-line-022h]")?.addEventListener("click", async () => {
      const msg = root.querySelector("#srMsg022F");
      if (!selected?.reference_name) {
        if (msg) msg.textContent = "Selecciona una referencia antes de agregar.";
        return;
      }
      const item = salesNormalizeItem022H({
        ...selected,
        quantity: Number(root.querySelector("#srQty022F")?.value || 0),
        unit_price: Number(root.querySelector("#srUnit022F")?.value || 0)
      });
      if (!item.quantity) {
        if (msg) msg.textContent = "La cantidad debe ser mayor a cero.";
        return;
      }
      salesInvoiceCart022H.items.push(item);
      if (msg) msg.textContent = "Artículo agregado a la factura actual.";
      await renderSalesRegisterCategory022F(session, category, searchInput?.value || "");
    });

    root.querySelector("#srPay022F")?.addEventListener("change", (event) => {
      salesInvoiceCart022H.payment_method = event.target.value || "efectivo";
    });
    root.querySelector("#srNotes022F")?.addEventListener("input", (event) => {
      salesInvoiceCart022H.notes = event.target.value || "";
    });

    root.querySelector("[data-sr-save-invoice-022h]")?.addEventListener("click", async () => {
      const msg = root.querySelector("#srMsg022F");
      salesInvoiceCart022H.payment_method = root.querySelector("#srPay022F")?.value || "efectivo";
      salesInvoiceCart022H.notes = root.querySelector("#srNotes022F")?.value || "";

      if (!salesInvoiceCart022H.items.length) {
        if (msg) msg.textContent = "Agrega al menos un artículo antes de guardar.";
        return;
      }

      try {
        if (msg) msg.textContent = "Guardando factura...";
        const data = await salesApi022F(`/sales?panel_type=${encodeURIComponent(panelType)}`, {
          method: "POST",
          body: JSON.stringify({
            payment_method: salesInvoiceCart022H.payment_method,
            notes: salesInvoiceCart022H.notes,
            items: salesInvoiceCart022H.items
          })
        });
        if (msg) msg.textContent = `Factura guardada ${data?.invoice_number || ""}.`;
        salesResetInvoice022H();
        await renderSalesRegisterCategory022F(session, category, searchInput?.value || "");
      } catch (error) {
        if (msg) msg.textContent = error.message || "No se pudo guardar la factura.";
      }
    });

    bindRefs();
    bindCartInputs();
    bindSalesPipelineActions022G(session, activeSales, () => renderSalesRegisterCategory022F(session, category, searchInput?.value || ""));
  }
  /* CLONEXA_022H_REGISTRO_VENTA_FACTURA_MULTIITEM_SCANNER_PRINT_END */

  /* CLONEXA_022I_MINIPANEL_SALES_SEARCH_KPI_LIMIT5_START */
  function salesUxStyles022I() {
    salesPipelineStyles022G();
    if (document.getElementById("cxSalesUxStyles022I")) return;
    const style = document.createElement("style");
    style.id = "cxSalesUxStyles022I";
    style.textContent = `
      .sr-search-row-022i{display:grid;gap:8px;margin:14px 0}
      .sr-search-row-022i input{width:100%;border:1px solid rgba(255,255,255,.15);background:rgba(5,7,22,.64);color:#fff;border-radius:16px;padding:14px 16px;font-weight:900;outline:none}
      .sr-search-row-022i input:focus{border-color:rgba(255,37,187,.68);box-shadow:0 0 0 3px rgba(255,37,187,.12)}
      .sr-search-meta-022i{display:flex;gap:8px;flex-wrap:wrap;align-items:center;color:rgba(255,255,255,.62);font-size:12px;font-weight:900;margin-top:8px}
      .sr-sales-scroll-022i{max-height:610px;overflow:auto;padding-right:4px;scrollbar-width:thin}
      .sr-sales-scroll-022i::-webkit-scrollbar{width:8px}
      .sr-sales-scroll-022i::-webkit-scrollbar-thumb{background:linear-gradient(180deg,#ff25bb,#35a8ff);border-radius:999px}
      .sr-empty-022i{border:1px dashed rgba(255,255,255,.18);border-radius:16px;padding:16px;color:rgba(255,255,255,.64);font-weight:900}
      .sr-category-hidden-022i{display:none!important}
    `;
    document.head.appendChild(style);
  }

  function salesSearchText022I(value) {
    return String(value ?? "").toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "").trim();
  }

  function salesMatchCategory022I(item, query) {
    const q = salesSearchText022I(query);
    if (!q) return true;
    return salesSearchText022I([
      item?.category,
      item?.slug,
      item?.source,
      item?.count,
      item?.icon
    ].filter(Boolean).join(" ")).includes(q);
  }

  function salesMatchRecord022I(item, query) {
    const q = salesSearchText022I(query);
    if (!q) return true;
    const items = Array.isArray(item?.items) ? item.items : [];
    const itemText = items.map((line) => [
      line?.reference_name,
      line?.reference_category,
      line?.reference_size,
      line?.reference_color,
      line?.barcode,
      line?.quantity,
      line?.unit_price,
      line?.total
    ].filter(Boolean).join(" ")).join(" ");
    return salesSearchText022I([
      item?.invoice_number,
      item?.reference_name,
      item?.reference_category,
      item?.reference_size,
      item?.reference_color,
      item?.payment_method,
      item?.status,
      item?.pipeline_status,
      item?.created_by_label,
      item?.source_user_label,
      item?.total,
      item?.quantity,
      itemText
    ].filter(Boolean).join(" ")).includes(q);
  }

  function salesRenderCategories022I(categories) {
    return (categories || []).map((item) => `
      <button class="sr-category-022f" type="button" data-sr-category-022f="${h(item.category || "")}">
        <div class="sr-icon-022f">${h(categoryIcon022F(item))}</div>
        <strong>${h(item.category || "Categoria")}</strong>
        <small>${Number(item.count || 0)} referencias</small>
      </button>
    `).join("") || `<div class="sr-empty-022i">No hay categorías disponibles. Crea referencias con canal Sistema o Ambos.</div>`;
  }

  function salesVisibleRecords022I(records, query = "", limitWhenEmpty = 5) {
    const active = (records || []).filter((item) => String(item?.status || "").toLowerCase() !== "archived");
    const filtered = active.filter((item) => salesMatchRecord022I(item, query));
    return query ? filtered.slice(0, 60) : filtered.slice(0, limitWhenEmpty);
  }

  function salesRenderRecords022I(records, query = "", emptyText = "Aún no tienes ventas activas.") {
    const list = salesVisibleRecords022I(records, query, 5);
    if (!list.length) return `<div class="sr-empty-022i">${h(emptyText)}</div>`;
    return list.map(salesCardHtml022G).join("");
  }

  function salesUpdateRecordsList022I(session, records, query, listSelector, countSelector, refreshFn) {
    const list = root.querySelector(listSelector);
    const count = root.querySelector(countSelector);
    const normalizedQuery = String(query || "").trim();
    const active = (records || []).filter((item) => String(item?.status || "").toLowerCase() !== "archived");
    const filtered = active.filter((item) => salesMatchRecord022I(item, normalizedQuery));
    const visible = normalizedQuery ? filtered.slice(0, 60) : filtered.slice(0, 5);

    if (list) {
      list.innerHTML = visible.length
        ? visible.map(salesCardHtml022G).join("")
        : `<div class="sr-empty-022i">${normalizedQuery ? "Sin ventas que coincidan con la búsqueda." : "Aún no tienes ventas activas."}</div>`;
    }

    if (count) {
      count.textContent = normalizedQuery
        ? `Mostrando ${visible.length} de ${filtered.length} coincidencias`
        : `Mostrando últimas ${Math.min(5, active.length)} de ${active.length} ventas activas`;
    }

    bindSalesPipelineActions022G(session, active, refreshFn);
  }

  function salesPeriodTotal023J(data, fallbackItems = []) {
    const candidates = [
      data?.cut?.total_amount,
      data?.total_amount
    ];
    for (const value of candidates) {
      const amount = Number(value);
      if (Number.isFinite(amount)) return amount;
    }
    return (fallbackItems || [])
      .filter((item) => String(item?.status || "").toLowerCase() !== "archived")
      .reduce((sum, item) => sum + Number(item?.total || 0), 0);
  }

  function salesPeriodCount023J(data, fallbackItems = []) {
    const candidates = [
      data?.cut?.period_count,
      data?.period_count,
      data?.cut?.active_count,
      data?.active_count
    ];
    for (const value of candidates) {
      const count = Number(value);
      if (Number.isFinite(count)) return count;
    }
    return (fallbackItems || []).filter((item) => String(item?.status || "").toLowerCase() !== "archived").length;
  }

  async function refreshMiniPanelSalesKpis022I() {
    try {
      if (typeof salesApi022F !== "function") return;
      const data = await salesApi022F(`/sales?panel_type=${encodeURIComponent(panelType)}`);
      const items = Array.isArray(data.items) ? data.items : [];
      const active = items.filter((item) => String(item?.status || "").toLowerCase() !== "archived");
      const total = salesPeriodTotal023J(data, items);
      const periodCount = salesPeriodCount023J(data, items);
      const teamTotals024A_R2 = (
        typeof isStorePanel023W === "function" &&
        isStorePanel023W() &&
        typeof storeTeamTotals024A_R1 === "function" &&
        typeof storeTeamMembers024A_R1 === "function" &&
        storeTeamMembers024A_R1().length
      )
        ? storeTeamTotals024A_R1()
        : null;

      const goal = teamTotals024A_R2
        ? Number(teamTotals024A_R2.goal || 0)
        : Number(currentOperational?.kpis?.monthly_goal || 0);
      const goalPct = goal > 0 ? Math.min(100, Math.round((total / goal) * 100)) : 0;

      const cards = Array.from(root.querySelectorAll(".mp-kpi-card"));
      const totalCard = cards.find((card) => salesSearchText022I(card.querySelector("span")?.textContent || "") === "total ventas mes");
      const goalCard = cards.find((card) => salesSearchText022I(card.querySelector("span")?.textContent || "") === "llevas vs meta");

      if (totalCard) {
        const strong = totalCard.querySelector("strong");
        const small = totalCard.querySelector("small");
        if (strong) strong.textContent = formatMoney(total);
        if (small) small.textContent = `${periodCount} ventas del corte actual · ${active.length} visibles`;
      }

      if (goalCard) {
        const strong = goalCard.querySelector("strong");
        const progress = goalCard.querySelector(".mp-progress i");
        const small = goalCard.querySelector("small");
        if (strong) strong.textContent = `${formatMoney(total)} / ${formatMoney(goal)}`;
        if (progress) progress.style.width = `${goalPct}%`;
        if (small) small.textContent = goal > 0 ? `${goalPct}% de cumplimiento` : "Meta pendiente de configurar";
      }
    } catch (error) {
      console.warn("CLONEXA 022I KPI ventas fallback:", error);
    }
  }

  async function openSalesRegisterModule022F(session) {
    salesUxStyles022I();
    let categories = [];
    let sales = [];
    let salesData = {};
    let loadError = "";

    try {
      const cats = await salesApi022F(`/categories?panel_type=${encodeURIComponent(panelType)}`);
      categories = Array.isArray(cats.items) ? cats.items : [];
      salesData = await salesApi022F(`/sales?panel_type=${encodeURIComponent(panelType)}`);
      sales = Array.isArray(salesData.items) ? salesData.items : [];
    } catch (error) {
      loadError = error.message || "No se pudo cargar Registro Venta.";
    }

    const activeSales = sales.filter((item) => String(item.status || "").toLowerCase() !== "archived");
    const totalAmount = salesPeriodTotal023J(salesData, sales);

    root.innerHTML = `
      <main class="sr-shell-022f">
        <header class="sr-card-022f sr-hero-022f">
          <div>
            <div class="sr-kicker-022f">Registro venta</div>
            <h1 class="sr-title-022f">Venta operativa</h1>
            <p class="sr-muted-022f">${h(session?.company?.name || "Empresa")} · ${h(labelType(panelType))} · ${h(session?.employee?.full_name || session?.user?.full_name || "usuario")}</p>
          </div>
          <button class="sr-btn-022f secondary" type="button" data-sr-back-022f>Volver</button>
        </header>

        <section class="sr-layout-022f">
          <div class="sr-card-022f sr-panel-022f">
            <div class="sr-kicker-022f">Categorías</div>
            <h2>Selecciona una categoría</h2>
            <p class="sr-muted-022f">Las referencias salen del módulo Referencias con canal Sistema o Ambos.</p>
            ${loadError ? `<div class="sr-message-022f" style="color:#ff9aae">${h(loadError)}</div>` : ""}

            <div class="sr-search-row-022i">
              <input id="srCategorySearch022I" placeholder="Buscar categoría: funda, celulares, audífonos, ropa..." autocomplete="off" />
              <div class="sr-search-meta-022i" id="srCategoryCount022I">Mostrando ${categories.length} categorías</div>
            </div>

            <div class="sr-grid-022f" id="srCategoryGrid022I">
              ${salesRenderCategories022I(categories)}
            </div>
          </div>

          <aside class="sr-card-022f sr-panel-022f">
            <div class="sr-kicker-022f">Mis ventas</div>
            <h2>${activeSales.length} activas</h2>
            <p class="sr-muted-022f">${h(formatMoney(totalAmount))} en el corte actual.</p>

            <div class="sr-search-row-022i">
              <input id="srSalesSearch022I" placeholder="Buscar venta: factura, referencia, pago, estado, total..." autocomplete="off" />
              <div class="sr-search-meta-022i" id="srSalesCount022I">Mostrando últimas ${Math.min(5, activeSales.length)} de ${activeSales.length} ventas activas</div>
            </div>

            <div class="sr-sales-list-022f sr-sales-scroll-022i" id="srSalesList022I">
              ${salesRenderRecords022I(activeSales, "", "Aún no tienes ventas activas.")}
            </div>
          </aside>
        </section>
      </main>
    `;

    function bindCategoryButtons() {
      root.querySelectorAll("[data-sr-category-022f]").forEach((button) => {
        button.addEventListener("click", async () => {
          await renderSalesRegisterCategory022F(session, button.getAttribute("data-sr-category-022f") || "");
        });
      });
    }

    root.querySelector("[data-sr-back-022f]")?.addEventListener("click", () => bootShell());
    bindCategoryButtons();

    const categorySearch = root.querySelector("#srCategorySearch022I");
    const categoryGrid = root.querySelector("#srCategoryGrid022I");
    const categoryCount = root.querySelector("#srCategoryCount022I");

    categorySearch?.addEventListener("input", () => {
      const q = categorySearch.value || "";
      const filtered = categories.filter((item) => salesMatchCategory022I(item, q));
      if (categoryGrid) categoryGrid.innerHTML = salesRenderCategories022I(filtered);
      if (categoryCount) categoryCount.textContent = q.trim()
        ? `Mostrando ${filtered.length} de ${categories.length} categorías`
        : `Mostrando ${categories.length} categorías`;
      bindCategoryButtons();
    });

    const salesSearch = root.querySelector("#srSalesSearch022I");
    salesSearch?.addEventListener("input", () => {
      salesUpdateRecordsList022I(
        session,
        activeSales,
        salesSearch.value || "",
        "#srSalesList022I",
        "#srSalesCount022I",
        () => openSalesRegisterModule022F(session)
      );
    });

    bindSalesPipelineActions022G(session, activeSales, () => openSalesRegisterModule022F(session));
  }

  async function renderSalesRegisterCategory022F(session, category, search = "") {
    salesUxStyles022I();

    if (!document.getElementById("cxSalesInvoiceStyles022H")) {
      const style = document.createElement("style");
      style.id = "cxSalesInvoiceStyles022H";
      style.textContent = `
        .sr-invoice-layout-022h{display:grid;grid-template-columns:minmax(0,1.05fr) minmax(360px,.95fr);gap:18px}
        .sr-invoice-box-022h{display:grid;gap:10px}
        .sr-invoice-line-022h{display:grid;grid-template-columns:minmax(0,1fr) 82px 110px 110px 72px;gap:8px;align-items:center;padding:12px;border-radius:16px;background:rgba(255,255,255,.08);border:1px solid rgba(255,255,255,.12)}
        .sr-invoice-line-022h small{display:block;color:rgba(255,255,255,.62);font-weight:800;margin-top:3px}
        .sr-invoice-line-022h input{width:100%;border:1px solid rgba(255,255,255,.15);background:rgba(5,7,22,.65);color:#fff;border-radius:12px;padding:10px;font-weight:900}
        .sr-invoice-line-022h button{border:0;border-radius:12px;background:rgba(255,74,124,.22);border:1px solid rgba(255,74,124,.42);color:#fff;padding:10px;font-weight:900;cursor:pointer}
        .sr-toolbar-022h{display:flex;gap:10px;flex-wrap:wrap;margin-top:12px}
        .sr-toolbar-022h button{border:0;border-radius:14px;padding:12px 14px;color:#fff;background:rgba(255,255,255,.12);border:1px solid rgba(255,255,255,.14);font-weight:950;cursor:pointer}
        .sr-toolbar-022h button.primary{background:linear-gradient(135deg,#ff25bb,#6d4cff);border:0}
        .sr-total-box-022h{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;margin-top:12px}
        .sr-total-pill-022h{border-radius:16px;padding:14px;background:rgba(255,255,255,.09);border:1px solid rgba(255,255,255,.13);font-weight:950}
        @media(max-width:960px){.sr-invoice-layout-022h{grid-template-columns:1fr}.sr-invoice-line-022h{grid-template-columns:1fr 70px 90px}.sr-invoice-line-022h strong[data-sr-cart-total]{grid-column:1/3}.sr-invoice-line-022h button{grid-column:3/4}}
      `;
      document.head.appendChild(style);
    }

    let refs = [];
    let sales = [];
    let selected = null;
    let loadError = "";

    async function loadRefs(q = "") {
      const params = new URLSearchParams();
      if (category) params.set("category", category);
      if (q) params.set("q", q);
      const data = await salesApi022F(`/references?${params.toString()}`);
      return Array.isArray(data.items) ? data.items : [];
    }

    function renderRefButtons(items) {
      return (items || []).map((item) => `
        <button class="sr-ref-022f" type="button"
          data-sr-ref-022f="${h(item.id || "")}"
          data-sr-ref-name="${h(item.name || "")}"
          data-sr-ref-category="${h(item.category || category || "")}"
          data-sr-ref-size="${h(item.size || "")}"
          data-sr-ref-color="${h(item.color || "")}"
          data-sr-ref-barcode="${h(item.barcode || item.code || item.sku || item.id || "")}"
          data-sr-ref-unit-price="${h(item.unit_price ?? item.price ?? 0)}">
          <strong>${h(item.name || "Referencia")}</strong><br>
          <small>${h([item.category, item.size, item.color].filter(Boolean).join(" · "))}</small>
        </button>
      `).join("") || `<div class="sr-muted-022f">Sin referencias para esta búsqueda.</div>`;
    }

    try {
      refs = await loadRefs(search);
      const salesData = await salesApi022F(`/sales?panel_type=${encodeURIComponent(panelType)}`);
      sales = Array.isArray(salesData.items) ? salesData.items : [];
    } catch (error) {
      loadError = error.message || "No se pudieron cargar referencias.";
    }

    const activeSales = sales.filter((item) => String(item.status || "").toLowerCase() !== "archived");

    root.innerHTML = `
      <main class="sr-shell-022f">
        <header class="sr-card-022f sr-hero-022f">
          <div>
            <div class="sr-kicker-022f">Registro venta</div>
            <h1 class="sr-title-022f">${h(category || "Categoría")}</h1>
            <p class="sr-muted-022f">Agrega varios artículos, cambia de categoría y guarda una sola factura.</p>
          </div>
          <div style="display:flex;gap:10px;flex-wrap:wrap">
            <button class="sr-btn-022f secondary" type="button" data-sr-categories-022f>Categorías</button>
            <button class="sr-btn-022f secondary" type="button" data-sr-new-invoice-022h>Nueva factura</button>
            <button class="sr-btn-022f secondary" type="button" data-sr-print-draft-022h>Imprimir factura</button>
            <button class="sr-btn-022f secondary" type="button" data-sr-back-022f>Dashboard</button>
          </div>
        </header>

        ${storeActorStripHtml023W("ventas")}

        <section class="sr-invoice-layout-022h">
          <section class="sr-card-022f sr-panel-022f">
            <div class="sr-kicker-022f">Referencia</div>
            <div class="sr-field-022f">
              <label>Filtro inteligente</label>
              <input id="srSearch022F" value="${h(search)}" placeholder="Escribe o escanea referencia, código, talla, color..." />
            </div>
            <div class="sr-toolbar-022h">
              <button class="primary" type="button" data-sr-scan-022h>Escanear código</button>
              <button type="button" data-sr-clear-search-022h>Limpiar búsqueda</button>
            </div>
            <div class="sr-ref-list-022f" id="srRefList022F" style="margin-top:14px">
              ${renderRefButtons(refs)}
            </div>
          </section>

          <aside class="sr-card-022f sr-panel-022f">
            <div class="sr-kicker-022f">Factura actual</div>
            <h2>Carrito operativo</h2>
            <div class="sr-message-022f" id="srSelected022F">Selecciona una referencia y agrégala a la factura.</div>

            <div class="sr-form-grid-022f" style="margin-top:14px">
              <div class="sr-field-022f">
                <label>Cantidad</label>
                <input id="srQty022F" type="number" min="0" step="1" value="1" />
              </div>
              <div class="sr-field-022f">
                <label>Valor unitario</label>
                <input id="srUnit022F" type="number" min="0" step="100" value="0" />
              </div>
            </div>

            <div class="sr-toolbar-022h">
              <button class="primary" type="button" data-sr-add-line-022h>Agregar a factura actual</button>
            </div>

            <div class="sr-invoice-box-022h" id="srCartRows022H" style="margin-top:14px">
              ${salesCartRowsHtml022H()}
            </div>

            <div class="sr-total-box-022h">
              <div class="sr-total-pill-022h">Artículos<br><span id="srInvoiceCount022H">${h(salesInvoiceCount022H())}</span></div>
              <div class="sr-total-pill-022h">Total<br><span id="srInvoiceTotal022H">${h(formatMoney(salesInvoiceTotal022H()))}</span></div>
            </div>

            <div class="sr-form-grid-022f" style="margin-top:14px">
              <div class="sr-field-022f">
                <label>Forma de pago</label>
                <select id="srPay022F">
                  <option value="efectivo" ${salesInvoiceCart022H.payment_method === "efectivo" ? "selected" : ""}>Efectivo</option>
                  <option value="transferencia" ${salesInvoiceCart022H.payment_method === "transferencia" ? "selected" : ""}>Transferencia</option>
                  <option value="tarjeta" ${salesInvoiceCart022H.payment_method === "tarjeta" ? "selected" : ""}>Tarjeta</option>
                  <option value="cheque" ${salesInvoiceCart022H.payment_method === "cheque" ? "selected" : ""}>Cheque</option>
                  <option value="otro" ${salesInvoiceCart022H.payment_method === "otro" ? "selected" : ""}>Otro</option>
                </select>
              </div>
              <div class="sr-field-022f">
                <label>Observación factura</label>
                <input id="srNotes022F" value="${h(salesInvoiceCart022H.notes || "")}" placeholder="Opcional" />
              </div>
            </div>

            <button class="sr-btn-022f" type="button" data-sr-save-invoice-022h style="margin-top:14px;width:100%">Guardar factura / venta</button>
            <div class="sr-message-022f" id="srMsg022F">${loadError ? h(loadError) : ""}</div>
          </aside>
        </section>

        <section class="sr-card-022f sr-panel-022f" style="margin-top:18px">
          <div class="sr-kicker-022f">Mis ventas activas</div>
          <div class="sr-search-row-022i">
            <input id="srCategorySalesSearch022I" placeholder="Buscar venta: factura, artículo, categoría, pago, estado..." autocomplete="off" />
            <div class="sr-search-meta-022i" id="srCategorySalesCount022I">Mostrando últimas ${Math.min(5, activeSales.length)} de ${activeSales.length} ventas activas</div>
          </div>
          <div class="sr-sales-list-022f sr-sales-scroll-022i" id="srCategorySalesList022I">
            ${salesRenderRecords022I(activeSales, "", "Sin ventas activas.")}
          </div>
        </section>
      </main>
    `;

    const searchInput = root.querySelector("#srSearch022F");
    bindStoreActorSelector023W();

    async function updateRefList(q = "", autoPick = false) {
      const nextRefs = await loadRefs(q);
      const list = root.querySelector("#srRefList022F");
      if (list) list.innerHTML = renderRefButtons(nextRefs);
      bindRefs();
      if (autoPick && nextRefs.length) {
        const firstBtn = root.querySelector("[data-sr-ref-022f]");
        firstBtn?.click();
      }
    }

    function bindRefs() {
      root.querySelectorAll("[data-sr-ref-022f]").forEach((button) => {
        button.addEventListener("click", () => {
          root.querySelectorAll("[data-sr-ref-022f]").forEach((item) => item.classList.remove("active"));
          button.classList.add("active");
          selected = {
            reference_id: button.getAttribute("data-sr-ref-022f") || "",
            reference_name: button.getAttribute("data-sr-ref-name") || "",
            reference_category: button.getAttribute("data-sr-ref-category") || "",
            reference_size: button.getAttribute("data-sr-ref-size") || "",
            reference_color: button.getAttribute("data-sr-ref-color") || "",
            barcode: button.getAttribute("data-sr-ref-barcode") || "",
            unit_price: Number(button.getAttribute("data-sr-ref-unit-price") || 0) || 0
          };
          const unitInput = root.querySelector("#srUnit022F");
          if (unitInput && selected.unit_price > 0) unitInput.value = String(selected.unit_price);
          const selectedBox = root.querySelector("#srSelected022F");
          if (selectedBox) selectedBox.textContent = `${selected.reference_name} · ${[selected.reference_size, selected.reference_color].filter(Boolean).join(" · ")}`;
        });
      });
    }

    function bindCartInputs() {
      root.querySelectorAll("[data-sr-cart-qty]").forEach((input) => {
        input.addEventListener("input", () => {
          const index = Number(input.getAttribute("data-sr-cart-qty") || 0);
          if (salesInvoiceCart022H.items[index]) {
            salesInvoiceCart022H.items[index].quantity = Number(input.value || 0);
            salesRefreshCartTotals022H();
          }
        });
      });

      root.querySelectorAll("[data-sr-cart-unit]").forEach((input) => {
        input.addEventListener("input", () => {
          const index = Number(input.getAttribute("data-sr-cart-unit") || 0);
          if (salesInvoiceCart022H.items[index]) {
            salesInvoiceCart022H.items[index].unit_price = Number(input.value || 0);
            salesRefreshCartTotals022H();
          }
        });
      });

      root.querySelectorAll("[data-sr-cart-remove]").forEach((button) => {
        button.addEventListener("click", async () => {
          const index = Number(button.getAttribute("data-sr-cart-remove") || 0);
          salesInvoiceCart022H.items.splice(index, 1);
          await renderSalesRegisterCategory022F(session, category, searchInput?.value || "");
        });
      });
    }

    let searchTimer = null;
    searchInput?.addEventListener("input", () => {
      clearTimeout(searchTimer);
      searchTimer = setTimeout(async () => {
        try {
          await updateRefList(searchInput.value || "", false);
        } catch (error) {
          const msg = root.querySelector("#srMsg022F");
          if (msg) msg.textContent = error.message || "No se pudo buscar.";
        }
      }, 260);
    });

    const categorySalesSearch = root.querySelector("#srCategorySalesSearch022I");
    categorySalesSearch?.addEventListener("input", () => {
      salesUpdateRecordsList022I(
        session,
        activeSales,
        categorySalesSearch.value || "",
        "#srCategorySalesList022I",
        "#srCategorySalesCount022I",
        () => renderSalesRegisterCategory022F(session, category, searchInput?.value || "")
      );
    });

    root.querySelector("[data-sr-back-022f]")?.addEventListener("click", () => bootShell());
    root.querySelector("[data-sr-categories-022f]")?.addEventListener("click", async () => openSalesRegisterModule022F(session));
    root.querySelector("[data-sr-clear-search-022h]")?.addEventListener("click", async () => {
      if (searchInput) searchInput.value = "";
      await updateRefList("", false);
    });
    root.querySelector("[data-sr-scan-022h]")?.addEventListener("click", async () => salesScanCode022H(searchInput, updateRefList));
    root.querySelector("[data-sr-new-invoice-022h]")?.addEventListener("click", async () => {
      if (salesInvoiceCart022H.items.length && !confirm("Crear nueva factura y limpiar la actual?")) return;
      salesResetInvoice022H();
      await renderSalesRegisterCategory022F(session, category, searchInput?.value || "");
    });
    root.querySelector("[data-sr-print-draft-022h]")?.addEventListener("click", () => salesPrintInvoiceDraft022H(session));

    root.querySelector("[data-sr-add-line-022h]")?.addEventListener("click", async () => {
      const msg = root.querySelector("#srMsg022F");
      if (!selected?.reference_name) {
        if (msg) msg.textContent = "Selecciona una referencia antes de agregar.";
        return;
      }
      const item = salesNormalizeItem022H({
        ...selected,
        quantity: Number(root.querySelector("#srQty022F")?.value || 0),
        unit_price: Number(root.querySelector("#srUnit022F")?.value || 0)
      });
      if (!item.quantity) {
        if (msg) msg.textContent = "La cantidad debe ser mayor a cero.";
        return;
      }
      salesInvoiceCart022H.items.push(item);
      if (msg) msg.textContent = "Artículo agregado a la factura actual.";
      await renderSalesRegisterCategory022F(session, category, searchInput?.value || "");
    });

    root.querySelector("#srPay022F")?.addEventListener("change", (event) => {
      salesInvoiceCart022H.payment_method = event.target.value || "efectivo";
    });
    root.querySelector("#srNotes022F")?.addEventListener("input", (event) => {
      salesInvoiceCart022H.notes = event.target.value || "";
    });

    root.querySelector("[data-sr-save-invoice-022h]")?.addEventListener("click", async () => {
      const msg = root.querySelector("#srMsg022F");
      salesInvoiceCart022H.payment_method = root.querySelector("#srPay022F")?.value || "efectivo";
      salesInvoiceCart022H.notes = root.querySelector("#srNotes022F")?.value || "";

      if (!salesInvoiceCart022H.items.length) {
        if (msg) msg.textContent = "Agrega al menos un artículo antes de guardar.";
        return;
      }

      try {
        if (msg) msg.textContent = "Guardando factura...";
        const data = await salesApi022F(`/sales?panel_type=${encodeURIComponent(panelType)}`, {
          method: "POST",
          body: JSON.stringify({
            payment_method: salesInvoiceCart022H.payment_method,
            notes: salesInvoiceCart022H.notes,
            items: salesInvoiceCart022H.items
          })
        });
        if (msg) msg.textContent = `Factura guardada ${data?.invoice_number || ""}.`;
        salesResetInvoice022H();
        await renderSalesRegisterCategory022F(session, category, searchInput?.value || "");
      } catch (error) {
        if (msg) msg.textContent = error.message || "No se pudo guardar la factura.";
      }
    });

    bindRefs();
    bindCartInputs();
    bindSalesPipelineActions022G(session, activeSales, () => renderSalesRegisterCategory022F(session, category, searchInput?.value || ""));
  }
  /* CLONEXA_022I_MINIPANEL_SALES_SEARCH_KPI_LIMIT5_END */

  /* CLONEXA_022F_REGISTRO_VENTA_DINAMICO_REFERENCIAS_END */

  /* CLONEXA_022J_SALES_TOP10_ADJUSTMENTS_CLEAN_VIEW_START */
  function salesEnsureAdjustment022J() {
    if (!salesInvoiceCart022H || typeof salesInvoiceCart022H !== "object") salesInvoiceCart022H = { items: [], payment_method: "efectivo", notes: "" };
    if (!Array.isArray(salesInvoiceCart022H.items)) salesInvoiceCart022H.items = [];
    if (!salesInvoiceCart022H.payment_method) salesInvoiceCart022H.payment_method = "efectivo";
    if (salesInvoiceCart022H.adjustment_type == null) salesInvoiceCart022H.adjustment_type = "none";
    if (salesInvoiceCart022H.adjustment_percent == null) salesInvoiceCart022H.adjustment_percent = 0;
    if (salesInvoiceCart022H.received_amount == null) salesInvoiceCart022H.received_amount = 0;
    if (salesInvoiceCart022H.change_amount == null) salesInvoiceCart022H.change_amount = 0;
  }

  function salesAdjustmentLabel022J(type) {
    return ({ none: "Sin ajuste", discount: "Descuento", retention: "Retención", iva: "IVA incluido", tax: "Impuesto incluido" })[String(type || "none").toLowerCase()] || "Sin ajuste";
  }

  function salesSubtotal022J(items = null) {
    const rows = Array.isArray(items) ? items : salesInvoiceCart022H.items;
    return Math.max(0, rows.reduce((sum, item) => sum + (Number(item.quantity || 0) * Number(item.unit_price || 0)), 0));
  }

  function salesAdjustmentMeta022J(items = null) {
    salesEnsureAdjustment022J();
    const subtotal = Math.round(salesSubtotal022J(items) * 100) / 100;
    const type = String(salesInvoiceCart022H.adjustment_type || "none").toLowerCase();
    const percentRaw = Number(salesInvoiceCart022H.adjustment_percent || 0);
    const percent = type === "none" ? 0 : Math.min(20, Math.max(1, percentRaw || 1));

    let baseAmount = subtotal;
    let adjustmentAmount = 0;
    let totalPayable = subtotal;
    let mode = "none";

    if (type === "discount" || type === "retention") {
      mode = "subtract";
      adjustmentAmount = Math.round((subtotal * percent / 100) * 100) / 100;
      totalPayable = Math.max(0, Math.round((subtotal - adjustmentAmount) * 100) / 100);
    } else if (type === "iva" || type === "tax") {
      mode = "included";
      baseAmount = Math.round((subtotal / (1 + (percent / 100))) * 100) / 100;
      adjustmentAmount = Math.round((subtotal - baseAmount) * 100) / 100;
      totalPayable = subtotal;
    }

    return {
      type,
      label: salesAdjustmentLabel022J(type),
      percent,
      subtotal,
      base_amount: Math.round(baseAmount * 100) / 100,
      adjustment_amount: Math.round(adjustmentAmount * 100) / 100,
      total_payable: Math.round(totalPayable * 100) / 100,
      mode
    };
  }

  function salesInvoiceTotal022H() {
    return salesAdjustmentMeta022J().total_payable;
  }

  function salesCashNumber023D(value) {
    const raw = String(value ?? "").replace(/[^\d.,-]/g, "").replace(",", ".");
    const number = Number(raw);
    return Number.isFinite(number) ? Math.max(0, number) : 0;
  }

  function salesPaymentIsCash023D() {
    salesEnsureAdjustment022J();
    return String(salesInvoiceCart022H.payment_method || "efectivo").toLowerCase() === "efectivo";
  }

  function salesCashChange023D() {
    salesEnsureAdjustment022J();
    if (!salesPaymentIsCash023D()) return 0;
    const received = salesCashNumber023D(salesInvoiceCart022H.received_amount);
    const total = salesInvoiceTotal022H();
    return Math.max(0, Math.round((received - total) * 100) / 100);
  }

  function salesCashPayload023D() {
    salesEnsureAdjustment022J();
    const isCash = salesPaymentIsCash023D();
    const received = isCash ? salesCashNumber023D(salesInvoiceCart022H.received_amount) : 0;
    const change = isCash ? salesCashChange023D() : 0;
    salesInvoiceCart022H.received_amount = received;
    salesInvoiceCart022H.change_amount = change;
    return {
      received_amount: received,
      change_amount: change,
    };
  }

  function salesRefreshCashChange023D() {
    salesEnsureAdjustment022J();
    const isCash = salesPaymentIsCash023D();
    const receivedInput = document.getElementById("srReceived023D");
    const changeInput = document.getElementById("srChange023D");
    if (!isCash) {
      salesInvoiceCart022H.received_amount = 0;
      salesInvoiceCart022H.change_amount = 0;
    } else {
      salesInvoiceCart022H.received_amount = salesCashNumber023D(salesInvoiceCart022H.received_amount);
      salesInvoiceCart022H.change_amount = salesCashChange023D();
    }
    if (receivedInput) {
      receivedInput.disabled = !isCash;
      receivedInput.value = String(salesInvoiceCart022H.received_amount || 0);
      receivedInput.placeholder = isCash ? "Dinero recibido" : "Solo efectivo";
    }
    if (changeInput) changeInput.value = formatMoney(salesInvoiceCart022H.change_amount || 0);
  }

  function salesInvoiceCount022H() {
    salesEnsureAdjustment022J();
    return salesInvoiceCart022H.items.reduce((sum, item) => sum + Number(item.quantity || 0), 0);
  }

  function salesResetInvoice022H() {
    salesInvoiceCart022H = { items: [], payment_method: "efectivo", notes: "", adjustment_type: "none", adjustment_percent: 0, received_amount: 0, change_amount: 0 };
  }

  function salesAdjustmentOptions022J() {
    salesEnsureAdjustment022J();
    const current = String(salesInvoiceCart022H.adjustment_type || "none").toLowerCase();
    return [
      ["none", "Ninguno"],
      ["discount", "Descuento"],
      ["iva", "IVA incluido"],
      ["retention", "Retención"],
      ["tax", "Impuesto incluido"]
    ].map(([value, label]) => `<option value="${value}" ${current === value ? "selected" : ""}>${label}</option>`).join("");
  }

  function salesPercentOptions022J() {
    salesEnsureAdjustment022J();
    const selected = Math.min(20, Math.max(1, Number(salesInvoiceCart022H.adjustment_percent || 1)));
    return Array.from({ length: 20 }, (_, index) => {
      const value = index + 1;
      return `<option value="${value}" ${selected === value ? "selected" : ""}>${value}%</option>`;
    }).join("");
  }

  function salesAdjustmentSummaryHtml022J() {
    const meta = salesAdjustmentMeta022J();
    if (meta.mode === "included") {
      return `
        <div class="sr-total-pill-022h">Base artículos<br><span>${h(formatMoney(meta.base_amount))}</span></div>
        <div class="sr-total-pill-022h">${h(meta.label)} ${h(meta.percent)}%<br><span>${h(formatMoney(meta.adjustment_amount))}</span></div>
        <div class="sr-total-pill-022h sr-total-payable-022j">Total a pagar<br><span id="srInvoiceTotal022H">${h(formatMoney(meta.total_payable))}</span></div>
      `;
    }
    if (meta.mode === "subtract") {
      return `
        <div class="sr-total-pill-022h">Total artículos<br><span>${h(formatMoney(meta.subtotal))}</span></div>
        <div class="sr-total-pill-022h">${h(meta.label)} ${h(meta.percent)}%<br><span>- ${h(formatMoney(meta.adjustment_amount))}</span></div>
        <div class="sr-total-pill-022h sr-total-payable-022j">Total a pagar<br><span id="srInvoiceTotal022H">${h(formatMoney(meta.total_payable))}</span></div>
      `;
    }
    return `
      <div class="sr-total-pill-022h">Total artículos<br><span>${h(formatMoney(meta.subtotal))}</span></div>
      <div class="sr-total-pill-022h">Ajuste<br><span>${h(formatMoney(0))}</span></div>
      <div class="sr-total-pill-022h sr-total-payable-022j">Total a pagar<br><span id="srInvoiceTotal022H">${h(formatMoney(meta.total_payable))}</span></div>
    `;
  }

  function salesInvoiceAdjustmentPayload022J() {
    const meta = salesAdjustmentMeta022J();
    return {
      adjustment_type: meta.type,
      adjustment_percent: meta.percent,
      subtotal: meta.subtotal,
      adjustment_amount: meta.adjustment_amount,
      total_payable: meta.total_payable
    };
  }

  function salesCartRowsHtml022H() {
    salesEnsureAdjustment022J();
    if (!salesInvoiceCart022H.items.length) return `<div class="sr-muted-022f">Factura actual vacía. Agrega artículos desde cualquier categoría.</div>`;
    return salesInvoiceCart022H.items.map((item, index) => `
      <article class="sr-invoice-line-022h" data-sr-cart-line="${index}">
        <div>
          <strong>${h(item.reference_name)}</strong>
          <small>${h([item.reference_category, item.reference_size, item.reference_color].filter(Boolean).join(" · "))}</small>
        </div>
        <input type="number" min="0" step="1" value="${h(item.quantity)}" data-sr-cart-qty="${index}" title="Cantidad">
        <input type="number" min="0" step="100" value="${h(item.unit_price)}" data-sr-cart-unit="${index}" title="Valor unitario">
        <strong data-sr-cart-total="${index}">${h(formatMoney(Number(item.quantity || 0) * Number(item.unit_price || 0)))}</strong>
        <button type="button" data-sr-cart-remove="${index}">Quitar</button>
      </article>
    `).join("");
  }

  function salesRefreshCartTotals022H() {
    salesEnsureAdjustment022J();
    salesInvoiceCart022H.items = salesInvoiceCart022H.items.map(salesNormalizeItem022H);
    document.querySelectorAll("[data-sr-cart-total]").forEach((node) => {
      const index = Number(node.getAttribute("data-sr-cart-total") || 0);
      const item = salesInvoiceCart022H.items[index];
      if (item) node.textContent = formatMoney(Number(item.quantity || 0) * Number(item.unit_price || 0));
    });
    const countNode = document.getElementById("srInvoiceCount022H");
    if (countNode) countNode.textContent = String(salesInvoiceCount022H());
    const totalBox = document.getElementById("srAdjustmentSummary022J");
    if (totalBox) totalBox.innerHTML = salesAdjustmentSummaryHtml022J();
    salesRefreshCashChange023D();
  }

  function salesPopularMap022J(sales, category) {
    const targetCategory = salesSearchText022I(category || "");
    const map = new Map();
    (sales || []).forEach((sale) => {
      const items = Array.isArray(sale?.items) && sale.items.length ? sale.items : [sale];
      items.forEach((item) => {
        const itemCategory = salesSearchText022I(item.reference_category || sale.reference_category || "");
        if (targetCategory && itemCategory !== targetCategory) return;
        const keyA = String(item.reference_id || "").toLowerCase();
        const keyB = String(item.reference_name || item.name || "").toLowerCase();
        const qty = Number(item.quantity || 0) || 1;
        if (keyA) map.set(keyA, (map.get(keyA) || 0) + qty);
        if (keyB) map.set(keyB, (map.get(keyB) || 0) + qty);
      });
    });
    return map;
  }

  function salesReferencePopularity022J(item, popularMap) {
    return Math.max(
      Number(popularMap.get(String(item.id || "").toLowerCase()) || 0),
      Number(popularMap.get(String(item.name || "").toLowerCase()) || 0)
    );
  }

  function salesSortReferences022J(refs, sales, category, search) {
    const popularMap = salesPopularMap022J(sales, category);
    const rows = [...(refs || [])].sort((a, b) => {
      const popDiff = salesReferencePopularity022J(b, popularMap) - salesReferencePopularity022J(a, popularMap);
      if (popDiff) return popDiff;
      return String(a.name || "").localeCompare(String(b.name || ""), "es", { sensitivity: "base" });
    });
    return String(search || "").trim() ? rows : rows.slice(0, 10);
  }

  function salesAdjustmentStyles022J() {
    if (document.getElementById("clonexa-sales-022j-style")) return;
    const style = document.createElement("style");
    style.id = "clonexa-sales-022j-style";
    style.textContent = `
      /* CLONEXA_022J_R1_VISUAL_RESTORE_KEEP_FUNCTIONS */
      .sr-invoice-layout-022h{
        display:grid;
        grid-template-columns:minmax(0,1.08fr) minmax(390px,.92fr);
        gap:18px;
        align-items:start;
      }
      .sr-invoice-layout-022h>.sr-panel-022f{min-width:0}
      .sr-invoice-box-022h{
        display:grid;
        gap:10px;
        max-height:280px;
        overflow:auto;
        padding-right:3px;
      }
      .sr-invoice-box-022h::-webkit-scrollbar{width:8px}
      .sr-invoice-box-022h::-webkit-scrollbar-thumb{
        background:linear-gradient(180deg,#ff25bb,#35a8ff);
        border-radius:999px;
      }
      .sr-invoice-line-022h{
        display:grid;
        grid-template-columns:minmax(0,1fr) 78px 108px 104px 68px;
        gap:8px;
        align-items:center;
        padding:12px;
        border-radius:16px;
        background:rgba(255,255,255,.08);
        border:1px solid rgba(255,255,255,.12);
      }
      .sr-invoice-line-022h small{
        display:block;
        color:rgba(255,255,255,.64);
        font-weight:800;
        margin-top:3px;
      }
      .sr-invoice-line-022h input{
        width:100%;
        box-sizing:border-box;
        border:1px solid rgba(255,255,255,.15);
        background:rgba(5,7,22,.65);
        color:#fff;
        border-radius:12px;
        padding:10px;
        font-weight:900;
        outline:none;
      }
      .sr-invoice-line-022h button{
        border:0;
        border-radius:12px;
        background:rgba(255,74,124,.22);
        border:1px solid rgba(255,74,124,.42);
        color:#fff;
        padding:10px;
        font-weight:900;
        cursor:pointer;
      }
      .sr-toolbar-022h{
        display:flex;
        gap:10px;
        flex-wrap:wrap;
        align-items:center;
        margin-top:12px;
      }
      .sr-toolbar-022h button{
        border:0;
        border-radius:16px;
        padding:12px 15px;
        color:#fff;
        background:rgba(255,255,255,.13);
        border:1px solid rgba(255,255,255,.15);
        font-weight:950;
        cursor:pointer;
        box-shadow:0 12px 28px rgba(0,0,0,.18);
      }
      .sr-toolbar-022h button.primary{
        background:linear-gradient(135deg,#ff25bb,#6d4cff);
        border:0;
      }
      .sr-ref-list-022f{
        display:grid;
        gap:10px;
        max-height:430px;
        overflow:auto;
        margin-top:14px;
        padding-right:3px;
      }
      .sr-ref-list-022f::-webkit-scrollbar{width:8px}
      .sr-ref-list-022f::-webkit-scrollbar-thumb{
        background:linear-gradient(180deg,#ff25bb,#35a8ff);
        border-radius:999px;
      }
      .sr-ref-022f{
        width:100%;
        text-align:left;
        border:1px solid rgba(255,255,255,.13);
        background:rgba(255,255,255,.07);
        color:#fff;
        border-radius:18px;
        padding:14px 15px;
        cursor:pointer;
      }
      .sr-ref-022f:hover{
        border-color:rgba(255,57,208,.42);
        background:rgba(255,255,255,.10);
      }
      .sr-ref-022f.active{
        border-color:#ff39d0;
        background:rgba(255,57,208,.16);
      }
      .sr-ref-popular-022j{
        display:inline-flex;
        align-items:center;
        margin-left:8px;
        padding:3px 8px;
        border-radius:999px;
        background:rgba(54,230,170,.14);
        color:#7cffd9;
        font-size:11px;
        font-weight:900;
      }
      .sr-top-label-022j{
        margin:14px 0 8px;
        color:rgba(255,255,255,.76);
        font-size:12px;
        font-weight:950;
        letter-spacing:.18em;
        text-transform:uppercase;
      }
      .sr-total-box-022h{
        display:grid;
        grid-template-columns:repeat(4,minmax(0,1fr));
        gap:10px;
        margin-top:14px;
      }
      .sr-total-pill-022h{
        border-radius:17px;
        padding:14px;
        background:linear-gradient(135deg,rgba(255,255,255,.10),rgba(255,255,255,.055));
        border:1px solid rgba(255,255,255,.14);
        font-weight:950;
        min-height:58px;
      }
      .sr-total-pill-022h span{
        display:block;
        margin-top:4px;
        font-size:18px;
        color:#fff;
      }
      .sr-total-payable-022j{
        border-color:rgba(247,37,179,.58)!important;
        box-shadow:0 16px 36px rgba(247,37,179,.16);
        background:linear-gradient(135deg,rgba(247,37,179,.20),rgba(57,148,255,.14));
      }
      .sr-adjust-grid-022j{
        display:grid;
        grid-template-columns:1.2fr .8fr;
        gap:12px;
        margin-top:14px;
      }
      .sr-cash-grid-023d{
        display:grid;
        grid-template-columns:1fr 1fr;
        gap:12px;
        margin-top:12px;
      }
      .sr-field-022f input[readonly],
      .sr-field-022f input:disabled{
        opacity:.82;
        cursor:not-allowed;
      }
      .sr-change-output-023d{
        color:#7cffd9!important;
        border-color:rgba(124,255,217,.24)!important;
        background:rgba(3,18,27,.62)!important;
      }
      .sr-adjust-grid-022j select,
      .sr-form-grid-022f select,
      .sr-form-grid-022f input,
      .sr-field-022f input{
        min-height:48px;
      }
      .sr-message-022f{
        margin-top:12px;
        font-weight:900;
        color:#76ffd5;
      }
      @media(max-width:1120px){
        .sr-invoice-layout-022h{grid-template-columns:1fr}
        .sr-total-box-022h{grid-template-columns:repeat(2,minmax(0,1fr))}
      }
      @media(max-width:760px){
        .sr-invoice-line-022h{grid-template-columns:1fr 70px 90px}
        .sr-invoice-line-022h strong[data-sr-cart-total]{grid-column:1/3}
        .sr-invoice-line-022h button{grid-column:3/4}
        .sr-total-box-022h,.sr-adjust-grid-022j,.sr-cash-grid-023d{grid-template-columns:1fr}
      }
    `;
    document.head.appendChild(style);
  }

  function salesPrintInvoiceDraft022H(session, sale = null) {
    const items = sale?.items || salesInvoiceCart022H.items;
    if (!items || !items.length) { alert("No hay artículos para imprimir."); return; }

    const invoiceNumber = sale?.invoice_number || "Factura actual";
    const seller = sale?.source_user_label || session?.employee?.full_name || session?.user?.full_name || "Vendedor";
    const company = session?.company?.name || "Empresa";
    const adjustment = sale?.adjustment || salesAdjustmentMeta022J(items);
    const total = Number(adjustment.total_payable ?? sale?.total ?? 0);
    const paymentMethod = String(sale?.payment_method || salesInvoiceCart022H.payment_method || "efectivo").toLowerCase();
    const receivedAmount = Number(sale?.received_amount ?? salesInvoiceCart022H.received_amount ?? 0) || 0;
    const changeAmount = Number(sale?.change_amount ?? salesCashChange023D() ?? 0) || 0;
    const rows = items.map((item) => `
      <tr>
        <td>${h(item.reference_name || "")}<br><small>${h([item.reference_category, item.reference_size, item.reference_color].filter(Boolean).join(" · "))}</small></td>
        <td style="text-align:center">${h(item.quantity || 0)}</td>
        <td style="text-align:right">${h(formatMoney(item.unit_price || 0))}</td>
        <td style="text-align:right">${h(formatMoney((Number(item.quantity || 0) * Number(item.unit_price || 0))))}</td>
      </tr>
    `).join("");

    let totalsHtml = "";
    if (adjustment.type === "iva" || adjustment.type === "tax") {
      totalsHtml = `<div class="line"><span>Base artículos</span><strong>${h(formatMoney(adjustment.base_amount || 0))}</strong></div><div class="line"><span>${h(adjustment.label || "Impuesto incluido")} ${h(adjustment.percent || 0)}%</span><strong>${h(formatMoney(adjustment.adjustment_amount || 0))}</strong></div><div class="total">TOTAL A PAGAR ${h(formatMoney(total))}</div>`;
    } else if (adjustment.type === "discount" || adjustment.type === "retention") {
      totalsHtml = `<div class="line"><span>Total artículos</span><strong>${h(formatMoney(adjustment.subtotal || 0))}</strong></div><div class="line"><span>${h(adjustment.label || "Ajuste")} ${h(adjustment.percent || 0)}%</span><strong>- ${h(formatMoney(adjustment.adjustment_amount || 0))}</strong></div><div class="total">TOTAL A PAGAR ${h(formatMoney(total))}</div>`;
    } else {
      totalsHtml = `<div class="total">TOTAL A PAGAR ${h(formatMoney(total))}</div>`;
    }
    const cashHtml = paymentMethod === "efectivo" && receivedAmount > 0
      ? `<div class="line"><span>Recibido</span><strong>${h(formatMoney(receivedAmount))}</strong></div><div class="line"><span>Cambio</span><strong>${h(formatMoney(changeAmount))}</strong></div>`
      : "";

    const win = window.open("", "_blank");
    if (!win) return;
    win.document.write(`
      <html><head><title>${h(invoiceNumber)}</title>
      <style>body{font-family:Arial,sans-serif;padding:28px;color:#111}h1{margin:0 0 4px;font-size:28px}.muted{color:#555;margin-bottom:22px}table{width:100%;border-collapse:collapse;margin-top:18px}th{background:#111;color:#fff;text-align:left;padding:10px}td{border-bottom:1px solid #ddd;padding:10px;vertical-align:top}.line{display:flex;justify-content:flex-end;gap:28px;margin-top:10px;font-size:15px}.total{font-size:24px;font-weight:900;text-align:right;margin-top:18px;color:#f725b3}.footer{margin-top:40px;color:#555;font-size:12px;text-align:center}</style>
      </head><body>
        <h1>${h(company)}</h1>
        <div class="muted">${h(invoiceNumber)} · Vendedor: ${h(seller)} · ${new Date().toLocaleString()}</div>
        <table><thead><tr><th>Artículo</th><th>Cant.</th><th>Valor unit.</th><th>Total</th></tr></thead><tbody>${rows}</tbody></table>
        ${totalsHtml}
        ${cashHtml}
        <div class="footer">Registro venta generado por CLONEXA</div>
        <script>setTimeout(()=>print(),500)<\/script>
      </body></html>
    `);
    win.document.close();
  }

  async function renderSalesRegisterCategory022F(session, category, search = "") {
    salesRegisterStyles022F();
    salesUxStyles022I();
    salesAdjustmentStyles022J();
    salesEnsureAdjustment022J();

    let refs = [];
    let sales = [];
    let selected = null;
    let loadError = "";

    async function loadRefs(q = "") {
      const params = new URLSearchParams();
      if (category) params.set("category", category);
      if (q) params.set("q", q);
      params.set("limit", "80");
      const data = await salesApi022F(`/references?${params.toString()}`);
      return Array.isArray(data.items) ? data.items : [];
    }

    function renderRefButtons(items, currentSearch = "") {
      const displayItems = salesSortReferences022J(items, sales, category, currentSearch);
      const popularMap = salesPopularMap022J(sales, category);
      return (displayItems || []).map((item) => {
        const popularity = salesReferencePopularity022J(item, popularMap);
        return `
          <button class="sr-ref-022f" type="button"
            data-sr-ref-022f="${h(item.id || "")}"
            data-sr-ref-name="${h(item.name || "")}"
            data-sr-ref-category="${h(item.category || category || "")}"
            data-sr-ref-size="${h(item.size || "")}"
            data-sr-ref-color="${h(item.color || "")}"
            data-sr-ref-barcode="${h(item.barcode || item.code || item.sku || item.id || "")}"
          data-sr-ref-unit-price="${h(item.unit_price ?? item.price ?? 0)}">
            <strong>${h(item.name || "Referencia")}${popularity ? `<span class="sr-ref-popular-022j">${h(popularity)} ped.</span>` : ""}</strong><br>
            <small>${h([item.category, item.size, item.color].filter(Boolean).join(" · "))}</small>
          </button>
        `;
      }).join("") || `<div class="sr-muted-022f">Sin referencias para esta búsqueda.</div>`;
    }

    try {
      refs = await loadRefs(search);
      const salesData = await salesApi022F(`/sales?panel_type=${encodeURIComponent(panelType)}`);
      sales = Array.isArray(salesData.items) ? salesData.items : [];
    } catch (error) {
      loadError = error.message || "No se pudieron cargar referencias.";
    }

    root.innerHTML = `
      <main class="sr-shell-022f">
        <header class="sr-card-022f sr-hero-022f">
          <div>
            <div class="sr-kicker-022f">Registro venta</div>
            <h1 class="sr-title-022f">${h(category || "Categoría")}</h1>
            <p class="sr-muted-022f">Top 10 más pedidos, búsqueda inteligente y factura con ajustes.</p>
          </div>
          <div style="display:flex;gap:10px;flex-wrap:wrap">
            <button class="sr-btn-022f secondary" type="button" data-sr-categories-022f>Categorías</button>
            <button class="sr-btn-022f secondary" type="button" data-sr-new-invoice-022h>Nueva factura</button>
            <button class="sr-btn-022f secondary" type="button" data-sr-print-draft-022h>Imprimir factura</button>
            <button class="sr-btn-022f secondary" type="button" data-sr-back-022f>Dashboard</button>
          </div>
        </header>

        ${storeActorStripHtml023W("ventas")}

        <section class="sr-invoice-layout-022h">
          <section class="sr-card-022f sr-panel-022f">
            <div class="sr-kicker-022f">Referencia</div>
            <div class="sr-field-022f">
              <label>Filtro inteligente</label>
              <input id="srSearch022F" value="${h(search)}" placeholder="Escribe o escanea referencia, código, talla, color..." />
            </div>
            <div class="sr-toolbar-022h">
              <button class="primary" type="button" data-sr-scan-022h>Escanear código</button>
              <button type="button" data-sr-clear-search-022h>Limpiar búsqueda</button>
            </div>
            <div class="sr-top-label-022j" id="srTopLabel022J">${search ? "Resultados de búsqueda" : "Top 10 más pedidos"}</div>
            <div class="sr-ref-list-022f" id="srRefList022F" style="margin-top:14px">${renderRefButtons(refs, search)}</div>
          </section>

          <aside class="sr-card-022f sr-panel-022f">
            <div class="sr-kicker-022f">Factura actual</div>
            <h2>Carrito operativo</h2>
            <div class="sr-message-022f" id="srSelected022F">Selecciona una referencia y agrégala a la factura.</div>

            <div class="sr-form-grid-022f" style="margin-top:14px">
              <div class="sr-field-022f"><label>Cantidad</label><input id="srQty022F" type="number" min="0" step="1" value="1" /></div>
              <div class="sr-field-022f"><label>Valor unitario</label><input id="srUnit022F" type="number" min="0" step="100" value="0" /></div>
            </div>

            <div class="sr-cash-grid-023d">
              <div class="sr-field-022f"><label>Recibido</label><input id="srReceived023D" type="number" min="0" step="100" value="${h(salesInvoiceCart022H.received_amount || 0)}" /></div>
              <div class="sr-field-022f"><label>Cambio</label><input id="srChange023D" class="sr-change-output-023d" readonly value="${h(formatMoney(salesCashChange023D()))}" /></div>
            </div>

            <div class="sr-toolbar-022h"><button class="primary" type="button" data-sr-add-line-022h>Agregar a factura actual</button></div>

            <div class="sr-invoice-box-022h" id="srCartRows022H" style="margin-top:14px">${salesCartRowsHtml022H()}</div>

            <div class="sr-total-box-022h">
              <div class="sr-total-pill-022h">Artículos<br><span id="srInvoiceCount022H">${h(salesInvoiceCount022H())}</span></div>
              <div id="srAdjustmentSummary022J" style="display:contents">${salesAdjustmentSummaryHtml022J()}</div>
            </div>

            <div class="sr-adjust-grid-022j">
              <div class="sr-field-022f"><label>Selección ajuste</label><select id="srAdjustmentType022J">${salesAdjustmentOptions022J()}</select></div>
              <div class="sr-field-022f"><label>Porcentaje</label><select id="srAdjustmentPercent022J">${salesPercentOptions022J()}</select></div>
            </div>

            <div class="sr-form-grid-022f" style="margin-top:14px">
              <div class="sr-field-022f">
                <label>Forma de pago</label>
                <select id="srPay022F">
                  <option value="efectivo" ${salesInvoiceCart022H.payment_method === "efectivo" ? "selected" : ""}>Efectivo</option>
                  <option value="transferencia" ${salesInvoiceCart022H.payment_method === "transferencia" ? "selected" : ""}>Transferencia</option>
                  <option value="tarjeta" ${salesInvoiceCart022H.payment_method === "tarjeta" ? "selected" : ""}>Tarjeta</option>
                  <option value="cheque" ${salesInvoiceCart022H.payment_method === "cheque" ? "selected" : ""}>Cheque</option>
                  <option value="otro" ${salesInvoiceCart022H.payment_method === "otro" ? "selected" : ""}>Otro</option>
                </select>
              </div>
              <div class="sr-field-022f"><label>Observación factura</label><input id="srNotes022F" value="${h(salesInvoiceCart022H.notes || "")}" placeholder="Opcional" /></div>
            </div>

            <button class="sr-btn-022f" type="button" data-sr-save-invoice-022h style="margin-top:14px;width:100%">Guardar factura / venta</button>
            <div class="sr-message-022f" id="srMsg022F">${loadError ? h(loadError) : ""}</div>
          </aside>
        </section>
      </main>
    `;

    const searchInput = root.querySelector("#srSearch022F");

    async function updateRefList(q = "", autoPick = false) {
      const nextRefs = await loadRefs(q);
      const list = root.querySelector("#srRefList022F");
      const topLabel = root.querySelector("#srTopLabel022J");
      if (list) list.innerHTML = renderRefButtons(nextRefs, q);
      if (topLabel) topLabel.textContent = String(q || "").trim() ? "Resultados de búsqueda" : "Top 10 más pedidos";
      bindRefs();
      if (autoPick && nextRefs.length) root.querySelector("[data-sr-ref-022f]")?.click();
    }

    function bindRefs() {
      root.querySelectorAll("[data-sr-ref-022f]").forEach((button) => {
        button.addEventListener("click", () => {
          root.querySelectorAll("[data-sr-ref-022f]").forEach((item) => item.classList.remove("active"));
          button.classList.add("active");
          selected = {
            reference_id: button.getAttribute("data-sr-ref-022f") || "",
            reference_name: button.getAttribute("data-sr-ref-name") || "",
            reference_category: button.getAttribute("data-sr-ref-category") || "",
            reference_size: button.getAttribute("data-sr-ref-size") || "",
            reference_color: button.getAttribute("data-sr-ref-color") || "",
            barcode: button.getAttribute("data-sr-ref-barcode") || "",
            unit_price: Number(button.getAttribute("data-sr-ref-unit-price") || 0) || 0
          };
          const unitInput = root.querySelector("#srUnit022F");
          if (unitInput && selected.unit_price > 0) unitInput.value = String(selected.unit_price);
          const selectedBox = root.querySelector("#srSelected022F");
          if (selectedBox) selectedBox.textContent = `${selected.reference_name} · ${[selected.reference_size, selected.reference_color].filter(Boolean).join(" · ")}`;
        });
      });
    }

    function bindCartInputs() {
      root.querySelectorAll("[data-sr-cart-qty]").forEach((input) => {
        input.addEventListener("input", () => {
          const index = Number(input.getAttribute("data-sr-cart-qty") || 0);
          if (salesInvoiceCart022H.items[index]) {
            salesInvoiceCart022H.items[index].quantity = Number(input.value || 0);
            salesRefreshCartTotals022H();
          }
        });
      });
      root.querySelectorAll("[data-sr-cart-unit]").forEach((input) => {
        input.addEventListener("input", () => {
          const index = Number(input.getAttribute("data-sr-cart-unit") || 0);
          if (salesInvoiceCart022H.items[index]) {
            salesInvoiceCart022H.items[index].unit_price = Number(input.value || 0);
            salesRefreshCartTotals022H();
          }
        });
      });
      root.querySelectorAll("[data-sr-cart-remove]").forEach((button) => {
        button.addEventListener("click", async () => {
          salesInvoiceCart022H.items.splice(Number(button.getAttribute("data-sr-cart-remove") || 0), 1);
          await renderSalesRegisterCategory022F(session, category, searchInput?.value || "");
        });
      });
    }

    let searchTimer = null;
    searchInput?.addEventListener("input", () => {
      clearTimeout(searchTimer);
      searchTimer = setTimeout(async () => {
        try { await updateRefList(searchInput.value || "", false); }
        catch (error) {
          const msg = root.querySelector("#srMsg022F");
          if (msg) msg.textContent = error.message || "No se pudo buscar.";
        }
      }, 260);
    });

    root.querySelector("[data-sr-back-022f]")?.addEventListener("click", () => bootShell());
    root.querySelector("[data-sr-categories-022f]")?.addEventListener("click", async () => openSalesRegisterModule022F(session));
    root.querySelector("[data-sr-clear-search-022h]")?.addEventListener("click", async () => { if (searchInput) searchInput.value = ""; await updateRefList("", false); });
    root.querySelector("[data-sr-scan-022h]")?.addEventListener("click", async () => salesScanCode022H(searchInput, updateRefList));
    root.querySelector("[data-sr-new-invoice-022h]")?.addEventListener("click", async () => {
      if (salesInvoiceCart022H.items.length && !confirm("Crear nueva factura y limpiar la actual?")) return;
      salesResetInvoice022H();
      await renderSalesRegisterCategory022F(session, category, searchInput?.value || "");
    });
    root.querySelector("[data-sr-print-draft-022h]")?.addEventListener("click", () => salesPrintInvoiceDraft022H(session));

    root.querySelector("[data-sr-add-line-022h]")?.addEventListener("click", async () => {
      const msg = root.querySelector("#srMsg022F");
      if (!selected?.reference_name) { if (msg) msg.textContent = "Selecciona una referencia antes de agregar."; return; }
      const item = salesNormalizeItem022H({
        ...selected,
        quantity: Number(root.querySelector("#srQty022F")?.value || 0),
        unit_price: Number(root.querySelector("#srUnit022F")?.value || 0)
      });
      if (!item.quantity) { if (msg) msg.textContent = "La cantidad debe ser mayor a cero."; return; }
      salesInvoiceCart022H.items.push(item);
      if (msg) msg.textContent = "Artículo agregado a la factura actual.";
      await renderSalesRegisterCategory022F(session, category, searchInput?.value || "");
    });

    root.querySelector("#srAdjustmentType022J")?.addEventListener("change", (event) => {
      salesInvoiceCart022H.adjustment_type = event.target.value || "none";
      salesInvoiceCart022H.adjustment_percent = salesInvoiceCart022H.adjustment_type === "none" ? 0 : (salesInvoiceCart022H.adjustment_percent || 1);
      salesRefreshCartTotals022H();
    });
    root.querySelector("#srAdjustmentPercent022J")?.addEventListener("change", (event) => {
      salesInvoiceCart022H.adjustment_percent = Number(event.target.value || 0);
      salesRefreshCartTotals022H();
    });
    root.querySelector("#srReceived023D")?.addEventListener("input", (event) => {
      salesInvoiceCart022H.received_amount = salesCashNumber023D(event.target.value || 0);
      salesRefreshCashChange023D();
    });
    root.querySelector("#srPay022F")?.addEventListener("change", (event) => {
      salesInvoiceCart022H.payment_method = event.target.value || "efectivo";
      salesRefreshCashChange023D();
    });
    root.querySelector("#srNotes022F")?.addEventListener("input", (event) => { salesInvoiceCart022H.notes = event.target.value || ""; });

    root.querySelector("[data-sr-save-invoice-022h]")?.addEventListener("click", async () => {
      const msg = root.querySelector("#srMsg022F");
      salesInvoiceCart022H.payment_method = root.querySelector("#srPay022F")?.value || "efectivo";
      salesInvoiceCart022H.notes = root.querySelector("#srNotes022F")?.value || "";
      salesInvoiceCart022H.received_amount = salesCashNumber023D(root.querySelector("#srReceived023D")?.value || 0);
      const cashPayload023D = salesCashPayload023D();
      // CLONEXA_022K_R2_SAVE_SALES_ADJUSTMENT_SAFE: read current adjustment controls at save time.
      const adjustmentTypeNode022K = root.querySelector("#srAdjustmentType022J");
      const adjustmentPercentNode022K = root.querySelector("#srAdjustmentPercent022J");
      salesInvoiceCart022H.adjustment_type = adjustmentTypeNode022K?.value || salesInvoiceCart022H.adjustment_type || "none";
      salesInvoiceCart022H.adjustment_percent = salesInvoiceCart022H.adjustment_type === "none"
        ? 0
        : Number(adjustmentPercentNode022K?.value || salesInvoiceCart022H.adjustment_percent || 1);
      if (!salesInvoiceCart022H.items.length) { if (msg) msg.textContent = "Agrega al menos un artículo antes de guardar."; return; }

      try {
        if (msg) msg.textContent = "Guardando factura...";
        const data = await salesApi022F(`/sales?panel_type=${encodeURIComponent(panelType)}`, {
          method: "POST",
          body: JSON.stringify({
            payment_method: salesInvoiceCart022H.payment_method,
            notes: salesInvoiceCart022H.notes,
            items: salesInvoiceCart022H.items,
            ...cashPayload023D,
            ...salesInvoiceAdjustmentPayload022J(),
            ...storeActorPayload023W()
          })
        });
        if (msg) msg.textContent = `Factura guardada ${data?.invoice_number || ""}.`;
        salesResetInvoice022H();
        await renderSalesRegisterCategory022F(session, category, searchInput?.value || "");
      } catch (error) {
        if (msg) msg.textContent = error.message || "No se pudo guardar la factura.";
      }
    });

    bindStoreActorSelector023W();
    bindRefs();
    bindCartInputs();
    salesRefreshCashChange023D();
  }
  /* CLONEXA_022J_SALES_TOP10_ADJUSTMENTS_CLEAN_VIEW_END */

  /* CLONEXA_023T_REQUESTS_MINI_PANEL_FLOW_START */
  const CX_REQUEST_CODES_023T = new Set([
    "requests",
    "request",
    "solicitud",
    "solicitudes",
    "stock_request",
    "stock_requests"
  ]);

  function isRequestsCode023T(code) {
    return CX_REQUEST_CODES_023T.has(normalizeModuleCode019H(code));
  }

  function requestApi023T(path, options = {}) {
    return api(`/api/v1/mini-panel-requests/companies/${encodeURIComponent(companyId)}${path}`, {
      ...options,
      headers: {
        ...authHeaders(),
        "Content-Type": "application/json",
        ...(options.headers || {})
      }
    });
  }

  function requestStatusClass023T(status) {
    const value = normalizeModuleCode019H(status || "sent");
    if (value === "received") return "ok";
    if (value === "ready") return "ready";
    if (value === "preparing") return "work";
    if (value === "archived") return "muted";
    return "live";
  }

  function requestDateLabel023T(value) {
    const raw = String(value || "").trim();
    if (!raw) return "Sin fecha";
    try {
      return new Date(raw).toLocaleString("es-CO", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" });
    } catch (_) {
      return raw.slice(0, 16);
    }
  }

  function requestItemLabel023T(item) {
    const parts = [item?.name, item?.size, item?.color].map((part) => String(part || "").trim()).filter(Boolean);
    return parts.join(" / ") || "Articulo";
  }

  function requestOptionKey023T(item) {
    return [
      item?.reference_id || "",
      item?.name || "",
      item?.sku || "",
      item?.size || "",
      item?.color || ""
    ].join("|").toLowerCase();
  }

  function requestMergeSuggestions023T(suggestions = {}) {
    const map = new Map();
    const sold = Array.isArray(suggestions.sold_items) ? suggestions.sold_items : [];
    const refs = Array.isArray(suggestions.references) ? suggestions.references : [];
    sold.forEach((item) => {
      const clean = { ...item, source: "sold" };
      map.set(requestOptionKey023T(clean), clean);
    });
    refs.forEach((item) => {
      const clean = { ...item, source: "reference" };
      const key = requestOptionKey023T(clean);
      const current = map.get(key) || {};
      map.set(key, { ...clean, sold_quantity: current.sold_quantity || clean.sold_quantity || 0, source: current.source === "sold" ? "sold_reference" : "reference" });
    });
    return Array.from(map.values());
  }

  function requestStyles023T() {
    if (document.getElementById("cxRequestsStyles023T")) return;
    const style = document.createElement("style");
    style.id = "cxRequestsStyles023T";
    style.textContent = `
      .rq-shell-023t{min-height:100vh;padding:28px;background:radial-gradient(circle at 10% 12%,rgba(255,43,214,.25),transparent 28%),radial-gradient(circle at 90% 10%,rgba(0,210,255,.20),transparent 32%),linear-gradient(135deg,#12091f,#071329 60%,#101326);color:#fff}
      .rq-card-023t{border:1px solid rgba(255,255,255,.15);border-radius:28px;background:linear-gradient(145deg,rgba(255,255,255,.11),rgba(255,255,255,.045));box-shadow:0 26px 86px rgba(0,0,0,.34);backdrop-filter:blur(16px)}
      .rq-hero-023t{padding:28px;margin-bottom:18px;display:flex;justify-content:space-between;gap:18px;align-items:flex-start}
      .rq-kicker-023t{font-size:11px;font-weight:950;letter-spacing:.32em;text-transform:uppercase;color:#ff42d4}
      .rq-title-023t{font-size:44px;line-height:1;margin:9px 0 8px;font-weight:950}
      .rq-muted-023t{color:rgba(255,255,255,.70);font-weight:800}
      .rq-btn-023t{border:0;border-radius:17px;padding:13px 16px;background:linear-gradient(135deg,#ff25bb,#7154ff);color:#fff;font-weight:950;cursor:pointer;box-shadow:0 16px 42px rgba(255,37,187,.22)}
      .rq-btn-023t.secondary{background:rgba(255,255,255,.11);border:1px solid rgba(255,255,255,.16);box-shadow:none}
      .rq-btn-023t.danger{background:rgba(255,80,130,.16);border:1px solid rgba(255,80,130,.38);box-shadow:none}
      .rq-layout-023t{display:grid;grid-template-columns:minmax(0,1.15fr) minmax(360px,.85fr);gap:18px;align-items:start}
      .rq-panel-023t{padding:22px}
      .rq-actions-023t{display:flex;gap:10px;flex-wrap:wrap;align-items:center}
      .rq-items-023t{display:grid;gap:10px;margin-top:16px}
      .rq-line-023t{display:grid;grid-template-columns:minmax(220px,1.5fr) 100px 1fr auto;gap:10px;align-items:end;border:1px solid rgba(255,255,255,.11);border-radius:20px;background:rgba(5,8,24,.28);padding:12px}
      .rq-field-023t label{display:block;margin:0 0 7px;font-size:11px;font-weight:950;text-transform:uppercase;letter-spacing:.14em;color:rgba(255,255,255,.66)}
      .rq-field-023t input,.rq-field-023t textarea,.rq-field-023t select{width:100%;box-sizing:border-box;border:1px solid rgba(255,255,255,.15);border-radius:15px;background:rgba(4,7,23,.62);color:#fff;padding:12px 13px;font-weight:850;outline:none}
      .rq-field-023t textarea{min-height:88px;resize:vertical}
      .rq-list-023t{display:grid;gap:12px;max-height:760px;overflow:auto;padding-right:4px}
      .rq-request-023t{display:grid;gap:12px;border:1px solid rgba(255,255,255,.12);border-radius:22px;background:rgba(255,255,255,.065);padding:16px}
      .rq-head-023t{display:flex;justify-content:space-between;gap:12px;align-items:flex-start}
      .rq-pill-023t{display:inline-flex;border-radius:999px;padding:7px 10px;border:1px solid rgba(255,255,255,.14);background:rgba(255,255,255,.09);font-size:12px;font-weight:950}
      .rq-pill-023t.live{color:#8fffd8;border-color:rgba(41,255,187,.34);background:rgba(41,255,187,.12)}
      .rq-pill-023t.work{color:#ffe2a0;border-color:rgba(255,190,80,.34);background:rgba(255,190,80,.12)}
      .rq-pill-023t.ready{color:#bba7ff;border-color:rgba(148,105,255,.35);background:rgba(148,105,255,.12)}
      .rq-pill-023t.ok{color:#c7ff9e;border-color:rgba(121,255,85,.34);background:rgba(121,255,85,.12)}
      .rq-pill-023t.muted{color:rgba(255,255,255,.62)}
      .rq-mini-023t{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px}
      .rq-mini-023t div{border:1px solid rgba(255,255,255,.09);border-radius:14px;background:rgba(0,0,0,.16);padding:10px}
      .rq-mini-023t span{display:block;font-size:10px;font-weight:950;letter-spacing:.12em;text-transform:uppercase;color:rgba(255,255,255,.58)}
      .rq-mini-023t strong{display:block;margin-top:5px}
      .rq-timeline-023t{display:flex;flex-wrap:wrap;gap:7px}
      .rq-empty-023t{border:1px dashed rgba(255,255,255,.20);border-radius:20px;padding:22px;text-align:center;color:rgba(255,255,255,.70);font-weight:850}
      .rq-msg-023t{margin-top:12px;font-weight:900;color:#8fffd8}
      @media(max-width:1100px){.rq-layout-023t,.rq-line-023t{grid-template-columns:1fr}.rq-mini-023t{grid-template-columns:1fr}.rq-title-023t{font-size:36px}}
    `;
    document.head.appendChild(style);
  }

  function requestLineHtml023T(index, item = {}) {
    const quantity = item.quantity !== undefined && item.quantity !== null && item.quantity !== ""
      ? item.quantity
      : "";
    return `
      <div class="rq-line-023t" data-rq-line-023t>
        <div class="rq-field-023t">
          <label>Articulo</label>
          <input data-rq-name-023t list="requestSuggestions023T" value="${h(requestItemLabel023T(item) === "Articulo" ? "" : requestItemLabel023T(item))}" placeholder="Producto, referencia o articulo manual">
        </div>
        <div class="rq-field-023t">
          <label>Cantidad</label>
          <input data-rq-qty-023t type="number" min="0" step="1" value="${h(quantity)}" placeholder="0">
        </div>
        <div class="rq-field-023t">
          <label>Nota</label>
          <input data-rq-note-023t value="${h(item.note || "")}" placeholder="Talla, color, urgencia...">
        </div>
        <button class="rq-btn-023t secondary" type="button" data-rq-remove-023t="${index}">Quitar</button>
      </div>
    `;
  }

  function requestSoldLineItem023U(item = {}) {
    const soldQuantity = Number(item.sold_quantity || item.quantity || 0);
    return {
      ...item,
      quantity: soldQuantity > 0 ? soldQuantity : 1,
    };
  }

  function requestSuggestionOptions023U(items = []) {
    return (Array.isArray(items) ? items : [])
      .map((item) => `<option value="${h(requestItemLabel023T(item))}">${h(item.sku || item.category || "")}</option>`)
      .join("");
  }

  function requestReadItems023T(suggestions = []) {
    const byLabel = new Map();
    suggestions.forEach((item) => byLabel.set(requestItemLabel023T(item).toLowerCase(), item));
    return Array.from(root.querySelectorAll("[data-rq-line-023t]")).map((row) => {
      const nameValue = String(row.querySelector("[data-rq-name-023t]")?.value || "").trim();
      const match = byLabel.get(nameValue.toLowerCase()) || {};
      return {
        reference_id: match.reference_id || "",
        name: nameValue || match.name || "",
        sku: match.sku || "",
        category: match.category || "",
        size: match.size || "",
        color: match.color || "",
        quantity: Number(row.querySelector("[data-rq-qty-023t]")?.value || 0),
        sold_quantity: Number(match.sold_quantity || 0),
        note: row.querySelector("[data-rq-note-023t]")?.value || ""
      };
    }).filter((item) => item.name && item.quantity > 0);
  }

  function requestTimelineHtml023T(request) {
    const rows = Array.isArray(request.timeline) ? request.timeline : [];
    if (!rows.length) return `<span class="rq-pill-023t ${h(requestStatusClass023T(request.status))}">${h(request.status_label || "Enviada")}</span>`;
    return rows.slice(-5).map((row) => `
      <span class="rq-pill-023t ${h(requestStatusClass023T(row.status))}" title="${h(requestDateLabel023T(row.at))}">
        ${h(row.label || row.status || "Estado")}
      </span>
    `).join("");
  }

  function requestCardHtml023T(request) {
    const items = Array.isArray(request.items) ? request.items : [];
    const canReceive = ["sent", "preparing", "ready"].includes(normalizeModuleCode019H(request.status));
    const canArchive = normalizeModuleCode019H(request.status) === "received";
    return `
      <article class="rq-request-023t">
        <div class="rq-head-023t">
          <div>
            <strong>${h(request.request_number || "Solicitud")}</strong>
            <div class="rq-muted-023t">${h(request.store_label || request.requested_by_label || "Tienda")} - ${h(requestDateLabel023T(request.created_at))}</div>
          </div>
          <span class="rq-pill-023t ${h(requestStatusClass023T(request.status))}">${h(request.status_label || "Enviada")}</span>
        </div>
        <div class="rq-mini-023t">
          <div><span>Articulos</span><strong>${h(request.items_count || items.length || 0)}</strong></div>
          <div><span>Cantidad</span><strong>${h(request.requested_units || 0)}</strong></div>
          <div><span>Alista</span><strong>${h(request.prepared_by || "Pendiente")}</strong></div>
        </div>
        <div class="rq-muted-023t">
          ${items.slice(0, 4).map((item) => `${h(requestItemLabel023T(item))} x ${h(item.quantity || 0)}`).join("<br>") || "Sin articulos"}
        </div>
        <div class="rq-timeline-023t">${requestTimelineHtml023T(request)}</div>
        <div class="rq-actions-023t">
          ${canReceive ? `<button class="rq-btn-023t" type="button" data-rq-received-023t="${h(request.id)}">Confirmar recibido</button>` : ""}
          ${canArchive ? `<button class="rq-btn-023t secondary" type="button" data-rq-archive-023t="${h(request.id)}">Guardar / archivar</button>` : ""}
        </div>
      </article>
    `;
  }

  async function openRequestsModule023T(session) {
    requestStyles023T();
    let suggestions = { references: [], sold_items: [] };
    let data = { items: [], summary: {} };
    let loadError = "";

    try {
      suggestions = await requestApi023T(`/suggestions?panel_type=${encodeURIComponent(panelType)}&limit=100`);
    } catch (error) {
      loadError = error.message || "No se pudieron cargar sugerencias.";
    }

    try {
      data = await requestApi023T(`?panel_type=${encodeURIComponent(panelType)}&status=active&limit=80`);
    } catch (error) {
      loadError = error.message || loadError || "No se pudieron cargar solicitudes.";
    }

    let merged = requestMergeSuggestions023T(suggestions);
    let sold = Array.isArray(suggestions.sold_items) ? suggestions.sold_items : [];
    const items = Array.isArray(data.items) ? data.items : [];
    const company = session?.company || {};
    const employee = session?.employee || session?.user || {};

    root.innerHTML = `
      <main class="rq-shell-023t">
        <header class="rq-card-023t rq-hero-023t">
          <div>
            <div class="rq-kicker-023t">Solicitudes</div>
            <h1 class="rq-title-023t">Solicitar productos</h1>
            <p class="rq-muted-023t">${h(company.name || "Empresa")} - ${h(employee.full_name || "Mini panel")}. Crea solicitudes, consulta estados y confirma recibido.</p>
          </div>
          <div class="rq-actions-023t">
            <button class="rq-btn-023t secondary" type="button" data-rq-refresh-023t>Actualizar</button>
            <button class="rq-btn-023t secondary" type="button" data-rq-back-023t>Dashboard</button>
          </div>
        </header>

        ${storeActorStripHtml023W("solicitudes")}

        <section class="rq-layout-023t">
          <section class="rq-card-023t rq-panel-023t">
            <div class="rq-kicker-023t">Nueva solicitud</div>
            <h2>Lista editable</h2>
            <p class="rq-muted-023t">Puedes traer vendidos recientes, elegir referencias activas o escribir articulos manualmente.</p>
            <datalist id="requestSuggestions023T">
              ${requestSuggestionOptions023U(merged)}
            </datalist>
            <div class="rq-actions-023t" style="margin-top:14px">
              <button class="rq-btn-023t secondary" type="button" data-rq-prefill-sold-023t>Traer vendidos</button>
              <button class="rq-btn-023t secondary" type="button" data-rq-add-line-023t>Agregar articulo</button>
            </div>
            <div class="rq-items-023t" data-rq-lines-023t>
              ${requestLineHtml023T(0, {})}
            </div>
            <div class="rq-field-023t" style="margin-top:14px">
              <label>Observacion</label>
              <textarea id="requestNotes023T" placeholder="Ej: se agoto en vitrina, enviar prioridad, surtido para fin de semana..."></textarea>
            </div>
            <button class="rq-btn-023t" type="button" data-rq-submit-023t style="width:100%;margin-top:14px">Enviar solicitud</button>
            <div class="rq-msg-023t" id="requestMsg023T">${h(loadError)}</div>
          </section>

          <aside class="rq-card-023t rq-panel-023t">
            <div class="rq-kicker-023t">Seguimiento</div>
            <h2>Solicitudes enviadas</h2>
            <div class="rq-list-023t">
              ${items.map(requestCardHtml023T).join("") || `<div class="rq-empty-023t">Aun no hay solicitudes activas para este mini panel.</div>`}
            </div>
          </aside>
        </section>
      </main>
    `;

    const lines = root.querySelector("[data-rq-lines-023t]");
    bindStoreActorSelector023W();
    root.querySelector("[data-rq-back-023t]")?.addEventListener("click", () => bootShell());
    root.querySelector("[data-rq-refresh-023t]")?.addEventListener("click", () => openRequestsModule023T(session));
    root.querySelector("[data-rq-add-line-023t]")?.addEventListener("click", () => {
      if (!lines) return;
      lines.insertAdjacentHTML("beforeend", requestLineHtml023T(lines.querySelectorAll("[data-rq-line-023t]").length, {}));
    });
    root.querySelector("[data-rq-prefill-sold-023t]")?.addEventListener("click", async () => {
      if (!lines) return;
      const msg = root.querySelector("#requestMsg023T");
      if (msg) msg.textContent = "Cargando vendidos recientes...";

      try {
        suggestions = await requestApi023T(`/suggestions?panel_type=${encodeURIComponent(panelType)}&limit=100`);
        merged = requestMergeSuggestions023T(suggestions);
        sold = Array.isArray(suggestions.sold_items) ? suggestions.sold_items : [];
        const list = root.querySelector("#requestSuggestions023T");
        if (list) list.innerHTML = requestSuggestionOptions023U(merged);
      } catch (error) {
        if (msg) msg.textContent = error.message || "No se pudieron cargar vendidos recientes.";
        return;
      }

      const base = sold.slice(0, 12);
      if (!base.length) {
        lines.innerHTML = requestLineHtml023T(0, {});
        if (msg) msg.textContent = "No hay vendidos recientes para cargar.";
        return;
      }
      lines.innerHTML = base.map((item, index) => requestLineHtml023T(index, requestSoldLineItem023U(item))).join("");
      if (msg) msg.textContent = "Vendidos cargados. Puedes editar cantidades o quitar articulos.";
    });
    lines?.addEventListener("click", (event) => {
      const remove = event.target.closest("[data-rq-remove-023t]");
      if (remove) {
        const row = remove.closest("[data-rq-line-023t]");
        if (row && root.querySelectorAll("[data-rq-line-023t]").length > 1) row.remove();
      }
    });

    root.querySelector("[data-rq-submit-023t]")?.addEventListener("click", async () => {
      const msg = root.querySelector("#requestMsg023T");
      const button = root.querySelector("[data-rq-submit-023t]");
      try {
        const payload = {
          panel_type: panelType,
          store_label: storeActorPayload023W().store_slot_name || employee.full_name || employee.email || "",
          notes: root.querySelector("#requestNotes023T")?.value || "",
          items: requestReadItems023T(merged),
          ...storeActorPayload023W()
        };
        if (!payload.items.length) throw new Error("Agrega al menos un articulo con cantidad.");
        if (msg) msg.textContent = "Enviando solicitud...";
        if (button) button.disabled = true;
        await requestApi023T("", { method: "POST", body: JSON.stringify(payload) });
        if (msg) msg.textContent = "Solicitud enviada.";
        await openRequestsModule023T(session);
      } catch (error) {
        if (button) button.disabled = false;
        if (msg) msg.textContent = error.message || "No fue posible enviar la solicitud.";
      }
    });

    root.querySelectorAll("[data-rq-received-023t]").forEach((button) => {
      button.addEventListener("click", async () => {
        const id = button.getAttribute("data-rq-received-023t");
        if (!id) return;
        await requestApi023T(`/${encodeURIComponent(id)}/received`, { method: "POST", body: JSON.stringify({}) });
        await openRequestsModule023T(session);
      });
    });

    root.querySelectorAll("[data-rq-archive-023t]").forEach((button) => {
      button.addEventListener("click", async () => {
        const id = button.getAttribute("data-rq-archive-023t");
        if (!id) return;
        await requestApi023T(`/${encodeURIComponent(id)}/archive`, { method: "POST", body: JSON.stringify({}) });
        await openRequestsModule023T(session);
      });
    });
  }
  /* CLONEXA_023T_REQUESTS_MINI_PANEL_FLOW_END */

  /* CLONEXA_023E_DAY_CLOSING_MINI_PANEL_DYNAMIC_R1_START */
  const CX_DAY_CLOSING_CODES_023E = new Set([
    "day_closing",
    "cierre_dia",
    "cierre_de_dia",
    "realizar_cierre",
    "cierre_diario",
    "commercial_closing"
  ]);

  function isDayClosingCode023E(code) {
    return CX_DAY_CLOSING_CODES_023E.has(normalizeModuleCode019H(code));
  }

  function dayClosingToday023E() {
    const now = new Date();
    const y = now.getFullYear();
    const m = String(now.getMonth() + 1).padStart(2, "0");
    const d = String(now.getDate()).padStart(2, "0");
    return `${y}-${m}-${d}`;
  }

  function dayClosingArea023E(value) {
    const type = normalizePanelType019H(value || panelType);
    if (type === "store" || type === "stores") return "tiendas";
    if (type === "sales") return "ventas";
    return type || "operacion";
  }

  function dayClosingNumber023E(value) {
    const number = Number(value || 0);
    return Number.isFinite(number) ? number : 0;
  }

  function dayClosingQty023E(value) {
    const number = dayClosingNumber023E(value);
    if (Math.abs(number - Math.round(number)) < 0.001) return String(Math.round(number));
    return number.toFixed(2);
  }

  function dayClosingDateLabel023E(value) {
    const raw = String(value || "");
    if (!raw) return dayClosingToday023E();
    try {
      const date = new Date(`${raw}T12:00:00`);
      return date.toLocaleDateString("es-CO", { weekday: "short", year: "numeric", month: "short", day: "2-digit" });
    } catch (_) {
      return raw;
    }
  }

  function dayClosingTimeLabel023E(value) {
    if (!value) return "—";
    try {
      return new Date(value).toLocaleString("es-CO", { hour: "2-digit", minute: "2-digit", day: "2-digit", month: "short" });
    } catch (_) {
      return String(value || "—");
    }
  }

  function dayClosingApi023E(path, options = {}) {
    const headers = {
      ...authHeaders(),
      "Content-Type": "application/json",
      ...(options.headers || {})
    };
    return api(`/api/v1/day-closing/companies/${encodeURIComponent(companyId)}${path}`, {
      ...options,
      headers
    });
  }

  function dayClosingStoreScope023P(forBody = false) {
    if (!isStorePanel023W()) return {};
    const store = currentStoreTeam023W?.store || {};
    const members = Array.isArray(currentStoreTeam023W?.members) ? currentStoreTeam023W.members : [];
    const employeeIds = members.map((member) => String(member.employee_id || "").trim()).filter(Boolean);
    const userIds = members.map((member) => String(member.user_id || "").trim()).filter(Boolean);
    return {
      store_slot_id: store.id || "",
      store_slot_name: store.name || "",
      store_employee_ids: forBody ? employeeIds : employeeIds.join(","),
      store_user_ids: forBody ? userIds : userIds.join(",")
    };
  }

  function dayClosingQuery023P(closureDate) {
    const params = new URLSearchParams({
      panel_type: panelType,
      closure_date: closureDate
    });
    const scope = dayClosingStoreScope023P(false);
    Object.entries(scope).forEach(([key, value]) => {
      if (value) params.set(key, value);
    });
    return params.toString();
  }

  function dayClosingStyles023E() {
    if (document.getElementById("cxDayClosingStyles023E")) return;
    const style = document.createElement("style");
    style.id = "cxDayClosingStyles023E";
    style.textContent = `
      .dc-shell-023e{min-height:100vh;padding:28px;background:
        radial-gradient(circle at 8% 8%,rgba(255,37,187,.26),transparent 30%),
        radial-gradient(circle at 92% 12%,rgba(41,152,255,.22),transparent 28%),
        linear-gradient(135deg,#12091f,#071328 58%,#101326);color:#fff}
      .dc-card-023e{background:linear-gradient(145deg,rgba(255,255,255,.105),rgba(255,255,255,.045));border:1px solid rgba(255,255,255,.15);border-radius:30px;box-shadow:0 28px 90px rgba(0,0,0,.38);backdrop-filter:blur(18px)}
      .dc-hero-023e{padding:28px;margin-bottom:18px;display:flex;align-items:flex-start;justify-content:space-between;gap:18px}
      .dc-kicker-023e{font-size:11px;font-weight:950;letter-spacing:.34em;text-transform:uppercase;color:#ff39d0}
      .dc-title-023e{font-size:44px;line-height:1;margin:10px 0 8px;font-weight:950}
      .dc-muted-023e{color:rgba(255,255,255,.70);font-weight:800}
      .dc-actions-023e{display:flex;gap:10px;flex-wrap:wrap;align-items:center}
      .dc-btn-023e{border:0;border-radius:18px;padding:13px 18px;color:#fff;background:linear-gradient(135deg,#ff25bb,#6d4cff);font-weight:950;cursor:pointer;box-shadow:0 18px 42px rgba(247,37,179,.22)}
      .dc-btn-023e.secondary{background:rgba(255,255,255,.11);border:1px solid rgba(255,255,255,.16);box-shadow:none}
      .dc-btn-023e:disabled{opacity:.55;cursor:not-allowed;filter:grayscale(.25)}
      .dc-grid-023e{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:14px;margin-bottom:18px}
      .dc-metric-023e{padding:18px;border-radius:24px;background:linear-gradient(145deg,rgba(255,255,255,.10),rgba(255,255,255,.045));border:1px solid rgba(255,255,255,.13);min-height:106px}
      .dc-metric-023e span{display:block;color:rgba(255,255,255,.64);font-size:11px;font-weight:950;letter-spacing:.18em;text-transform:uppercase}
      .dc-metric-023e strong{display:block;font-size:26px;margin-top:8px;font-weight:950}
      .dc-metric-023e small{display:block;color:rgba(255,255,255,.62);font-weight:800;margin-top:4px}
      .dc-layout-023e{display:grid;grid-template-columns:minmax(0,1.35fr) minmax(360px,.65fr);gap:18px;align-items:start}
      .dc-panel-023e{padding:22px}
      .dc-user-list-023e{display:grid;gap:12px;margin-top:16px}
      .dc-user-023e{border:1px solid rgba(255,255,255,.13);border-radius:22px;background:rgba(255,255,255,.065);padding:16px}
      .dc-user-head-023e{display:flex;justify-content:space-between;gap:12px;align-items:flex-start;margin-bottom:12px}
      .dc-user-head-023e strong{font-size:18px}
      .dc-pill-023e{display:inline-flex;align-items:center;justify-content:center;border-radius:999px;padding:7px 10px;font-size:11px;font-weight:950;background:rgba(255,57,208,.18);border:1px solid rgba(255,57,208,.26);color:#ffd7f4}
      .dc-pill-023e.ok{background:rgba(55,235,173,.14);border-color:rgba(55,235,173,.28);color:#86ffe0}
      .dc-user-metrics-023e{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px}
      .dc-mini-023e{border-radius:16px;padding:12px;background:rgba(0,0,0,.16);border:1px solid rgba(255,255,255,.09)}
      .dc-mini-023e span{display:block;color:rgba(255,255,255,.58);font-size:10px;font-weight:950;letter-spacing:.12em;text-transform:uppercase}
      .dc-mini-023e strong{display:block;margin-top:5px;font-size:15px}
      .dc-pay-grid-023e{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;margin-top:10px}
      .dc-side-stack-023e{display:grid;gap:14px}
      .dc-field-023e label{display:block;font-size:11px;font-weight:950;letter-spacing:.15em;text-transform:uppercase;color:rgba(255,255,255,.68);margin-bottom:8px}
      .dc-field-023e textarea{width:100%;min-height:120px;resize:vertical;box-sizing:border-box;border:1px solid rgba(255,255,255,.15);border-radius:18px;background:rgba(4,7,23,.58);color:#fff;padding:14px;font-weight:850;outline:none}
      .dc-status-023e{border-radius:20px;padding:15px;background:rgba(255,255,255,.075);border:1px solid rgba(255,255,255,.12);font-weight:850}
      .dc-status-023e.ok{border-color:rgba(55,235,173,.30);background:rgba(55,235,173,.10);color:#8dffe0}
      .dc-status-023e.warn{border-color:rgba(255,207,107,.34);background:rgba(255,207,107,.10);color:#ffe0a3}
      .dc-message-023e{margin-top:12px;font-weight:900;color:#79ffe1}
      @media(max-width:1120px){.dc-grid-023e,.dc-user-metrics-023e{grid-template-columns:repeat(2,minmax(0,1fr))}.dc-layout-023e{grid-template-columns:1fr}.dc-title-023e{font-size:36px}}
      @media(max-width:640px){.dc-shell-023e{padding:18px}.dc-hero-023e{display:block}.dc-grid-023e,.dc-user-metrics-023e,.dc-pay-grid-023e{grid-template-columns:1fr}.dc-title-023e{font-size:32px}}
    `;
    document.head.appendChild(style);
  }

  function dayClosingConnectionSnapshot023E() {
    const op = currentOperational || {};
    return {
      status: op.status || "",
      status_label: operationalLabel(op.status),
      active_seconds: liveValue("active"),
      break_seconds: liveValue("break"),
      active_label: formatSeconds(liveValue("active")),
      break_label: formatSeconds(liveValue("break")),
      started_at: op.started_at || op.startedAt || op.opened_at || op.created_at || "",
      updated_at: op.updated_at || "",
      captured_at: new Date().toISOString()
    };
  }

  function dayClosingConnectionHtml023E(snapshot) {
    const safe = snapshot || dayClosingConnectionSnapshot023E();
    return `
      <div class="dc-grid-023e" style="grid-template-columns:repeat(2,minmax(0,1fr));margin:0">
        <article class="dc-metric-023e">
          <span>Tiempo conectado</span>
          <strong>${h(safe.active_label || formatSeconds(safe.active_seconds || 0))}</strong>
          <small>Activo efectivo del mini panel</small>
        </article>
        <article class="dc-metric-023e">
          <span>Pausas</span>
          <strong>${h(safe.break_label || formatSeconds(safe.break_seconds || 0))}</strong>
          <small>${h(safe.status_label || operationalLabel(safe.status))}</small>
        </article>
      </div>
      <div class="dc-status-023e" style="margin-top:12px">
        Inicio: ${h(dayClosingTimeLabel023E(safe.started_at))}<br>
        Captura: ${h(dayClosingTimeLabel023E(safe.captured_at))}
      </div>
    `;
  }

  function dayClosingUserHtml023E(user, areaLabel) {
    const salesAmount = dayClosingNumber023E(user.total_amount);
    const units = dayClosingQty023E(user.units_sold);
    return `
      <article class="dc-user-023e">
        <div class="dc-user-head-023e">
          <div>
            <strong>${h(user.label || user.full_name || "Usuario")}</strong>
            <div class="dc-muted-023e">${h(areaLabel)} · ${h(user.username || user.email || user.user_id || "panel")}</div>
          </div>
          <span class="dc-pill-023e ok">${h(formatMoney(salesAmount))} · ${h(units)} und</span>
        </div>

        <div class="dc-user-metrics-023e">
          <div class="dc-mini-023e"><span>Facturas</span><strong>${h(user.invoices_count || 0)}</strong></div>
          <div class="dc-mini-023e"><span>Cotizaciones</span><strong>${h(user.quotes_count || 0)} · ${h(formatMoney(user.quotes_amount || 0))}</strong></div>
          <div class="dc-mini-023e"><span>Solicitudes</span><strong>${h(user.requests_count || 0)} prox.</strong></div>
          <div class="dc-mini-023e"><span>Cantidad vendida</span><strong>${h(units)} und</strong></div>
        </div>

        <div class="dc-pay-grid-023e">
          <div class="dc-mini-023e"><span>Efectivo</span><strong>${h(formatMoney(user.cash_amount || 0))}</strong></div>
          <div class="dc-mini-023e"><span>Transferencias</span><strong>${h(formatMoney(user.transfer_amount || 0))}</strong></div>
          <div class="dc-mini-023e"><span>Cheques</span><strong>${h(formatMoney(user.check_amount || 0))}</strong></div>
          <div class="dc-mini-023e"><span>Otro</span><strong>${h(formatMoney(user.other_amount || 0))}</strong></div>
        </div>
      </article>
    `;
  }

  async function openDayClosingModule023E(session) {
    dayClosingStyles023E();
    const closureDate = dayClosingToday023E();
    let summary = null;
    let loadError = "";

    try {
      const fresh = await loadOperationalSession().catch(() => null);
      if (fresh) startTimers(fresh.operational_session || fresh);
    } catch (_) {}

    if (isStorePanel023W()) {
      try {
        await loadStoreTeam023W(true);
      } catch (error) {
        console.warn("CLONEXA 024P day closing store scope fallback:", error);
      }
    }

    try {
      const data = await dayClosingApi023E(`/mini-panel/summary?${dayClosingQuery023P(closureDate)}`);
      summary = data || {};
    } catch (error) {
      loadError = error.message || "No se pudo cargar el cierre diario.";
      summary = {
        panel_type: panelType,
        area: dayClosingArea023E(panelType),
        closure_date: closureDate,
        locked: false,
        totals: {},
        users: []
      };
    }

    const totals = summary.totals || {};
    const users = Array.isArray(summary.users) ? summary.users : [];
    const areaLabel = summary.area || dayClosingArea023E(panelType);
    const locked = Boolean(summary.locked || summary.status === "submitted");
    const connectionSnapshot = dayClosingConnectionSnapshot023E();

    root.innerHTML = `
      <main class="dc-shell-023e">
        <header class="dc-card-023e dc-hero-023e">
          <div>
            <div class="dc-kicker-023e">Cierre diario</div>
            <h1 class="dc-title-023e">Realizar cierre</h1>
            <p class="dc-muted-023e">${h(session?.company?.name || "Empresa")} · Área ${h(areaLabel)} · ${h(dayClosingDateLabel023E(summary.closure_date || closureDate))}</p>
          </div>
          <div class="dc-actions-023e">
            <span class="dc-pill-023e ${locked ? "ok" : ""}">${locked ? "Enviado" : "Abierto"}</span>
            <button class="dc-btn-023e secondary" type="button" data-dc-refresh-023e>Actualizar</button>
            <button class="dc-btn-023e secondary" type="button" data-dc-back-023e>Dashboard</button>
          </div>
        </header>

        <section class="dc-grid-023e">
          <article class="dc-metric-023e">
            <span>Cantidad vendida</span>
            <strong>${h(dayClosingQty023E(totals.units_sold || 0))} und</strong>
            <small>${h(formatMoney(totals.total_amount || 0))} total vendido</small>
          </article>
          <article class="dc-metric-023e">
            <span>Facturas generadas</span>
            <strong>${h(totals.invoices_count || 0)}</strong>
            <small>${h(users.length)} usuario(s) en panel</small>
          </article>
          <article class="dc-metric-023e">
            <span>Cotizaciones</span>
            <strong>${h(totals.quotes_count || 0)}</strong>
            <small>${h(formatMoney(totals.quotes_amount || 0))} cotizado</small>
          </article>
          <article class="dc-metric-023e">
            <span>Solicitudes</span>
            <strong>${h(totals.requests_count || 0)}</strong>
            <small>Tiendas / prox. según módulo activo</small>
          </article>
        </section>

        <section class="dc-grid-023e">
          <article class="dc-metric-023e"><span>Efectivo</span><strong>${h(formatMoney(totals.cash_amount || 0))}</strong><small>Ventas en efectivo</small></article>
          <article class="dc-metric-023e"><span>Transferencias</span><strong>${h(formatMoney(totals.transfer_amount || 0))}</strong><small>Pagos transferidos</small></article>
          <article class="dc-metric-023e"><span>Cheques</span><strong>${h(formatMoney(totals.check_amount || 0))}</strong><small>Pagos por cheque</small></article>
          <article class="dc-metric-023e"><span>Otro</span><strong>${h(formatMoney(totals.other_amount || 0))}</strong><small>Tarjeta u otros métodos</small></article>
        </section>

        <section class="dc-layout-023e">
          <section class="dc-card-023e dc-panel-023e">
            <div class="dc-kicker-023e">Usuarios del panel</div>
            <h2>Resumen discriminado</h2>
            <p class="dc-muted-023e">El cierre consolida automáticamente todas las ventas, cotizaciones y solicitudes del panel.</p>
            <div class="dc-user-list-023e">
              ${users.map((user) => dayClosingUserHtml023E(user, areaLabel)).join("") || `<div class="dc-status-023e warn">Sin actividad para cerrar en este panel durante el día.</div>`}
            </div>
          </section>

          <aside class="dc-side-stack-023e">
            <section class="dc-card-023e dc-panel-023e">
              <div class="dc-kicker-023e">Horario de conexión</div>
              <h2>Sesión del mini panel</h2>
              ${dayClosingConnectionHtml023E(connectionSnapshot)}
            </section>

            <section class="dc-card-023e dc-panel-023e">
              <div class="dc-kicker-023e">Observaciones</div>
              <h2>Enviar cierre</h2>
              <div class="dc-field-023e">
                <label>Observación del cierre</label>
                <textarea id="dcNotes023E" ${locked ? "disabled" : ""} placeholder="Ej: caja correcta, novedad de transferencia, solicitud pendiente...">${h(summary.notes || "")}</textarea>
              </div>
              <button class="dc-btn-023e" type="button" data-dc-submit-023e ${locked ? "disabled" : ""} style="width:100%;margin-top:14px">${locked ? "Cierre enviado" : "Enviar cierre diario"}</button>
              <div class="dc-message-023e" id="dcMsg023E">${loadError ? h(loadError) : (locked ? `Cierre enviado ${h(dayClosingTimeLabel023E(summary.submitted_at))}` : "")}</div>
            </section>
          </aside>
        </section>
      </main>
    `;

    root.querySelector("[data-dc-back-023e]")?.addEventListener("click", () => bootShell());
    root.querySelector("[data-dc-refresh-023e]")?.addEventListener("click", () => openDayClosingModule023E(session));
    root.querySelector("[data-dc-submit-023e]")?.addEventListener("click", async () => {
      const msg = root.querySelector("#dcMsg023E");
      const button = root.querySelector("[data-dc-submit-023e]");
      try {
        if (msg) msg.textContent = "Enviando cierre diario...";
        if (button) button.disabled = true;
        await dayClosingApi023E(`/mini-panel/submit?${dayClosingQuery023P(closureDate)}`, {
          method: "POST",
          body: JSON.stringify({
            closure_date: closureDate,
            notes: root.querySelector("#dcNotes023E")?.value || "",
            connection_snapshot: dayClosingConnectionSnapshot023E(),
            ...dayClosingStoreScope023P(true)
          })
        });
        if (msg) msg.textContent = "Cierre diario enviado.";
        await openDayClosingModule023E(session);
      } catch (error) {
        if (button) button.disabled = false;
        if (msg) msg.textContent = error.message || "No fue posible enviar el cierre.";
      }
    });
  }
  /* CLONEXA_023E_DAY_CLOSING_MINI_PANEL_DYNAMIC_R1_END */

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

  /* CLONEXA_024A_PERFECT_R1_FIELD_OPS_MINIPANEL_START */
  const CX_FIELD_OPS_CODES_024A_R1 = new Set([
    "field",
    "fld",
    "operacion_campo",
    "operacion_en_campo",
    "operaciones_en_campo"
  ]);

  function isFieldOpsCode024A_R1(code = "") {
    return CX_FIELD_OPS_CODES_024A_R1.has(normalizeModuleCode019H(code));
  }

  function storeTeamMembers024A_R1() {
    return Array.isArray(currentStoreTeam023W?.members) ? currentStoreTeam023W.members : [];
  }

  function storeTeamTotals024A_R1() {
    const members = storeTeamMembers024A_R1();
    return members.reduce((acc, member) => {
      acc.goal += Number(member.monthly_goal || 0);
      acc.sales += Number(member.sales_total || 0);
      acc.count += Number(member.sales_count || 0);
      const status = String(member.session?.status || "").toLowerCase();
      if (status === "active") acc.active += 1;
      if (status === "break") acc.breaks += 1;
      return acc;
    }, { goal: 0, sales: 0, count: 0, active: 0, breaks: 0 });
  }

  function storeTeamGoalPct024A_R1(sales, goal) {
    const s = Number(sales || 0);
    const g = Number(goal || 0);
    if (!g) return 0;
    return Math.max(0, Math.min(999, Math.round((s / g) * 100)));
  }

  function fieldOpsStatus024A_R1(status = "") {
    const clean = String(status || "closed").toLowerCase();
    if (clean === "active") return "Activo";
    if (clean === "break") return "En pausa";
    if (clean === "finished") return "Finalizado";
    return "Sin turno";
  }

  function fieldOpsMemberRow024A_R1(member) {
    const session = member.session || {};
    const status = String(session.status || "closed").toLowerCase();
    const goal = Number(member.monthly_goal || 0);
    const sales = Number(member.sales_total || 0);
    const pct = storeTeamGoalPct024A_R1(sales, goal);
    const canStart = status !== "active" && status !== "break";
    const canPause = status === "active";
    const canResume = status === "break";
    const canFinish = status === "active" || status === "break";

    return `
      <article class="st-card-023w st-member-023w" data-field-member-024a-r1="${h(member.employee_id || "")}">
        <div class="st-member-head-023w">
          <div>
            <strong>${h(member.full_name || "Colaborador")}</strong>
            <div class="st-muted-023w">${h(member.role || "cajero")} ${member.phone ? `- ${h(member.phone)}` : ""}</div>
          </div>
          <div style="display:flex;gap:8px;flex-wrap:wrap;justify-content:flex-end">
            ${member.is_admin ? `<span class="st-pill-023w admin">Admin tienda</span>` : ""}
            <span class="st-pill-023w ${status === "break" ? "break" : (status === "active" ? "live" : "")}">${h(fieldOpsStatus024A_R1(status))}</span>
          </div>
        </div>

        <div class="st-metrics-023w">
          <div class="st-mini-023w"><span>Activo</span><strong data-field-active-024a-r1>${h(formatSeconds(storeTeamLiveValue023W(member, "active")))}</strong></div>
          <div class="st-mini-023w"><span>Pausa</span><strong data-field-break-024a-r1>${h(formatSeconds(storeTeamLiveValue023W(member, "break")))}</strong></div>
          <div class="st-mini-023w"><span>Meta asignada</span><strong>${h(formatMoney(goal))}</strong></div>
          <div class="st-mini-023w"><span>Ventas realizadas</span><strong>${h(formatMoney(sales))}</strong></div>
        </div>
        <div class="st-progress-023w"><i style="width:${Math.min(100, pct)}%"></i></div>
        <div class="st-muted-023w">${h(pct)}% cumplimiento - ${h(member.sales_count || 0)} venta(s)</div>

        <div class="st-actions-023w">
          <button class="st-btn-023w" type="button" data-field-action-024a-r1="start" data-field-employee-024a-r1="${h(member.employee_id)}" ${canStart ? "" : "disabled"}>Inicio jornada</button>
          <button class="st-btn-023w secondary" type="button" data-field-action-024a-r1="pause" data-field-employee-024a-r1="${h(member.employee_id)}" ${canPause ? "" : "disabled"}>Pausa jornada</button>
          <button class="st-btn-023w secondary" type="button" data-field-action-024a-r1="resume" data-field-employee-024a-r1="${h(member.employee_id)}" ${canResume ? "" : "disabled"}>Retomar labores</button>
          <button class="st-btn-023w danger" type="button" data-field-action-024a-r1="finish" data-field-employee-024a-r1="${h(member.employee_id)}" ${canFinish ? "" : "disabled"}>Finalizar turno</button>
        </div>
      </article>
    `;
  }

  function updateFieldOpsTimers024A_R1() {
    root.querySelectorAll("[data-field-member-024a-r1]").forEach((card) => {
      const employeeId = card.getAttribute("data-field-member-024a-r1") || "";
      const member = storeTeamMembers024A_R1().find((item) => item.employee_id === employeeId);
      const active = card.querySelector("[data-field-active-024a-r1]");
      const pause = card.querySelector("[data-field-break-024a-r1]");
      if (active) active.textContent = formatSeconds(storeTeamLiveValue023W(member, "active"));
      if (pause) pause.textContent = formatSeconds(storeTeamLiveValue023W(member, "break"));
    });
  }

  /* CLONEXA_024A_PERFECT_R2_VISUAL_FIELD_OPS_START */
  function ensureFieldOpsVisual024A_R2() {
    if (document.getElementById("fieldOpsVisual024AR2")) return;

    const style = document.createElement("style");
    style.id = "fieldOpsVisual024AR2";
    style.textContent = `
      .st-shell-023w {
        width: min(100%, 1540px);
        margin: 0 auto;
        padding: 26px clamp(18px, 3vw, 34px);
        display: grid;
        gap: 20px;
      }

      .st-hero-023w {
        min-height: 150px;
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 20px;
      }

      .st-title-023w {
        font-size: clamp(38px, 5vw, 64px);
        line-height: 1;
        margin: 8px 0 10px;
      }

      .st-grid-023w {
        display: grid;
        grid-template-columns: repeat(4, minmax(190px, 1fr));
        gap: 16px;
      }

      .st-grid-023w:has(.st-member-023w) {
        grid-template-columns: repeat(2, minmax(360px, 1fr));
      }

      .st-card-023w {
        border-radius: 26px;
      }

      .st-member-023w {
        padding: 24px;
        display: grid;
        gap: 18px;
        min-height: auto;
      }

      .st-member-head-023w {
        display: flex;
        justify-content: space-between;
        align-items: flex-start;
        gap: 12px;
      }

      .st-member-head-023w strong {
        font-size: 24px;
        line-height: 1.1;
      }

      .st-metrics-023w {
        display: grid;
        grid-template-columns: repeat(4, minmax(130px, 1fr));
        gap: 12px;
      }

      .st-mini-023w {
        padding: 14px;
        border-radius: 18px;
        background: rgba(7, 12, 32, .52);
        border: 1px solid rgba(255,255,255,.10);
      }

      .st-mini-023w span {
        display: block;
        font-size: 11px;
        text-transform: uppercase;
        letter-spacing: .12em;
        font-weight: 1000;
        color: rgba(255,255,255,.62);
        margin-bottom: 8px;
      }

      .st-mini-023w strong {
        display: block;
        font-size: 20px;
        color: #fff;
      }

      .st-actions-023w {
        display: flex;
        flex-wrap: wrap;
        gap: 10px;
      }

      .st-actions-023w .st-btn-023w {
        min-height: 46px;
        border-radius: 16px;
        padding-inline: 18px;
      }

      .st-progress-023w {
        height: 10px;
        border-radius: 999px;
        overflow: hidden;
        background: rgba(255,255,255,.08);
      }

      .st-progress-023w i {
        display: block;
        height: 100%;
        border-radius: inherit;
      }

      @media (max-width: 1200px) {
        .st-grid-023w,
        .st-grid-023w:has(.st-member-023w) {
          grid-template-columns: 1fr 1fr;
        }

        .st-metrics-023w {
          grid-template-columns: 1fr 1fr;
        }
      }

      @media (max-width: 760px) {
        .st-grid-023w,
        .st-grid-023w:has(.st-member-023w) {
          grid-template-columns: 1fr;
        }

        .st-hero-023w,
        .st-member-head-023w {
          flex-direction: column;
        }
      }
    `;

    document.head.appendChild(style);
  }
  /* CLONEXA_024A_PERFECT_R2_VISUAL_FIELD_OPS_END */

  async function openFieldOpsMiniPanel024A_R1(session) {
    storeTeamStyles023W();
    ensureFieldOpsVisual024A_R2();
    

    const msgId = "fieldOpsMsg024AR1";
    let loadError = "";

    try {
      await loadStoreTeam023W(true);
    } catch (error) {
      loadError = error.message || "No se pudo cargar Operación de campo.";
      currentStoreTeam023W = { store: {}, members: [] };
    }

    const store = currentStoreTeam023W?.store || {};
    const members = storeTeamMembers024A_R1();
    const totals = storeTeamTotals024A_R1();
    const pct = storeTeamGoalPct024A_R1(totals.sales, totals.goal);

    root.innerHTML = `
      <main class="st-shell-023w">
        <header class="st-card-023w st-hero-023w">
          <div>
            <div class="st-kicker-023w">Operación de campo</div>
            <h1 class="st-title-023w">${h(store.name || "Tienda actual")}</h1>
            <p class="st-muted-023w">Colaboradores asociados a esta tienda, jornada, pausas no computables y meta vs ventas.</p>
          </div>
          <div class="st-actions-023w">
            <button class="st-btn-023w secondary" type="button" data-field-refresh-024a-r1>Actualizar</button>
            <button class="st-btn-023w secondary" type="button" data-field-back-024a-r1>Dashboard</button>
          </div>
        </header>

        <section class="st-grid-023w">
          <article class="st-card-023w">
            <div class="st-kicker-023w">Colaboradores</div>
            <h2>${h(members.length)}</h2>
          </article>
          <article class="st-card-023w">
            <div class="st-kicker-023w">Conectados</div>
            <h2>${h(totals.active)}</h2>
          </article>
          <article class="st-card-023w">
            <div class="st-kicker-023w">En pausa</div>
            <h2>${h(totals.breaks)}</h2>
          </article>
          <article class="st-card-023w">
            <div class="st-kicker-023w">Ventas vs meta</div>
            <h2>${h(formatMoney(totals.sales))} / ${h(formatMoney(totals.goal))}</h2>
            <div class="st-progress-023w"><i style="width:${Math.min(100, pct)}%"></i></div>
            <div class="st-muted-023w">${h(pct)}% cumplimiento - ${h(totals.count)} venta(s)</div>
          </article>
        </section>

        <section>
          <div class="st-kicker-023w">Detalle por colaborador</div>
          <div class="st-grid-023w">
            ${members.map(fieldOpsMemberRow024A_R1).join("") || `<div class="st-card-023w st-member-023w">No hay colaboradores asociados a esta tienda desde Login tiendas.</div>`}
          </div>
        </section>

        <div class="st-msg-023w" id="${msgId}">${h(loadError)}</div>
      </main>
    `;

    updateFieldOpsTimers024A_R1();
    if (storeTeamTimer023W) window.clearInterval(storeTeamTimer023W);
    storeTeamTimer023W = window.setInterval(updateFieldOpsTimers024A_R1, 1000);

    root.querySelector("[data-field-back-024a-r1]")?.addEventListener("click", () => bootShell());
    root.querySelector("[data-field-refresh-024a-r1]")?.addEventListener("click", () => openFieldOpsMiniPanel024A_R1(session));

    root.querySelectorAll("[data-field-action-024a-r1]").forEach((button) => {
      button.addEventListener("click", async () => {
        const employeeId = button.getAttribute("data-field-employee-024a-r1") || "";
        const action = button.getAttribute("data-field-action-024a-r1") || "";
        const msg = root.querySelector(`#${msgId}`);

        try {
          if (msg) msg.textContent = "Actualizando jornada...";
          button.disabled = true;
          await storeTeamAction023W(employeeId, action);
          await openFieldOpsMiniPanel024A_R1(session);
        } catch (error) {
          if (msg) msg.textContent = error.message || "No se pudo actualizar la jornada.";
          button.disabled = false;
        }
      });
    });
  }

  async function finishStoreTeamFromDashboard024A_R1() {
    if (!isStorePanel023W()) {
      return operationalAction("finish");
    }

    try {
      await loadStoreTeam023W(true);
    } catch (_) {}

    const store = currentStoreTeam023W?.store || {};
    const members = storeTeamMembers024A_R1();
    const adminId = String(store.admin_employee_id || "").trim();
    const currentId = String(store.current_employee_id || "").trim();
    const targetId = adminId || currentId || members.find((member) => member.is_admin)?.employee_id || members.find((member) => member.is_current)?.employee_id || members[0]?.employee_id || "";

    if (!targetId) {
      return operationalAction("finish");
    }

    try {
      return await storeTeamAction023W(targetId, "finish", { cascadeTeam: true });
    } catch (error) {
      console.warn("CLONEXA 024A finish team fallback:", error);
      return operationalAction("finish");
    }
  }
  /* CLONEXA_024A_PERFECT_R1_FIELD_OPS_MINIPANEL_END */

  
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
      if (isStorePanel023W()) {
        await loadStoreTeam023W(true).catch((error) => {
          console.warn("CLONEXA 023W store team fallback:", error);
          currentStoreTeam023W = null;
        });
      }
      currentNotesSummary020A = await loadNotesSummary020A(currentModuleConfig).catch((error) => {
        console.warn("CLONEXA 020A notes summary fallback:", error);
        return defaultNotesSummary020A();
      });
      renderShell(session, operational.operational_session || operational, currentModuleConfig);
      refreshMiniPanelSalesKpis022I().catch((error) => console.warn("CLONEXA 022I KPI refresh boot:", error));
    } catch (error) {
      clearMiniPanelToken024B();
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

/* CLONEXA_024A_FORCE_FIX_R5_CANCELLED_MINI_PANEL_RUNTIME_OK */

/* CLONEXA_024B_R2_STORE_ADMIN_SESSION_ISOLATION_OK */
/* CLONEXA_024E_REQUESTS_SOLD_PREFILL_EDITABLE_OK */
/* CLONEXA_024F_STORE_REQUESTS_TEAM_SOLD_PREFILL_OK */
