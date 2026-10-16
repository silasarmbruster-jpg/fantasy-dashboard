// Fantasy Dashboard – Vanilla JS SPA (hash-routing, kein Build-Step im Browser)
(() => {
  "use strict";

  const TABS = [
    { id: "overview", label: "Übersicht", icon: "home" },
    { id: "roster", label: "Mein Roster", icon: "user" },
    { id: "startsit", label: "Start/Sit", icon: "repeat" },
    { id: "waiver", label: "Waiver Wire", icon: "trending-up" },
    { id: "players", label: "Alle Spieler", icon: "list" },
    { id: "tradefinder", label: "Trade Finder", icon: "arrow-left-right" },
    { id: "tradeanalyzer", label: "Trade-Analyzer", icon: "scale" },
    { id: "sellbuy", label: "Sell/Buy", icon: "bar-chart-2" },
    { id: "league", label: "Liga", icon: "trophy" },
    { id: "planner", label: "Planer", icon: "calendar" },
    { id: "live", label: "Live", icon: "satellite-dish" },
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
      node.appendChild(c instanceof Node ? c : document.createTextNode(String(c)));
    }
    return node;
  }
  function fmt1(n) { return (n === null || n === undefined) ? "–" : Number(n).toFixed(1); }
  function fmtInt(n) { return (n === null || n === undefined) ? "–" : Math.round(Number(n)).toLocaleString("de-DE"); }
  // Fehlender Marktwert (z.B. tiefe Bankspieler ohne FantasyCalc-Notierung)
  // soll erkennbar "kein Marktwert" heißen statt als leeres Feld/bloßer
  // Strich zu wirken.
  function fmtTradeValue(v) { return (v === null || v === undefined || v === 0) ? el("span", { class: "null-value" }, "kein Marktwert") : fmtInt(v); }
  // Einheitliche Icons über Lucide (keine Emojis als UI-Elemente). icon()
  // erzeugt nur den Platzhalter <i data-lucide>; refreshIcons() muss danach
  // aufgerufen werden, damit Lucide ihn durch das Inline-SVG ersetzt.
  function icon(name, attrs = {}) {
    return el("i", { "data-lucide": name, ...attrs });
  }
  function refreshIcons() {
    if (window.lucide && typeof window.lucide.createIcons === "function") {
      try { window.lucide.createIcons(); } catch (e) { /* ignore */ }
    }
  }
  // Kurzes Hochzählen für die prominentesten Zahlen (Punkte, Matchup-Score).
  // Sparsam eingesetzt, nur an wenigen Stellen - kein durchgängiges Feature.
  function animateNumber(node, target, { decimals = 1, duration = 500, suffix = "" } = {}) {
    if (!Number.isFinite(target)) { node.textContent = "–"; return; }
    if (window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      node.textContent = target.toFixed(decimals) + suffix;
      return;
    }
    const startTime = performance.now();
    function tick(now) {
      const progress = Math.min(1, (now - startTime) / duration);
      const eased = 1 - Math.pow(1 - progress, 3);
      node.textContent = (target * eased).toFixed(decimals) + suffix;
      if (progress < 1) requestAnimationFrame(tick);
    }
    requestAnimationFrame(tick);
  }
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

  function initialsOf(name) {
    return (name || "?").split(" ").map((w) => w[0]).filter(Boolean).slice(0, 2).join("").toUpperCase() || "?";
  }
  function avatarFallback(p, size) {
    return el("div", { class: `avatar-fallback pos-${(p && p.position) || ""}` }, p ? initialsOf(p.name) : "?");
  }
  // size: "sm" (Listen/Tabellen), "md" (Karten), "lg" (Detailansicht)
  function playerAvatar(p, size = "sm") {
    const wrap = el("div", { class: `avatar avatar-${size}` });
    if (p && p.photo) {
      const img = el("img", { class: "avatar-img", src: p.photo, alt: "", loading: "lazy" });
      img.addEventListener(
        "error",
        () => {
          wrap.innerHTML = "";
          wrap.appendChild(avatarFallback(p));
        },
        { once: true }
      );
      wrap.appendChild(img);
    } else {
      wrap.appendChild(avatarFallback(p));
    }
    return wrap;
  }
  // Kompakte Zeile: Avatar + Positions-Chip + klickbarer Name (für Tabellen/Listen)
  function playerTag(pid, extra) {
    const p = DATA.players[pid];
    if (!p) return el("span", { style: "color:var(--text-faint);" }, pid);
    return el("span", { class: "player-row", style: "display:inline-flex;gap:8px;" }, [
      playerAvatar(p, "sm"),
      posChip(p.position),
      playerLink(pid),
      extra ? el("span", { style: "color:var(--text-muted);font-size:11.5px;" }, extra) : null,
    ].filter(Boolean));
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
    root.classList.remove("view-fade");
    void root.offsetWidth; // Reflow erzwingen, damit die Animation bei jedem Tab-Wechsel neu startet
    root.classList.add("view-fade");

    if (LOAD_STATE === "loading") {
      root.appendChild(renderSkeleton());
      return;
    }
    if (!DATA) {
      root.appendChild(renderError("Daten konnten nicht geladen werden."));
      refreshIcons();
      return;
    }
    const banner = renderDataFreshnessBanner();
    if (banner) root.appendChild(banner);
    if (tabId === "overview") root.appendChild(renderOverview());
    else if (tabId === "roster") root.appendChild(renderRoster());
    else if (tabId === "players") root.appendChild(renderPlayers());
    else if (tabId === "waiver") root.appendChild(renderWaiver());
    else if (tabId === "startsit") root.appendChild(renderStartSit());
    else if (tabId === "tradefinder") root.appendChild(renderTradeFinder());
    else if (tabId === "tradeanalyzer") root.appendChild(renderTradeAnalyzer());
    else if (tabId === "sellbuy") root.appendChild(renderSellBuy());
    else if (tabId === "league") root.appendChild(renderLeague());
    else if (tabId === "planner") root.appendChild(renderPlanner());
    else if (tabId === "live") root.appendChild(renderLive());
    refreshIcons();
  }

  function renderNav(activeId) {
    const items = TABS.map((t) =>
      el(
        "button",
        {
          class: `nav-item ${t.id === activeId ? "active" : ""}`,
          onclick: () => navigateTo(t.id),
        },
        [icon(t.icon, { class: "icon" }), el("span", {}, t.label)]
      )
    );
    const navHost = $("#nav-items");
    navHost.innerHTML = "";
    items.forEach((i) => navHost.appendChild(i));
    refreshIcons(); // wandelt die <i data-lucide> in navHost in echte SVGs um, bevor geklont wird

    const mobileHost = $("#mobile-tabbar");
    mobileHost.innerHTML = "";
    items.forEach((i) => mobileHost.appendChild(i.cloneNode(true)));
    // Re-bind onclick for mobile clones (cloneNode doesn't copy listeners)
    TABS.forEach((t, idx) => {
      mobileHost.children[idx].addEventListener("click", () => navigateTo(t.id));
    });
  }

  const SOURCE_LABELS_DE = {
    schedule: "NFL-Spielplan",
    trending: "Trending Adds/Drops",
    weekly_stats: "Wochenstatistiken",
    projections: "Projections",
    fantasycalc: "FantasyCalc Trade-Werte",
    future_matchups: "Künftige Matchups",
    historical_matchups: "Historische Matchups",
    transactions: "Transaktionen",
    vegas_odds: "Vegas-Odds",
  };

  function renderDataFreshnessBanner() {
    const status = (DATA.meta && DATA.meta.source_status) || {};
    const failed = Object.entries(status).filter(([, v]) => v !== "ok");
    if (!failed.length) return null;
    return el("div", { class: "info-banner warn", style: "align-items:flex-start;margin-bottom:16px;" }, [
      el("div", { class: "ib-icon" }, icon("triangle-alert")),
      el("div", {}, [
        el("div", { class: "ib-title" }, "Einzelne Datenquellen hatten beim letzten Build-Lauf Probleme"),
        el(
          "ul",
          { style: "margin:4px 0 0;padding-left:18px;font-size:12px;color:var(--text-muted);" },
          failed.map(([key, msg]) => el("li", {}, `${SOURCE_LABELS_DE[key] || key}: ${msg}`))
        ),
        el("div", { class: "ib-sub", style: "margin-top:6px;" }, "Betroffene Werte nutzen Fallbacks (leer/vorheriger Stand) statt erfundener Daten."),
      ]),
    ]);
  }

  function renderError(msg) {
    return el("div", { class: "card placeholder-card" }, [
      el("div", { class: "big-icon" }, icon("triangle-alert", { style: "width:34px;height:34px;" })),
      el("div", {}, msg),
    ]);
  }

  // ---------- Header (shared) ----------
  function renderHeader(opts) {
    const me = DATA.me;
    const league = DATA.league;
    const genDate = new Date(DATA.generated_at);
    const stats = [
      el("div", { class: "header-stat" }, [
        el("div", { class: "value" }, `${me.wins}-${me.losses}${me.ties ? `-${me.ties}` : ""}`),
        el("div", { class: "label" }, "Bilanz"),
      ]),
      el("div", { class: "header-stat" }, [
        el("div", { class: "value" }, `#${me.rank}`),
        el("div", { class: "label" }, `von ${league.total_rosters}`),
      ]),
      (() => {
        const valNode = el("div", { class: "value num" }, "0.0");
        animateNumber(valNode, me.fpts || 0);
        return el("div", { class: "header-stat" }, [valNode, el("div", { class: "label" }, "Punkte")]);
      })(),
    ];
    if (opts && opts.showPlayoffNote) {
      const myPlayoff = (DATA.playoffs?.results || []).find((r) => r.roster_id === me.roster_id);
      stats.push(
        el("div", { class: "header-stat" }, [
          el("div", { class: "value" }, myPlayoff ? `${myPlayoff.playoff_probability}%` : "–"),
          el("div", { class: "label" }, "Playoff-Chance"),
        ])
      );
    }
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
      el("div", { class: "header-stats" }, stats),
    ]);
  }

  // ---------- Übersicht ----------
  function renderTodoCard() {
    const actions = [];
    const decisions = DATA.start_sit.decisions || [];
    if (decisions.length) {
      const rec = DATA.players[decisions[0].recommended_player_id];
      actions.push({
        iconName: "repeat",
        title: `Lineup-Lücke: ${decisions.length} Verbesserung${decisions.length > 1 ? "en" : ""} möglich`,
        sub: `${decisions[0].slot}: ${rec ? rec.name : "–"} (+${decisions[0].delta} Pkt.)`,
        go: "startsit",
      });
    }
    const topWaiver = (DATA.waiver.top_overall || [])[0];
    if (topWaiver) {
      const p = DATA.players[topWaiver.player_id];
      actions.push({
        iconName: "trending-up",
        title: `Waiver-Gebot: ${p ? p.name : "Top-Pickup"}`,
        sub: (topWaiver.reasons || [])[0] || "Top-Empfehlung diese Woche",
        go: "waiver",
      });
    }
    // Dieselbe gefilterte/sortierte Liste wie im Trade-Finder-Tab selbst,
    // damit hier und dort nie unterschiedliche Top-Vorschläge/Zahlen stehen.
    const topTrade = filterAndSortProposals()[0];
    if (topTrade) {
      actions.push({
        iconName: "arrow-left-right",
        title: `Trade-Idee mit ${topTrade.team_name}`,
        sub: `${topTrade.lineup_delta >= 0 ? "+" : ""}${topTrade.lineup_delta} Pkt./Woche diese Woche`,
        go: "tradefinder",
      });
    }
    const card = el("div", { class: "todo-card" }, [el("div", { class: "card-title" }, "Heute zu tun")]);
    if (!actions.length) {
      card.appendChild(el("div", { class: "todo-empty" }, "Alles im grünen Bereich – aktuell keine dringenden Aktionen erkannt."));
    } else {
      actions.slice(0, 3).forEach((a) => {
        card.appendChild(
          el("div", { class: "todo-row", onclick: () => navigateTo(a.go) }, [
            el("div", { class: "tr-icon" }, icon(a.iconName)),
            el("div", {}, [el("div", { class: "tr-title" }, a.title), el("div", { class: "tr-sub" }, a.sub)]),
            el("div", { class: "tr-arrow" }, icon("chevron-right")),
          ])
        );
      });
    }
    return card;
  }

  function renderInfoBanners() {
    const banners = [];
    const league = DATA.league;
    const playoffTeams = league.playoff_teams;
    const oppRosterId = DATA.matchup && DATA.matchup.opponent ? DATA.matchup.opponent.roster_id : null;
    if (oppRosterId != null && playoffTeams) {
      const oppTeam = DATA.teams.find((t) => t.roster_id === oppRosterId);
      if (oppTeam && Math.abs(oppTeam.rank - playoffTeams) <= 1) {
        banners.push(
          el("div", { class: "info-banner warn" }, [
            el("div", { class: "ib-icon" }, icon("trophy")),
            el("div", {}, [
              el("div", { class: "ib-title" }, "Playoff-Duell diese Woche"),
              el("div", { class: "ib-sub" }, `${oppTeam.team_name} steht auf Rang #${oppTeam.rank} – direkt an der Playoff-Linie (${playoffTeams} Plätze).`),
            ]),
          ])
        );
      }
    }
    if (league.trade_deadline) {
      const weeksLeft = league.trade_deadline - league.week;
      if (weeksLeft >= 0) {
        banners.push(
          el("div", { class: "info-banner" }, [
            el("div", { class: "ib-icon" }, icon("alarm-clock")),
            el("div", {}, [
              el("div", { class: "ib-title" }, weeksLeft === 0 ? "Trade-Deadline diese Woche!" : `Trade-Deadline in ${weeksLeft} Woche${weeksLeft > 1 ? "n" : ""}`),
              el("div", { class: "ib-sub" }, `Deadline: Woche ${league.trade_deadline} · Playoffs ab Woche ${league.playoff_week_start} (${league.playoff_teams} von ${league.total_rosters} Teams).`),
            ]),
          ])
        );
      }
    }
    if (!banners.length) return null;
    return el("div", { class: "banner-row" }, banners);
  }

  function renderOverview() {
    const frag = el("div", {});
    frag.appendChild(renderHeader({ showPlayoffNote: true }));
    frag.appendChild(renderTodoCard());
    frag.appendChild(renderMatchupCard());
    const banners = renderInfoBanners();
    if (banners) frag.appendChild(banners);

    const grid = el("div", { class: "grid grid-2" });
    grid.appendChild(renderInjuryAlertsCard());
    grid.appendChild(renderTrendingCard());
    grid.appendChild(renderStartSitTipsCard());
    grid.appendChild(renderWaiverCategoryCard());
    frag.appendChild(grid);

    const grid2 = el("div", { class: "grid grid-2" });
    grid2.appendChild(renderTradeTipsCard());
    grid2.appendChild(renderSellBuyCard());
    frag.appendChild(grid2);

    frag.appendChild(renderPositionStrengthCard());
    frag.appendChild(renderOutlookCard());
    return frag;
  }

  function matchupShortAnalysis(m) {
    const sum = (starters) => {
      const byPos = {};
      starters.forEach((s) => {
        const p = DATA.players[s.player_id];
        if (!p) return;
        byPos[p.position] = (byPos[p.position] || 0) + (s.actual_points || p.projection_week || 0);
      });
      return byPos;
    };
    const mine = sum(m.me.starters);
    const theirs = sum(m.opponent.starters);
    const diffs = POSITIONS.map((pos) => ({ pos, d: (mine[pos] || 0) - (theirs[pos] || 0) })).filter((x) => Math.abs(x.d) > 0.5);
    diffs.sort((a, b) => Math.abs(b.d) - Math.abs(a.d));
    const myEdges = diffs.filter((x) => x.d > 0).slice(0, 2);
    const oppEdges = diffs.filter((x) => x.d < 0).slice(0, 2);
    if (!myEdges.length && !oppEdges.length) return null;
    const parts = [];
    if (myEdges.length) parts.push(`Du bist stärker bei ${myEdges.map((e) => `${e.pos} (+${e.d.toFixed(1)})`).join(", ")}.`);
    if (oppEdges.length) parts.push(`Der Gegner ist stärker bei ${oppEdges.map((e) => `${e.pos} (${e.d.toFixed(1)})`).join(", ")}.`);
    return parts.join(" ");
  }

  function teamAvatar(team, size = "sm") {
    const wrap = el("div", { class: `avatar avatar-${size}` });
    const name = (team && team.team_name) || "?";
    const fallback = () => el("div", { class: "avatar-fallback", style: "background:var(--accent-gradient);" }, initialsOf(name));
    if (team && team.avatar_url) {
      const img = el("img", { class: "avatar-img", src: team.avatar_url, alt: "", loading: "lazy" });
      img.addEventListener("error", () => { wrap.innerHTML = ""; wrap.appendChild(fallback()); }, { once: true });
      wrap.appendChild(img);
    } else {
      wrap.appendChild(fallback());
    }
    return wrap;
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
    const myTeam = DATA.teams.find((t) => t.roster_id === m.me.roster_id);
    const oppTeam = DATA.teams.find((t) => t.roster_id === m.opponent.roster_id);
    const myScoreNode = el("div", { class: "hs-score num" }, "0.0");
    const oppScoreNode = el("div", { class: "hs-score num" }, "0.0");
    animateNumber(myScoreNode, m.me.projected_points || 0);
    animateNumber(oppScoreNode, m.opponent.projected_points || 0);
    const card = el("div", { class: "hero-matchup" }, [
      el("div", { class: "hero-matchup-head" }, [el("span", {}, `Matchup · Woche ${m.week}`), el("span", {}, DATA.league.name)]),
      el("div", { class: "hero-sides" }, [
        el("div", { class: "hero-side me" }, [
          el("div", { class: "hs-team" }, [teamAvatar(myTeam, "md"), el("div", { class: "hs-name" }, m.me.team_name)]),
          myScoreNode,
          el("div", { class: "hs-actual" }, `aktuell: ${fmt1(m.me.points)} Pkt.`),
        ]),
        el("div", { class: "hero-vs" }, "VS"),
        el("div", { class: "hero-side opp" }, [
          el("div", { class: "hs-team" }, [teamAvatar(oppTeam, "md"), el("div", { class: "hs-name" }, m.opponent.team_name)]),
          oppScoreNode,
          el("div", { class: "hs-actual" }, `aktuell: ${fmt1(m.opponent.points)} Pkt.`),
        ]),
      ]),
    ]);

    if (winProb !== null && winProb !== undefined) {
      const heroWinprob = el("div", { class: "hero-winprob" });
      const bar = el("div", { class: "winprob-bar" }, [el("div", { class: "fill", style: `width:${winProb}%` })]);
      heroWinprob.appendChild(bar);
      heroWinprob.appendChild(
        el("div", { class: "winprob-label" }, [
          el("span", {}, `${winProb}% Sieg-Chance (Simulation, 10.000 Durchläufe)`),
          el("span", {}, `${(100 - winProb).toFixed(1)}%`),
        ])
      );
      card.appendChild(heroWinprob);
    }

    const shortAnalysis = matchupShortAnalysis(m);
    if (shortAnalysis) {
      card.appendChild(el("div", { style: "font-size:12.5px;color:var(--text-muted);margin:10px 0 2px;padding:10px 12px;background:var(--accent-soft);border-radius:var(--radius-sm);" }, shortAnalysis));
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
        el("td", {}, playerTag(s.player_id)),
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
    const replacementsByPid = {};
    (DATA.waiver.injury_replacements || []).forEach((r) => (replacementsByPid[r.player_id] = r));

    const body = injured.length
      ? el(
          "div",
          { class: "mini-list" },
          injured.map((p) => {
            const st = statusInfo(p);
            const rep = replacementsByPid[p.id];
            return el("div", { class: "mini-item", style: "display:block;" }, [
              el("div", { style: "display:flex;justify-content:space-between;align-items:center;" }, [
                playerTag(p.id),
                el("span", { class: `status-dot ${st.cls}`, title: st.label }),
              ]),
              rep && rep.replacement_id
                ? el("div", { class: "reason" }, [`Ersatz (${rep.source === "bench" ? "Bank" : "Waiver"}): `, playerLink(rep.replacement_id)])
                : null,
            ].filter(Boolean));
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
              playerTag(p.id, `(${teamAvailability(p)})`),
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

  const WAIVER_CATEGORY_LABELS = {
    overall: "Beste Gesamt",
    lineup_upgrade: "Lineup-Upgrade",
    trending: "Trending",
    handcuffs: "Handcuffs",
    ir_stashes: "IR-Stashes",
    breakouts: "Breakouts",
    streaming: "Streaming",
  };
  let overviewWaiverCategory = "overall";

  function buildWaiverCategoryBody(key) {
    let items = [];
    if (key === "overall") {
      items = (DATA.waiver.top_overall || []).slice(0, 3).map((e) => ({ id: e.player_id, note: e.reasons[0] }));
    } else if (key === "lineup_upgrade") {
      items = (DATA.waiver.lineup_upgrades || []).slice(0, 3).map((e) => {
        const rep = DATA.players[e.replaces_player_id];
        return { id: e.player_id, note: `ersetzt ${rep ? rep.name : "?"} · +${e.delta} Pkt. diese Woche` };
      });
    } else if (key === "trending") {
      items = (DATA.waiver.trending || []).slice(0, 3).map((id) => {
        const p = DATA.players[id];
        return { id, note: `+${fmtInt(p.trending_add)} Adds (24h)` };
      });
    } else if (key === "handcuffs") {
      items = (DATA.waiver.handcuffs || []).slice(0, 3).map((e) => {
        const starter = DATA.players[e.handcuff_for_player_id];
        return { id: e.player_id, note: `Handcuff für ${starter ? starter.name : "?"}${e.is_mine ? " (dein Spieler)" : ""}` };
      });
    } else if (key === "ir_stashes") {
      items = (DATA.waiver.ir_stashes || []).slice(0, 3).map((e) => ({ id: e.player_id, note: `Status ${e.injury_status} · Ø ${fmt1(e.season_avg)} Pkt./Sp. vor der Verletzung` }));
    } else if (key === "breakouts") {
      items = (DATA.waiver.breakouts || []).slice(0, 3).map((id) => ({ id, note: "Junger Spieler mit steigender Nutzung" }));
    } else if (key === "streaming") {
      items = Object.entries(DATA.waiver.streaming || {}).map(([pos, e]) => ({
        id: e.player_id,
        note: `${pos}-Streamer diese Woche${e.opponent ? ` · vs ${e.opponent}` : ""}`,
      }));
    }
    if (!items.length) return el("div", { class: "empty-state" }, "Keine Daten für diese Kategorie.");
    return el(
      "div",
      { class: "mini-list" },
      items.map((it) => el("div", { class: "mini-item", style: "display:block;" }, [playerTag(it.id), el("div", { class: "reason" }, it.note)]))
    );
  }

  function renderWaiverCategoryCard() {
    const card = el("div", { class: "card" }, [
      el("div", { class: "card-title" }, ["Top Waiver-Picks", el("button", { class: "see-all", onclick: () => navigateTo("waiver") }, "Alle ansehen")]),
    ]);
    const tabRow = el("div", { class: "tab-row" });
    const bodyHost = el("div", {});

    function refreshTabs() {
      tabRow.innerHTML = "";
      Object.entries(WAIVER_CATEGORY_LABELS).forEach(([key, label]) => {
        tabRow.appendChild(
          el(
            "button",
            {
              class: `tab-pill ${overviewWaiverCategory === key ? "active" : ""}`,
              onclick: () => {
                overviewWaiverCategory = key;
                refreshTabs();
                refreshBody();
              },
            },
            label
          )
        );
      });
    }
    function refreshBody() {
      bodyHost.innerHTML = "";
      bodyHost.appendChild(buildWaiverCategoryBody(overviewWaiverCategory));
    }
    refreshTabs();
    refreshBody();
    card.appendChild(tabRow);
    card.appendChild(bodyHost);
    return card;
  }

  function renderSellBuyCard() {
    const sh = (DATA.sell_buy.sell_high || []).slice(0, 3);
    const bl = (DATA.sell_buy.buy_low || []).slice(0, 3);
    return el("div", { class: "card" }, [
      el("div", { class: "card-title" }, ["Sell High / Buy Low", el("button", { class: "see-all", onclick: () => navigateTo("sellbuy") }, "Alle ansehen")]),
      el("div", { class: "grid grid-2" }, [
        el("div", {}, [
          el("div", { style: "font-weight:700;font-size:11px;color:var(--status-bad);margin-bottom:8px;letter-spacing:0.03em;" }, "SELL HIGH"),
          sh.length
            ? el("div", { class: "mini-list" }, sh.map((e) => el("div", { class: "mini-item" }, [playerTag(e.player_id), el("span", { class: "reason" }, `${e.ppo_ratio}×`)])))
            : el("div", { class: "empty-state" }, "–"),
        ]),
        el("div", {}, [
          el("div", { style: "font-weight:700;font-size:11px;color:var(--status-good);margin-bottom:8px;letter-spacing:0.03em;" }, "BUY LOW"),
          bl.length
            ? el("div", { class: "mini-list" }, bl.map((e) => el("div", { class: "mini-item" }, [playerTag(e.player_id), el("span", { class: "reason" }, `${e.opp_ratio}× Usage`)])))
            : el("div", { class: "empty-state" }, "–"),
        ]),
      ]),
    ]);
  }

  function renderPositionStrengthCard() {
    const ps = DATA.position_strength;
    const myRosterId = DATA.me.roster_id;
    const rows = POSITIONS.map((pos) => {
      const list = ps[pos] || [];
      const mine = list.find((e) => e.roster_id === myRosterId);
      if (!mine) return null;
      const maxVal = Math.max(...list.map((e) => e.value), 0.01);
      const pct = Math.max(4, (mine.value / maxVal) * 100);
      const barColor = mine.rank <= 4 ? "var(--status-good)" : mine.rank <= 10 ? "var(--status-warn)" : "var(--status-bad)";
      return el("div", { style: "display:flex;align-items:center;gap:12px;margin-bottom:10px;" }, [
        posChip(pos),
        el("div", { style: "flex:1;background:var(--accent-soft);border-radius:6px;height:10px;overflow:hidden;" }, [
          el("div", { style: `width:${pct}%;height:100%;background:${barColor};border-radius:6px;` }),
        ]),
        el("div", { style: "font-size:12.5px;font-weight:700;width:50px;text-align:right;" }, `#${mine.rank}/${list.length}`),
      ]);
    }).filter(Boolean);
    return el("div", { class: "card" }, [el("div", { class: "card-title" }, "Positionsstärke im Liga-Vergleich"), ...rows]);
  }

  function renderOutlookCard() {
    const rest = (DATA.planner.remaining_schedule || []).slice(0, 4);
    const powerByRoster = {};
    (DATA.league_feed.power_ranking || []).forEach((e) => (powerByRoster[e.roster_id] = e));
    const rows = rest.map((g) => {
      const pr = g.opponent_roster_id != null ? powerByRoster[g.opponent_roster_id] : null;
      const cls = pr ? (pr.power_rank <= 5 ? "status-bad" : pr.power_rank >= 10 ? "status-good" : "status-warn") : "";
      const label = pr ? (pr.power_rank <= 5 ? "Schwer" : pr.power_rank >= 10 ? "Leicht" : "Mittel") : "–";
      return el("div", { style: "display:flex;justify-content:space-between;align-items:center;padding:9px 0;border-top:1px solid var(--card-border);" }, [
        el("div", {}, [el("span", { style: "font-weight:700;" }, `W${g.week}`), ` · ${g.opponent_team_name || "–"}`]),
        el("div", { style: "display:flex;align-items:center;gap:6px;" }, [cls ? el("span", { class: `status-dot ${cls}` }) : null, el("span", { style: "font-size:12px;color:var(--text-muted);" }, label)].filter(Boolean)),
      ]);
    });
    return el("div", { class: "card" }, [
      el("div", { class: "card-title" }, ["Ausblick", el("button", { class: "see-all", onclick: () => navigateTo("planner") }, "Alle ansehen")]),
      rows.length ? el("div", {}, rows) : el("div", { class: "empty-state" }, "Kein Restprogramm verfügbar."),
    ]);
  }

  function renderStartSitTipsCard() {
    const decisions = (DATA.start_sit.decisions || []).slice(0, 3);
    const body = decisions.length
      ? el(
          "div",
          { class: "mini-list" },
          decisions.map((d) => {
            const rec = DATA.players[d.recommended_player_id];
            const cur = d.current_player_id ? DATA.players[d.current_player_id] : null;
            return el("div", { class: "mini-item", style: "display:block;" }, [
              el("div", {}, [
                cur ? playerLink(cur.id) : "–",
                " → ",
                el("strong", {}, playerLink(rec.id)),
              ]),
              el("div", { class: "reason" }, `${d.slot} · ${d.delta >= 0 ? "+" : ""}${d.delta} Pkt. erwartet`),
            ]);
          })
        )
      : el("div", { class: "empty-state" }, "Dein Lineup ist bereits optimal gesetzt.");
    return el("div", { class: "card" }, [
      el("div", { class: "card-title" }, ["Start/Sit-Hinweise", el("button", { class: "see-all", onclick: () => navigateTo("startsit") }, "Alle ansehen")]),
      body,
    ]);
  }

  function renderTradeTipsCard() {
    // Dieselbe Quelle wie der Trade-Finder-Tab (filterAndSortProposals),
    // damit hier nie andere Top-Vorschläge/Zahlen stehen als dort.
    const shown = filterAndSortProposals().slice(0, 3);
    const body = shown.length
      ? el(
          "div",
          { class: "mini-list" },
          shown.map((p) => {
            const giveNames = p.give_player_ids.map((pid) => DATA.players[pid]?.name).join(" + ");
            const getNames = p.get_player_ids.map((pid) => DATA.players[pid]?.name).join(" + ");
            return el("div", { class: "mini-item", style: "display:block;" }, [
              el("div", {}, `${giveNames} ⇄ ${getNames}`),
              el("div", { class: "reason" }, `mit ${p.team_name} · ${p.lineup_delta >= 0 ? "+" : ""}${p.lineup_delta} Pkt./Woche diese Woche · ${p.relaxation_label}`),
            ]);
          })
        )
      : el("div", { class: "empty-state" }, "Aktuell kein passender Vorschlag gefunden.");
    return el("div", { class: "card" }, [
      el("div", { class: "card-title" }, ["Top Trade-Vorschläge", el("button", { class: "see-all", onclick: () => navigateTo("tradefinder") }, "Alle ansehen")]),
      body,
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
        el("td", {}, [slots ? el("span", { class: "slot-tag" }, slotByPid[pid]) : null, playerTag(pid)].filter(Boolean)),
        el("td", {}, posChip(p.position)),
        el("td", {}, p.team || "–"),
        el("td", {}, p.bye_week ? `W${p.bye_week}` : "–"),
        el("td", {}, [el("span", { class: `status-dot ${st.cls}` }), " ", st.label]),
        el("td", {}, fmt1(p.projection_week)),
        el("td", {}, fmt1(p.avg_last3)),
        el("td", {}, fmt1(p.season_avg)),
        el("td", {}, fmtTradeValue(p.trade_value)),
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

  // ---------- Alle Spieler ----------
  const POSITIONS = ["QB", "RB", "WR", "TE", "K", "DEF"];
  const playersView = {
    search: "",
    positions: new Set(),
    availability: "all", // all | free | rostered
    injuredOnly: false,
    favoritesOnly: false,
    sortKey: "season_total",
    sortDir: "desc",
  };

  // ---------- Vergleichsmodus (zwei Spieler nebeneinander) ----------
  const compareState = { visible: false, a: null, b: null };
  const COMPARE_STATS = [
    { key: "trade_value", label: "Trade-Wert", fmt: fmtTradeValue },
    { key: "season_avg", label: "Ø Saison", fmt: fmt1 },
    { key: "avg_last3", label: "Ø letzte 3", fmt: fmt1 },
    { key: "projection_week", label: "Projektion", fmt: fmt1 },
    { key: "target_share", label: "Target Share", fmt: (v) => (v != null ? `${v}%` : null) },
    { key: "snap_pct", label: "Snap %", fmt: (v) => (v != null ? `${v}%` : null) },
    { key: "touches_pg", label: "Touches/Sp.", fmt: fmt1 },
    { key: "redzone_pg", label: "Red-Zone/Sp.", fmt: fmt1 },
    { key: "games_played", label: "Spiele", fmt: (v) => v },
  ];

  function buildComparePicker(slot) {
    const input = el("input", {
      type: "text",
      placeholder: "Spieler suchen…",
      style: "width:100%;padding:8px 10px;border-radius:8px;border:1px solid var(--card-border);background:var(--bg);color:var(--text);",
    });
    const results = el("div", { style: "margin-top:8px;max-height:200px;overflow-y:auto;display:flex;flex-direction:column;gap:4px;" });
    input.addEventListener("input", () => {
      const q = input.value.trim().toLowerCase();
      results.innerHTML = "";
      if (q.length < 2) return;
      Object.values(DATA.players)
        .filter((p) => p.name.toLowerCase().includes(q))
        .slice(0, 8)
        .forEach((p) => {
          results.appendChild(
            el(
              "div",
              {
                class: "player-card",
                style: "margin-bottom:0;",
                onclick: () => {
                  compareState[slot] = p.id;
                  refreshCompareCardInPlace();
                },
              },
              [playerAvatar(p, "sm"), el("div", {}, [el("div", { class: "pc-name" }, p.name), el("div", { class: "pc-meta" }, `${p.position} · ${p.team || "FA"}`)])]
            )
          );
        });
    });
    return el("div", { class: "compare-pick" }, [icon("search", { style: "width:20px;height:20px;" }), el("div", { style: "margin:6px 0;" }, "Spieler auswählen"), input, results]);
  }

  function buildCompareColumn(pid, otherPid) {
    const p = DATA.players[pid];
    const other = otherPid ? DATA.players[otherPid] : null;
    const st = statusInfo(p);
    return el("div", { class: "compare-col" }, [
      el("div", { style: "display:flex;align-items:center;gap:12px;margin-bottom:4px;" }, [
        playerAvatar(p, "md"),
        el("div", {}, [
          el("div", { style: "font-weight:800;font-size:15px;" }, playerLink(pid)),
          el("div", { class: "pc-meta" }, [posChip(p.position), ` ${p.team || "FA"}`]),
        ]),
        el(
          "button",
          { class: "icon-btn", style: "margin-left:auto;", title: "Anderen Spieler wählen", onclick: () => { compareState[pid === compareState.a ? "a" : "b"] = null; refreshCompareCardInPlace(); } },
          icon("x")
        ),
      ]),
      el("div", { style: "margin:6px 0;" }, [el("span", { class: `status-dot ${st.cls}` }), " ", st.label]),
      ...COMPARE_STATS.map((s) => {
        const val = p[s.key];
        const fv = s.fmt(val);
        const otherVal = other ? other[s.key] : null;
        const isBetter = fv != null && otherVal != null && val != null && Number(val) > Number(otherVal);
        return el("div", { class: "compare-row" }, [
          el("span", { class: "cr-label" }, s.label),
          el("span", { class: `cr-val${isBetter ? " better" : ""}` }, fv != null ? fv : el("span", { class: "null-value" }, "kein Wert")),
        ]);
      }),
    ]);
  }

  function renderCompareCard() {
    const card = el("div", { class: "card" }, [el("div", { class: "card-title" }, "Spieler-Vergleich")]);
    const grid = el("div", { class: "compare-grid" }, [
      compareState.a ? buildCompareColumn(compareState.a, compareState.b) : buildComparePicker("a"),
      compareState.b ? buildCompareColumn(compareState.b, compareState.a) : buildComparePicker("b"),
    ]);
    card.appendChild(grid);
    card.id = "compare-card-host";
    return card;
  }

  function refreshCompareCardInPlace() {
    const old = $("#compare-card-host");
    if (!old) return;
    old.replaceWith(renderCompareCard());
  }

  function renderPlayers() {
    const frag = el("div", {});
    frag.appendChild(renderHeader());
    frag.appendChild(el("div", { class: "card-title", style: "margin-bottom:0;" }, "Alle Spieler"));

    const filterBar = el("div", { class: "card", style: "display:flex;gap:10px;flex-wrap:wrap;align-items:center;" });
    const searchInput = el("input", {
      type: "text",
      placeholder: "Spieler suchen…",
      value: playersView.search,
      style: "flex:1;min-width:160px;padding:8px 10px;border-radius:8px;border:1px solid var(--card-border);background:var(--bg);color:var(--text);",
      oninput: (e) => {
        playersView.search = e.target.value;
        refreshTable();
      },
    });
    filterBar.appendChild(searchInput);

    const posWrap = el("div", { style: "display:flex;gap:6px;flex-wrap:wrap;" });
    POSITIONS.forEach((pos) => {
      const active = playersView.positions.has(pos);
      const btn = el(
        "button",
        {
          class: "btn",
          style: active ? "background:var(--accent);border-color:var(--accent);color:#fff;" : "",
          onclick: () => {
            if (playersView.positions.has(pos)) playersView.positions.delete(pos);
            else playersView.positions.add(pos);
            renderFilterBar();
            refreshTable();
          },
        },
        pos
      );
      posWrap.appendChild(btn);
    });
    filterBar.appendChild(posWrap);

    const availSelect = el(
      "select",
      {
        style: "padding:8px 10px;border-radius:8px;border:1px solid var(--card-border);background:var(--bg);color:var(--text);",
        onchange: (e) => {
          playersView.availability = e.target.value;
          refreshTable();
        },
      },
      [
        el("option", { value: "all", selected: playersView.availability === "all" ? "selected" : null }, "Alle"),
        el("option", { value: "free", selected: playersView.availability === "free" ? "selected" : null }, "Nur verfügbar"),
        el("option", { value: "rostered", selected: playersView.availability === "rostered" ? "selected" : null }, "Nur vergeben"),
      ]
    );
    filterBar.appendChild(availSelect);

    const injuryLabel = el("label", { style: "display:flex;align-items:center;gap:6px;font-size:12.5px;color:var(--text-muted);" }, [
      el("input", {
        type: "checkbox",
        checked: playersView.injuredOnly ? "checked" : null,
        onchange: (e) => {
          playersView.injuredOnly = e.target.checked;
          refreshTable();
        },
      }),
      "nur verletzt/fraglich",
    ]);
    filterBar.appendChild(injuryLabel);

    const favLabel = el("label", { style: "display:flex;align-items:center;gap:6px;font-size:12.5px;color:var(--text-muted);" }, [
      el("input", {
        type: "checkbox",
        checked: playersView.favoritesOnly ? "checked" : null,
        onchange: (e) => {
          playersView.favoritesOnly = e.target.checked;
          refreshTable();
        },
      }),
      icon("star", { style: "width:12px;height:12px;" }),
      " nur Favoriten",
    ]);
    filterBar.appendChild(favLabel);

    const compareHost = el("div", {});
    const compareToggleBtn = el(
      "button",
      {
        class: "btn",
        onclick: () => {
          compareState.visible = !compareState.visible;
          compareToggleBtn.style.cssText = compareState.visible ? "background:var(--accent);border-color:var(--accent);color:#fff;" : "";
          refreshCompareHost();
        },
      },
      [icon("shuffle", { style: "width:13px;height:13px;" }), "Vergleichen"]
    );
    filterBar.appendChild(compareToggleBtn);

    frag.appendChild(filterBar);
    frag.appendChild(compareHost);
    function refreshCompareHost() {
      compareHost.innerHTML = "";
      if (compareState.visible) compareHost.appendChild(renderCompareCard());
    }
    refreshCompareHost();

    const tableHost = el("div", {});
    frag.appendChild(tableHost);

    function renderFilterBar() {
      // Positions-Buttons neu zeichnen (aktiver Zustand)
      const newBar = renderPlayers();
      frag.replaceWith(newBar);
      refreshIcons();
    }

    function refreshTable() {
      tableHost.innerHTML = "";
      tableHost.appendChild(buildPlayersTable());
      refreshIcons();
    }

    tableHost.appendChild(buildPlayersTable());
    return frag;
  }

  const PLAYERS_COLUMNS = [
    { key: "name", label: "Spieler", sortable: false },
    { key: "position", label: "Pos", sortable: true },
    { key: "team", label: "Team", sortable: true },
    { key: "avail", label: "Verfügbar", sortable: false },
    { key: "season_total", label: "Punkte", sortable: true },
    { key: "season_avg", label: "Ø", sortable: true },
    { key: "targets_pg", label: "Targets/Sp.", sortable: true },
    { key: "target_share", label: "Tgt-Share", sortable: true },
    { key: "snap_pct", label: "Snap %", sortable: true },
    { key: "touches_pg", label: "Touches/Sp.", sortable: true },
    { key: "redzone_pg", label: "RZ/Sp.", sortable: true },
    { key: "projection_week", label: "Proj.", sortable: true },
    { key: "trade_value", label: "Trade-Wert", sortable: true },
  ];

  function buildPlayersTable() {
    let list = Object.values(DATA.players);

    if (playersView.search.trim()) {
      const q = playersView.search.trim().toLowerCase();
      list = list.filter((p) => p.name.toLowerCase().includes(q));
    }
    if (playersView.positions.size) {
      list = list.filter((p) => playersView.positions.has(p.position));
    }
    if (playersView.availability === "free") list = list.filter((p) => !p.fantasy_team);
    if (playersView.availability === "rostered") list = list.filter((p) => p.fantasy_team);
    if (playersView.injuredOnly) list = list.filter((p) => p.injury_status);
    if (playersView.favoritesOnly) list = list.filter((p) => isFavorite(p.id));

    const { sortKey, sortDir } = playersView;
    list.sort((a, b) => {
      let av = a[sortKey];
      let bv = b[sortKey];
      if (av === null || av === undefined) av = -Infinity;
      if (bv === null || bv === undefined) bv = -Infinity;
      if (typeof av === "string") return sortDir === "asc" ? av.localeCompare(bv) : bv.localeCompare(av);
      return sortDir === "asc" ? av - bv : bv - av;
    });

    const total = list.length;
    list = list.slice(0, 200);

    const headRow = el(
      "tr",
      {},
      PLAYERS_COLUMNS.map((col) =>
        el(
          "th",
          {
            class: col.sortable && playersView.sortKey === col.key ? "sorted" : "",
            onclick: col.sortable
              ? () => {
                  if (playersView.sortKey === col.key) {
                    playersView.sortDir = playersView.sortDir === "asc" ? "desc" : "asc";
                  } else {
                    playersView.sortKey = col.key;
                    playersView.sortDir = "desc";
                  }
                  render();
                }
              : null,
          },
          col.label + (col.sortable && playersView.sortKey === col.key ? (playersView.sortDir === "asc" ? " ▲" : " ▼") : "")
        )
      )
    );

    const rows = list.map((p) => {
      const st = statusInfo(p);
      return el("tr", {}, [
        el("td", {}, [isFavorite(p.id) ? icon("star", { fill: "#f5b800", stroke: "#f5b800", style: "width:13px;height:13px;margin-right:4px;vertical-align:middle;" }) : null, playerTag(p.id)].filter(Boolean)),
        el("td", {}, p.position),
        el("td", {}, p.team || "–"),
        el("td", {}, [el("span", { class: `status-dot ${st.cls}` }), " ", p.fantasy_team ? p.fantasy_team.team_name : "Frei"]),
        el("td", {}, fmt1(p.season_total)),
        el("td", {}, fmt1(p.season_avg)),
        el("td", {}, fmt1(p.targets_pg)),
        el("td", {}, p.target_share != null ? `${p.target_share}%` : "–"),
        el("td", {}, p.snap_pct ? `${p.snap_pct}%` : "–"),
        el("td", {}, fmt1(p.touches_pg)),
        el("td", {}, fmt1(p.redzone_pg)),
        el("td", {}, fmt1(p.projection_week)),
        el("td", {}, fmtTradeValue(p.trade_value)),
      ]);
    });

    const wrap = el("div", { class: "card table-wrap" }, [
      el("div", { style: "font-size:12px;color:var(--text-muted);margin-bottom:8px;" }, `${total} Spieler gefunden${total > 200 ? " (zeige erste 200)" : ""}`),
      rows.length
        ? el("table", { class: "data-table" }, [el("thead", {}, headRow), el("tbody", {}, rows)])
        : el("div", { class: "empty-state" }, "Keine Spieler gefunden."),
    ]);
    return wrap;
  }

  // ---------- Lineup-Optimizer (Port von fantasy/startsit.py, für Trade-Analyzer) ----------
  const HARD_OUT_STATUSES = new Set(["Out", "IR", "NA", "Sus", "PUP", "COV", "DNR"]);
  const SOFT_INJURY_MULTIPLIER = { Doubtful: 0.5, Questionable: 0.9 };

  function effectiveProjection(p, currentWeek) {
    if (!p) return 0;
    if (p.bye_week === currentWeek) return 0;
    if (HARD_OUT_STATUSES.has(p.injury_status)) return 0;
    const mult = SOFT_INJURY_MULTIPLIER[p.injury_status] || 1;
    const factor = p.matchup_factor || 1;
    return (p.projection_week || 0) * mult * factor;
  }

  function bestLineupPoints(playerIds, rosterPositions, currentWeek) {
    const byPos = { QB: [], RB: [], WR: [], TE: [], K: [], DEF: [] };
    playerIds.forEach((pid) => {
      const p = DATA.players[pid];
      if (!p || !byPos[p.position]) return;
      if (p.bye_week === currentWeek || HARD_OUT_STATUSES.has(p.injury_status)) return;
      byPos[p.position].push({ id: pid, eff: effectiveProjection(p, currentWeek) });
    });
    Object.values(byPos).forEach((l) => l.sort((a, b) => b.eff - a.eff));

    const used = new Set();
    function take(pos, n) {
      const out = [];
      for (const item of byPos[pos]) {
        if (out.length >= n) break;
        if (used.has(item.id)) continue;
        out.push(item);
        used.add(item.id);
      }
      return out;
    }
    const counts = {};
    rosterPositions.forEach((l) => (counts[l] = (counts[l] || 0) + 1));

    let total = 0;
    ["QB", "RB", "WR", "TE", "K", "DEF"].forEach((pos) => {
      total += take(pos, counts[pos] || 0).reduce((s, i) => s + i.eff, 0);
    });

    const flexNeeded = counts["FLEX"] || 0;
    const flexCandidates = [];
    ["RB", "WR", "TE"].forEach((pos) => byPos[pos].forEach((item) => { if (!used.has(item.id)) flexCandidates.push(item); }));
    flexCandidates.sort((a, b) => b.eff - a.eff);
    total += flexCandidates.slice(0, flexNeeded).reduce((s, i) => s + i.eff, 0);

    return Math.round(total * 10) / 10;
  }

  // Wie bestLineupPoints(), aber gibt die tatsächliche Slot-Zuordnung
  // zurück (welcher Spieler steht auf welchem Slot) statt nur die Summe -
  // für die Slot-für-Slot-Anzeige in Trade-Analyzer und Trade-Finder-Karten.
  function buildBestLineupAssignment(playerIds, rosterPositions, currentWeek) {
    const byPos = { QB: [], RB: [], WR: [], TE: [], K: [], DEF: [] };
    playerIds.forEach((pid) => {
      const p = DATA.players[pid];
      if (!p || !byPos[p.position]) return;
      if (p.bye_week === currentWeek || HARD_OUT_STATUSES.has(p.injury_status)) return;
      byPos[p.position].push({ id: pid, eff: effectiveProjection(p, currentWeek) });
    });
    Object.values(byPos).forEach((l) => l.sort((a, b) => b.eff - a.eff));

    const used = new Set();
    function take(pos, n) {
      const out = [];
      for (const item of byPos[pos]) {
        if (out.length >= n) break;
        if (used.has(item.id)) continue;
        out.push(item);
        used.add(item.id);
      }
      return out;
    }
    const counts = {};
    rosterPositions.forEach((l) => (counts[l] = (counts[l] || 0) + 1));
    const poolsByLabel = {};
    ["QB", "RB", "WR", "TE", "K", "DEF"].forEach((pos) => { poolsByLabel[pos] = take(pos, counts[pos] || 0); });

    const flexNeeded = counts["FLEX"] || 0;
    const flexCandidates = [];
    ["RB", "WR", "TE"].forEach((pos) => byPos[pos].forEach((item) => { if (!used.has(item.id)) flexCandidates.push(item); }));
    flexCandidates.sort((a, b) => b.eff - a.eff);
    const flex = flexCandidates.slice(0, flexNeeded);
    flex.forEach((f) => used.add(f.id));
    poolsByLabel["FLEX"] = flex;

    return rosterPositions.map((label) => {
      const bucket = poolsByLabel[label] || [];
      return bucket.length ? bucket.shift() : null;
    });
  }

  // Nur die Slots, die sich zwischen zwei Aufstellungen unterscheiden -
  // für eine kompakte "Was ändert sich" statt einer vollen 10-Zeilen-Tabelle.
  function lineupSlotChanges(beforeIds, afterIds, rosterPositions, currentWeek) {
    const before = buildBestLineupAssignment(beforeIds, rosterPositions, currentWeek);
    const after = buildBestLineupAssignment(afterIds, rosterPositions, currentWeek);
    const changes = [];
    rosterPositions.forEach((slot, i) => {
      const outItem = before[i];
      const inItem = after[i];
      if ((outItem?.id || null) !== (inItem?.id || null)) {
        changes.push({ slot, outId: outItem?.id || null, inId: inItem?.id || null });
      }
    });
    return changes;
  }

  // ---------- Trade-Block (localStorage, geräteweit) ----------
  const TRADE_BLOCK_KEY = "tradeBlock";
  function loadTradeBlock() {
    try {
      const raw = localStorage.getItem(TRADE_BLOCK_KEY);
      if (raw) {
        const parsed = JSON.parse(raw);
        return { give: parsed.give || [], untouchable: parsed.untouchable || [], target: parsed.target || [] };
      }
    } catch (e) { /* ignore */ }
    return { give: [], untouchable: [], target: [] };
  }
  const tradeBlock = loadTradeBlock();
  function saveTradeBlock() {
    try { localStorage.setItem(TRADE_BLOCK_KEY, JSON.stringify(tradeBlock)); } catch (e) { /* ignore */ }
  }
  function tradeBlockStatus(pid) {
    if (tradeBlock.give.includes(pid)) return "give";
    if (tradeBlock.untouchable.includes(pid)) return "untouchable";
    if (tradeBlock.target.includes(pid)) return "target";
    return null;
  }
  function setTradeBlockStatus(pid, status) {
    tradeBlock.give = tradeBlock.give.filter((x) => x !== pid);
    tradeBlock.untouchable = tradeBlock.untouchable.filter((x) => x !== pid);
    tradeBlock.target = tradeBlock.target.filter((x) => x !== pid);
    if (status) tradeBlock[status].push(pid);
    saveTradeBlock();
  }
  function exportTradeBlock() {
    const blob = new Blob([JSON.stringify(tradeBlock, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "trade-block.json";
    a.click();
    URL.revokeObjectURL(url);
  }
  function importTradeBlock(file, onDone) {
    const reader = new FileReader();
    reader.onload = () => {
      try {
        const parsed = JSON.parse(reader.result);
        tradeBlock.give = parsed.give || [];
        tradeBlock.untouchable = parsed.untouchable || [];
        tradeBlock.target = parsed.target || [];
        saveTradeBlock();
        onDone();
      } catch (e) {
        alert("Datei konnte nicht gelesen werden.");
      }
    };
    reader.readAsText(file);
  }

  // ---------- Favoriten & Notizen (localStorage, geräteweit) ----------
  const FAVORITES_KEY = "favoritesAndNotes";
  function loadFavorites() {
    try {
      const raw = localStorage.getItem(FAVORITES_KEY);
      if (raw) {
        const parsed = JSON.parse(raw);
        return { favorites: parsed.favorites || [], notes: parsed.notes || {} };
      }
    } catch (e) { /* ignore */ }
    return { favorites: [], notes: {} };
  }
  const favoritesState = loadFavorites();
  function saveFavorites() {
    try { localStorage.setItem(FAVORITES_KEY, JSON.stringify(favoritesState)); } catch (e) { /* ignore */ }
  }
  function isFavorite(pid) { return favoritesState.favorites.includes(pid); }
  function toggleFavorite(pid) {
    if (isFavorite(pid)) favoritesState.favorites = favoritesState.favorites.filter((x) => x !== pid);
    else favoritesState.favorites.push(pid);
    saveFavorites();
  }
  function getNote(pid) { return favoritesState.notes[pid] || ""; }
  function setNote(pid, text) {
    if (text && text.trim()) favoritesState.notes[pid] = text;
    else delete favoritesState.notes[pid];
    saveFavorites();
  }

  function combosOf(arr, size) {
    const out = [];
    const chosen = [];
    (function rec(start) {
      if (chosen.length === size) { out.push(chosen.slice()); return; }
      for (let i = start; i < arr.length; i++) {
        chosen.push(arr[i]);
        rec(i + 1);
        chosen.pop();
      }
    })(0);
    return out;
  }

  // Für client-seitiges Trade-Block-Matching (1-3 markierte "Abzugeben"-
  // Spieler gegen Kombinationen aus 1-2 Spielern jedes anderen Teams).
  function findTradeBlockMatches() {
    const giveIds = tradeBlock.give.slice(0, 3);
    if (!giveIds.length) return [];
    const v1 = giveIds.reduce((s, id) => s + (DATA.players[id]?.trade_value || 0), 0);
    if (!v1) return [];
    const myRosterId = DATA.me.roster_id;
    const weaknessMatrix = DATA.trade_finder.weakness_matrix || {};
    const myWeakness = weaknessMatrix[String(myRosterId)] || {};
    const results = [];
    Object.entries(DATA.trade_finder.team_pools || {}).forEach(([ridStr, pool]) => {
      const rid = Number(ridStr);
      if (rid === myRosterId) return;
      const theirWeakness = weaknessMatrix[ridStr] || {};
      const candidates = pool.filter((p) => !tradeBlock.untouchable.includes(p.player_id) && !giveIds.includes(p.player_id));
      [1, 2].forEach((size) => {
        combosOf(candidates, size).forEach((combo) => {
          const v2 = combo.reduce((s, p) => s + (p.trade_value || 0), 0);
          if (!v2) return;
          const diffPct = Math.abs(v1 - v2) / Math.max(v1, v2);
          if (diffPct > 0.25) return;
          const myNeedFit = combo.reduce((s, p) => s + (myWeakness[p.position] || 0), 0);
          const theirNeedFit = giveIds.reduce((s, id) => s + (theirWeakness[DATA.players[id]?.position] || 0), 0);
          const team = DATA.teams.find((t) => t.roster_id === rid);
          results.push({ rosterId: rid, teamName: team ? team.team_name : `Team ${rid}`, getIds: combo.map((p) => p.player_id), diffPct, priority: myNeedFit * 2 + theirNeedFit });
        });
      });
    });
    results.sort((a, b) => b.priority - a.priority);
    return results.slice(0, 8);
  }

  // ---------- Trade-Analyzer ----------
  const tradeAnalyzer = { give: [], get: [], giveSearch: "", getSearch: "" };

  function renderTradeAnalyzer() {
    const frag = el("div", {});
    frag.appendChild(renderHeader());
    frag.appendChild(el("div", { class: "card-title", style: "margin-bottom:0;" }, "Trade-Analyzer"));
    frag.appendChild(
      el("div", { class: "empty-state", style: "margin:4px 0 14px;" }, "Wähle Spieler aus deinem Kader und von anderen Teams, um einen Trade zu bewerten.")
    );

    const columns = el("div", { class: "grid grid-2" });
    const verdictHost = el("div", {});

    function refreshVerdict() {
      verdictHost.innerHTML = "";
      verdictHost.appendChild(buildAnalyzerVerdict());
    }

    function myCandidates() {
      const mine = [
        ...DATA.my_roster.slots.map((s) => s.player_id),
        ...DATA.my_roster.bench,
        ...DATA.my_roster.reserve,
      ];
      return mine.map((id) => DATA.players[id]).filter((p) => p && !tradeAnalyzer.give.includes(p.id));
    }
    function otherCandidates() {
      return Object.values(DATA.players).filter(
        (p) => p.fantasy_team && p.fantasy_team.roster_id !== DATA.me.roster_id && !tradeAnalyzer.get.includes(p.id)
      );
    }

    columns.appendChild(buildAnalyzerSide("give", "Du gibst ab", myCandidates, refreshVerdict));
    columns.appendChild(buildAnalyzerSide("get", "Du bekommst", otherCandidates, refreshVerdict));
    frag.appendChild(columns);
    frag.appendChild(verdictHost);
    refreshVerdict();

    return frag;
  }

  function buildAnalyzerSide(side, title, candidatesFn, onChange) {
    const card = el("div", { class: "card" });
    card.appendChild(el("div", { class: "card-title" }, title));

    const input = el("input", {
      type: "text",
      placeholder: "Spieler hinzufügen…",
      style:
        "width:100%;padding:8px 10px;border-radius:8px;border:1px solid var(--card-border);background:var(--bg);color:var(--text);margin-bottom:8px;",
    });
    input.value = tradeAnalyzer[side + "Search"] || "";

    const suggestionsHost = el("div", {});
    const selectedHost = el("div", { class: "mini-list" });
    const totalHost = el("div", { style: "text-align:right;font-weight:800;margin-top:8px;font-size:13px;" });

    function refreshSuggestions() {
      suggestionsHost.innerHTML = "";
      const search = (tradeAnalyzer[side + "Search"] || "").trim();
      if (!search) return;
      const q = search.toLowerCase();
      const filtered = candidatesFn().filter((p) => p.name.toLowerCase().includes(q)).slice(0, 8);
      if (!filtered.length) {
        suggestionsHost.appendChild(el("div", { class: "empty-state" }, "Keine Treffer."));
        return;
      }
      suggestionsHost.appendChild(
        el(
          "div",
          { style: "border:1px solid var(--card-border);border-radius:8px;margin-bottom:10px;overflow:hidden;" },
          filtered.map((p) =>
            el(
              "div",
              {
                style: "padding:8px 10px;cursor:pointer;border-top:1px solid var(--card-border);",
                onclick: () => {
                  tradeAnalyzer[side].push(p.id);
                  tradeAnalyzer[side + "Search"] = "";
                  input.value = "";
                  refreshSuggestions();
                  refreshSelected();
                  onChange();
                },
              },
              [playerAvatar(p, "sm"), posChip(p.position), ` ${p.name} `, el("span", { style: "color:var(--text-muted);font-size:11px;" }, p.fantasy_team ? `(${p.fantasy_team.team_name})` : "Frei")]
            )
          )
        )
      );
    }

    function refreshSelected() {
      selectedHost.innerHTML = "";
      const ids = tradeAnalyzer[side];
      if (!ids.length) {
        selectedHost.appendChild(el("div", { class: "empty-state" }, "Noch keine Spieler ausgewählt."));
      } else {
        ids.forEach((id) => {
          const p = DATA.players[id];
          if (!p) return;
          selectedHost.appendChild(
            el("div", { class: "mini-item" }, [
              playerTag(p.id),
              el("div", { style: "display:flex;align-items:center;gap:8px;" }, [
                el("span", {}, fmtTradeValue(p.trade_value)),
                el(
                  "button",
                  {
                    class: "btn",
                    style: "padding:2px 8px;",
                    onclick: () => {
                      tradeAnalyzer[side] = tradeAnalyzer[side].filter((x) => x !== id);
                      refreshSuggestions();
                      refreshSelected();
                      onChange();
                    },
                  },
                  icon("x", { style: "width:12px;height:12px;" })
                ),
              ]),
            ])
          );
        });
      }
      const total = ids.reduce((s, id) => s + (DATA.players[id]?.trade_value || 0), 0);
      totalHost.textContent = `Summe: ${fmtInt(total)}`;
    }

    input.addEventListener("input", (e) => {
      tradeAnalyzer[side + "Search"] = e.target.value;
      refreshSuggestions();
    });

    card.appendChild(input);
    card.appendChild(suggestionsHost);
    card.appendChild(selectedHost);
    card.appendChild(totalHost);
    refreshSuggestions();
    refreshSelected();
    return card;
  }

  function buildAnalyzerVerdict() {
    const giveIds = tradeAnalyzer.give;
    const getIds = tradeAnalyzer.get;
    if (!giveIds.length && !getIds.length) {
      return el("div", { class: "card empty-state" }, "Wähle Spieler auf beiden Seiten, um den Trade zu bewerten.");
    }

    const giveValue = giveIds.reduce((s, id) => s + (DATA.players[id]?.trade_value || 0), 0);
    const getValue = getIds.reduce((s, id) => s + (DATA.players[id]?.trade_value || 0), 0);
    const diffPct = giveValue || getValue ? (getValue - giveValue) / Math.max(giveValue, getValue, 1) : 0;

    let verdict = "Fair";
    let verdictColor = "var(--text-muted)";
    if (diffPct > 0.1) {
      verdict = "Gewinn für dich";
      verdictColor = "var(--status-good)";
    } else if (diffPct < -0.1) {
      verdict = "Verlust für dich";
      verdictColor = "var(--status-bad)";
    }

    const currentWeek = DATA.league.week;
    const rosterPositions = DATA.league.roster_positions;
    const myCurrentIds = [...DATA.my_roster.slots.map((s) => s.player_id), ...DATA.my_roster.bench];
    const hypotheticalIds = myCurrentIds.filter((id) => !giveIds.includes(id)).concat(getIds.filter((id) => !myCurrentIds.includes(id)));

    const beforePts = bestLineupPoints(myCurrentIds, rosterPositions, currentWeek);
    const afterPts = bestLineupPoints(hypotheticalIds, rosterPositions, currentWeek);
    const ptsDelta = Math.round((afterPts - beforePts) * 10) / 10;

    const slotChanges = lineupSlotChanges(myCurrentIds, hypotheticalIds, rosterPositions, currentWeek);
    const slotRows = slotChanges.length
      ? slotChanges.map((c) =>
          el("div", { style: "display:flex;align-items:center;gap:10px;padding:6px 0;border-top:1px solid var(--card-border);" }, [
            el("span", { class: "slot-tag", style: "width:auto;" }, c.slot),
            c.outId ? el("span", { style: "color:var(--status-bad);" }, playerLink(c.outId)) : el("span", { class: "null-value" }, "leer"),
            icon("arrow-right", { style: "width:13px;height:13px;color:var(--text-faint);" }),
            c.inId ? el("span", { style: "color:var(--status-good);font-weight:700;" }, playerLink(c.inId)) : el("span", { class: "null-value" }, "leer"),
          ])
        )
      : [el("div", { class: "empty-state" }, "Keine Slot-Änderungen - dieselben Spieler starten weiter.")];

    return el("div", { class: "card" }, [
      el("div", { class: "card-title" }, "Urteil"),
      el("div", { style: `font-size:20px;font-weight:800;color:${verdictColor};` }, verdict),
      el(
        "div",
        { style: "color:var(--text-muted);font-size:13px;margin-top:4px;" },
        `Wertdifferenz: ${fmtInt(giveValue)} abgegeben vs. ${fmtInt(getValue)} erhalten (${(diffPct * 100).toFixed(1)}%)`
      ),
      el("div", { class: "section-label" }, "Auswirkung auf dein Lineup"),
      el("div", { style: "display:flex;gap:20px;align-items:center;flex-wrap:wrap;" }, [
        el("div", {}, [el("div", { style: "font-size:22px;font-weight:800;" }, fmt1(beforePts)), el("div", { style: "font-size:11px;color:var(--text-muted);" }, "Vorher")]),
        el("div", { style: "color:var(--text-faint);" }, "→"),
        el("div", {}, [el("div", { style: "font-size:22px;font-weight:800;" }, fmt1(afterPts)), el("div", { style: "font-size:11px;color:var(--text-muted);" }, "Nachher")]),
        el(
          "div",
          { style: `font-weight:800;color:${ptsDelta >= 0 ? "var(--status-good)" : "var(--status-bad)"};` },
          `${ptsDelta >= 0 ? "+" : ""}${ptsDelta} Pkt./Woche`
        ),
      ]),
      el("div", { class: "section-label" }, "Lineup Slot-für-Slot (vorher → nachher)"),
      el("div", {}, slotRows),
      el("div", { class: "section-label" }, "Restprogramm-Effekt (Hochrechnung)"),
      el("div", { style: "font-size:12.5px;color:var(--text-muted);" }, (() => {
        const weeks = DATA.trade_finder?.remaining_weeks_estimate || 12;
        const giveAvg = giveIds.reduce((s, id) => s + (DATA.players[id]?.season_avg || 0), 0);
        const getAvg = getIds.reduce((s, id) => s + (DATA.players[id]?.season_avg || 0), 0);
        const seasonDelta = Math.round((getAvg - giveAvg) * weeks * 10) / 10;
        return `Auf Basis der Saison-Durchschnitte über die restlichen ${weeks} Wochen: ${seasonDelta >= 0 ? "+" : ""}${seasonDelta} Pkt. — grobe Hochrechnung, kein Woche-für-Woche-Modell.`;
      })()),
    ]);
  }

  function addPlayerToAnalyzer(pid) {
    const p = DATA.players[pid];
    if (!p) return;
    const isMine = p.fantasy_team && p.fantasy_team.roster_id === DATA.me.roster_id;
    const side = isMine ? "give" : "get";
    if (!tradeAnalyzer[side].includes(pid)) tradeAnalyzer[side].push(pid);
    closePlayerDetail();
    navigateTo("tradeanalyzer");
    render();
  }

  // ---------- Trade Finder ----------
  // ---------- Sell High / Buy Low ----------
  function renderSellBuy() {
    const frag = el("div", {});
    frag.appendChild(renderHeader());
    frag.appendChild(
      el("div", { class: "card empty-state" },
        "Sell High: Spieler, die über ihrem Usage-Niveau punkten (Regressions-Risiko). Buy Low: Spieler mit hoher Usage, die aktuell unter Wert punkten (Kaufchance)."
      )
    );

    function openInTradeFinder(p, isMine) {
      if (isMine) setTradeBlockStatus(p.player_id, "give");
      else setTradeBlockStatus(p.player_id, "target");
      tradeFinderView.position = DATA.players[p.player_id]?.position || null;
      navigateTo("tradefinder");
      render();
    }

    function buildSection(title, color, entries, isMineFlag) {
      frag.appendChild(el("div", { class: "section-label" }, title));
      if (!entries.length) {
        frag.appendChild(el("div", { class: "card empty-state" }, "Keine Spieler gefunden."));
        return;
      }
      entries.forEach((e) => {
        const p = DATA.players[e.player_id];
        if (!p) return;
        const card = el("div", { class: "card" }, [
          el("div", { style: "display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px;" }, [
            el("div", { style: "display:flex;align-items:center;gap:10px;" }, [
              playerAvatar(p, "sm"),
              el("div", {}, [
                el("div", { style: "font-weight:700;font-size:14px;" }, [p.name, p.fantasy_team ? el("span", { style: "color:var(--text-muted);font-weight:400;font-size:12px;margin-left:6px;" }, `(${p.fantasy_team.team_name})`) : null].filter(Boolean)),
                el("div", { class: "pc-meta" }, [posChip(p.position), ` ${p.team || "FA"}`]),
              ]),
            ]),
            el("div", { style: `font-size:17px;font-weight:800;color:${color};` }, `${e.ppo_ratio}×`),
          ]),
          el("div", { style: "font-size:12px;color:var(--text-muted);margin-top:8px;" },
            `${fmt1(p.season_avg)} Pkt./Spiel bei ${e.opportunity_pg} ${p.position === "RB" ? "Touches" : "Targets"}/Spiel (${e.ppo_ratio}× Positions-Schnitt an Punkten pro Opportunity)`
          ),
          el("button", { class: "btn", style: "margin-top:10px;", onclick: () => openInTradeFinder(e, isMineFlag(p)) },
            isMineFlag(p) ? "Zum Trade-Block hinzufügen & Trade Finder öffnen" : "Als Ziel merken & Trade Finder öffnen"
          ),
        ]);
        frag.appendChild(card);
      });
    }

    const sb = DATA.sell_buy;
    buildSection("Sell High (eher abgeben)", "var(--status-bad)", sb.sell_high, (p) => p.fantasy_team && p.fantasy_team.roster_id === DATA.me.roster_id);
    buildSection("Buy Low (eher holen)", "var(--status-good)", sb.buy_low, () => false);

    return frag;
  }

  const tradeFinderView = {
    excludeKeyPlayers: true,
    onlyImproving: false,
    onlyRealistic: false,
    onlyWinWin: false,
    showCurrentOpponent: false,
    fairness: "any",
    position: null,
    team: null,
    purpose: null,
    maxSideSize: "any", // "any" = unbegrenzt (Standard), siehe Spezifikation
    sort: "lineup",
  };
  const tradeBlockView = { allowCombos: false };

  // ---------- Trade-Vorschlag-Status (gesendet/abgelehnt/angenommen), lokal gespeichert ----------
  const TRADE_STATUS_KEY = "tradeProposalStatus";
  function loadTradeStatusMap() {
    try {
      const raw = localStorage.getItem(TRADE_STATUS_KEY);
      return raw ? JSON.parse(raw) : {};
    } catch (e) { return {}; }
  }
  const tradeStatusMap = loadTradeStatusMap();
  function saveTradeStatusMap() {
    try { localStorage.setItem(TRADE_STATUS_KEY, JSON.stringify(tradeStatusMap)); } catch (e) { /* ignore */ }
  }
  function proposalKey(p) {
    return `${p.roster_id}|${[...p.give_player_ids].sort().join(",")}|${[...p.get_player_ids].sort().join(",")}`;
  }
  function getTradeStatus(p) { return tradeStatusMap[proposalKey(p)] || null; }
  function setTradeStatus(p, status) {
    const key = proposalKey(p);
    if (status) tradeStatusMap[key] = status;
    else delete tradeStatusMap[key];
    saveTradeStatusMap();
  }

  // Standardsortierung "Lineup-Verbesserung": mein Gewinn minus 0,5x dem
  // Gewinn eines Konkurrenten um die Playoff-Plätze (siehe Backend-Feld
  // is_playoff_rival) - ein Trade, der einem direkten Konkurrenten stark
  // hilft, soll nicht ganz oben stehen, auch wenn er mir ebenfalls nützt.
  function rivalAdjustedScore(p) {
    const rivalPenalty = p.is_playoff_rival ? 0.5 * Math.max(p.their_lineup_delta, 0) : 0;
    return p.lineup_delta - rivalPenalty;
  }

  function filterAndSortProposals(list) {
    list = (list || DATA.trade_finder.proposals || []).slice();
    list = list.filter((p) => !p.give_player_ids.some((id) => tradeBlock.untouchable.includes(id)));
    list = list.filter((p) => getTradeStatus(p) !== "rejected"); // abgelehnte verschwinden
    if (!tradeFinderView.showCurrentOpponent) list = list.filter((p) => !p.is_current_week_opponent);
    if (tradeFinderView.excludeKeyPlayers) list = list.filter((p) => !p.includes_key_player);
    if (tradeFinderView.onlyImproving) list = list.filter((p) => p.lineup_delta > 0);
    if (tradeFinderView.onlyWinWin) list = list.filter((p) => p.is_win_win);
    if (tradeFinderView.onlyRealistic) list = list.filter((p) => p.acceptance !== "niedrig" && p.value_diff_pct <= 20);
    if (tradeFinderView.fairness !== "any") list = list.filter((p) => p.value_diff_pct <= Number(tradeFinderView.fairness));
    if (tradeFinderView.position) {
      list = list.filter((p) => [...p.give_player_ids, ...p.get_player_ids].some((id) => DATA.players[id]?.position === tradeFinderView.position));
    }
    if (tradeFinderView.team) list = list.filter((p) => p.roster_id === tradeFinderView.team);
    if (tradeFinderView.purpose) list = list.filter((p) => p.purpose_labels.includes(tradeFinderView.purpose));
    if (tradeFinderView.maxSideSize !== "any") {
      const max = Number(tradeFinderView.maxSideSize);
      list = list.filter((p) => p.give_player_ids.length <= max && p.get_player_ids.length <= max);
    }

    const acceptRank = { hoch: 3, mittel: 2, niedrig: 1 };
    if (tradeFinderView.sort === "value") list.sort((a, b) => b.get_value - b.give_value - (a.get_value - a.give_value));
    else if (tradeFinderView.sort === "acceptance") list.sort((a, b) => acceptRank[b.acceptance] - acceptRank[a.acceptance]);
    else list.sort((a, b) => rivalAdjustedScore(b) - rivalAdjustedScore(a));
    return list;
  }

  function allPurposeLabels() {
    const set = new Set();
    (DATA.trade_finder.proposals || []).forEach((p) => p.purpose_labels.forEach((l) => set.add(l)));
    return Array.from(set).sort();
  }

  function buildPitchText(p) {
    const giveNames = p.give_player_ids.map((id) => DATA.players[id]?.name).filter(Boolean).join(" und ");
    const getNames = p.get_player_ids.map((id) => DATA.players[id]?.name).filter(Boolean).join(" und ");
    const reason = (p.partner_accept_reasons || [])[0] || "";
    return `Hey! Hätte Interesse an einem Trade: Ich gebe dir ${giveNames}, dafür bekomme ich ${getNames}. ${reason ? reason + ". " : ""}Lass mich wissen, was du denkst!`;
  }

  function buildTradeProposalCard(p) {
    const card = el("div", { class: "card" });
    const status = getTradeStatus(p);

    const headerRow = el("div", { style: "display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px;margin-bottom:10px;" }, [
      el("div", { style: "display:flex;gap:6px;flex-wrap:wrap;" }, p.purpose_labels.map((l) =>
        el("span", { class: "tab-pill", style: "cursor:default;background:var(--accent-soft);color:var(--accent);border-color:transparent;" }, l)
      )),
      p.is_win_win ? el("span", { class: "tab-pill", style: "cursor:default;background:var(--status-good);color:#fff;border-color:transparent;display:inline-flex;align-items:center;gap:4px;" }, [icon("handshake", { style: "width:11px;height:11px;" }), "Win-Win"]) : null,
      p.is_playoff_rival ? el("span", { class: "tab-pill", style: "cursor:default;color:var(--status-warn);display:inline-flex;align-items:center;gap:4px;" }, [icon("swords", { style: "width:11px;height:11px;" }), "Konkurrent um Playoff-Platz"]) : null,
      p.is_current_week_opponent ? el("span", { class: "tab-pill", style: "cursor:default;" }, "Dein Gegner diese Woche") : null,
      el("span", { class: "tab-pill", style: "cursor:default;color:var(--text-muted);" }, p.relaxation_label),
    ].filter(Boolean));
    card.appendChild(headerRow);

    card.appendChild(
      el("div", { style: "display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:16px;" }, [
        el("div", {}, [
          el("div", { style: "font-weight:700;font-size:11px;color:var(--text-muted);margin-bottom:6px;text-transform:uppercase;" }, "Du gibst"),
          el("div", { style: "display:flex;flex-direction:column;gap:6px;" }, p.give_player_ids.map((id) => playerTag(id))),
          el("div", { style: "font-size:11px;color:var(--text-muted);margin-top:6px;" }, `Wert: ${fmtInt(p.give_value)}`),
        ]),
        icon("arrow-left-right", { style: "width:18px;height:18px;color:var(--text-faint);align-self:center;" }),
        el("div", {}, [
          el("div", { style: "font-weight:700;font-size:11px;color:var(--text-muted);margin-bottom:6px;text-transform:uppercase;" }, `Du bekommst · ${p.team_name} (${p.their_record})`),
          el("div", { style: "display:flex;flex-direction:column;gap:6px;" }, p.get_player_ids.map((id) => playerTag(id))),
          el("div", { style: "font-size:11px;color:var(--text-muted);margin-top:6px;" },
            `Wert: ${fmtInt(p.get_value)} · Diff ${p.value_diff_pct_signed >= 0 ? "+" : ""}${p.value_diff_pct_signed}% ${p.value_diff_pct_signed > 0 ? "(du überzahlst)" : p.value_diff_pct_signed < 0 ? "(Partner überzahlt)" : "(ausgeglichen)"}`
          ),
        ]),
      ])
    );
    card.appendChild(
      el(
        "div",
        { style: "display:flex;gap:8px;flex-wrap:wrap;margin-top:12px;" },
        [
          el("span", { class: "tab-pill", style: `background:${p.lineup_delta >= 0 ? "var(--status-good)" : "var(--status-bad)"};color:#fff;border:none;cursor:default;` }, `${p.lineup_delta >= 0 ? "+" : ""}${p.lineup_delta} Pkt. diese Woche`),
          el("span", { class: "tab-pill", style: "cursor:default;" }, `Bis Deadline: ${p.my_value_delta_until_deadline >= 0 ? "+" : ""}${p.my_value_delta_until_deadline}`),
          el("span", { class: "tab-pill", style: "cursor:default;" }, `Playoffs: ${p.my_value_delta_playoffs >= 0 ? "+" : ""}${p.my_value_delta_playoffs}`),
          el("span", { class: "tab-pill", style: "cursor:default;" }, `Annahme: ${p.acceptance}`),
          p.stance ? el("span", { class: "tab-pill", style: "cursor:default;" }, p.stance) : null,
          !p.roster_legal_for_me ? el("span", { class: "tab-pill", style: "color:var(--status-warn);cursor:default;display:inline-flex;align-items:center;gap:4px;" }, [icon("triangle-alert", { style: "width:11px;height:11px;" }), "Trotz dünner Tiefe - hoher Gesamtgewinn"]) : null,
          p.must_drop_players
            ? el("span", { class: "tab-pill", style: "color:var(--status-warn);cursor:default;display:inline-flex;align-items:center;gap:4px;" }, [
                icon("users", { style: "width:11px;height:11px;" }),
                `Jemand muss gedroppt werden (${p.can_fill_via_waiver_mine ? "Waiver-Ersatz verfügbar" : "kein Waiver-Ersatz verfügbar"})`,
              ])
            : null,
        ].filter(Boolean)
      )
    );
    if ((p.injured_players_detail || []).length) {
      card.appendChild(
        el("div", { style: "font-size:11.5px;color:var(--status-bad);margin-top:8px;display:flex;align-items:center;gap:5px;" }, [
          icon("triangle-alert", { style: "width:12px;height:12px;flex-shrink:0;" }),
          p.injured_players_detail.map((d) => `${d.name} (${d.status})`).join(", "),
        ])
      );
    }
    if ((p.variants || []).length) {
      const details = document.createElement("details");
      details.style.marginTop = "8px";
      const summary = document.createElement("summary");
      summary.style.cssText = "font-size:11.5px;color:var(--text-muted);cursor:pointer;";
      summary.textContent = `${p.variants.length} ähnliche Variante${p.variants.length > 1 ? "n" : ""} mit demselben Team`;
      details.appendChild(summary);
      const list = el("div", { style: "display:flex;flex-direction:column;gap:4px;margin-top:6px;" }, p.variants.map((v) =>
        el("div", { style: "font-size:11.5px;color:var(--text-muted);" },
          `${v.give_player_ids.map((id) => DATA.players[id]?.name).join(" + ")} ⇄ ${v.get_player_ids.map((id) => DATA.players[id]?.name).join(" + ")} · ${v.lineup_delta >= 0 ? "+" : ""}${v.lineup_delta} Pkt. · Diff ${v.value_diff_pct}%`
        )
      ));
      details.appendChild(list);
      card.appendChild(details);
    }
    {
      const details = document.createElement("details");
      details.style.marginTop = "8px";
      const summary = document.createElement("summary");
      summary.style.cssText = "font-size:11.5px;color:var(--text-muted);cursor:pointer;";
      summary.textContent = "Woche-für-Woche-Aufschlüsselung";
      details.appendChild(summary);
      const vb = p.value_breakdown;
      const body = el("div", { style: "display:flex;flex-direction:column;gap:3px;margin-top:6px;" }, [
        vb.short_term_negative_long_term_positive
          ? el("div", { style: "font-size:11.5px;color:var(--status-warn);margin-bottom:4px;" }, "Kurzfristig ein Minus, langfristig (Deadline/Playoffs) ein Plus.")
          : null,
        ...vb.weeks.map((w) =>
          el("div", { style: "display:flex;justify-content:space-between;font-size:11.5px;color:var(--text-muted);gap:10px;" }, [
            el("span", {}, `Woche ${w.week}`),
            el("span", { style: `color:${w.delta >= 0 ? "var(--status-good)" : "var(--status-bad)"};` }, `${w.delta >= 0 ? "+" : ""}${w.delta}`),
          ])
        ),
      ].filter(Boolean));
      details.appendChild(body);
      card.appendChild(details);
    }

    const myCurrentIds = [...DATA.my_roster.slots.map((s) => s.player_id), ...DATA.my_roster.bench];
    const myHypotheticalIds = myCurrentIds.filter((id) => !p.give_player_ids.includes(id)).concat(p.get_player_ids);
    const slotChanges = lineupSlotChanges(myCurrentIds, myHypotheticalIds, DATA.league.roster_positions, DATA.league.week);
    if (slotChanges.length) {
      card.appendChild(el("div", { class: "section-label" }, "Lineup-Änderungen"));
      card.appendChild(
        el("div", { style: "display:flex;flex-direction:column;gap:4px;" }, slotChanges.map((c) =>
          el("div", { style: "display:flex;align-items:center;gap:8px;font-size:12.5px;" }, [
            el("span", { class: "slot-tag", style: "width:auto;" }, c.slot),
            c.outId ? el("span", { style: "color:var(--status-bad);" }, DATA.players[c.outId]?.name || c.outId) : el("span", { class: "null-value" }, "leer"),
            icon("arrow-right", { style: "width:12px;height:12px;color:var(--text-faint);" }),
            c.inId ? el("span", { style: "color:var(--status-good);font-weight:700;" }, DATA.players[c.inId]?.name || c.inId) : el("span", { class: "null-value" }, "leer"),
          ])
        ))
      );
    }

    card.appendChild(el("div", { class: "section-label" }, "Warum der Partner zustimmen könnte"));
    card.appendChild(el("ul", { style: "margin:0 0 10px;padding-left:18px;font-size:12px;color:var(--text-muted);" }, (p.partner_accept_reasons || []).map((r) => el("li", {}, r))));
    card.appendChild(el("ul", { style: "margin:0;padding-left:18px;font-size:12px;color:var(--text-muted);" }, p.reasons.map((r) => el("li", {}, r))));

    const actionRow = el("div", { style: "display:flex;gap:8px;flex-wrap:wrap;margin-top:12px;" });
    actionRow.appendChild(
      el("button", { class: "btn", onclick: () => { tradeAnalyzer.give = [...p.give_player_ids]; tradeAnalyzer.get = [...p.get_player_ids]; navigateTo("tradeanalyzer"); render(); } }, "Im Trade-Analyzer öffnen")
    );
    const pitchBtn = el("button", { class: "btn" }, [icon("copy", { style: "width:12px;height:12px;" }), "Angebotstext kopieren"]);
    pitchBtn.addEventListener("click", () => {
      const text = buildPitchText(p);
      (navigator.clipboard?.writeText(text) || Promise.reject()).then(
        () => { pitchBtn.innerHTML = ""; pitchBtn.append(" Kopiert!"); setTimeout(() => { pitchBtn.innerHTML = ""; pitchBtn.appendChild(icon("copy", { style: "width:12px;height:12px;" })); pitchBtn.append(" Angebotstext kopieren"); refreshIcons(); }, 1500); },
        () => alert("Konnte nicht in die Zwischenablage kopieren.")
      );
    });
    actionRow.appendChild(pitchBtn);
    card.appendChild(actionRow);

    const statusRow = el("div", { style: "display:flex;gap:6px;flex-wrap:wrap;margin-top:8px;" });
    const statusPill = (label, value) =>
      el("button", {
        class: "tab-pill" + (status === value ? " active" : ""),
        onclick: () => { setTradeStatus(p, status === value ? null : value); render(); },
      }, label);
    statusRow.appendChild(statusPill("Gesendet", "sent"));
    statusRow.appendChild(statusPill("Angenommen", "accepted"));
    statusRow.appendChild(statusPill("Abgelehnt", "rejected"));
    card.appendChild(statusRow);

    return card;
  }

  function renderTradeBlockSection() {
    const host = el("div", { class: "card" });
    function refresh() {
      host.innerHTML = "";
      host.appendChild(el("div", { class: "card-title" }, "Mein Trade-Block"));

      function listBlock(iconName, title, ids, emptyLabel) {
        return el("div", { style: "min-width:170px;flex:1;" }, [
          el("div", { style: "font-weight:700;font-size:11px;color:var(--text-muted);margin-bottom:8px;text-transform:uppercase;display:flex;align-items:center;gap:5px;" }, [icon(iconName, { style: "width:12px;height:12px;" }), title]),
          ids.length
            ? el(
                "div",
                { style: "display:flex;flex-direction:column;gap:6px;" },
                ids.map((id) =>
                  el("div", { style: "display:flex;align-items:center;gap:6px;justify-content:space-between;" }, [
                    playerTag(id),
                    el("button", { class: "btn", style: "padding:1px 7px;font-size:10px;", onclick: () => { setTradeBlockStatus(id, null); refresh(); } }, icon("x", { style: "width:11px;height:11px;" })),
                  ])
                )
              )
            : el("div", { class: "empty-state" }, emptyLabel),
        ]);
      }
      host.appendChild(
        el("div", { style: "display:flex;gap:20px;flex-wrap:wrap;margin-bottom:14px;" }, [
          listBlock("tag", "Abzugeben", tradeBlock.give, "Keine Spieler markiert."),
          listBlock("target", "Ziele", tradeBlock.target, "Keine Spieler markiert."),
          listBlock("lock", "Unantastbar", tradeBlock.untouchable, "Keine Spieler markiert."),
        ])
      );
      host.appendChild(
        el("div", { style: "display:flex;gap:8px;margin-bottom:14px;" }, [
          el("button", { class: "btn", onclick: exportTradeBlock }, "Exportieren"),
          el("label", { class: "btn", style: "cursor:pointer;" }, [
            "Importieren",
            el("input", {
              type: "file",
              accept: "application/json",
              style: "display:none;",
              onchange: (e) => { if (e.target.files[0]) importTradeBlock(e.target.files[0], refresh); },
            }),
          ]),
        ])
      );

      if (tradeBlock.give.length) {
        host.appendChild(el("div", { class: "section-label", style: "margin-top:0;" }, "Vorschläge pro Abzugabe-Spieler"));
        host.appendChild(
          el("label", { style: "display:flex;align-items:center;gap:6px;font-size:12px;color:var(--text-muted);margin-bottom:10px;" }, [
            el("input", {
              type: "checkbox",
              checked: tradeBlockView.allowCombos ? "checked" : null,
              onchange: (e) => { tradeBlockView.allowCombos = e.target.checked; refresh(); },
            }),
            "Kombinationen aus 2 Block-Spielern in einem Trade erlauben (Standard: nur 1 Hauptspieler + optional Füllspieler aus deinem Überschuss)",
          ])
        );
        tradeBlock.give.forEach((pid) => {
          host.appendChild(el("div", { style: "font-weight:700;font-size:13px;margin:14px 0 8px;" }, [playerLink(pid), " - was dafür realistisch drin ist"]));
          const { sectionA, sectionB } = blockPlayerSections(pid);

          host.appendChild(el("div", { style: "font-size:11.5px;font-weight:700;color:var(--text-muted);text-transform:uppercase;margin-bottom:6px;" }, "Für deinen Bedarf"));
          if (!sectionA.length) {
            host.appendChild(el("div", { class: "empty-state" }, "Kein Vorschlag trifft aktuell deinen Bedarf - siehe 'Allgemein' unten."));
          } else {
            sectionA.slice(0, 10).forEach((m) => host.appendChild(buildTradeProposalCard(m)));
          }

          host.appendChild(el("div", { style: "font-size:11.5px;font-weight:700;color:var(--text-muted);text-transform:uppercase;margin:14px 0 6px;" }, "Allgemein: was bringt dir am meisten"));
          if (!sectionB.length) {
            host.appendChild(el("div", { class: "empty-state" }, "Keine passenden, sinnvollen Vorschläge gefunden (alle Regeln aus dem Trade Finder gelten auch hier)."));
          } else {
            sectionB.slice(0, 10).forEach((m) => host.appendChild(buildTradeProposalCard(m)));
          }
        });
      }

      if (tradeBlock.target.length) {
        host.appendChild(el("div", { class: "section-label" }, "Was du für deine Ziele bieten könntest"));
        tradeBlock.target.forEach((tid) => {
          const tiers = targetOfferTiers(tid);
          host.appendChild(el("div", { style: "font-weight:700;font-size:13px;margin-bottom:6px;" }, playerLink(tid)));
          if (!tiers || !Object.keys(tiers).length) {
            host.appendChild(el("div", { class: "card empty-state" }, "Kein Angebot aus deinem Kader gefunden, das alle Sinn-Regeln erfüllt."));
            return;
          }
          const tierLabels = { entry: "Einstieg", mid: "Mitte", max: "Maximum" };
          host.appendChild(
            el("div", { class: "grid grid-3", style: "margin-bottom:14px;" }, ["entry", "mid", "max"].filter((k) => tiers[k]).map((k) =>
              el("div", {}, [
                el("div", { style: "font-size:11px;color:var(--text-muted);text-transform:uppercase;font-weight:700;margin-bottom:6px;" }, tierLabels[k]),
                buildTradeProposalCard(tiers[k]),
              ])
            ))
          );
        });
      }
    }
    refresh();
    return host;
  }

  // Abschnitt A ("Für deinen Bedarf") + B ("Allgemein: was bringt dir am
  // meisten") kommen direkt aus dem Backend-Index block_player_candidates -
  // dort wurde für JEDEN handelbaren eigenen Spieler sichergestellt, dass
  // mindestens 5 sinnvolle (alle Sinn-Regeln erfüllende) Vorschläge
  // existieren, notfalls über eine gezielte Nachsuche. Der "Kombinationen
  // erlauben"-Schalter ist rein clientseitiger Zustand (welche MEINER
  // markierten Block-Spieler zusammen auftauchen dürfen), daher wird er
  // hier als zusätzlicher Filter angewendet.
  function filterByComboToggle(list) {
    return list.filter((p) => {
      if (p.give_player_ids.some((id) => tradeBlock.untouchable.includes(id))) return false;
      const blockedInGive = p.give_player_ids.filter((id) => tradeBlock.give.includes(id));
      if (!tradeBlockView.allowCombos && blockedInGive.length > 1) return false;
      if (blockedInGive.length > 2) return false; // alle 3 zusammen gibt es nie
      return true;
    });
  }

  function blockPlayerSections(pid) {
    const entry = DATA.trade_finder.block_player_candidates[pid];
    if (!entry) return { sectionA: [], sectionB: [] };
    return {
      sectionA: filterByComboToggle(entry.section_a || []),
      sectionB: filterByComboToggle(entry.section_b || []),
    };
  }

  function targetOfferTiers(targetId) {
    return DATA.trade_finder.target_offers[targetId] || null;
  }

  function renderTradeFinder() {
    const frag = el("div", {});
    frag.appendChild(renderHeader());

    const tf = DATA.trade_finder;
    frag.appendChild(
      el("div", { class: "card" }, [
        el("div", { class: "card-title" }, "Meine Lage"),
        el("div", {}, `Bedarf: ${tf.my_needs.length ? tf.my_needs.join(", ") : "kein akuter Bedarf"}`),
        el("div", { style: "margin-top:6px;font-size:12px;color:var(--text-muted);" }, [
          "Schlüsselspieler (standardmäßig vom Angebot ausgeschlossen): ",
          ...tf.key_player_ids.flatMap((id, i) => [i > 0 ? ", " : "", playerLink(id)]),
        ]),
        el("div", { style: "margin-top:6px;font-size:11px;color:var(--text-faint);" }, tf.league_rules_note),
      ])
    );

    frag.appendChild(renderTradeBlockSection());

    frag.appendChild(el("div", { class: "section-label" }, "Alle Vorschläge"));
    const filterBar = el("div", { class: "card", style: "display:flex;gap:10px;flex-wrap:wrap;align-items:center;" });
    const listHost = el("div", {});

    function refreshList() {
      listHost.innerHTML = "";
      const list = filterAndSortProposals();
      listHost.appendChild(el("div", { style: "font-size:12px;color:var(--text-muted);margin:4px 0 10px;" }, `${list.length} Vorschläge gefunden`));
      if (!list.length) listHost.appendChild(el("div", { class: "card empty-state" }, "Keine Vorschläge für diese Filter. Toleranz erhöhen oder Filter zurücksetzen."));
      else list.slice(0, 40).forEach((p) => listHost.appendChild(buildTradeProposalCard(p)));
    }

    const posOptions = [null, ...POSITIONS];
    filterBar.appendChild(
      el(
        "select",
        {
          style: "padding:7px 10px;border-radius:8px;border:1px solid var(--card-border);background:var(--bg);color:var(--text);font-size:12.5px;",
          onchange: (e) => { tradeFinderView.position = e.target.value || null; refreshList(); },
        },
        posOptions.map((pos) => el("option", { value: pos || "" }, pos || "Alle Positionen"))
      )
    );
    filterBar.appendChild(
      el(
        "select",
        {
          style: "padding:7px 10px;border-radius:8px;border:1px solid var(--card-border);background:var(--bg);color:var(--text);font-size:12.5px;",
          onchange: (e) => { tradeFinderView.team = e.target.value ? Number(e.target.value) : null; refreshList(); },
        },
        [el("option", { value: "" }, "Alle Teams"), ...DATA.teams.filter((t) => t.roster_id !== DATA.me.roster_id).map((t) => el("option", { value: t.roster_id }, t.team_name))]
      )
    );
    filterBar.appendChild(
      el(
        "select",
        {
          style: "padding:7px 10px;border-radius:8px;border:1px solid var(--card-border);background:var(--bg);color:var(--text);font-size:12.5px;",
          onchange: (e) => { tradeFinderView.fairness = e.target.value; refreshList(); },
        },
        ["any", "5", "10", "15", "25"].map((v) => el("option", { value: v }, v === "any" ? "Toleranz: egal" : `Toleranz: ${v}%`))
      )
    );
    filterBar.appendChild(
      el(
        "select",
        {
          style: "padding:7px 10px;border-radius:8px;border:1px solid var(--card-border);background:var(--bg);color:var(--text);font-size:12.5px;",
          onchange: (e) => { tradeFinderView.purpose = e.target.value || null; refreshList(); },
        },
        [el("option", { value: "" }, "Alle Zwecke"), ...allPurposeLabels().map((l) => el("option", { value: l }, l))]
      )
    );
    filterBar.appendChild(
      el(
        "select",
        {
          style: "padding:7px 10px;border-radius:8px;border:1px solid var(--card-border);background:var(--bg);color:var(--text);font-size:12.5px;",
          onchange: (e) => { tradeFinderView.maxSideSize = e.target.value; refreshList(); },
        },
        ["any", "1", "2", "3", "4", "5"].map((v) => el("option", { value: v }, v === "any" ? "Spieler/Seite: unbegrenzt" : `Max. ${v} Spieler/Seite`))
      )
    );
    filterBar.appendChild(
      el(
        "select",
        {
          style: "padding:7px 10px;border-radius:8px;border:1px solid var(--card-border);background:var(--bg);color:var(--text);font-size:12.5px;",
          onchange: (e) => { tradeFinderView.sort = e.target.value; refreshList(); },
        },
        [
          el("option", { value: "lineup" }, "Sortierung: Lineup-Verbesserung"),
          el("option", { value: "value" }, "Sortierung: Trade-Wert-Gewinn"),
          el("option", { value: "acceptance" }, "Sortierung: Annahme-Wahrscheinlichkeit"),
        ]
      )
    );
    const checkbox = (label, key, defaultChecked) =>
      el("label", { style: "display:flex;align-items:center;gap:6px;font-size:12px;color:var(--text-muted);" }, [
        el("input", {
          type: "checkbox",
          checked: defaultChecked ? "checked" : null,
          onchange: (e) => { tradeFinderView[key] = e.target.checked; refreshList(); },
        }),
        label,
      ]);
    filterBar.appendChild(checkbox("Schlüsselspieler ausschließen", "excludeKeyPlayers", true));
    filterBar.appendChild(checkbox("Nur Lineup-Verbesserung", "onlyImproving", false));
    filterBar.appendChild(checkbox("Nur Win-Win", "onlyWinWin", false));
    filterBar.appendChild(checkbox("Nur realistische Trades", "onlyRealistic", false));
    filterBar.appendChild(checkbox("Aktuellen Gegner einblenden", "showCurrentOpponent", false));

    frag.appendChild(filterBar);
    frag.appendChild(listHost);
    refreshList();

    return frag;
  }

  // ---------- Liga ----------
  let selectedLeagueTeamId = null;

  function playerLabel(pid) {
    const p = DATA.players[pid];
    if (p) return [posChip(p.position), " ", playerLink(pid)];
    return [el("span", { style: "color:var(--text-faint);" }, pid)];
  }

  function renderLeague() {
    const frag = el("div", {});
    frag.appendChild(renderHeader());

    frag.appendChild(el("div", { class: "section-label" }, "Tabelle"));
    const standingsRows = DATA.teams.map((t) =>
      el("tr", {}, [
        el("td", {}, `#${t.rank}`),
        el("td", {}, t.team_name),
        el("td", {}, `${t.wins}-${t.losses}${t.ties ? "-" + t.ties : ""}`),
        el("td", {}, fmt1(t.fpts)),
        el("td", {}, fmt1(t.fpts_against)),
        el("td", {}, t.streak || "–"),
      ])
    );
    frag.appendChild(
      el("div", { class: "card table-wrap" }, [
        el("table", { class: "data-table" }, [
          el("thead", {}, el("tr", {}, [el("th", {}, "Rang"), el("th", {}, "Team"), el("th", {}, "W-L-T"), el("th", {}, "Punkte"), el("th", {}, "Gegen"), el("th", {}, "Serie")])),
          el("tbody", {}, standingsRows),
        ]),
      ])
    );

    frag.appendChild(el("div", { class: "section-label" }, "Power-Ranking (nach Roster-Wert)"));
    const prRows = DATA.league_feed.power_ranking.map((t) =>
      el("tr", {}, [
        el("td", {}, `#${t.power_rank}`),
        el("td", {}, t.team_name),
        el("td", {}, t.roster_value ? fmtInt(t.roster_value) : "–"),
      ])
    );
    frag.appendChild(
      el("div", { class: "card table-wrap" }, [
        el("table", { class: "data-table" }, [
          el("thead", {}, el("tr", {}, [el("th", {}, "Rang"), el("th", {}, "Team"), el("th", {}, "Roster-Wert")])),
          el("tbody", {}, prRows),
        ]),
      ])
    );

    frag.appendChild(el("div", { class: "section-label" }, "Positionsstärke je Team"));
    frag.appendChild(renderPositionStrengthMatrix());

    frag.appendChild(el("div", { class: "section-label" }, "Scouting-Profile"));
    frag.appendChild(renderScoutingProfiles());

    frag.appendChild(el("div", { class: "section-label" }, "Rosters"));
    const teamPicker = el(
      "div",
      { style: "display:flex;gap:6px;flex-wrap:wrap;margin-bottom:10px;" },
      DATA.teams.map((t) =>
        el(
          "button",
          {
            class: "btn",
            style: (selectedLeagueTeamId || DATA.me.roster_id) === t.roster_id ? "background:var(--accent);border-color:var(--accent);color:#fff;" : "",
            onclick: () => {
              selectedLeagueTeamId = t.roster_id;
              render();
            },
          },
          t.team_name
        )
      )
    );
    frag.appendChild(teamPicker);
    frag.appendChild(renderTeamRosterCard(selectedLeagueTeamId || DATA.me.roster_id));

    frag.appendChild(el("div", { class: "section-label" }, "Letzte Transaktionen"));
    const txList = DATA.league_feed.transactions;
    if (!txList.length) {
      frag.appendChild(el("div", { class: "card empty-state" }, "Keine Transaktionen gefunden."));
    } else {
      frag.appendChild(
        el(
          "div",
          { class: "card mini-list" },
          txList.map((tx) => renderTransactionItem(tx))
        )
      );
    }

    return frag;
  }

  function renderPositionStrengthMatrix() {
    const ps = DATA.position_strength;
    const rankByTeam = {};
    DATA.teams.forEach((t) => (rankByTeam[t.roster_id] = { team_name: t.team_name, roster_id: t.roster_id }));
    POSITIONS.forEach((pos) => {
      (ps[pos] || []).forEach((e) => {
        if (rankByTeam[e.roster_id]) rankByTeam[e.roster_id][pos] = e.rank;
      });
    });
    const rows = Object.values(rankByTeam)
      .sort((a, b) => a.team_name.localeCompare(b.team_name))
      .map((t) =>
        el("tr", { style: t.roster_id === DATA.me.roster_id ? "background:var(--accent-soft);" : "" }, [
          el("td", { style: "font-weight:700;" }, t.team_name),
          ...POSITIONS.map((pos) => {
            const rank = t[pos];
            const color = !rank ? "var(--text-faint)" : rank <= 4 ? "var(--status-good)" : rank <= 10 ? "var(--status-warn)" : "var(--status-bad)";
            return el("td", { style: `text-align:center;color:${color};font-weight:700;` }, rank ? `#${rank}` : "–");
          }),
        ])
      );
    return el("div", { class: "card table-wrap" }, [
      el("table", { class: "data-table" }, [
        el("thead", {}, el("tr", {}, [el("th", {}, "Team"), ...POSITIONS.map((pos) => el("th", { style: "text-align:center;" }, pos))])),
        el("tbody", {}, rows),
      ]),
      el("div", { style: "font-size:11px;color:var(--text-muted);margin-top:8px;" }, "Rang 1 = stärkste Position der Liga (grün), Rang > 10 = schwach (rot)."),
    ]);
  }

  function renderScoutingProfiles() {
    const profiles = DATA.league_feed.scouting_profiles || [];
    if (!profiles.length) return el("div", { class: "card empty-state" }, "Keine Scouting-Daten verfügbar.");
    return el(
      "div",
      { class: "grid grid-3" },
      profiles.map((p) =>
        el("div", { class: "card", style: "margin-bottom:0;" }, [
          el("div", { style: "font-weight:800;font-size:14px;margin-bottom:8px;" }, p.team_name),
          el("div", { style: "display:flex;gap:16px;margin-bottom:8px;" }, [
            el("div", {}, [el("div", { style: "font-size:18px;font-weight:800;" }, p.waiver_moves), el("div", { style: "font-size:10px;color:var(--text-muted);text-transform:uppercase;" }, "Waiver-Moves")]),
            el("div", {}, [el("div", { style: "font-size:18px;font-weight:800;" }, p.trades), el("div", { style: "font-size:10px;color:var(--text-muted);text-transform:uppercase;" }, "Trades")]),
          ]),
          el("div", { style: "font-size:12px;" }, [
            el("strong", {}, "Bedarf: "),
            p.needs.length ? p.needs.join(", ") : "keiner erkennbar",
          ]),
          el("div", { style: "font-size:12px;margin-top:4px;" }, [
            el("strong", {}, "Überschuss: "),
            p.surplus.length ? p.surplus.join(", ") : "keiner erkennbar",
          ]),
        ])
      )
    );
  }

  function renderTeamRosterCard(rosterId) {
    const team = DATA.teams.find((t) => t.roster_id === rosterId);
    if (!team) return el("div", { class: "empty-state" }, "Team nicht gefunden.");
    const starterSet = new Set(team.starters || []);
    const reserveSet = new Set(team.reserve || []);
    const rows = (team.players || []).map((pid) => {
      const p = DATA.players[pid];
      if (!p) return null;
      const role = starterSet.has(pid) ? "Starter" : reserveSet.has(pid) ? "Reserve" : "Bank";
      const st = statusInfo(p);
      return el("tr", {}, [
        el("td", {}, playerTag(pid)),
        el("td", {}, p.team || "–"),
        el("td", {}, role),
        el("td", {}, [el("span", { class: `status-dot ${st.cls}` }), " ", st.label]),
        el("td", {}, fmt1(p.season_avg)),
      ]);
    }).filter(Boolean);
    return el("div", { class: "card table-wrap" }, [
      el("table", { class: "data-table" }, [
        el("thead", {}, el("tr", {}, [el("th", {}, "Spieler"), el("th", {}, "Team"), el("th", {}, "Rolle"), el("th", {}, "Status"), el("th", {}, "Ø Saison")])),
        el("tbody", {}, rows),
      ]),
    ]);
  }

  function renderTransactionItem(tx) {
    const date = new Date(tx.created).toLocaleDateString("de-DE", { day: "2-digit", month: "2-digit" });
    if (tx.type === "trade") {
      return el("div", { class: "mini-item", style: "display:block;" }, [
        el("div", { style: "font-size:11px;color:var(--text-faint);" }, `${date} · Trade`),
        el(
          "div",
          { style: "display:flex;flex-wrap:wrap;gap:16px;margin-top:4px;" },
          tx.participants.map((side) =>
            el("div", {}, [
              el("div", { style: "font-weight:700;font-size:12.5px;" }, side.team_name),
              side.gets.length ? el("div", { style: "font-size:12px;" }, ["bekommt: ", ...side.gets.flatMap((pid, i) => [i > 0 ? ", " : "", ...playerLabel(pid)])]) : null,
            ].filter(Boolean))
          )
        ),
      ]);
    }
    const label = tx.type === "waiver" ? "Waiver" : "Free Agent";
    return el("div", { class: "mini-item", style: "display:block;" }, [
      el("div", { style: "font-size:11px;color:var(--text-faint);" }, `${date} · ${label} · ${tx.team_name}`),
      el("div", { style: "font-size:12.5px;margin-top:2px;" }, [
        tx.adds.length ? el("span", {}, ["+ ", ...tx.adds.flatMap((pid, i) => [i > 0 ? ", " : "", ...playerLabel(pid)])]) : null,
        tx.adds.length && tx.drops.length ? el("span", { style: "margin:0 6px;" }, "·") : null,
        tx.drops.length ? el("span", {}, ["− ", ...tx.drops.flatMap((pid, i) => [i > 0 ? ", " : "", ...playerLabel(pid)])]) : null,
      ].filter(Boolean)),
    ]);
  }

  // ---------- Planer ----------
  function renderPlanner() {
    const frag = el("div", {});
    frag.appendChild(renderHeader());

    frag.appendChild(el("div", { class: "section-label" }, "Playoff-Wahrscheinlichkeit"));
    frag.appendChild(renderPlayoffOddsCard());

    frag.appendChild(el("div", { class: "section-label" }, "Matchup-Vorhersage (nächste Wochen)"));
    frag.appendChild(renderMatchupForecastCard());

    frag.appendChild(el("div", { class: "section-label" }, "Restprogramm (Fantasy-Gegner)"));
    const rest = DATA.planner.remaining_schedule;
    if (!rest.length) {
      frag.appendChild(el("div", { class: "card empty-state" }, "Kein Restprogramm verfügbar (Saisonende erreicht)."));
    } else {
      frag.appendChild(
        el("div", { class: "card table-wrap" }, [
          el("table", { class: "data-table" }, [
            el("thead", {}, el("tr", {}, [el("th", {}, "Woche"), el("th", {}, "Gegner")])),
            el(
              "tbody",
              {},
              rest.map((g) =>
                el("tr", { style: g.week === DATA.league.playoff_week_start ? "background:var(--accent-soft);" : "" }, [
                  el("td", {}, `W${g.week}${g.week === DATA.league.playoff_week_start ? " (Playoffs)" : ""}`),
                  el("td", {}, g.opponent_team_name || "–"),
                ])
              )
            ),
          ]),
        ])
      );
    }

    frag.appendChild(el("div", { class: "section-label" }, "Bye Weeks deines Kaders"));
    const byeCalendar = DATA.planner.bye_calendar;
    const weeks = Object.keys(byeCalendar).map(Number).sort((a, b) => a - b);
    const upcoming = weeks.filter((w) => w >= DATA.league.week);
    if (!upcoming.length) {
      frag.appendChild(el("div", { class: "card empty-state" }, "Keine weiteren Bye Weeks in deinem Kader."));
    } else {
      frag.appendChild(
        el(
          "div",
          { class: "grid grid-3" },
          upcoming.map((wk) => {
            const nearPlayoffs = (DATA.planner.byes_near_playoffs || []).includes(wk);
            return el("div", { class: "card", style: `margin-bottom:0;${nearPlayoffs ? "border-left:4px solid var(--status-warn);" : ""}` }, [
              el("div", { style: "font-weight:800;font-size:14px;margin-bottom:8px;" }, [
                `Woche ${wk}`,
                nearPlayoffs ? el("span", { style: "color:var(--status-warn);font-weight:700;font-size:11px;margin-left:8px;display:inline-flex;align-items:center;gap:3px;" }, [icon("triangle-alert", { style: "width:11px;height:11px;" }), "kurz vor Playoffs"]) : null,
              ].filter(Boolean)),
              el(
                "div",
                { style: "display:flex;flex-direction:column;gap:6px;" },
                byeCalendar[String(wk)].map((pid) => el("div", {}, playerLabel(pid)))
              ),
            ]);
          })
        )
      );
    }

    return frag;
  }

  function renderPlayoffOddsCard() {
    const po = DATA.playoffs;
    if (!po || !po.results || !po.results.length) {
      return el("div", { class: "card empty-state" }, "Keine Playoff-Simulation verfügbar.");
    }
    const myEntry = po.results.find((r) => r.roster_id === DATA.me.roster_id);
    const rows = po.results.map((r) =>
      el("tr", { style: r.roster_id === DATA.me.roster_id ? "background:var(--accent-soft);" : "" }, [
        el("td", { style: "font-weight:700;" }, r.team_name),
        el("td", {}, `${r.current_wins}-${r.current_losses}`),
        el("td", {}, [
          el("div", { style: "display:flex;align-items:center;gap:8px;" }, [
            el("div", { style: "flex:1;max-width:120px;background:var(--accent-soft);border-radius:6px;height:10px;overflow:hidden;" }, [
              el("div", { style: `width:${r.playoff_probability}%;height:100%;background:${r.playoff_probability >= 50 ? "var(--status-good)" : "var(--status-bad)"};border-radius:6px;` }),
            ]),
            el("span", { style: "font-weight:700;font-size:12.5px;width:46px;" }, `${r.playoff_probability}%`),
          ]),
        ]),
        el("td", {}, fmt1(r.projected_final_wins)),
        el("td", {}, `#${fmt1(r.projected_rank)}`),
      ])
    );
    const keyGameRows = (po.key_games || []).map((k) =>
      el("div", { class: "card", style: "margin-bottom:8px;" }, [
        el("div", { style: "display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px;" }, [
          el("div", { style: "font-weight:700;" }, `Woche ${k.week} vs. ${k.opponent_team_name}`),
          el("div", { style: `font-weight:800;color:${k.swing >= 5 ? "var(--status-warn)" : "var(--text-muted)"};` }, `±${k.swing} Prozentpunkte`),
        ]),
        el("div", { style: "font-size:12px;color:var(--text-muted);margin-top:4px;" }, `Playoff-Chance bei Sieg: ${k.playoff_probability_if_win}% · bei Niederlage: ${k.playoff_probability_if_loss}%`),
      ])
    );
    return el("div", {}, [
      myEntry
        ? el("div", { class: "card", style: `border-left:4px solid ${myEntry.playoff_probability >= 50 ? "var(--status-good)" : "var(--status-bad)"};` }, [
            el("div", { style: "font-size:28px;font-weight:800;" }, `${myEntry.playoff_probability}%`),
            el("div", { style: "font-size:12.5px;color:var(--text-muted);" }, `Playoff-Chance von ${DATA.me.team_name} · voraussichtlich ${fmt1(myEntry.projected_final_wins)} Siege, wahrscheinlicher Platz #${fmt1(myEntry.projected_rank)} am Saisonende`),
          ])
        : null,
      el("div", { class: "card table-wrap", style: "margin-top:10px;" }, [
        el("table", { class: "data-table" }, [
          el("thead", {}, el("tr", {}, [el("th", {}, "Team"), el("th", {}, "Bilanz"), el("th", {}, "Playoff-Chance"), el("th", {}, "Ø Siege (Hochrechnung)"), el("th", {}, "Ø Platz")])),
          el("tbody", {}, rows),
        ]),
      ]),
      keyGameRows.length ? el("div", { class: "section-label" }, "Wichtigste Spiele für deine Playoff-Chance") : null,
      ...keyGameRows,
      el("div", { style: "font-size:11px;color:var(--text-muted);margin-top:8px;" }, `${po.method_note} (${po.trials.toLocaleString("de-DE")} Durchläufe, ${po.playoff_teams} Playoff-Plätze.)`),
    ].filter(Boolean));
  }

  function renderMatchupForecastCard() {
    const forecast = DATA.planner.matchup_forecast || [];
    if (!forecast.length) {
      return el("div", { class: "card empty-state" }, "Kein Restprogramm für eine Vorhersage verfügbar.");
    }
    const rows = forecast.map((f) => {
      const wp = f.win_probability_me;
      const color = wp == null ? "var(--text-faint)" : wp >= 60 ? "var(--status-good)" : wp <= 40 ? "var(--status-bad)" : "var(--status-warn)";
      return el("div", { class: "card", style: `margin-bottom:10px;border-left:4px solid ${color};` }, [
        el("div", { style: "display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px;" }, [
          el("div", {}, [
            el("span", { style: "font-weight:700;" }, `Woche ${f.week}`),
            ` vs. ${f.opponent_team_name || "–"}`,
          ]),
          wp != null ? el("div", { style: `font-weight:800;color:${color};` }, `${wp}% Sieg-Chance`) : el("div", { style: "color:var(--text-faint);font-size:12px;" }, "Gegner unbekannt"),
        ]),
        el("div", { style: "font-size:12.5px;color:var(--text-muted);margin-top:6px;" }, `Projektion: ${fmt1(f.my_projected_points)} vs. ${f.opponent_projected_points != null ? fmt1(f.opponent_projected_points) : "–"} Pkt.`),
      ]);
    });
    return el("div", {}, [
      ...rows,
      el("div", { style: "font-size:11px;color:var(--text-muted);margin-top:4px;" }, DATA.planner.forecast_note),
    ]);
  }

  // ---------- Live (experimentell, holt Live-Scores direkt vom Browser) ----------
  // Sleeper erlaubt CORS von jedem Origin (access-control-allow-origin: *),
  // daher kann die Matchups-Antwort für die laufende Woche direkt aus dem
  // Browser geladen werden, ohne den täglichen Build-Lauf abzuwarten. Das
  // ist nur während laufender NFL-Spiele aussagekräftig (sonst stehen die
  // Werte aus data.json und hier praktisch gleich).
  let liveRefreshTimer = null;
  let liveState = { loading: false, error: null, matchups: null, fetchedAt: null };

  async function fetchLiveMatchups() {
    liveState.loading = true;
    liveState.error = null;
    renderLiveHost();
    try {
      const res = await fetch(`https://api.sleeper.app/v1/league/${DATA.league.league_id}/matchups/${DATA.league.week}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      liveState.matchups = await res.json();
      liveState.fetchedAt = new Date();
    } catch (e) {
      liveState.error = "Live-Daten konnten nicht geladen werden (" + e.message + "). Sleeper evtl. nicht erreichbar.";
    } finally {
      liveState.loading = false;
      renderLiveHost();
    }
  }

  function renderLiveHost() {
    const host = $("#live-host");
    if (!host) return;
    host.innerHTML = "";
    host.appendChild(buildLiveBody());
  }

  function buildLiveBody() {
    if (liveState.loading && !liveState.matchups) {
      return el("div", { class: "card empty-state" }, "Lade Live-Scores …");
    }
    if (liveState.error) {
      return el("div", { class: "card empty-state" }, liveState.error);
    }
    if (!liveState.matchups || !liveState.matchups.length) {
      return el("div", { class: "card empty-state" }, "Keine Live-Daten für die aktuelle Woche verfügbar (Woche evtl. noch nicht gestartet).");
    }
    const teamNameByRoster = {};
    DATA.teams.forEach((t) => (teamNameByRoster[t.roster_id] = t.team_name));

    const byMatchup = {};
    liveState.matchups.forEach((m) => {
      (byMatchup[m.matchup_id] = byMatchup[m.matchup_id] || []).push(m);
    });

    const cards = Object.values(byMatchup).map((pair) => {
      const [a, b] = pair.sort((x, y) => (y.points || 0) - (x.points || 0));
      const nameA = teamNameByRoster[a.roster_id] || `Team ${a.roster_id}`;
      const nameB = b ? (teamNameByRoster[b.roster_id] || `Team ${b.roster_id}`) : null;
      const isMineA = a.roster_id === DATA.me.roster_id;
      const isMineB = b && b.roster_id === DATA.me.roster_id;
      return el("div", { class: "card", style: (isMineA || isMineB) ? "border-left:4px solid var(--accent);" : "" }, [
        el("div", { style: "display:flex;justify-content:space-between;align-items:center;" }, [
          el("div", { style: `font-weight:${isMineA ? "800" : "600"};` }, nameA),
          el("div", { style: "font-size:20px;font-weight:800;" }, fmt1(a.points || 0)),
        ]),
        b
          ? el("div", { style: "display:flex;justify-content:space-between;align-items:center;margin-top:6px;" }, [
              el("div", { style: `font-weight:${isMineB ? "800" : "600"};` }, nameB),
              el("div", { style: "font-size:20px;font-weight:800;" }, fmt1(b.points || 0)),
            ])
          : el("div", { style: "color:var(--text-faint);font-size:12px;margin-top:6px;" }, "Kein Gegner gefunden."),
      ]);
    });

    return el("div", {}, [
      el("div", { class: "grid grid-2" }, cards),
      liveState.fetchedAt
        ? el("div", { style: "font-size:11px;color:var(--text-muted);margin-top:10px;" }, `Zuletzt live geladen: ${liveState.fetchedAt.toLocaleTimeString("de-DE")}`)
        : null,
    ].filter(Boolean));
  }

  function renderLive() {
    const frag = el("div", {});
    frag.appendChild(renderHeader());
    frag.appendChild(
      el("div", { class: "card", style: "margin-bottom:16px;border-left:4px solid var(--status-warn);" }, [
        el("div", { style: "font-weight:700;font-size:13px;display:flex;align-items:center;gap:6px;" }, [icon("satellite-dish", { style: "width:14px;height:14px;" }), "Experimentell: Live-Scores direkt von Sleeper"]),
        el("div", { style: "font-size:12px;color:var(--text-muted);margin-top:4px;" }, "Lädt die aktuelle Woche direkt im Browser von der öffentlichen Sleeper-API (nicht aus data.json). Nur während laufender NFL-Spiele aussagekräftig."),
      ])
    );
    const btnRow = el("div", { style: "display:flex;gap:8px;align-items:center;margin-bottom:16px;" }, [
      el("button", { class: "btn", onclick: () => fetchLiveMatchups() }, [icon("refresh-cw", { style: "width:13px;height:13px;" }), "Jetzt aktualisieren"]),
    ]);
    frag.appendChild(btnRow);
    frag.appendChild(el("div", { id: "live-host" }, [buildLiveBody()]));

    if (!liveState.matchups && !liveState.loading) fetchLiveMatchups();
    if (liveRefreshTimer) clearInterval(liveRefreshTimer);
    liveRefreshTimer = setInterval(() => {
      if (currentTabId() === "live") fetchLiveMatchups();
      else clearInterval(liveRefreshTimer);
    }, 30000);

    return frag;
  }

  // ---------- Start/Sit ----------
  const CONFIDENCE_COLORS = { hoch: "var(--status-good)", mittel: "var(--status-warn)", niedrig: "var(--text-faint)" };

  function renderDuelSummary(duel) {
    if (!duel) return null;
    const color = duel.stance === "favorit" ? "var(--status-good)" : duel.stance === "underdog" ? "var(--status-bad)" : "var(--status-warn)";
    return el("div", { class: "card", style: `border-left:4px solid ${color};` }, [
      el("div", { style: "font-weight:700;font-size:13px;margin-bottom:4px;" }, `${duel.win_probability_me}% Sieg-Chance diese Woche (${duel.stance === "favorit" ? "Favorit" : duel.stance === "underdog" ? "Underdog" : "ausgeglichen"})`),
      el("div", { style: "font-size:12.5px;color:var(--text-muted);" }, duel.advice),
    ]);
  }

  function renderSlotCard(s, isChanged) {
    const p = s.player_id ? DATA.players[s.player_id] : null;
    if (!p) {
      return el("div", { class: "card", style: "margin-bottom:10px;" }, [el("span", { class: "slot-tag" }, s.slot), " – Slot nicht besetzt."]);
    }
    const st = statusInfo(p);
    return el("div", { class: "card", style: `margin-bottom:10px;${isChanged ? "border-left:4px solid var(--accent);" : ""}` }, [
      el("div", { style: "display:flex;align-items:center;justify-content:space-between;gap:10px;flex-wrap:wrap;" }, [
        el("div", { style: "display:flex;align-items:center;gap:10px;" }, [
          el("span", { class: "slot-tag", style: "width:auto;" }, s.slot),
          playerAvatar(p, "sm"),
          el("div", {}, [
            el("div", { style: "font-weight:700;font-size:14px;" }, [p.name, el("span", { class: `status-dot ${st.cls}`, style: "margin-left:6px;" })]),
            el("div", { class: "pc-meta" }, [posChip(p.position), ` ${p.team || "FA"}`, isChanged ? el("span", { style: "color:var(--accent);font-weight:700;margin-left:6px;" }, "NEU") : null].filter(Boolean)),
          ]),
        ]),
        el("div", { style: "text-align:right;" }, [el("div", { style: "font-size:18px;font-weight:800;" }, fmt1(s.effective_projection)), el("div", { style: "font-size:10px;color:var(--text-muted);text-transform:uppercase;" }, "Proj.")]),
      ]),
      s.reasons && s.reasons.length
        ? el("ul", { style: "margin:10px 0 0;padding-left:18px;font-size:12px;color:var(--text-muted);" }, s.reasons.map((r) => el("li", {}, r)))
        : null,
    ].filter(Boolean));
  }

  function renderStartSit() {
    const frag = el("div", {});
    frag.appendChild(renderHeader());

    const ss = DATA.start_sit;
    const duelCard = renderDuelSummary(ss.duel_summary);
    if (duelCard) frag.appendChild(duelCard);

    frag.appendChild(el("div", { class: "section-label" }, "Empfohlenes Lineup"));
    const changedIds = new Set((ss.decisions || []).map((d) => d.recommended_player_id));
    ss.recommended_slots.forEach((s) => frag.appendChild(renderSlotCard(s, s.player_id && changedIds.has(s.player_id))));

    frag.appendChild(el("div", { class: "section-label" }, "Entscheidungen"));
    const decisions = ss.decisions || [];
    if (!decisions.length) {
      frag.appendChild(el("div", { class: "card empty-state" }, "Dein aktuelles Lineup ist bereits optimal gesetzt — keine Änderungen empfohlen."));
    } else {
      decisions.forEach((d) => {
        const rec = DATA.players[d.recommended_player_id];
        const cur = d.current_player_id ? DATA.players[d.current_player_id] : null;
        frag.appendChild(
          el("div", { class: "card" }, [
            el("div", { style: "display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:10px;" }, [
              el("div", { style: "display:flex;align-items:center;gap:10px;font-size:15px;font-weight:700;" }, [
                cur ? playerTag(cur.id) : el("span", { style: "color:var(--text-faint);" }, "Bank"),
                el("span", { style: "color:var(--text-faint);" }, "→"),
                playerTag(rec.id),
              ]),
              el("div", { style: "text-align:right;" }, [
                el("div", { style: `font-weight:800;color:${d.delta >= 0 ? "var(--status-good)" : "var(--status-bad)"};` }, `${d.delta >= 0 ? "+" : ""}${d.delta} Pkt.`),
                el("div", { style: `font-size:10.5px;font-weight:700;color:${CONFIDENCE_COLORS[d.confidence] || "var(--text-muted)"};text-transform:uppercase;` }, `Konfidenz: ${d.confidence}`),
              ]),
            ]),
            el(
              "ul",
              { style: "margin:10px 0 0;padding-left:18px;font-size:12.5px;color:var(--text-muted);" },
              d.reasons.map((r) => el("li", {}, r))
            ),
          ])
        );
      });
    }

    return frag;
  }

  // ---------- Waiver Wire ----------
  const POS_LABELS_DE = { QB: "Quarterback", RB: "Running Back", WR: "Wide Receiver", TE: "Tight End", K: "Kicker", DEF: "Defense" };
  const WAIVER_TABS = {
    position: "Nach Position",
    lineup_upgrade: "Lineup-Upgrade",
    trending: "Trending",
    handcuffs: "Handcuffs",
    ir_stashes: "IR-Stashes",
    breakouts: "Breakouts",
    streaming: "Streaming",
  };
  const waiverView = { tab: "position", posFilter: null, sortKey: "score" };

  function renderWaiverSystemBanner() {
    const ws = DATA.waiver.waiver_system || {};
    let text;
    if (ws.type === "faab") {
      text = `FAAB-Liga: Restbudget ${ws.budget_remaining ?? "?"} von ${ws.budget_total ?? "?"}. Gebotsvorschläge stehen bei den Spielern unten.`;
    } else if (ws.type === "priority") {
      text = `Prioritäts-Waiver (keine FAAB-Gebote): deine aktuelle Position ist #${ws.priority ?? "?"} von ${ws.total_teams ?? "?"}. Je kleiner die Zahl, desto eher bekommst du den Zuschlag.`;
    } else {
      text = "Waiver-System der Liga konnte nicht eindeutig ermittelt werden (keine Transaktionshistorie verfügbar).";
    }
    return el("div", { class: "card", style: "font-size:12.5px;color:var(--text-muted);display:flex;align-items:center;gap:8px;" }, [
      icon("info", { style: "width:16px;height:16px;flex-shrink:0;" }),
      text,
    ]);
  }

  function buildWaiverPlayerCard(entry) {
    const p = DATA.players[entry.player_id];
    if (!p) return null;
    const st = statusInfo(p);
    const drop = entry.drop_candidate_id ? DATA.players[entry.drop_candidate_id] : null;
    const usage =
      p.position === "RB"
        ? `${fmt1(p.touches_pg)} Touches/Sp.${p.rush_share != null ? ` · ${p.rush_share}% Rushing Share` : ""}`
        : ["WR", "TE"].includes(p.position)
        ? `${fmt1(p.targets_pg)} Targets/Sp.${p.target_share != null ? ` · ${p.target_share}% Target Share` : ""}`
        : null;

    const card = el("div", { class: "player-card", style: "flex-wrap:wrap;align-items:flex-start;cursor:default;" }, [
      el("div", { style: "display:flex;gap:12px;align-items:center;cursor:pointer;", onclick: () => openPlayerDetail(p.id) }, [
        playerAvatar(p, "md"),
        el("div", {}, [
          el("div", { class: "pc-name" }, [p.name, el("span", { class: `status-dot ${st.cls}`, style: "margin-left:6px;", title: st.label })]),
          el("div", { class: "pc-meta" }, [posChip(p.position), ` ${p.team || "FA"} · ${teamAvailability(p)}`]),
        ]),
      ]),
      el("div", { class: "pc-stats" }, [
        el("div", { class: "pc-value" }, fmt1(p.projection_week)),
        el("div", { class: "pc-label" }, "Proj."),
      ]),
    ]);

    const metaRow = el("div", { style: "width:100%;display:flex;gap:14px;flex-wrap:wrap;margin-top:10px;font-size:11.5px;color:var(--text-muted);" }, [
      p.trending_add ? el("span", { style: "display:inline-flex;align-items:center;gap:3px;" }, [icon("trending-up", { style: "width:11px;height:11px;" }), `+${fmtInt(p.trending_add)} Adds`]) : null,
      usage ? el("span", {}, usage) : null,
      entry.high_competition ? el("span", { style: "color:var(--status-warn);font-weight:700;display:inline-flex;align-items:center;gap:3px;" }, [icon("triangle-alert", { style: "width:11px;height:11px;" }), "Hohe Konkurrenz"]) : null,
    ].filter(Boolean));
    if (metaRow.children.length) card.appendChild(metaRow);

    card.appendChild(el("div", { style: "width:100%;margin-top:6px;font-size:12px;color:var(--text-muted);" }, entry.reasons.join(" · ")));
    card.appendChild(
      el("div", { style: "width:100%;margin-top:4px;font-size:12px;color:var(--text-muted);" },
        drop ? ["Drop-Kandidat: ", playerLink(drop.id)] : "Kein klarer Drop-Kandidat auf deiner Bank."
      )
    );
    if (entry.faab_bid) {
      card.appendChild(
        el("div", { style: "width:100%;margin-top:6px;font-size:12.5px;font-weight:700;color:var(--accent);" },
          `Gebotsvorschlag: ${entry.faab_bid.amount} (${entry.faab_bid.pct_of_budget}% des Restbudgets)`
        )
      );
    }
    return card;
  }

  function buildWaiverPositionView(host) {
    host.innerHTML = "";

    const filterBar = el("div", { style: "display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin-bottom:14px;" });
    const posWrap = el("div", { style: "display:flex;gap:6px;flex-wrap:wrap;" });
    [null, ...POSITIONS].forEach((pos) => {
      posWrap.appendChild(
        el(
          "button",
          {
            class: "tab-pill" + (waiverView.posFilter === pos ? " active" : ""),
            onclick: () => {
              waiverView.posFilter = pos;
              buildWaiverPositionView(host);
            },
          },
          pos || "Alle"
        )
      );
    });
    filterBar.appendChild(posWrap);
    const sortSelect = el(
      "select",
      {
        style: "padding:7px 10px;border-radius:8px;border:1px solid var(--card-border);background:var(--bg);color:var(--text);font-size:12.5px;",
        onchange: (e) => {
          waiverView.sortKey = e.target.value;
          buildWaiverPositionView(host);
        },
      },
      [
        el("option", { value: "score", selected: waiverView.sortKey === "score" ? "selected" : null }, "Sortierung: Nutzen"),
        el("option", { value: "trending", selected: waiverView.sortKey === "trending" ? "selected" : null }, "Sortierung: Trending"),
        el("option", { value: "projection", selected: waiverView.sortKey === "projection" ? "selected" : null }, "Sortierung: Projection"),
      ]
    );
    filterBar.appendChild(sortSelect);
    host.appendChild(filterBar);

    const posList = waiverView.posFilter ? [waiverView.posFilter] : POSITIONS;
    let anyEntries = false;
    posList.forEach((pos) => {
      let entries = ((DATA.waiver.by_position && DATA.waiver.by_position[pos]) || []).slice();
      if (!entries.length) return;
      anyEntries = true;
      if (waiverView.sortKey === "trending") {
        entries.sort((a, b) => (DATA.players[b.player_id].trending_add || 0) - (DATA.players[a.player_id].trending_add || 0));
      } else if (waiverView.sortKey === "projection") {
        entries.sort((a, b) => (DATA.players[b.player_id].projection_week || 0) - (DATA.players[a.player_id].projection_week || 0));
      }
      host.appendChild(el("div", { class: "section-label" }, POS_LABELS_DE[pos] || pos));
      host.appendChild(
        el(
          "div",
          { style: "display:flex;flex-direction:column;gap:10px;margin-bottom:8px;" },
          entries.map(buildWaiverPlayerCard).filter(Boolean)
        )
      );
    });
    if (!anyEntries) host.appendChild(el("div", { class: "card empty-state" }, "Keine Waiver-Spieler für diese Auswahl gefunden."));
  }

  function buildWaiverSpecialView(host, tab) {
    host.innerHTML = "";
    let cards = [];
    if (tab === "lineup_upgrade") {
      cards = (DATA.waiver.lineup_upgrades || []).map((e) => {
        const base = buildWaiverPlayerCard({ player_id: e.player_id, reasons: [`+${e.delta} Pkt. ggü. deinem schwächsten Starter diese Woche`], drop_candidate_id: null });
        const rep = DATA.players[e.replaces_player_id];
        if (base && rep) base.appendChild(el("div", { style: "width:100%;margin-top:4px;font-size:12px;color:var(--text-muted);" }, ["Würde ersetzen: ", playerLink(rep.id)]));
        return base;
      });
    } else if (tab === "trending") {
      cards = (DATA.waiver.trending || []).map((id) => {
        const p = DATA.players[id];
        return buildWaiverPlayerCard({ player_id: id, reasons: [`+${fmtInt(p.trending_add)} Adds in den letzten 24h`], drop_candidate_id: _drop_candidate_client(p.position) });
      });
    } else if (tab === "handcuffs") {
      cards = (DATA.waiver.handcuffs || []).map((e) => {
        const starter = DATA.players[e.handcuff_for_player_id];
        return buildWaiverPlayerCard({
          player_id: e.player_id,
          reasons: [`Backup hinter ${starter ? starter.name : "?"}${e.is_mine ? " (dein Starter)" : ""}`],
          drop_candidate_id: _drop_candidate_client("RB"),
        });
      });
    } else if (tab === "ir_stashes") {
      cards = (DATA.waiver.ir_stashes || []).map((e) =>
        buildWaiverPlayerCard({ player_id: e.player_id, reasons: [e.note], drop_candidate_id: null })
      );
    } else if (tab === "breakouts") {
      cards = (DATA.waiver.breakouts || []).map((id) => {
        const p = DATA.players[id];
        return buildWaiverPlayerCard({ player_id: id, reasons: ["Junger Spieler (≤2 Jahre Erfahrung) mit steigender Nutzung/Trending"], drop_candidate_id: _drop_candidate_client(p.position) });
      });
    } else if (tab === "streaming") {
      cards = Object.entries(DATA.waiver.streaming || {}).map(([pos, e]) => {
        const factorNote = e.matchup_factor ? ` (Matchup-Faktor ${e.matchup_factor}×)` : "";
        return buildWaiverPlayerCard({
          player_id: e.player_id,
          reasons: [`Beste${pos === "DEF" ? "" : "r"} ${pos}-Streamer diese Woche${e.opponent ? ` · Gegner ${e.opponent}` : ""}${factorNote}`],
          drop_candidate_id: _drop_candidate_client(pos),
        });
      });
    }
    cards = cards.filter(Boolean);
    if (!cards.length) {
      host.appendChild(el("div", { class: "card empty-state" }, "Keine Daten für diese Kategorie verfügbar."));
      return;
    }
    host.appendChild(el("div", { style: "display:flex;flex-direction:column;gap:10px;" }, cards));
  }

  function _drop_candidate_client(position) {
    const compatible = ["RB", "WR", "TE"].includes(position) ? ["RB", "WR", "TE"] : [position];
    const bench = DATA.my_roster.bench.map((id) => DATA.players[id]).filter((p) => p && compatible.includes(p.position));
    if (!bench.length) return null;
    return bench.reduce((worst, p) => (p.season_avg < worst.season_avg ? p : worst), bench[0]).id;
  }

  function renderWaiver() {
    const frag = el("div", {});
    frag.appendChild(renderHeader());
    frag.appendChild(renderWaiverSystemBanner());

    const weakness = DATA.waiver.position_weakness || {};
    frag.appendChild(
      el("div", { class: "card" }, [
        el("div", { class: "card-title" }, "Deine Roster-Schwächen"),
        el(
          "div",
          { style: "display:flex;gap:16px;flex-wrap:wrap;" },
          POSITIONS.map((pos) => {
            const w = weakness[pos] || 0;
            const level = w > 3 ? "status-bad" : w > 1 ? "status-warn" : "status-good";
            return el("div", { style: "text-align:center;" }, [
              posChip(pos),
              el("div", { style: "font-size:17px;font-weight:800;margin-top:4px;" }, [el("span", { class: `status-dot ${level}` }), " ", w.toFixed(1)]),
            ]);
          })
        ),
        el("div", { class: "empty-state", style: "padding-top:10px;" }, "Höherer Wert = stärkerer Bedarf relativ zum Liga-Durchschnitt."),
      ])
    );

    const tabRow = el("div", { class: "tab-row" });
    const bodyHost = el("div", {});
    function refreshTabs() {
      tabRow.innerHTML = "";
      Object.entries(WAIVER_TABS).forEach(([key, label]) => {
        tabRow.appendChild(
          el(
            "button",
            {
              class: `tab-pill ${waiverView.tab === key ? "active" : ""}`,
              onclick: () => {
                waiverView.tab = key;
                refreshTabs();
                refreshBody();
              },
            },
            label
          )
        );
      });
    }
    function refreshBody() {
      if (waiverView.tab === "position") buildWaiverPositionView(bodyHost);
      else buildWaiverSpecialView(bodyHost, waiverView.tab);
    }
    refreshTabs();
    frag.appendChild(tabRow);
    frag.appendChild(bodyHost);
    refreshBody();

    return frag;
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

    const rest = ((p.team && DATA.team_schedules[p.team]) || []).slice(0, 6);
    const restRow = rest.length
      ? el("div", { style: "display:flex;gap:6px;flex-wrap:wrap;margin-top:6px;" }, rest.map((g) =>
          el("span", { class: "pos-chip", style: "background:var(--card-border);color:var(--text);" }, `W${g.week} ${g.home ? "vs" : "@"} ${g.opponent}`)
        ))
      : el("div", { class: "empty-state" }, "Kein Restprogramm verfügbar.");

    panel.innerHTML = "";
    panel.appendChild(el("div", { class: "panel-drag-handle" }));
    panel.appendChild(el("button", { class: "btn panel-close", onclick: closePlayerDetail }, icon("x")));
    const favBtn = el("button", {
      class: "btn panel-close",
      style: "right:56px;",
      title: isFavorite(pid) ? "Favorit entfernen" : "Als Favorit markieren",
      onclick: () => { toggleFavorite(pid); openPlayerDetail(pid); },
    }, isFavorite(pid) ? icon("star", { fill: "#f5b800", stroke: "#f5b800" }) : icon("star"));
    panel.appendChild(favBtn);
    panel.appendChild(
      el("div", { class: "panel-head" }, [
        playerAvatar(p, "lg"),
        el("div", {}, [
          el("div", { class: "name" }, p.name),
          el("div", { class: "player-meta", style: "margin-top:4px;font-size:12.5px;" }, [posChip(p.position), ` ${p.team || "FA"} · Alter ${p.age ?? "–"} · Bye ${p.bye_week ? "W" + p.bye_week : "–"}`]),
          el("div", { style: "margin-top:6px;font-size:18px;font-weight:800;" }, fmtTradeValue(p.trade_value)),
          el("div", { style: "font-size:10.5px;color:var(--text-muted);text-transform:uppercase;" }, "Trade-Wert"),
        ]),
      ])
    );
    panel.appendChild(
      el("div", { style: "margin-top:10px;display:flex;align-items:center;gap:8px;flex-wrap:wrap;" }, [
        el("span", { class: `status-dot ${st.cls}` }),
        el("span", {}, st.label),
        el("span", { style: "color:var(--text-faint);" }, "·"),
        el("span", {}, teamAvailability(p)),
      ])
    );
    if (p.injury_status) {
      const injuryText =
        (p.injury_body_part ? `Verletzung: ${p.injury_body_part} · ` : "") +
        (p.practice_description ? `Training: ${p.practice_description}` : "Keine Trainingsstatus-Daten verfügbar");
      panel.appendChild(el("div", { style: "font-size:11.5px;color:var(--text-muted);margin-top:4px;" }, injuryText));
    }

    const statGrid = el("div", { class: "grid grid-3", style: "margin-top:14px;" }, [
      statTile("Projektion", fmt1(p.projection_week)),
      statTile("Ø letzte 3", fmt1(p.avg_last3)),
      statTile("Ø Saison", fmt1(p.season_avg)),
      statTile("Trade-Wert", fmtTradeValue(p.trade_value)),
      statTile("Pos-Rang (Wert)", p.trade_pos_rank ? `#${p.trade_pos_rank}` : "–"),
      statTile("Trending", p.trending_add ? `+${fmtInt(p.trending_add)}` : p.trending_drop ? `-${fmtInt(p.trending_drop)}` : "–"),
    ]);
    panel.appendChild(statGrid);

    if (["QB", "RB", "WR", "TE"].includes(p.position)) {
      const usageTiles = [];
      if (p.position === "RB") {
        usageTiles.push(statTile("Rushing Share", p.rush_share != null ? `${p.rush_share}%` : "–"));
        usageTiles.push(statTile("Target Share", p.target_share != null ? `${p.target_share}%` : "–"));
      } else if (p.position === "WR" || p.position === "TE") {
        usageTiles.push(statTile("Target Share", p.target_share != null ? `${p.target_share}%` : "–"));
        usageTiles.push(statTile("Air-Yards-Share", p.air_yards_share != null ? `${p.air_yards_share}%` : "–"));
      }
      usageTiles.push(
        statTile("Snap %", p.snap_pct ? `${p.snap_pct}%` : "–"),
        statTile("Touches/Sp.", fmt1(p.touches_pg)),
        statTile("Red-Zone/Sp.", fmt1(p.redzone_pg)),
        statTile("Spiele", p.games_played ?? "–")
      );
      panel.appendChild(el("div", { class: "section-label" }, "Usage (Ø pro Spiel)"));
      panel.appendChild(el("div", { class: "grid grid-3" }, usageTiles));

      const mates = buildTeammateComparison(p);
      if (mates) {
        panel.appendChild(el("div", { class: "section-label" }, `Vergleich ${p.position === "RB" ? "Backfield" : "Receiver"} (${p.team})`));
        panel.appendChild(mates);
      }
    }

    panel.appendChild(el("div", { class: "section-label" }, "Fantasy-Punkte pro Woche"));
    panel.appendChild(chart);

    panel.appendChild(el("div", { class: "section-label" }, "Trade-Wert-Verlauf"));
    panel.appendChild(buildTradeValueSparkline(p));

    panel.appendChild(el("div", { class: "section-label" }, "Restprogramm"));
    panel.appendChild(restRow);

    const isMine = p.fantasy_team && p.fantasy_team.roster_id === DATA.me.roster_id;
    const tbHost = el("div", { style: "margin-top:16px;" });
    function refreshTradeBlockButtons() {
      tbHost.innerHTML = "";
      const status = tradeBlockStatus(pid);
      const pill = (iconName, label, value) =>
        el(
          "button",
          {
            class: "tab-pill" + (status === value ? " active" : ""),
            style: "display:inline-flex;align-items:center;gap:5px;",
            onclick: () => {
              setTradeBlockStatus(pid, status === value ? null : value);
              refreshTradeBlockButtons();
            },
          },
          [icon(iconName, { style: "width:12px;height:12px;" }), label]
        );
      tbHost.appendChild(el("div", { class: "section-label", style: "margin-top:0;" }, "Trade-Block"));
      const row = el("div", { style: "display:flex;gap:6px;flex-wrap:wrap;" });
      if (isMine) {
        row.appendChild(pill("tag", "Trade-Block", "give"));
        row.appendChild(pill("lock", "Unantastbar", "untouchable"));
      } else {
        row.appendChild(pill("target", "Als Ziel markieren", "target"));
      }
      tbHost.appendChild(row);
    }
    refreshTradeBlockButtons();
    panel.appendChild(tbHost);

    panel.appendChild(el("div", { class: "section-label" }, "Notizen"));
    const noteBox = el("textarea", {
      class: "note-textarea",
      placeholder: "Private Notiz zu diesem Spieler (nur auf diesem Gerät gespeichert)…",
      style: "width:100%;min-height:64px;padding:8px;border-radius:8px;border:1px solid var(--card-border);background:var(--card-bg);color:var(--text);font:inherit;resize:vertical;",
      onchange: (e) => setNote(pid, e.target.value),
    });
    noteBox.value = getNote(pid);
    panel.appendChild(noteBox);

    panel.appendChild(
      el("div", { style: "margin-top:16px;display:flex;gap:8px;flex-wrap:wrap;" }, [
        el("button", { class: "btn", onclick: () => addPlayerToAnalyzer(pid) }, "Zum Trade-Analyzer hinzufügen"),
        el("button", { class: "btn", onclick: () => toggleSavedList("waiverTargets", pid) }, "Als Waiver-Ziel merken"),
        el("button", { class: "btn", onclick: () => { compareState.a = pid; compareState.b = null; compareState.visible = true; closePlayerDetail(); navigateTo("players"); render(); } }, [icon("shuffle", { style: "width:13px;height:13px;" }), "Vergleichen"]),
      ])
    );

    panel.classList.add("open");
    backdrop.classList.add("open");
  }

  function buildTeammateComparison(p) {
    if (!p.team) return null;
    const groupPositions = p.position === "RB" ? ["RB"] : ["WR", "TE"];
    const metric = p.position === "RB" ? "rush_share" : "target_share";
    const mates = Object.values(DATA.players).filter(
      (x) => x.team === p.team && groupPositions.includes(x.position) && x[metric] != null
    );
    if (mates.length < 2) return null;
    mates.sort((a, b) => (b[metric] || 0) - (a[metric] || 0));
    const max = Math.max(...mates.map((m) => m[metric] || 0), 1);
    return el(
      "div",
      {},
      mates.slice(0, 6).map((m) =>
        el("div", { style: "display:flex;align-items:center;gap:8px;margin-bottom:6px;" }, [
          el("div", { style: `width:92px;font-size:11.5px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-weight:${m.id === p.id ? "800" : "400"};` }, m.name),
          el("div", { style: "flex:1;background:var(--accent-soft);border-radius:4px;height:8px;overflow:hidden;" }, [
            el("div", { style: `width:${Math.max(3, (m[metric] / max) * 100)}%;height:100%;background:${m.id === p.id ? "var(--accent)" : "var(--text-faint)"};` }),
          ]),
          el("div", { style: "width:42px;text-align:right;font-size:11px;color:var(--text-muted);" }, `${m[metric]}%`),
        ])
      )
    );
  }

  function buildTradeValueSparkline(p) {
    const points = p.trade_value_history || [];
    if (points.length < 2) {
      return el("div", { class: "empty-state" },
        points.length === 1
          ? `Erster erfasster Wert: ${fmtInt(points[0].value)} (Verlauf baut sich mit künftigen täglichen Läufen auf)`
          : "Noch keine Verlaufsdaten erfasst."
      );
    }
    const vals = points.map((pt) => pt.value);
    const min = Math.min(...vals), max = Math.max(...vals);
    const range = Math.max(1, max - min);
    const w = 280, h = 44;
    const stepX = w / (vals.length - 1);
    const coords = vals.map((v, i) => `${(i * stepX).toFixed(1)},${(h - ((v - min) / range) * h).toFixed(1)}`).join(" ");
    const trendUp = vals[vals.length - 1] >= vals[0];
    const color = trendUp ? "var(--status-good)" : "var(--status-bad)";
    const svgWrap = el("div", {});
    svgWrap.innerHTML = `<svg width="${w}" height="${h}" viewBox="0 0 ${w} ${h}" style="display:block;max-width:100%;"><polyline points="${coords}" fill="none" stroke="${color}" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/></svg>`;
    return el("div", {}, [
      svgWrap,
      el("div", { style: "font-size:11px;color:var(--text-muted);margin-top:4px;" }, `${fmtInt(vals[0])} → ${fmtInt(vals[vals.length - 1])} (${points.length} Läufe)`),
    ]);
  }

  function statTile(label, value) {
    return el("div", { class: "card", style: "padding:12px 10px;text-align:center;margin-bottom:0;" }, [
      el("div", { style: "font-size:19px;font-weight:800;letter-spacing:-0.01em;" }, value),
      el("div", { style: "font-size:10.5px;color:var(--text-muted);text-transform:uppercase;margin-top:2px;" }, label),
    ]);
  }

  function closePlayerDetail() {
    $("#detail-panel").classList.remove("open");
    $("#panel-backdrop").classList.remove("open");
  }

  // Wisch-Geste zum Schließen des Vollbild-Sheets auf dem Handy (nur
  // runter-wischen; seitliches Scrollen von Inhalten bleibt unberührt).
  function setupPanelSwipeToClose() {
    const panel = $("#detail-panel");
    let startY = null;
    let dragging = false;
    panel.addEventListener("touchstart", (e) => {
      if (!panel.classList.contains("open") || window.innerWidth > 860) return;
      if (panel.scrollTop > 2) return; // nur schließen, wenn oben im Panel gewischt wird
      startY = e.touches[0].clientY;
      dragging = true;
      panel.style.transition = "none";
    }, { passive: true });
    panel.addEventListener("touchmove", (e) => {
      if (!dragging || startY === null) return;
      const delta = e.touches[0].clientY - startY;
      if (delta > 0) panel.style.transform = `translateY(${delta}px)`;
    }, { passive: true });
    panel.addEventListener("touchend", (e) => {
      if (!dragging || startY === null) return;
      const delta = (e.changedTouches[0]?.clientY || startY) - startY;
      panel.style.transition = "";
      panel.style.transform = "";
      dragging = false;
      startY = null;
      if (delta > 110) closePlayerDetail();
    });
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
  // Dunkel ist der Standard (siehe styles.css :root); Hell ist eine
  // gleichwertige, explizit gespeicherte Alternative über [data-theme="light"].
  function updateThemeToggleUI() {
    const isLight = document.documentElement.getAttribute("data-theme") === "light";
    const label = $("#theme-toggle-label");
    if (label) label.textContent = isLight ? "Light" : "Dark";
    const btn = $("#theme-toggle");
    if (btn) {
      const oldIcon = btn.querySelector("[data-lucide], svg");
      if (oldIcon) oldIcon.remove();
      btn.prepend(icon(isLight ? "sun" : "moon"));
      refreshIcons();
    }
  }
  function initTheme() {
    let theme = null;
    try { theme = localStorage.getItem("theme"); } catch (e) { /* ignore */ }
    if (theme === "light") document.documentElement.setAttribute("data-theme", "light");
    updateThemeToggleUI();
    $("#theme-toggle").addEventListener("click", () => {
      const isLight = document.documentElement.getAttribute("data-theme") === "light";
      const next = isLight ? "dark" : "light";
      if (next === "light") document.documentElement.setAttribute("data-theme", "light");
      else document.documentElement.removeAttribute("data-theme");
      try { localStorage.setItem("theme", next); } catch (e) { /* ignore */ }
      updateThemeToggleUI();
    });
  }

  // ---------- Boot ----------
  let LOAD_STATE = "loading"; // loading | ready | error

  function renderSkeleton() {
    return el("div", {}, [
      el("div", { class: "skeleton skeleton-block", style: "height:150px;" }),
      el("div", { class: "grid grid-2" }, [
        el("div", { class: "skeleton skeleton-block" }),
        el("div", { class: "skeleton skeleton-block" }),
      ]),
      el("div", { class: "skeleton skeleton-line" }),
      el("div", { class: "skeleton skeleton-line", style: "width:40%;" }),
    ]);
  }

  // Sicherheitsnetz: viele kleine dynamische Updates (Trade-Analyzer-Listen,
  // Trade-Block-Toggles, Live-Tab) rufen refreshIcons() nicht einzeln auf -
  // ein debounced MutationObserver fängt alle neu eingefügten <i data-lucide>
  // Platzhalter zuverlässig ab, ohne jede Stelle einzeln pflegen zu müssen.
  function setupIconObserver() {
    if (!window.MutationObserver) return;
    let scheduled = false;
    const obs = new MutationObserver(() => {
      if (scheduled) return;
      scheduled = true;
      requestAnimationFrame(() => {
        scheduled = false;
        refreshIcons();
      });
    });
    obs.observe(document.body, { childList: true, subtree: true });
  }

  function boot() {
    initTheme();
    setupIconObserver();
    setupPanelSwipeToClose();
    $("#panel-backdrop").addEventListener("click", closePlayerDetail);
    window.addEventListener("hashchange", render);
    render(); // zeigt das Skeleton, während data.json noch lädt

    fetch("data.json")
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then((data) => {
        DATA = data;
        LOAD_STATE = "ready";
        render();
      })
      .catch((err) => {
        console.error("Konnte data.json nicht laden:", err);
        DATA = null;
        LOAD_STATE = "error";
        render();
      });
  }

  document.addEventListener("DOMContentLoaded", boot);
})();
