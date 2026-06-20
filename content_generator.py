#!/usr/bin/env python3
"""
PROJECT OLYMPUS — Content Generator
=====================================
Reads olympus_live.json and generates content_ideas.md
with post-ready insights for Instagram / LinkedIn
"""

import json, os
from datetime import datetime, timezone

def load_json(path):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading {path}: {e}")
        return None

def emoji_flag(code):
    flags = {
        "ESP":"🇪🇸","FRA":"🇫🇷","ENG":"🏴󠁧󠁢󠁥󠁮󠁧󠁿","POR":"🇵🇹","GER":"🇩🇪","BRA":"🇧🇷",
        "ARG":"🇦🇷","NOR":"🇳🇴","CRO":"🇭🇷","JPN":"🇯🇵","SUI":"🇨🇭","NED":"🇳🇱",
        "BEL":"🇧🇪","USA":"🇺🇸","AUT":"🇦🇹","SWE":"🇸🇪","SCO":"🏴󠁧󠁢󠁳󠁣󠁴󠁿","MAR":"🇲🇦",
        "CIV":"🇨🇮","SEN":"🇸🇳","KOR":"🇰🇷","TUR":"🇹🇷","MEX":"🇲🇽","ALG":"🇩🇿",
        "COL":"🇨🇴","EGY":"🇪🇬","COD":"🇨🇩","PAR":"🇵🇾","URU":"🇺🇾","IRN":"🇮🇷",
        "BIH":"🇧🇦","TUN":"🇹🇳","AUS":"🇦🇺","CAN":"🇨🇦","IRQ":"🇮🇶","ZAF":"🇿🇦",
        "QAT":"🇶🇦","CUW":"🇨🇼","CZE":"🇨🇿","CPV":"🇨🇻","NZL":"🇳🇿","ECU":"🇪🇨",
        "UZB":"🇺🇿","HAI":"🇭🇹","KSA":"🇸🇦","GHA":"🇬🇭","JOR":"🇯🇴","PAN":"🇵🇦",
    }
    return flags.get(code, "🏳️")

def arrow(delta):
    if delta > 0: return f"↑ +{delta:.1f}%"
    if delta < 0: return f"↓ {delta:.1f}%"
    return f"→ {delta:.1f}%"

