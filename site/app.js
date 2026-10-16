// Fantasy Dashboard – Vanilla JS SPA (hash-routing, kein Build-Step im Browser)
(() => {
  "use strict";

  const TABS = [
    { id: "overview", label: "Übersicht", icon: "🏠", ready: true },
    { id: "roster", label: "Mein Roster", icon: "👤", ready: true },
    { id: "startsit", label: "Start/Sit", icon: "🔁", ready: false, phase: "Phase 3" },
    { id: "waiver", label: "Waiver Wire", icon: "📈", ready: false, phase: "Phase 2" },
    { id: "players", label: "Alle Spieler", icon: "📋", ready: false, phase: "Phase 2" },
    { id: "tradefinder", label: "Trade Finder", icon: "🔄", ready: false, phase: "Phase 4" },
    { id: "tradeanalyzer", label: "Trade-Analyzer", icon: "⚖️", ready: false, phase: "Phase 4" },
    { id: "league", label: "Liga", icon: "🏆", ready: false, phase: "Phase 5" },
    { id: "planner", label: "Planer", icon: "🗓️", ready: false, phase: "Phase 5" },
  ];

  const STATUS_LABELS = {
    Questionable: "Fraglich",
    Doubtful: "Unwahrscheinlich",
    Out: "Out",
    IR: "Verletzt (IR)",
    PUP: "PUP",
    Sus: "Gesperrt",
    NA: "N/A",
    COV: "COVID",
  };

  let DATA = null;

  // ---------- Utilities ----------
  function $(sel, root = document) { return root.querySelector(sel); }
  function el(tag, attrs = {}, children = []) {
    const node = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) {
      if (k === "html") node.innerHTML = v;
      else if (k.startsWith("on") && typeof v === "function") node.addEventListener(k.slice(2), v);
      else if (v !== null && v !== undefined) node.setAttribute(k, v);
    }
    for (const c of [].concat(children)) {
      if (c === null || c === undefined) continue;
      node.appendChild(typeof c === "string" ? document.createTextNode(c) : c);
    }
    return node;
  }
  function fmt1(n) { return (n === null || n === undefined) ? "–" : Number(n).toFixed(1); }
  function fmtInt(n) { return (n === null || n === undefined) ? "–" : Math.round(Number(n)).toLocaleString("de-DE"); }
  function posChip(pos) {
    return el("span", { class: `pos-chip pos-${pos || ""}` }, pos || "?");
  }
  function statusInfo(player) {
    const s = player.injury_status;
    if (!s) return { cls: "status-good", label: "Gesund" };
    if (s === "Questionable") return { cls: "status-warn", label: STATUS_LABELS[s] };
    return { cls: "status-bad", label: STATUS_LABELS[s] || s };
  }
  function playerLink(pid, labelOverride) {
    const p = DATA.players[pid];
    const label = labelOverride || (p ? p.name : pid);
    return el("span", { class: "player-link", onclick: () => openPlayerDetail(pid) }, label);
  }
  function teamAvailability(p) {
    if (p.fantasy_team) return `bei ${p.fantasy_team.team_name}`;
    return "Frei (Waiver/FA)";
  }

  // ---------- Router ----------
  function currentTabId() {
    const hash = (location.hash || "#overview").replace("#", "");
    return TABS.some((t) => t.id === hash) ? hash : "overview";
  }

  function navigateTo(tabId) { location.hash = `#${tabId}`; }

  function render() {
    const tabId = currentTabId();
    renderNav(tabId);
    const root = $("#view-root");
    root.innerHTML = "";
    if (!DATA) {
      root.appendChild(renderError("Daten konnten nicht geladen werden."));
      return;
    }
    const tab = TABS.find((t) => t.id === tabId);
    if (!tab.ready) {
      root.appendChild(renderPlaceholder(tab));
      return;
    }
    if (tabId === "overview") root.appendChild(renderOverview());
    else if (tabId === "roster") root.appendChild(renderRoster());
  }

  function renderNav(activeId) {
    const items = TABS.map((t) =>
      el(
        "button",
        {
          class: `nav-item ${t.id === activeId ? "active" : ""}`,
          onclick: () => navigateTo(t.id),
        },
        [el("span", { class: "icon" }, t.icon), el("span", {}, t.label)]
      )
    );
    const navHost = $("#nav-items");
    navHost.innerHTML = "";
    items.forEach((i) => navHost.appendChild(i));

    const mobileHost = $("#mobile-tabbar");
    mobileHost.innerHTML = "";
    items.forEach((i) => mobileHost.appendChild(i.cloneNode(true)));
    // Re-bind onclick for mobile clones (cloneNode doesn't copy listeners)
    TABS.forEach((t, idx) => {
      mobileHost.children[idx].addEventListener("click", () => navigateTo(t.id));
    });
  }

  function renderError(msg) {
    return el("div", { class: "card placeholder-card" }, [
      el("div", { class: "big-icon" }, "⚠️"),
      el("div", {}, msg),
    ]);
  }

  function renderPlaceholder(tab) {
    return el("div", { class: "card placeholder-card" }, [
      el("div", { class: "big-icon" }, tab.icon),
      el("div", { style: "font-weight:700;font-size:16px;margin-bottom:6px;" }, tab.label),
      el("div", {}, `Kommt in ${tab.phase} des Dashboard-Ausbaus.`),
    ]);
  }

  // ---------- Header (shared) ----------
  function renderHeader() {
    const me = DATA.me;
    const league = DATA.league;
    const genDate = new Date(DATA.generated_at);
    return el("div", { class: "page-header" }, [
      el("div", {}, [
        el("h1", {}, me.team_name),
        el(
          "div",
          { class: "header-meta" },
          `Woche ${league.week} · Zuletzt aktualisiert: ${genDate.toLocaleString("de-DE", {
            dateStyle: "medium",
            timeStyle: "short",
          })}`
        ),
      ]),
      el("div", { class: "header-stats" }, [
        el("div", { class: "header-stat" }, [
          el("div", { class: "value" }, `${me.wins}-${me.losses}${me.ties ? `-${me.ties}` : ""}`),
          el("div", { class: "label" }, "Bilanz"),
        ]),
        el("div", { class: "header-stat" }, [
          el("div", { class: "value" }, `#${me.rank}`),
          el("div", { class: "label" }, `von ${league.total_rosters}`),
        ]),
        el("div", { class: "header-stat" }, [
          el("div", { class: "value" }, fmt1(me.fpts)),
          el("div", { class: "label" }, "Punkte"),
        ]),
      ]),
    ]);
  }

  // ---------- Übersicht ----------
  function renderOverview() {
    const frag = el("div", {});
    frag.appendChild(renderHeader());
    frag.appendChild(renderMatchupCard());

    const grid = el("div", { class: "grid grid-2" });
    grid.appendChild(renderInjuryAlertsCard());
    grid.appendChild(renderTrendingCard());
    grid.appendChild(renderComingSoonMiniCard("Top Waiver-Tipps", "📈", "waiver", "Phase 2"));
    grid.appendChild(renderComingSoonMiniCard("Start/Sit-Hinweise", "🔁", "startsit", "Phase 3"));
    frag.appendChild(grid);

    const grid2 = el("div", { class: "grid grid-2" });
    grid2.appendChild(renderComingSoonMiniCard("Top Trade-Vorschläge", "🔄", "tradefinder", "Phase 4"));
    frag.appendChild(grid2);
    return frag;
  }

  function renderMatchupCard() {
    const m = DATA.matchup;
    if (!m || !m.opponent) {
      return el("div", { class: "card" }, [
        el("div", { class: "card-title" }, "Matchup"),
        el("div", { class: "empty-state" }, "Keine Matchup-Daten für diese Woche."),
      ]);
    }
    const winProb = m.win_probability_me;
    const card = el("div", { class: "card" }, [
      el("div", { class: "card-title" }, `Matchup · Woche ${m.week}`),
      el("div", { class: "matchup-sides" }, [
        el("div", { class: "matchup-side me" }, [
          el("div", { class: "team-name" }, m.me.team_name),
          el("div", { class: "proj" }, fmt1(m.me.projected_points)),
          el("div", { class: "actual" }, `aktuell: ${fmt1(m.me.points)} Pkt.`),
        ]),
        el("div", { class: "matchup-vs" }, "VS"),
        el("div", { class: "matchup-side opp" }, [
          el("div", { class: "team-name" }, m.opponent.team_name),
          el("div", { class: "proj" }, fmt1(m.opponent.projected_points)),
          el("div", { class: "actual" }, `aktuell: ${fmt1(m.opponent.points)} Pkt.`),
        ]),
      ]),
    ]);

    if (winProb !== null && winProb !== undefined) {
      const bar = el("div", { class: "winprob-bar" }, [el("div", { class: "fill", style: `width:${winProb}%` })]);
      card.appendChild(bar);
      card.appendChild(
        el("div", { class: "winprob-label" }, [
          el("span", {}, `${winProb}% Sieg-Chance (Schätzung)`),
          el("span", {}, `${(100 - winProb).toFixed(1)}%`),
        ])
      );
    }

    card.appendChild(renderLineupTable("Mein Lineup", m.me.starters));
    card.appendChild(renderLineupTable(m.opponent.team_name, m.opponent.starters));
    return card;
  }

  function renderLineupTable(title, starters) {
    const rows = starters.map((s) => {
      const p = DATA.players[s.player_id];
      if (!p) return el("tr", {}, [el("td", { colspan: "4" }, s.player_id)]);
      const st = statusInfo(p);
      return el("tr", {}, [
        el("td", {}, el("span", { class: "slot-tag" }, s.slot)),
        el("td", {}, [posChip(p.position), " ", playerLink(s.player_id)]),
        el("td", {}, [el("span", { class: `status-dot ${st.cls}`, title: st.label })]),
        el("td", {}, fmt1(s.actual_points ?? p.projection_week)),
      ]);
    });
    return el("div", {}, [
      el("div", { class: "section-label" }, title),
      el("table", { class: "lineup-table" }, [
        el("thead", {}, el("tr", {}, [el("th", {}, "Slot"), el("th", {}, "Spieler"), el("th", {}, ""), el("th", {}, "Pkt.")])),
        el("tbody", {}, rows),
      ]),
    ]);
  }

  function renderInjuryAlertsCard() {
    const myIds = new Set([...DATA.my_roster.slots.map((s) => s.player_id), ...DATA.my_roster.bench, ...DATA.my_roster.reserve]);
    const injured = [...myIds]
      .map((id) => DATA.players[id])
      .filter((p) => p && p.injury_status);

    const body = injured.length
      ? el(
          "div",
          { class: "mini-list" },
          injured.map((p) => {
            const st = statusInfo(p);
            return el("div", { class: "mini-item" }, [
              el("div", {}, [posChip(p.position), " ", playerLink(p.id)]),
              el("span", { class: `status-dot ${st.cls}` , title: st.label}),
            ]);
          })
        )
      : el("div", { class: "empty-state" }, "Keine Verletzungs-Alarme in deinem Kader.");

    return el("div", { class: "card" }, [el("div", { class: "card-title" }, "Verletzungs-Alarme"), body]);
  }

  function renderTrendingCard() {
    const list = Object.values(DATA.players)
      .filter((p) => p.trending_add)
      .sort((a, b) => b.trending_add - a.trending_add)
      .slice(0, 5);
    const body = list.length
      ? el(
          "div",
          { class: "mini-list" },
          list.map((p) =>
            el("div", { class: "mini-item" }, [
              el("div", {}, [posChip(p.position), " ", playerLink(p.id), ` (${teamAvailability(p)})`]),
              el("span", { class: "reason" }, `+${fmtInt(p.trending_add)}`),
            ])
          )
        )
      : el("div", { class: "empty-state" }, "Keine Trending-Daten verfügbar.");
    return el("div", { class: "card" }, [
      el("div", { class: "card-title" }, [
        "Trending-Spieler",
        el("button", { class: "see-all", onclick: () => navigateTo("waiver") }, "Alle ansehen"),
      ]),
      body,
    ]);
  }

  function renderComingSoonMiniCard(title, icon, tabId, phase) {
    return el("div", { class: "card" }, [
      el("div", { class: "card-title" }, [title, el("button", { class: "see-all", onclick: () => navigateTo(tabId) }, "Alle ansehen")]),
      el("div", { class: "empty-state" }, `${icon} Verfügbar ab ${phase}.`),
    ]);
  }

  // ---------- Mein Roster ----------
  function renderRoster() {
    const frag = el("div", {});
    frag.appendChild(renderHeader());

    frag.appendChild(el("div", { class: "section-label" }, "Starter"));
    frag.appendChild(renderRosterTable(DATA.my_roster.slots.map((s) => s.player_id), DATA.my_roster.slots));

    frag.appendChild(el("div", { class: "section-label" }, "Bank"));
    frag.appendChild(renderRosterTable(DATA.my_roster.bench));

    if (DATA.my_roster.reserve && DATA.my_roster.reserve.length) {
      frag.appendChild(el("div", { class: "section-label" }, "Reserve / IR"));
      frag.appendChild(renderRosterTable(DATA.my_roster.reserve));
    }
    return frag;
  }

  function renderRosterTable(playerIds, slots) {
    const slotByPid = {};
    if (slots) slots.forEach((s) => (slotByPid[s.player_id] = s.slot));

    const rows = playerIds.map((pid) => {
      const p = DATA.players[pid];
      if (!p) return null;
      const st = statusInfo(p);
      return el("tr", {}, [
        el("td", {}, [slots ? el("span", { class: "slot-tag" }, slotByPid[pid]) : null, " ", playerLink(pid)].filter(Boolean)),
        el("td", {}, posChip(p.position)),
        el("td", {}, p.team || "–"),
        el("td", {}, p.bye_week ? `W${p.bye_week}` : "–"),
        el("td", {}, [el("span", { class: `status-dot ${st.cls}` }), " ", st.label]),
        el("td", {}, fmt1(p.projection_week)),
        el("td", {}, fmt1(p.avg_last3)),
        el("td", {}, fmt1(p.season_avg)),
        el("td", {}, p.trade_value ? fmtInt(p.trade_value) : "–"),
      ]);
    }).filter(Boolean);

    if (!rows.length) {
      return el("div", { class: "card" }, el("div", { class: "empty-state" }, "Keine Spieler in diesem Bereich."));
    }

    return el("div", { class: "card table-wrap" }, [
      el("table", { class: "data-table" }, [
        el(
          "thead",
          {},
          el("tr", {}, [
            el("th", {}, "Spieler"),
            el("th", {}, "Pos"),
            el("th", {}, "Team"),
            el("th", {}, "Bye"),
            el("th", {}, "Status"),
            el("th", {}, "Proj."),
            el("th", {}, "Ø L3"),
            el("th", {}, "Ø Saison"),
            el("th", {}, "Trade-Wert"),
          ])
        ),
        el("tbody", {}, rows),
      ]),
    ]);
  }

  // ---------- Player detail panel ----------
  function openPlayerDetail(pid) {
    const p = DATA.players[pid];
    if (!p) return;
    const panel = $("#detail-panel");
    const backdrop = $("#panel-backdrop");
    const st = statusInfo(p);

    const weeks = Object.keys(p.weekly_points).map(Number).sort((a, b) => a - b);
    const maxPts = Math.max(1, ...weeks.map((w) => p.weekly_points[w]));
    const chart = el(
      "div",
      { style: "display:flex;align-items:flex-end;gap:4px;height:70px;margin:10px 0;" },
      weeks.map((w) =>
        el("div", { style: "flex:1;display:flex;flex-direction:column;align-items:center;gap:3px;" }, [
          el("div", {
            style: `width:100%;background:var(--accent);border-radius:3px 3px 0 0;height:${Math.max(2, (p.weekly_points[w] / maxPts) * 54)}px;`,
            title: `Woche ${w}: ${p.weekly_points[w]} Pkt.`,
          }),
          el("div", { style: "font-size:9px;color:var(--text-faint);" }, `W${w}`),
        ])
      )
    );

    const rest = (p.rest_of_season || []).slice(0, 6);
    const restRow = rest.length
      ? el("div", { style: "display:flex;gap:6px;flex-wrap:wrap;margin-top:6px;" }, rest.map((g) =>
          el("span", { class: "pos-chip", style: "background:var(--card-border);color:var(--text);" }, `W${g.week} ${g.home ? "vs" : "@"} ${g.opponent}`)
        ))
      : el("div", { class: "empty-state" }, "Kein Restprogramm verfügbar.");

    panel.innerHTML = "";
    panel.appendChild(el("button", { class: "btn panel-close", onclick: closePlayerDetail }, "✕"));
    panel.appendChild(
      el("div", { style: "display:flex;gap:12px;align-items:center;margin-top:10px;" }, [
        p.photo ? el("img", { class: "player-photo", style: "width:56px;height:56px;", src: p.photo }) : null,
        el("div", {}, [
          el("div", { style: "font-weight:800;font-size:17px;" }, p.name),
          el("div", { class: "player-meta" }, [posChip(p.position), ` ${p.team || "FA"} · Alter ${p.age ?? "–"} · Bye ${p.bye_week ? "W" + p.bye_week : "–"}`]),
        ]),
      ].filter(Boolean))
    );
    panel.appendChild(
      el("div", { style: "margin-top:10px;display:flex;align-items:center;gap:8px;" }, [
        el("span", { class: `status-dot ${st.cls}` }),
        el("span", {}, st.label),
        el("span", { style: "color:var(--text-faint);" }, "·"),
        el("span", {}, teamAvailability(p)),
      ])
    );

    const statGrid = el("div", { class: "grid grid-3", style: "margin-top:14px;" }, [
      statTile("Projektion", fmt1(p.projection_week)),
      statTile("Ø letzte 3", fmt1(p.avg_last3)),
      statTile("Ø Saison", fmt1(p.season_avg)),
      statTile("Trade-Wert", p.trade_value ? fmtInt(p.trade_value) : "–"),
      statTile("Pos-Rang (Wert)", p.trade_pos_rank ? `#${p.trade_pos_rank}` : "–"),
      statTile("Trending", p.trending_add ? `+${fmtInt(p.trending_add)}` : p.trending_drop ? `-${fmtInt(p.trending_drop)}` : "–"),
    ]);
    panel.appendChild(statGrid);

    panel.appendChild(el("div", { class: "section-label" }, "Fantasy-Punkte pro Woche"));
    panel.appendChild(chart);

    panel.appendChild(el("div", { class: "section-label" }, "Restprogramm"));
    panel.appendChild(restRow);

    panel.appendChild(
      el("div", { style: "margin-top:16px;display:flex;gap:8px;flex-wrap:wrap;" }, [
        el("button", { class: "btn", onclick: () => toggleSavedList("tradeTargets", pid) }, "Zum Trade-Analyzer hinzufügen"),
        el("button", { class: "btn", onclick: () => toggleSavedList("waiverTargets", pid) }, "Als Waiver-Ziel merken"),
      ])
    );

    panel.classList.add("open");
    backdrop.classList.add("open");
  }

  function statTile(label, value) {
    return el("div", { class: "card", style: "padding:10px;text-align:center;margin-bottom:0;" }, [
      el("div", { style: "font-size:16px;font-weight:800;" }, value),
      el("div", { style: "font-size:10.5px;color:var(--text-muted);text-transform:uppercase;" }, label),
    ]);
  }

  function closePlayerDetail() {
    $("#detail-panel").classList.remove("open");
    $("#panel-backdrop").classList.remove("open");
  }

  function toggleSavedList(key, pid) {
    try {
      const raw = localStorage.getItem(key);
      const list = raw ? JSON.parse(raw) : [];
      const idx = list.indexOf(pid);
      if (idx >= 0) list.splice(idx, 1);
      else list.push(pid);
      localStorage.setItem(key, JSON.stringify(list));
    } catch (e) {
      /* localStorage evtl. nicht verfügbar – kein Blocker */
    }
  }

  // ---------- Theme ----------
  function initTheme() {
    let theme = null;
    try { theme = localStorage.getItem("theme"); } catch (e) { /* ignore */ }
    if (theme) document.documentElement.setAttribute("data-theme", theme);
    $("#theme-toggle").addEventListener("click", () => {
      const current = document.documentElement.getAttribute("data-theme");
      const next = current === "dark" ? "light" : current === "light" ? null : "dark";
      if (next) document.documentElement.setAttribute("data-theme", next);
      else document.documentElement.removeAttribute("data-theme");
      try {
        if (next) localStorage.setItem("theme", next);
        else localStorage.removeItem("theme");
      } catch (e) { /* ignore */ }
    });
  }

  // ---------- Boot ----------
  function boot() {
    initTheme();
    $("#panel-backdrop").addEventListener("click", closePlayerDetail);
    window.addEventListener("hashchange", render);

    fetch("data.json")
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then((data) => {
        DATA = data;
        render();
      })
      .catch((err) => {
        console.error("Konnte data.json nicht laden:", err);
        DATA = null;
        render();
      });
  }

  document.addEventListener("DOMContentLoaded", boot);
})();
