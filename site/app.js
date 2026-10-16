// Fantasy Dashboard – Vanilla JS SPA (hash-routing, kein Build-Step im Browser)
(() => {
  "use strict";

  const TABS = [
    { id: "overview", label: "Übersicht", icon: "🏠" },
    { id: "roster", label: "Mein Roster", icon: "👤" },
    { id: "startsit", label: "Start/Sit", icon: "🔁" },
    { id: "waiver", label: "Waiver Wire", icon: "📈" },
    { id: "players", label: "Alle Spieler", icon: "📋" },
    { id: "tradefinder", label: "Trade Finder", icon: "🔄" },
    { id: "tradeanalyzer", label: "Trade-Analyzer", icon: "⚖️" },
    { id: "league", label: "Liga", icon: "🏆" },
    { id: "planner", label: "Planer", icon: "🗓️" },
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
    if (!DATA) {
      root.appendChild(renderError("Daten konnten nicht geladen werden."));
      return;
    }
    if (tabId === "overview") root.appendChild(renderOverview());
    else if (tabId === "roster") root.appendChild(renderRoster());
    else if (tabId === "players") root.appendChild(renderPlayers());
    else if (tabId === "waiver") root.appendChild(renderWaiver());
    else if (tabId === "startsit") root.appendChild(renderStartSit());
    else if (tabId === "tradefinder") root.appendChild(renderTradeFinder());
    else if (tabId === "tradeanalyzer") root.appendChild(renderTradeAnalyzer());
    else if (tabId === "league") root.appendChild(renderLeague());
    else if (tabId === "planner") root.appendChild(renderPlanner());
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
      el("div", { class: "header-stat" }, [
        el("div", { class: "value" }, fmt1(me.fpts)),
        el("div", { class: "label" }, "Punkte"),
      ]),
    ];
    if (opts && opts.showPlayoffNote) {
      stats.push(
        el("div", { class: "header-stat" }, [
          el("div", { class: "value", style: "font-size:15px;color:var(--text-faint);" }, "—"),
          el("div", { class: "label" }, "Playoff-Chance (ab Phase 4)"),
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
  function renderOverview() {
    const frag = el("div", {});
    frag.appendChild(renderHeader({ showPlayoffNote: true }));
    frag.appendChild(renderMatchupCard());

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

    const shortAnalysis = matchupShortAnalysis(m);
    if (shortAnalysis) {
      card.appendChild(el("div", { style: "font-size:12.5px;color:var(--text-muted);margin:8px 0 2px;padding:10px 12px;background:var(--accent-soft);border-radius:8px;" }, shortAnalysis));
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
      el("div", { class: "card-title" }, "Sell High / Buy Low"),
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
    const withProposal = DATA.trade_finder.teams.filter((t) => t.proposal).slice(0, 3);
    const body = withProposal.length
      ? el(
          "div",
          { class: "mini-list" },
          withProposal.map((t) => {
            const g = DATA.players[t.proposal.give_player_id];
            const r = DATA.players[t.proposal.get_player_id];
            return el("div", { class: "mini-item", style: "display:block;" }, [
              el("div", {}, [playerLink(g.id), " ⇄ ", playerLink(r.id)]),
              el("div", { class: "reason" }, `mit ${t.team_name}`),
            ]);
          })
        )
      : el("div", { class: "empty-state" }, "Aktuell kein ausgeglichener Vorschlag gefunden.");
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

  // ---------- Alle Spieler ----------
  const POSITIONS = ["QB", "RB", "WR", "TE", "K", "DEF"];
  const playersView = {
    search: "",
    positions: new Set(),
    availability: "all", // all | free | rostered
    injuredOnly: false,
    sortKey: "season_total",
    sortDir: "desc",
  };

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

    frag.appendChild(filterBar);

    const tableHost = el("div", {});
    frag.appendChild(tableHost);

    function renderFilterBar() {
      // Positions-Buttons neu zeichnen (aktiver Zustand)
      const newBar = renderPlayers();
      frag.replaceWith(newBar);
    }

    function refreshTable() {
      tableHost.innerHTML = "";
      tableHost.appendChild(buildPlayersTable());
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
        el("td", {}, playerTag(p.id)),
        el("td", {}, p.position),
        el("td", {}, p.team || "–"),
        el("td", {}, [el("span", { class: `status-dot ${st.cls}` }), " ", p.fantasy_team ? p.fantasy_team.team_name : "Frei"]),
        el("td", {}, fmt1(p.season_total)),
        el("td", {}, fmt1(p.season_avg)),
        el("td", {}, fmt1(p.targets_pg)),
        el("td", {}, p.snap_pct ? `${p.snap_pct}%` : "–"),
        el("td", {}, fmt1(p.touches_pg)),
        el("td", {}, fmt1(p.redzone_pg)),
        el("td", {}, fmt1(p.projection_week)),
        el("td", {}, p.trade_value ? fmtInt(p.trade_value) : "–"),
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
                el("span", {}, p.trade_value ? fmtInt(p.trade_value) : "–"),
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
                  "✕"
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

    function countByPos(ids) {
      const c = {};
      ids.forEach((id) => {
        const p = DATA.players[id];
        if (p) c[p.position] = (c[p.position] || 0) + 1;
      });
      return c;
    }
    const before = countByPos(myCurrentIds);
    const after = countByPos(hypotheticalIds);
    const posRows = POSITIONS.map((pos) =>
      el("div", { style: "text-align:center;" }, [
        posChip(pos),
        el("div", { style: "font-size:13px;margin-top:4px;" }, `${before[pos] || 0} → ${after[pos] || 0}`),
      ])
    );

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
      el("div", { class: "section-label" }, "Positions-Tiefe (vorher → nachher)"),
      el("div", { style: "display:flex;gap:16px;flex-wrap:wrap;" }, posRows),
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
  function renderTradeFinder() {
    const frag = el("div", {});
    frag.appendChild(renderHeader());

    const tf = DATA.trade_finder;
    frag.appendChild(
      el("div", { class: "card" }, [
        el("div", { class: "card-title" }, "Meine Lage"),
        el("div", {}, `Bedarf: ${tf.my_needs.length ? tf.my_needs.join(", ") : "kein akuter Bedarf"}`),
        el("div", { style: "margin-top:6px;font-size:12px;color:var(--text-muted);" }, [
          "Geschützte Schlüsselspieler (werden nie angeboten): ",
          ...tf.key_player_ids.flatMap((id, i) => [i > 0 ? ", " : "", playerLink(id)]),
        ]),
      ])
    );

    tf.teams.forEach((t) => {
      const card = el("div", { class: "card" }, [
        el("div", { style: "display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:6px;" }, [
          el("div", { style: "font-weight:700;" }, t.team_name),
          el("div", { style: "font-size:11.5px;color:var(--text-muted);" }, [
            t.needs.length ? `Bedarf: ${t.needs.join(", ")}` : "kein Bedarf",
            " · ",
            t.surplus.length ? `Überschuss: ${t.surplus.join(", ")}` : "kein Überschuss",
          ]),
        ]),
      ]);
      if (t.proposal) {
        const g = DATA.players[t.proposal.give_player_id];
        const r = DATA.players[t.proposal.get_player_id];
        card.appendChild(
          el("div", { style: "display:flex;align-items:center;justify-content:space-between;margin-top:10px;flex-wrap:wrap;gap:10px;" }, [
            el("div", { style: "display:flex;align-items:center;gap:8px;flex-wrap:wrap;" }, [
              playerTag(g.id, `(${fmtInt(t.proposal.give_value)})`),
              el("span", { style: "color:var(--text-faint);" }, "⇄"),
              playerTag(r.id, `(${fmtInt(t.proposal.get_value)})`),
            ]),
            el(
              "button",
              {
                class: "btn",
                onclick: () => {
                  tradeAnalyzer.give = [g.id];
                  tradeAnalyzer.get = [r.id];
                  navigateTo("tradeanalyzer");
                  render();
                },
              },
              "Im Trade-Analyzer öffnen"
            ),
          ])
        );
      } else {
        card.appendChild(el("div", { class: "empty-state", style: "margin-top:8px;" }, "Kein ausgeglichener 1-für-1-Vorschlag gefunden."));
      }
      frag.appendChild(card);
    });

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
          upcoming.map((wk) =>
            el("div", { class: "card", style: "margin-bottom:0;" }, [
              el("div", { style: "font-weight:800;font-size:14px;margin-bottom:8px;" }, `Woche ${wk}`),
              el(
                "div",
                { style: "display:flex;flex-direction:column;gap:6px;" },
                byeCalendar[String(wk)].map((pid) => el("div", {}, playerLabel(pid)))
              ),
            ])
          )
        )
      );
    }

    return frag;
  }

  // ---------- Start/Sit ----------
  function renderStartSit() {
    const frag = el("div", {});
    frag.appendChild(renderHeader());

    const ss = DATA.start_sit;

    frag.appendChild(el("div", { class: "section-label" }, "Empfohlenes Lineup"));
    const rows = ss.recommended_slots.map((s) => {
      const p = s.player_id ? DATA.players[s.player_id] : null;
      if (!p) {
        return el("tr", {}, [el("td", {}, el("span", { class: "slot-tag" }, s.slot)), el("td", { colspan: "3" }, "–")]);
      }
      const st = statusInfo(p);
      const changed = (ss.decisions || []).some((d) => d.recommended_player_id === p.id);
      return el("tr", { style: changed ? "background:var(--accent-soft);" : "" }, [
        el("td", {}, el("span", { class: "slot-tag" }, s.slot)),
        el("td", {}, [playerTag(p.id), changed ? el("span", { style: "color:var(--accent);font-size:11px;margin-left:6px;", title: "Wechsel empfohlen" }, "NEU") : null].filter(Boolean)),
        el("td", {}, [el("span", { class: `status-dot ${st.cls}` }), ` ${p.team || "FA"} · ${p.matchup_opponent ? "vs " + p.matchup_opponent : ""}`]),
        el("td", {}, fmt1(s.effective_projection)),
      ]);
    });
    frag.appendChild(
      el("div", { class: "card table-wrap" }, [
        el("table", { class: "lineup-table" }, [
          el("thead", {}, el("tr", {}, [el("th", {}, "Slot"), el("th", {}, "Spieler"), el("th", {}, "Team/Gegner"), el("th", {}, "Proj.")])),
          el("tbody", {}, rows),
        ]),
      ])
    );

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
              el("div", { style: `font-weight:800;color:${d.delta >= 0 ? "var(--status-good)" : "var(--status-bad)"};` }, `${d.delta >= 0 ? "+" : ""}${d.delta} Pkt.`),
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
      el("span", { style: "font-size:16px;" }, "🏷️"),
      text,
    ]);
  }

  function buildWaiverPlayerCard(entry) {
    const p = DATA.players[entry.player_id];
    if (!p) return null;
    const st = statusInfo(p);
    const drop = entry.drop_candidate_id ? DATA.players[entry.drop_candidate_id] : null;
    const usage = p.position === "RB" ? `${fmt1(p.touches_pg)} Touches/Sp.` : ["WR", "TE"].includes(p.position) ? `${fmt1(p.targets_pg)} Targets/Sp.` : null;

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
      p.trending_add ? el("span", {}, `📈 +${fmtInt(p.trending_add)} Adds`) : null,
      usage ? el("span", {}, usage) : null,
      entry.high_competition ? el("span", { style: "color:var(--status-warn);font-weight:700;" }, "⚠️ Hohe Konkurrenz") : null,
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

    const rest = (p.rest_of_season || []).slice(0, 6);
    const restRow = rest.length
      ? el("div", { style: "display:flex;gap:6px;flex-wrap:wrap;margin-top:6px;" }, rest.map((g) =>
          el("span", { class: "pos-chip", style: "background:var(--card-border);color:var(--text);" }, `W${g.week} ${g.home ? "vs" : "@"} ${g.opponent}`)
        ))
      : el("div", { class: "empty-state" }, "Kein Restprogramm verfügbar.");

    panel.innerHTML = "";
    panel.appendChild(el("button", { class: "btn panel-close", onclick: closePlayerDetail }, "✕"));
    panel.appendChild(
      el("div", { class: "panel-head" }, [
        playerAvatar(p, "lg"),
        el("div", {}, [
          el("div", { class: "name" }, p.name),
          el("div", { class: "player-meta", style: "margin-top:4px;font-size:12.5px;" }, [posChip(p.position), ` ${p.team || "FA"} · Alter ${p.age ?? "–"} · Bye ${p.bye_week ? "W" + p.bye_week : "–"}`]),
          el("div", { style: "margin-top:6px;font-size:18px;font-weight:800;" }, p.trade_value ? fmtInt(p.trade_value) : "–"),
          el("div", { style: "font-size:10.5px;color:var(--text-muted);text-transform:uppercase;" }, "Trade-Wert"),
        ]),
      ])
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

    if (["QB", "RB", "WR", "TE"].includes(p.position)) {
      panel.appendChild(el("div", { class: "section-label" }, "Usage (Ø pro Spiel)"));
      panel.appendChild(
        el("div", { class: "grid grid-3" }, [
          statTile("Targets", fmt1(p.targets_pg)),
          statTile("Snap %", p.snap_pct ? `${p.snap_pct}%` : "–"),
          statTile("Touches", fmt1(p.touches_pg)),
          statTile("Red-Zone", fmt1(p.redzone_pg)),
          statTile("Air Yards", p.air_yards ? fmtInt(p.air_yards / Math.max(1, p.games_played)) : "–"),
          statTile("Spiele", p.games_played ?? "–"),
        ])
      );
    }

    panel.appendChild(el("div", { class: "section-label" }, "Fantasy-Punkte pro Woche"));
    panel.appendChild(chart);

    panel.appendChild(el("div", { class: "section-label" }, "Restprogramm"));
    panel.appendChild(restRow);

    panel.appendChild(
      el("div", { style: "margin-top:16px;display:flex;gap:8px;flex-wrap:wrap;" }, [
        el("button", { class: "btn", onclick: () => addPlayerToAnalyzer(pid) }, "Zum Trade-Analyzer hinzufügen"),
        el("button", { class: "btn", onclick: () => toggleSavedList("waiverTargets", pid) }, "Als Waiver-Ziel merken"),
      ])
    );

    panel.classList.add("open");
    backdrop.classList.add("open");
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