def main():
    live = load_json("olympus_live.json")
    base = load_json("olympus_v2p_results.json")
    if not live or not base:
        print("Missing JSON files — skipping content generation")
        return

    now = datetime.now(timezone.utc).strftime("%B %d, %Y %H:%M UTC")
    meta = live.get("meta", {})
    live_data = live.get("live", {})
    teams = live.get("teams", {})
    base_teams = base.get("teams", {})
    live_ranked = live_data.get("live_ranked", [])
    base_ranked = base.get("ranked", [])
    results = live_data.get("results", [])
    standings = live_data.get("standings", {})
    player_stats = live_data.get("player_stats", [])
    tournament_goals = live_data.get("tournament_goals", {})
    phase = live_data.get("phase", "GROUP_STAGE")
    matches_played = meta.get("matches_completed", 0)

    # Build pre-tournament win% lookup
    pre_win = {r["code"]: r["win"] for r in base_ranked}

    lines = []
    lines.append(f"# 🏆 Project Olympus — Content Ideas")
    lines.append(f"*Auto-generated: {now} · Phase: {phase.replace('_',' ').title()} · {matches_played} matches played*")
    lines.append("")
    lines.append("---")
    lines.append("")

    # ── SECTION 1: WIN PROBABILITY MOVERS ────────────────────────────
    lines.append("## 📈 Biggest Win Probability Movers")
    lines.append("*Compare live model vs pre-tournament prediction*")
    lines.append("")

    deltas = []
    for r in live_ranked:
        code = r["code"]
        live_win = r["win"]
        pre = pre_win.get(code, 0)
        delta = round(live_win - pre, 2)
        name = teams.get(code, {}).get("name", code)
        deltas.append((code, name, live_win, pre, delta))

    risers = sorted(deltas, key=lambda x: -x[4])[:5]
    fallers = sorted(deltas, key=lambda x: x[4])[:5]

    lines.append("### 🚀 Biggest Risers")
    for code, name, live_win, pre, delta in risers:
        if delta <= 0: continue
        lines.append(f"- {emoji_flag(code)} **{name}**: {pre}% → {live_win}% ({arrow(delta)})")
    lines.append("")

    lines.append("### 📉 Biggest Fallers")
    for code, name, live_win, pre, delta in fallers:
        if delta >= 0: continue
        lines.append(f"- {emoji_flag(code)} **{name}**: {pre}% → {live_win}% ({arrow(delta)})")
    lines.append("")

    # ── SECTION 2: CURRENT TOP 5 WIN PROBABILITIES ───────────────────
    lines.append("## 🥇 Current Top 5 to Win the World Cup")
    lines.append("*Live model after real match results*")
    lines.append("")
    top5 = sorted(live_ranked, key=lambda x: -x["win"])[:5]
    for i, r in enumerate(top5, 1):
        code = r["code"]
        name = teams.get(code, {}).get("name", code)
        lines.append(f"{i}. {emoji_flag(code)} **{name}** — {r['win']}% to win · {r['final']}% to reach final · {r['sf']}% semifinal")
    lines.append("")

    # ── SECTION 3: MODEL ACCURACY ─────────────────────────────────────
    lines.append("## 🎯 Model Prediction Accuracy")
    lines.append("")
    correct = 0
    total = 0
    upsets = []
    for r in results:
        pred = r.get("prediction")
        if not pred: continue
        hg, ag = r.get("hg", 0), r.get("ag", 0)
        home, away = r.get("home"), r.get("away")
        if hg > ag:
            actual = "home"
            model_pct = pred["home_win"]
        elif ag > hg:
            actual = "away"
            model_pct = pred["away_win"]
        else:
            actual = "draw"
            model_pct = pred["draw"]

        # Model predicted correctly if its highest probability matched outcome
        home_win_p = pred["home_win"]
        draw_p = pred["draw"]
        away_win_p = pred["away_win"]
        best = max(home_win_p, draw_p, away_win_p)
        if best == home_win_p: predicted = "home"
        elif best == away_win_p: predicted = "away"
        else: predicted = "draw"

        total += 1
        if predicted == actual:
            correct += 1
        else:
            # It's an upset — model was wrong
            hname = teams.get(home, {}).get("name", home)
            aname = teams.get(away, {}).get("name", away)
            upsets.append({
                "home": hname, "away": aname,
                "hg": hg, "ag": ag,
                "home_code": home, "away_code": away,
                "model_pct": round(model_pct, 1),
                "stage": r.get("stage", "")
            })

    if total > 0:
        accuracy = round(correct / total * 100, 1)
        lines.append(f"- **Correct predictions:** {correct}/{total} matches ({accuracy}%)")
        lines.append(f"- **Upsets called wrong:** {total - correct}")
        lines.append("")

    if upsets:
        lines.append("### 😱 Biggest Upsets (model got wrong)")
        upsets_sorted = sorted(upsets, key=lambda x: x["model_pct"])[:5]
        for u in upsets_sorted:
            lines.append(f"- {emoji_flag(u['home_code'])} {u['home']} {u['hg']}–{u['ag']} {u['away']} {emoji_flag(u['away_code'])} · Model only gave this outcome {u['model_pct']}% chance")
        lines.append("")

    # ── SECTION 4: FORM NUDGES (over/underperformers) ────────────────
    lines.append("## 💥 Over & Underperformers vs Model Expectations")
    lines.append("*form_nudge = score adjustment based on actual vs predicted goals*")
    lines.append("")

    nudges = []
    for code, t in teams.items():
        nudge = t.get("form_nudge", 0)
        played = t.get("played", 0)
        if played > 0:
            nudges.append((code, t.get("name", code), nudge, played))

    overperformers = sorted(nudges, key=lambda x: -x[2])[:5]
    underperformers = sorted(nudges, key=lambda x: x[2])[:5]

    lines.append("### ⬆️ Overperforming (better than expected)")
    for code, name, nudge, played in overperformers:
        if nudge <= 0: continue
        lines.append(f"- {emoji_flag(code)} **{name}**: +{nudge:.2f} pts after {played} game{'s' if played > 1 else ''}")
    lines.append("")

    lines.append("### ⬇️ Underperforming (worse than expected)")
    for code, name, nudge, played in underperformers:
        if nudge >= 0: continue
        lines.append(f"- {emoji_flag(code)} **{name}**: {nudge:.2f} pts after {played} game{'s' if played > 1 else ''}")
    lines.append("")

    # ── SECTION 5: TOP SCORERS ────────────────────────────────────────
    lines.append("## ⚽ Golden Boot Race")
    lines.append("")

    # Merge player stats with tournament goals
    scorers = []
    seen = set()
    for p in player_stats:
        pid = str(p.get("id"))
        goals = tournament_goals.get(pid, p.get("goals", 0))
        if goals > 0 and pid not in seen:
            seen.add(pid)
            scorers.append({
                "name": p.get("name", "Unknown"),
                "team_code": p.get("team_code", ""),
                "goals": goals,
                "assists": p.get("assists", 0),
            })

    scorers = sorted(scorers, key=lambda x: (-x["goals"], -x["assists"]))[:10]
    for i, p in enumerate(scorers, 1):
        g_str = f"{p['goals']} goal{'s' if p['goals'] != 1 else ''}"
        a_str = f"{p['assists']} assist{'s' if p['assists'] != 1 else ''}"
        lines.append(f"{i}. {emoji_flag(p['team_code'])} **{p['name']}** — {g_str}, {a_str}")
    lines.append("")

    # ── SECTION 6: GROUP STANDINGS SNAPSHOT ──────────────────────────
    lines.append("## 📊 Group Stage Snapshot")
    lines.append("")
    for grp in sorted(standings.keys()):
        rows = standings[grp]
        if not rows: continue
        has_games = any(r[1].get("played", 0) > 0 for r in rows)
        if not has_games: continue
        lines.append(f"**Group {grp}**")
        for i, (code, s) in enumerate(rows):
            name = teams.get(code, {}).get("name", code)
            marker = "→" if i < 2 else "  "
            lines.append(f"  {marker} {emoji_flag(code)} {name}: {s['pts']}pts · GD {s['gd']:+d} · {s['played']}P")
        lines.append("")

    # ── SECTION 7: READY-TO-POST CAPTIONS ────────────────────────────
    lines.append("---")
    lines.append("")
    lines.append("## ✍️ Ready-to-Post Caption Ideas")
    lines.append("")

    # Caption 1: Top mover
    if risers and risers[0][4] > 0:
        code, name, live_win, pre, delta = risers[0]
        lines.append(f"### Caption 1 — Biggest Riser")
        lines.append(f"```")
        lines.append(f"{emoji_flag(code)} {name} are the biggest movers in our World Cup model.")
        lines.append(f"")
        lines.append(f"Pre-tournament win probability: {pre}%")
        lines.append(f"After {matches_played} matches: {live_win}%")
        lines.append(f"")
        lines.append(f"That's a {delta:+.1f}% swing based on real match data.")
        lines.append(f"")
        lines.append(f"Our model updates after every game using Poisson simulation")
        lines.append(f"& Bayesian score adjustment. 10,000 simulations per update.")
        lines.append(f"")
        lines.append(f"#WC2026 #WorldCup2026 #Football #DataScience #ProjectOlympus")
        lines.append(f"```")
        lines.append("")

    # Caption 2: Accuracy
    if total > 0:
        lines.append(f"### Caption 2 — Model Accuracy")
        lines.append(f"```")
        lines.append(f"📊 {matches_played} matches played at WC2026.")
        lines.append(f"Our model predicted the correct outcome in {correct}/{total} ({accuracy}%).")
        lines.append(f"")
        if upsets_sorted:
            u = upsets_sorted[0]
            lines.append(f"Biggest miss: {emoji_flag(u['home_code'])} {u['home']} {u['hg']}–{u['ag']} {u['away']} {emoji_flag(u['away_code'])}")
            lines.append(f"We only gave that result a {u['model_pct']}% chance.")
        lines.append(f"")
        lines.append(f"That's football. The model learns and adapts after every game.")
        lines.append(f"")
        lines.append(f"#WC2026 #WorldCup #FootballData #MachineLearning #ProjectOlympus")
        lines.append(f"```")
        lines.append("")

    # Caption 3: Top scorers
    if scorers:
        top = scorers[0]
        lines.append(f"### Caption 3 — Golden Boot")
        lines.append(f"```")
        lines.append(f"⚽ Golden Boot race at WC2026 — matchday {matches_played} update")
        lines.append(f"")
        for i, p in enumerate(scorers[:5], 1):
            lines.append(f"{i}. {emoji_flag(p['team_code'])} {p['name']} — {p['goals']}G {p['assists']}A")
        lines.append(f"")
        lines.append(f"#WC2026 #WorldCup2026 #GoldenBoot #Football #ProjectOlympus")
        lines.append(f"```")
        lines.append("")

    # ── WRITE OUTPUT ──────────────────────────────────────────────────
    output = "\n".join(lines)
    with open("content_ideas.md", "w", encoding="utf-8") as f:
        f.write(output)

    print(f"✅ content_ideas.md generated ({len(output)} chars)")
    print(f"   Matches: {matches_played} | Accuracy: {correct}/{total} ({accuracy if total>0 else 0}%) | Top scorer: {scorers[0]['name'] if scorers else 'N/A'}")

if __name__ == "__main__":
    main()
