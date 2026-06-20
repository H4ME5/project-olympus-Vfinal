#!/usr/bin/env python3
"""
PROJECT OLYMPUS - LIVE UPDATER (Official API-Football v3)
==========================================================
Uses v3.football.api-sports.io — official API-Football Pro plan
Required GitHub secret: APIFOOTBALL_KEY
"""

import os, json, sys, numpy as np
from datetime import datetime, timezone, timedelta, date
from collections import defaultdict
import urllib.request

np.random.seed(int(datetime.now().timestamp()) % 999999)

API_KEY  = os.environ.get('APIFOOTBALL_KEY', '')
API_HOST = 'v3.football.api-sports.io'
BASE_URL = 'https://' + API_HOST
WC_ID    = 1
SEASON   = 2026

CACHE_PLAYERS = 'cache_players.json'
CACHE_EVENTS  = 'cache_events.json'
CACHE_LINEUPS = 'cache_lineups.json'
PLAYER_CACHE_TTL_MINUTES = 60

print('  API key present: ' + str(bool(API_KEY)) + ' | length: ' + str(len(API_KEY)))

# ── Official FIFA Annex C slot definitions ────────────────────────────
ANNEX_C_SLOTS = [
    "3ABCDF",  # B1 — faces 1E
    "3CDFGH",  # B2 — faces 1I
    "3AEHIJ",  # B3 — faces 1G
    "3BEFIJ",  # B4 — faces 1D
    "3CEFHI",  # B5 — faces 1A
    "3EHIJK",  # B6 — faces 1L
    "3EFGIJ",  # B7 — faces 1B
    "3DEIJL",  # B8 — faces 1K
]

# Official FIFA R32 pairings
R32_PAIRS = [
    ("1E","B1"), ("1I","B2"), ("2A","2B"), ("1F","2C"),
    ("2K","2L"), ("1H","2J"), ("1D","B4"), ("1G","B3"),
    ("1C","2F"), ("2E","2I"), ("1A","B5"), ("1L","B6"),
    ("1J","2H"), ("2D","2G"), ("1B","B7"), ("1K","B8"),
]

def assign_annex_c(b8_teams):
    """
    Assign 8 best-third teams to B1-B8 slots per FIFA Annex C.
    Each team appears in exactly ONE slot.
    """
    assigned = {}
    used_codes = set()
    for i, slot_groups_str in enumerate(ANNEX_C_SLOTS):
        slot = f"B{i+1}"
        allowed = set(slot_groups_str[1:])
        for t in b8_teams:
            if t['grp'] in allowed and t['code'] not in used_codes:
                assigned[slot] = t['code']
                used_codes.add(t['code'])
                break
        if slot not in assigned:
            assigned[slot] = None
    return assigned

# ── API helper ────────────────────────────────────────────────────────
def api_get(path):
    if not API_KEY:
        print('No API key — skipping')
        return None
    try:
        req = urllib.request.Request(
            BASE_URL + path,
            headers={
                'x-apisports-key': API_KEY,
                'x-apisports-host': API_HOST,
            }
        )
        resp = urllib.request.urlopen(req, timeout=15)
        data = json.loads(resp.read())
        errors = data.get('errors', {})
        if errors:
            print('  API errors: ' + str(errors))
            return None
        return data.get('response', [])
    except Exception as e:
        print('API error ' + path + ': ' + str(e))
        return None

def parse_utc(s):
    if not s: return None
    try:
        return datetime.fromisoformat(str(s).replace('Z', '+00:00'))
    except:
        return None

# ── Team name → 3-letter code ─────────────────────────────────────────
NAME_MAP = {
    'Spain':'ESP','England':'ENG','Germany':'GER','France':'FRA',
    'Portugal':'POR','Brazil':'BRA','Argentina':'ARG','Netherlands':'NED',
    'Japan':'JPN','Norway':'NOR','United States':'USA','Austria':'AUT',
    'Colombia':'COL','Uruguay':'URU','Turkey':'TUR','Turkiye':'TUR',
    'Croatia':'CRO','Switzerland':'SUI','Scotland':'SCO','Mexico':'MEX',
    'Belgium':'BEL','Senegal':'SEN','Morocco':'MAR','Sweden':'SWE',
    'Canada':'CAN','Egypt':'EGY','Ghana':'GHA','Czech Republic':'CZE',
    'Czechia':'CZE',"Ivory Coast":'CIV',"Cote d'Ivoire":'CIV',
    'Ecuador':'ECU','Iran':'IRN','South Korea':'KOR','Korea Republic':'KOR',
    'Algeria':'ALG','Australia':'AUS','Paraguay':'PAR',
    'Bosnia':'BIH','Bosnia and Herzegovina':'BIH','Bosnia & Herzegovina':'BIH',
    'South Africa':'ZAF','Panama':'PAN','DR Congo':'COD','Congo DR':'COD',
    'Uzbekistan':'UZB','Iraq':'IRQ','Jordan':'JOR','Qatar':'QAT',
    'Saudi Arabia':'KSA','Cape Verde':'CPV','Tunisia':'TUN',
    'New Zealand':'NZL','Curacao':'CUW','Curaçao':'CUW','Haiti':'HAI',
    'Cape Verde Islands':'CPV','Türkiye':'TUR',
    'United States':'USA','USA':'USA','Paraguay':'PAR','Australia':'AUS',
    'Korea Republic':'KOR','South Korea':'KOR','IR Iran':'IRN','Iran':'IRN',
    'Ivory Coast':'CIV',"Cote d'Ivoire":'CIV',"Côte d'Ivoire":'CIV',
}
def name_to_code(name):
    if not name: return None
    return NAME_MAP.get(str(name).strip())

# ── Cache helpers ─────────────────────────────────────────────────────
def load_cache(path):
    try:
        with open(path) as f:
            return json.load(f)
    except:
        return {}

def save_cache(path, data):
    try:
        with open(path, 'w') as f:
            json.dump(data, f, separators=(',', ':'))
    except Exception as e:
        print(f'  Cache write error {path}: {e}')

def cache_is_fresh(cache, ttl_minutes):
    ts = cache.get('_timestamp')
    if not ts:
        return False
    age = (datetime.now(timezone.utc) - parse_utc(ts)).total_seconds() / 60
    return age < ttl_minutes

# ── Fetch fixtures ────────────────────────────────────────────────────
def fetch_fixtures():
    data = api_get(f'/fixtures?league={WC_ID}&season={SEASON}')
    if not data:
        print('  No data returned from API')
        return []
    print(f'  Raw fixtures returned: {len(data)}')
    return data

# ── Fetch lineups ─────────────────────────────────────────────────────
def fetch_lineups_raw(fixture_id):
    data = api_get(f'/fixtures/lineups?fixture={fixture_id}')
    if not data or not isinstance(data, list):
        return None
    lineups = []
    for team_data in data:
        team = team_data.get('team', {})
        players = []
        for p in team_data.get('startXI', []):
            pi = p.get('player', {})
            players.append({
                'id':     pi.get('id'),
                'name':   pi.get('name', ''),
                'number': pi.get('number'),
                'pos':    pi.get('pos', ''),
                'grid':   pi.get('grid', ''),
            })
        lineups.append({
            'team_name': team.get('name', ''),
            'team_code': name_to_code(team.get('name', '')),
            'formation': team_data.get('formation', ''),
            'players':   players,
        })
    return lineups

def get_lineups_cached(finished, live_now):
    cache = load_cache(CACHE_LINEUPS)
    newly_fetched = 0
    for fx in finished:
        fid = str(fx.get('fixture_id'))
        if not fid or fid == 'None': continue
        if fid in cache:
            cache[fid]['hg'] = fx['hg']; cache[fid]['ag'] = fx['ag']
            cache[fid]['live'] = False; continue
        lu = fetch_lineups_raw(fx['fixture_id'])
        if lu and len(lu) == 2 and any(len(t.get('players', [])) > 0 for t in lu):
            cache[fid] = {'home': fx['home'], 'away': fx['away'],
                'hg': fx['hg'], 'ag': fx['ag'], 'stage': fx['stage'],
                'date': fx['date'], 'live': False, 'lineups': lu,
                'fixture_id': fx['fixture_id']}
            newly_fetched += 1
            print(f'  Lineup cached: {fx["home_name"]} vs {fx["away_name"]}')
    for fx in live_now:
        fid = str(fx.get('fixture_id'))
        if not fid or fid == 'None': continue
        if fid in cache:
            cache[fid]['hg'] = fx['hg']; cache[fid]['ag'] = fx['ag']
            cache[fid]['live'] = True; continue
        lu = fetch_lineups_raw(fx['fixture_id'])
        if lu and len(lu) == 2 and any(len(t.get('players', [])) > 0 for t in lu):
            cache[fid] = {'home': fx['home'], 'away': fx['away'],
                'hg': fx['hg'], 'ag': fx['ag'], 'stage': fx['stage'],
                'date': fx['date'], 'live': True, 'lineups': lu,
                'fixture_id': fx['fixture_id']}
            newly_fetched += 1
            print(f'  Live lineup cached: {fx["home_name"]} vs {fx["away_name"]}')
    save_cache(CACHE_LINEUPS, cache)
    if newly_fetched > 0:
        print(f'  Lineups: fetched {newly_fetched} new, {len(cache)} total cached')
    else:
        print(f'  Lineups: all {len(cache)} from cache (0 API calls)')
    return list(cache.values())

# ── Fetch events ──────────────────────────────────────────────────────
def fetch_match_events(fixture_id):
    data = api_get(f'/fixtures/events?fixture={fixture_id}&type=Goal')
    if not data or not isinstance(data, list): return []
    events = []
    for e in data:
        player = e.get('player', {}); team = e.get('team', {})
        events.append({
            'minute':      e.get('time', {}).get('elapsed', 0),
            'player_name': player.get('name', ''),
            'player_id':   player.get('id'),
            'team_name':   team.get('name', ''),
            'detail':      e.get('detail', 'Normal Goal'),
        })
    return events

def build_tournament_goals(all_events):
    goals = {}
    for ev in all_events:
        pid = ev.get('player_id')
        if pid and ev.get('detail') != 'Own Goal':
            goals[str(pid)] = goals.get(str(pid), 0) + 1
    return goals

def get_all_events_cached(finished, live_now):
    cache = load_cache(CACHE_EVENTS)
    all_events = []; newly_fetched = 0
    for fx in finished:
        fid = str(fx.get('fixture_id'))
        if not fid or fid == 'None': continue
        if fid in cache: all_events.extend(cache[fid])
        else:
            events = fetch_match_events(fx['fixture_id'])
            cache[fid] = events; all_events.extend(events); newly_fetched += 1
    for fx in live_now:
        fid = str(fx.get('fixture_id'))
        if not fid or fid == 'None': continue
        events = fetch_match_events(fx['fixture_id'])
        cache[fid] = events; all_events.extend(events); newly_fetched += 1
    if newly_fetched > 0:
        save_cache(CACHE_EVENTS, cache)
        print(f'  Events: fetched {newly_fetched} new fixtures, {len(cache)} total cached')
    else:
        print(f'  Events: all {len(cache)} fixtures from cache (0 API calls)')
    return all_events

# ── Player stats ──────────────────────────────────────────────────────
def parse_player_item(item):
    player = item.get('player', {}); stats = item.get('statistics', [{}])[0]
    games = stats.get('games', {}); goals = stats.get('goals', {})
    cards = stats.get('cards', {}); passes = stats.get('passes', {})
    shots = stats.get('shots', {}); dribbles = stats.get('dribbles', {})
    team_name = stats.get('team', {}).get('name', '')
    return {
        'id': player.get('id'), 'name': player.get('name', ''),
        'nationality': player.get('nationality', ''), 'photo': player.get('photo', ''),
        'team_name': team_name, 'team_code': name_to_code(team_name),
        'appearances': games.get('appearences') or 0,
        'minutes': games.get('minutes') or 0,
        'rating': round(float(games.get('rating')), 1) if games.get('rating') else None,
        'goals': goals.get('total') or 0, 'assists': goals.get('assists') or 0,
        'yellow_cards': cards.get('yellow') or 0,
        'red_cards': (cards.get('red') or 0) + (cards.get('yellowred') or 0),
        'shots_total': shots.get('total') or 0, 'shots_on': shots.get('on') or 0,
        'key_passes': passes.get('key') or 0, 'pass_accuracy': passes.get('accuracy') or 0,
        'dribbles': dribbles.get('success') or 0,
    }

def get_player_stats_cached():
    cache = load_cache(CACHE_PLAYERS)
    if cache_is_fresh(cache, PLAYER_CACHE_TTL_MINUTES):
        players = cache.get('players', [])
        print(f'  Player stats: {len(players)} from cache (skipping API calls)')
        return players
    print('  Player stats cache stale/missing — fetching from API...')
    all_players = []
    for page in range(1, 16):
        data = api_get(f'/players?league={WC_ID}&season={SEASON}&page={page}')
        if not data or not isinstance(data, list):
            data = api_get(f'/players?league={WC_ID}&season={SEASON}&page={page}')
            if not data or not isinstance(data, list): continue
        if len(data) == 0: break
        for item in data:
            p = parse_player_item(item)
            if p['appearances'] > 0: all_players.append(p)
    top_scorers_data = api_get(f'/players/topscorers?league={WC_ID}&season={SEASON}')
    if top_scorers_data and isinstance(top_scorers_data, list):
        existing_ids = {p['id'] for p in all_players}
        added = 0
        for item in top_scorers_data:
            p = parse_player_item(item)
            if p['id'] in existing_ids:
                for existing in all_players:
                    if existing['id'] == p['id'] and p['goals'] > existing['goals']:
                        existing['goals'] = p['goals']; existing['assists'] = p['assists']
                continue
            if p['goals'] == 0: continue
            all_players.append(p); added += 1
        print(f'  Top scorers: added {added} new players')
    print(f'  Total players fetched: {len(all_players)}')
    save_cache(CACHE_PLAYERS, {'_timestamp': datetime.now(timezone.utc).isoformat(), 'players': all_players})
    return all_players

def merge_goals_into_stats(player_stats, tournament_goals, all_events):
    event_player_info = {}
    for ev in all_events:
        pid = ev.get('player_id')
        if pid and ev.get('detail') != 'Own Goal':
            event_player_info[str(pid)] = {
                'name': ev.get('player_name', ''), 'team_name': ev.get('team_name', ''),
                'team_code': name_to_code(ev.get('team_name', '')),
            }
    existing_ids = {}
    for p in player_stats:
        existing_ids[str(p['id'])] = p
        pid_str = str(p['id'])
        if pid_str in tournament_goals:
            if tournament_goals[pid_str] > p['goals']:
                p['goals'] = tournament_goals[pid_str]
    added = 0
    for pid_str, goal_count in tournament_goals.items():
        if pid_str not in existing_ids and goal_count > 0:
            info = event_player_info.get(pid_str, {})
            player_stats.append({
                'id': int(pid_str) if pid_str.isdigit() else pid_str,
                'name': info.get('name', f'Player {pid_str}'),
                'nationality': '', 'photo': '',
                'team_name': info.get('team_name', ''), 'team_code': info.get('team_code'),
                'appearances': 1, 'minutes': 0, 'rating': None,
                'goals': goal_count, 'assists': 0, 'yellow_cards': 0, 'red_cards': 0,
                'shots_total': 0, 'shots_on': 0, 'key_passes': 0, 'pass_accuracy': 0, 'dribbles': 0,
            })
            added += 1
    if added: print(f'  Merged {added} live-match scorers into player stats')
    return player_stats

# ── Match engine ──────────────────────────────────────────────────────
BASE_GOALS = 1.35
EXP = 1.15

def get_lambdas(home, away, teams):
    hd = teams[home]; ad = teams[away]
    h_att = ((hd['P2']*0.50+hd['P1']*0.28+hd['P3']*0.12+hd['P4']*0.10)/100)**EXP
    a_def = ((ad['P1']*0.50+ad['P2']*0.22+ad['P4']*0.18+ad['P3']*0.10)/100)**EXP
    a_att = ((ad['P2']*0.50+ad['P1']*0.28+ad['P3']*0.12+ad['P4']*0.10)/100)**EXP
    h_def = ((hd['P1']*0.50+hd['P2']*0.22+hd['P4']*0.18+hd['P3']*0.10)/100)**EXP
    return max(0.1, BASE_GOALS*h_att/max(a_def,0.1)), max(0.1, BASE_GOALS*a_att/max(h_def,0.1))

def sim_match(home, away, teams):
    lh, la = get_lambdas(home, away, teams)
    hg = np.random.poisson(lh); ag = np.random.poisson(la)
    if hg > ag: return home
    if ag > hg: return away
    return home if np.random.random() < 0.5 else away

def predict_match(home, away, base_teams):
    if home not in base_teams or away not in base_teams: return None
    lh, la = get_lambdas(home, away, base_teams)
    N = 50000
    hg = np.random.poisson(lh, N); ag = np.random.poisson(la, N)
    return {
        'home_win': round(int(np.sum(hg > ag)) / N * 100, 1),
        'draw':     round(int(np.sum(hg == ag)) / N * 100, 1),
        'away_win': round(int(np.sum(ag > hg)) / N * 100, 1),
        'exp_home': round(lh, 2), 'exp_away': round(la, 2),
    }

def add_predictions_to_results(results, base_teams):
    enriched = []
    for r in results:
        r2 = dict(r)
        if r.get('finished') or not r.get('live', False):
            pred = predict_match(r['home'], r['away'], base_teams)
            if pred: r2['prediction'] = pred
        enriched.append(r2)
    return enriched

# ── LIVE MONTE CARLO TOURNAMENT SIMULATOR ────────────────────────────
def simulate_group(codes, teams, known_results):
    pts = defaultdict(int); gd = defaultdict(int); gf_ = defaultdict(int)
    played_pairs = set()
    for h, a, hg, ag in known_results:
        if h not in codes or a not in codes: continue
        played_pairs.add((h, a))
        gf_[h] += hg; gd[h] += hg-ag; gf_[a] += ag; gd[a] += ag-hg
        if hg > ag: pts[h] += 3
        elif ag > hg: pts[a] += 3
        else: pts[h] += 1; pts[a] += 1
    for i, h in enumerate(codes):
        for a in codes[i+1:]:
            if (h,a) in played_pairs or (a,h) in played_pairs: continue
            if h not in teams or a not in teams: continue
            lh, la = get_lambdas(h, a, teams)
            hg = np.random.poisson(lh); ag = np.random.poisson(la)
            gf_[h] += hg; gd[h] += hg-ag; gf_[a] += ag; gd[a] += ag-hg
            if hg > ag: pts[h] += 3
            elif ag > hg: pts[a] += 3
            else: pts[h] += 1; pts[a] += 1
    return sorted(codes, key=lambda c: (-pts[c], -gd[c], -gf_[c]))

def run_live_tournament_sims(N, updated_teams, base_groups, finished_fixtures, r32_slots):
    group_results = defaultdict(list)
    for fx in finished_fixtures:
        h, a = fx['home'], fx['away']
        if not h or not a: continue
        if 'Group' not in fx.get('stage', ''): continue
        for grp, teams in base_groups.items():
            codes = [t['code'] for t in teams]
            if h in codes and a in codes:
                group_results[grp].append((h, a, fx['hg'], fx['ag'])); break

    wins = defaultdict(int); finals = defaultdict(int)
    sfs  = defaultdict(int); qfs    = defaultdict(int)
    r16s = defaultdict(int); advs   = defaultdict(int)

    # Appearance tracking per slot (for R32 non-B slots)
    r32_slot_appearances = defaultdict(lambda: defaultdict(int))
    # Winner tracking per slot (for deterministic chain)
    r32_winner_counts = defaultdict(lambda: defaultdict(int))
    r16_winner_counts = defaultdict(lambda: defaultdict(int))
    qf_winner_counts  = defaultdict(lambda: defaultdict(int))
    sf_winner_counts  = defaultdict(lambda: defaultdict(int))
    final_winner_counts = defaultdict(int)

    # ── NEW: track most likely 3rd-place team per group ──────────────
    # third_place_counts[grp][code] = number of sims where code finished 3rd in grp
    third_place_counts = defaultdict(lambda: defaultdict(int))

    for _ in range(N):
        # ── Group stage ────────────────────────────────────────────
        group_standings = {}; all_thirds = []
        for grp, teams in base_groups.items():
            codes = [t['code'] for t in teams]
            standing = simulate_group(codes, updated_teams, group_results[grp])
            group_standings[grp] = standing
            third_code = standing[2]
            third_place_counts[grp][third_code] += 1
            all_thirds.append({
                'code': third_code, 'grp': grp,
                'score': updated_teams.get(third_code, {}).get('score', 0),
            })

        b8 = sorted(all_thirds, key=lambda t: -t['score'])[:8]
        for grp, standing in group_standings.items():
            advs[standing[0]] += 1; advs[standing[1]] += 1
            if standing[2] in {t['code'] for t in b8}: advs[standing[2]] += 1

        slot_map = {}
        for grp, standing in group_standings.items():
            slot_map[f'1{grp}'] = standing[0]
            slot_map[f'2{grp}'] = standing[1]

        b_assigned = assign_annex_c(b8)
        for slot, code in b_assigned.items():
            if code: slot_map[slot] = code

        # ── R32 ────────────────────────────────────────────────────
        r32_winners = []
        for si, slot in enumerate(r32_slots):
            h = slot_map.get(slot['home_slot'])
            a = slot_map.get(slot['away_slot'])
            if not h or not a or h not in updated_teams or a not in updated_teams:
                w = h or a; r32_winners.append(w)
                if w: r32_slot_appearances[si][w] += 1; r32_winner_counts[si][w] += 1
                continue
            r16s[h] += 1; r16s[a] += 1
            r32_slot_appearances[si][h] += 1; r32_slot_appearances[si][a] += 1
            winner = sim_match(h, a, updated_teams)
            r32_winners.append(winner)
            r32_winner_counts[si][winner] += 1

        # ── R16 ────────────────────────────────────────────────────
        r16_winners = []
        for i in range(0, 16, 2):
            h = r32_winners[i]; a = r32_winners[i+1]; si = i // 2
            if not h or not a:
                w = h or a; r16_winners.append(w)
                if w: r16_winner_counts[si][w] += 1
                continue
            qfs[h] += 1; qfs[a] += 1
            winner = sim_match(h, a, updated_teams)
            r16_winners.append(winner)
            r16_winner_counts[si][winner] += 1

        # ── QF ─────────────────────────────────────────────────────
        qf_winners = []
        for i in range(0, 8, 2):
            h = r16_winners[i]; a = r16_winners[i+1]; si = i // 2
            if not h or not a:
                w = h or a; qf_winners.append(w)
                if w: qf_winner_counts[si][w] += 1
                continue
            sfs[h] += 1; sfs[a] += 1
            winner = sim_match(h, a, updated_teams)
            qf_winners.append(winner)
            qf_winner_counts[si][winner] += 1

        # ── SF ─────────────────────────────────────────────────────
        sf_winners = []
        for i in range(0, 4, 2):
            h = qf_winners[i]; a = qf_winners[i+1]; si = i // 2
            if not h or not a:
                w = h or a; sf_winners.append(w)
                if w: sf_winner_counts[si][w] += 1
                continue
            finals[h] += 1; finals[a] += 1
            winner = sim_match(h, a, updated_teams)
            sf_winners.append(winner)
            sf_winner_counts[si][winner] += 1

        # ── Final ──────────────────────────────────────────────────
        if len(sf_winners) >= 2 and sf_winners[0] and sf_winners[1]:
            h = sf_winners[0]; a = sf_winners[1]
            champion = sim_match(h, a, updated_teams)
            wins[champion] += 1
            final_winner_counts[champion] += 1

    # Convert to percentages
    results = {}
    for code in updated_teams:
        results[code] = {
            'win':   round(wins[code]   / N * 100, 2),
            'final': round(finals[code] / N * 100, 2),
            'sf':    round(sfs[code]    / N * 100, 2),
            'qf':    round(qfs[code]    / N * 100, 2),
            'r16':   round(r16s[code]   / N * 100, 2),
            'adv':   round(advs[code]   / N * 100, 2),
        }

    def top_winner(d):
        """Most frequent winner in a slot dict."""
        if not d: return None
        w = max(d, key=d.get)
        return {'code': w, 'pct': round(d[w] / N * 100, 1)}

    def top2_appearances(slot_dict, slot_idx):
        """Top 2 teams that appeared in a slot (for R32 non-B cards)."""
        d = slot_dict[slot_idx]
        if not d: return None, None
        sorted_teams = sorted(d.items(), key=lambda x: -x[1])
        t1 = {'code': sorted_teams[0][0], 'pct': round(sorted_teams[0][1]/N*100,1)}
        t2 = {'code': sorted_teams[1][0], 'pct': round(sorted_teams[1][1]/N*100,1)} if len(sorted_teams) > 1 else None
        return t1, t2

    def h2h_pct(code_a, code_b, teams_dict):
        """Compute head-to-head win% for code_a vs code_b using the model."""
        if not code_a or not code_b: return 50.0
        if code_a not in teams_dict or code_b not in teams_dict: return 50.0
        lh, la = get_lambdas(code_a, code_b, teams_dict)
        import math
        def pmf(k, lam):
            return math.exp(-lam) * (lam**k) / math.factorial(k)
        hw = 0.0; dw = 0.0; aw = 0.0
        for g in range(8):
            for ga in range(8):
                p = pmf(g, lh) * pmf(ga, la)
                if g > ga: hw += p
                elif g == ga: dw += p
                else: aw += p
        tot = hw + dw + aw
        return round(hw / tot * 100, 1) if tot > 0 else 50.0

    def make_card(slot_name, h_code, a_code, teams_dict):
        """Build a bracket card with H2H win% and determine winner."""
        if not h_code and not a_code:
            return {'slot': slot_name, 'home': None, 'away': None, 'winner': None}
        if not h_code:
            return {'slot': slot_name, 'home': None,
                    'away': {'code': a_code, 'pct': 100.0},
                    'winner': {'code': a_code, 'pct': 100.0}}
        if not a_code:
            return {'slot': slot_name,
                    'home': {'code': h_code, 'pct': 100.0},
                    'away': None, 'winner': {'code': h_code, 'pct': 100.0}}
        h_pct = h2h_pct(h_code, a_code, teams_dict)
        a_pct = round(100.0 - h_pct, 1)
        winner_code = h_code if h_pct >= 50.0 else a_code
        winner_pct  = h_pct if h_pct >= 50.0 else a_pct
        return {
            'slot': slot_name,
            'home': {'code': h_code, 'pct': h_pct},
            'away': {'code': a_code, 'pct': a_pct},
            'winner': {'code': winner_code, 'pct': round(winner_pct, 1)},
        }

    # ── Resolve most likely team per slot for R32 display ────────────
    #
    # FIX: B-slots (third-place slots) must use the most likely actual
    # 3rd-place team from each eligible group, NOT raw slot appearance
    # counts. Raw appearances were incorrectly promoting teams whose
    # modal position is 1st or 2nd (e.g. URU showing as a third-placer
    # despite 61% chance of finishing 2nd in Group H).
    #
    # For each B-slot, we:
    #   1. Find the eligible groups per Annex C
    #   2. For each eligible group, find the most likely 3rd-place team
    #   3. Rank those candidates by their score (same as assign_annex_c)
    #   4. Assign greedily, no team used twice

    def resolve_b_slots(base_groups, updated_teams, third_place_counts, N):
        """
        For each B1-B8 slot, determine the most likely third-place team
        using per-group third-place frequency counts rather than slot
        appearance counts.
        Returns dict: {'B1': {'code': ..., 'pct': ...}, ...}
        """
        # For each group, find the most likely 3rd-place team and their pct
        most_likely_third = {}
        for grp in base_groups:
            counts = third_place_counts[grp]
            if not counts:
                continue
            best_code = max(counts, key=counts.get)
            best_pct = round(counts[best_code] / N * 100, 1)
            most_likely_third[grp] = {'code': best_code, 'pct': best_pct,
                                       'score': updated_teams.get(best_code, {}).get('score', 0)}

        # Now assign to B-slots using Annex C rules, greedy, no repeat
        assigned = {}
        used_codes = set()
        for i, slot_groups_str in enumerate(ANNEX_C_SLOTS):
            slot = f"B{i+1}"
            allowed_groups = list(slot_groups_str[1:])
            # Candidates: most likely 3rd from each allowed group, sorted by score desc
            candidates = []
            for grp in allowed_groups:
                if grp in most_likely_third:
                    c = most_likely_third[grp]
                    if c['code'] not in used_codes:
                        candidates.append({'grp': grp, **c})
            candidates.sort(key=lambda x: -x['score'])
            if candidates:
                winner = candidates[0]
                assigned[slot] = {'code': winner['code'], 'pct': winner['pct']}
                used_codes.add(winner['code'])
            else:
                assigned[slot] = None
        return assigned

    b_slot_display = resolve_b_slots(base_groups, updated_teams, third_place_counts, N)

    # ── Build R32 slot→team lookup for display ────────────────────────
    # For non-B slots (1X, 2X), use top2_appearances as before.
    # For B slots, use b_slot_display.

    # Map r32_slots index to slot strings
    r32_slot_strings = [(slot['home_slot'], slot['away_slot']) for slot in r32_slots]

    def resolve_r32_side(slot_str, slot_appearances, slot_idx, b_slot_display):
        """Resolve a single side of an R32 matchup for display."""
        if slot_str.startswith('B'):
            entry = b_slot_display.get(slot_str)
            if entry:
                return {'code': entry['code'], 'pct': entry['pct']}
            return None
        else:
            # 1X or 2X slot — use appearance counts
            d = slot_appearances[slot_idx]
            if not d: return None
            best = max(d, key=d.get)
            return {'code': best, 'pct': round(d[best] / N * 100, 1)}

    # Build R32 cards
    r32_cards = []
    for i, slot in enumerate(r32_slots):
        h_str = slot['home_slot']
        a_str = slot['away_slot']
        h_display = resolve_r32_side(h_str, r32_slot_appearances, i, b_slot_display)
        a_display  = resolve_r32_side(a_str, r32_slot_appearances, i, b_slot_display)
        h_code = h_display['code'] if h_display else None
        a_code = a_display['code'] if a_display else None
        card = make_card(f'R32_{i+1}', h_code, a_code, updated_teams)
        # Overwrite pct with display pct (appearance % for 1X/2X, third-place % for B)
        if h_display and card.get('home'): card['home']['pct'] = h_display['pct']
        if a_display and card.get('away'): card['away']['pct'] = a_display['pct']
        r32_cards.append(card)

    # R16: winner of R32[2i] vs winner of R32[2i+1] — deterministic chain
    r16_cards = []
    for i in range(8):
        h_code = r32_cards[i*2]['winner']['code']   if r32_cards[i*2].get('winner')   else None
        a_code = r32_cards[i*2+1]['winner']['code'] if r32_cards[i*2+1].get('winner') else None
        r16_cards.append(make_card(f'R16_{i+1}', h_code, a_code, updated_teams))

    # QF: winner of R16[2i] vs winner of R16[2i+1]
    qf_cards = []
    for i in range(4):
        h_code = r16_cards[i*2]['winner']['code']   if r16_cards[i*2].get('winner')   else None
        a_code = r16_cards[i*2+1]['winner']['code'] if r16_cards[i*2+1].get('winner') else None
        qf_cards.append(make_card(f'QF_{i+1}', h_code, a_code, updated_teams))

    # SF: winner of QF[2i] vs winner of QF[2i+1]
    sf_cards = []
    for i in range(2):
        h_code = qf_cards[i*2]['winner']['code']   if qf_cards[i*2].get('winner')   else None
        a_code = qf_cards[i*2+1]['winner']['code'] if qf_cards[i*2+1].get('winner') else None
        sf_cards.append(make_card(f'SF_{i+1}', h_code, a_code, updated_teams))

    # Final: winner of SF[0] vs winner of SF[1]
    final_h = sf_cards[0]['winner']['code'] if sf_cards[0].get('winner') else None
    final_a = sf_cards[1]['winner']['code'] if sf_cards[1].get('winner') else None
    final_card = make_card('Final', final_h, final_a, updated_teams)

    live_bracket = {
        'r32':   r32_cards,
        'r16':   r16_cards,
        'qf':    qf_cards,
        'sf':    sf_cards,
        'final': final_card,
    }

    return results, live_bracket

# ── Bayesian score update ─────────────────────────────────────────────
def update_scores(base_teams, finished):
    teams = {code: dict(t) for code,t in base_teams.items()}
    actual   = defaultdict(lambda: {'gf':0,'ga':0,'n':0})
    expected = defaultdict(lambda: {'gf':0.0,'ga':0.0})
    for fx in finished:
        h, a = fx['home'], fx['away']
        if not h or not a or h not in teams or a not in teams: continue
        lh, la = get_lambdas(h, a, teams)
        actual[h]['gf']+=fx['hg']; actual[h]['ga']+=fx['ag']; actual[h]['n']+=1
        actual[a]['gf']+=fx['ag']; actual[a]['ga']+=fx['hg']; actual[a]['n']+=1
        expected[h]['gf']+=lh; expected[h]['ga']+=la
        expected[a]['gf']+=la; expected[a]['ga']+=lh
    LEARN = 0.08
    for code in teams:
        n = actual[code]['n']
        if n == 0: continue
        att_d = (actual[code]['gf']/n - expected[code]['gf']/n)*LEARN*10
        def_d = (expected[code]['ga']/n - actual[code]['ga']/n)*LEARN*8
        nudge = max(-8.0, min(6.0, att_d+def_d))
        teams[code]['score']      = round(teams[code]['score']+nudge, 2)
        teams[code]['form_nudge'] = round(nudge, 2)
        teams[code]['played']     = n
    return teams

# ── In-play win probability ───────────────────────────────────────────
def live_win_probability(home, away, hg_now, ag_now, minute, teams):
    if home not in teams or away not in teams: return None
    lh_90, la_90 = get_lambdas(home, away, teams)
    mins_played = max(1, min(int(minute) if minute else 45, 89))
    remaining   = (90 - mins_played) / 90
    extra_h = np.random.poisson(lh_90*remaining, 10000)
    extra_a = np.random.poisson(la_90*remaining, 10000)
    final_h = hg_now + extra_h; final_a = ag_now + extra_a
    return {
        'home_win':  round(int(np.sum(final_h > final_a))/10000*100, 1),
        'draw':      round(int(np.sum(final_h == final_a))/10000*100, 1),
        'away_win':  round(int(np.sum(final_a > final_h))/10000*100, 1),
        'minute':    mins_played,
        'remaining': round(remaining*90, 0),
    }

def compute_live_probs(live_fixtures, teams):
    probs = []
    for fx in live_fixtures:
        if not fx['home'] or not fx['away']: continue
        prob = live_win_probability(fx['home'], fx['away'], fx['hg'], fx['ag'], fx['minute'], teams)
        if prob:
            probs.append({'home': fx['home'], 'away': fx['away'],
                'hg': fx['hg'], 'ag': fx['ag'], 'minute': fx['minute'],
                'stage': fx['stage'], 'prob': prob})
    return probs

# ── Group standings ───────────────────────────────────────────────────
def compute_standings(finished, base_groups):
    standings = {}
    for g, teams in base_groups.items():
        standings[g] = {t['code']: {'pts':0,'gd':0,'gf':0,'ga':0,'played':0} for t in teams}
    for fx in finished:
        h, a = fx['home'], fx['away']
        if not h or not a: continue
        grp = None
        for g, teams in base_groups.items():
            codes = [t['code'] for t in teams]
            if h in codes and a in codes: grp = g; break
        if not grp: continue
        if 'Group' not in fx.get('stage', 'Group'): continue
        s = standings[grp]; hg, ag = fx['hg'], fx['ag']
        s[h]['gf']+=hg; s[h]['ga']+=ag; s[h]['gd']+=hg-ag; s[h]['played']+=1
        s[a]['gf']+=ag; s[a]['ga']+=hg; s[a]['gd']+=ag-hg; s[a]['played']+=1
        if hg > ag: s[h]['pts'] += 3
        elif ag > hg: s[a]['pts'] += 3
        else: s[h]['pts'] += 1; s[a]['pts'] += 1
    return {g: sorted(tbl.items(), key=lambda x: (-x[1]['pts'],-x[1]['gd'],-x[1]['gf']))
            for g, tbl in standings.items()}

def get_eliminated(finished):
    elim = set()
    for fx in finished:
        if 'Group' in fx.get('stage', 'Group'): continue
        if fx['hg'] < fx['ag']: elim.add(fx['home'])
        elif fx['ag'] < fx['hg']: elim.add(fx['away'])
    return [e for e in elim if e]

def get_phase(fixtures):
    stages = set(fx['stage'] for fx in fixtures if fx['finished'] or fx['live'])
    if any('Final' in s and 'Semi' not in s and 'Quarter' not in s for s in stages): return 'FINAL'
    if any('Semi'    in s for s in stages): return 'SEMI_FINALS'
    if any('Quarter' in s for s in stages): return 'QUARTER_FINALS'
    if any('Round of 32' in s for s in stages): return 'ROUND_OF_32'
    if any('Group'   in s for s in stages): return 'GROUP_STAGE'
    return 'PRE_TOURNAMENT'

def parse_fixture(fx):
    fixture = fx.get('fixture', {}); teams = fx.get('teams', {})
    goals = fx.get('goals', {}); league = fx.get('league', {})
    status = fixture.get('status', {})
    home_name = teams.get('home', {}).get('name', '')
    away_name = teams.get('away', {}).get('name', '')
    status_short = status.get('short', ''); elapsed = status.get('elapsed') or 0
    hg = goals.get('home') or 0; ag = goals.get('away') or 0
    is_finished = status_short in ('FT', 'AET', 'PEN', 'AWD', 'WO')
    is_live     = status_short in ('1H', 'HT', '2H', 'ET', 'BT', 'P', 'INT', 'LIVE')
    is_upcoming = status_short in ('NS', 'TBD', 'PST', 'CANC', 'ABD')
    ko_str = fixture.get('date', ''); ko = parse_utc(ko_str)
    if not is_finished and ko:
        if (datetime.now(timezone.utc) - ko).total_seconds() / 3600 > 3:
            is_finished = True; is_live = False
    return {
        'fixture_id': fixture.get('id'),
        'home': name_to_code(home_name), 'away': name_to_code(away_name),
        'home_name': home_name, 'away_name': away_name,
        'hg': int(hg), 'ag': int(ag),
        'minute': int(elapsed) if elapsed else 0,
        'status': status_short, 'stage': str(league.get('round', 'Group Stage')),
        'date': ko_str[:16].replace('T',' ') if ko_str else '',
        'kickoff': ko, 'live': is_live, 'finished': is_finished, 'upcoming': is_upcoming,
    }

def should_update(fixtures):
    now = datetime.now(timezone.utc); next_kickoff = None
    for fx in fixtures:
        if fx['live']:
            return True, f"Match live: {fx['home_name']} vs {fx['away_name']} ({fx['minute']}')", None
        if fx['upcoming'] and fx['kickoff']:
            mins = (fx['kickoff'] - now).total_seconds() / 60
            if -5 <= mins <= 10:
                return True, f"Kickoff imminent: {fx['home_name']} vs {fx['away_name']}", fx['kickoff']
            if mins > 0 and (next_kickoff is None or fx['kickoff'] < next_kickoff):
                next_kickoff = fx['kickoff']
    for fx in fixtures:
        if fx['finished'] and fx['kickoff']:
            if (now - fx['kickoff']).total_seconds() / 3600 < 3:
                return True, f"Recent result: {fx['home_name']} {fx['hg']}-{fx['ag']} {fx['away_name']}", None
    if next_kickoff:
        mins = (next_kickoff - now).total_seconds() / 60
        return False, f"Next kickoff in {round(mins)}m ({next_kickoff.strftime('%Y-%m-%d %H:%M UTC')})", next_kickoff
    return False, "No active or upcoming matches", None

def format_result(fx):
    return {'home':fx['home'],'away':fx['away'],'hg':fx['hg'],'ag':fx['ag'],
            'live':fx['live'],'stage':fx['stage'],'date':fx['date'],
            'status':fx['status'],'minute':fx['minute']}

def format_fixture(fx):
    now = datetime.now(timezone.utc)
    mins = round((fx['kickoff']-now).total_seconds()/60) if fx['kickoff'] else 9999
    return {'home':fx['home'],'away':fx['away'],'date':fx['date'],
            'stage':fx['stage'],'mins_until':mins}

# ── Main ──────────────────────────────────────────────────────────────
def main():
    now = datetime.now(timezone.utc)
    print(f'Project Olympus Live Updater -- {now.isoformat()}')

    with open('olympus_v2p_results.json') as f:
        BASE = json.load(f)

    print('Fetching WC 2026 fixtures...')
    raw = fetch_fixtures()
    if not raw:
        print('No fixtures returned — aborting'); sys.exit(0)

    fixtures = []; unmapped = []
    for fx in raw:
        p = parse_fixture(fx)
        if p['home'] and p['away']: fixtures.append(p)
        else:
            h = fx.get('teams',{}).get('home',{}).get('name','?')
            a = fx.get('teams',{}).get('away',{}).get('name','?')
            unmapped.append(f'{h} vs {a}')

    if unmapped: print(f'  Unmapped teams: {unmapped[:5]}')

    finished = [fx for fx in fixtures if fx['finished']]
    live_now = [fx for fx in fixtures if fx['live']]
    upcoming = sorted([fx for fx in fixtures if fx['upcoming'] and fx['kickoff']],
                      key=lambda x: x['kickoff'])

    print(f'  Parsed: {len(fixtures)} | Finished: {len(finished)} | Live: {len(live_now)} | Upcoming: {len(upcoming)}')
    if finished:
        print('  Results so far:')
        for fx in finished:
            print(f'    {fx["home_name"]} {fx["hg"]}-{fx["ag"]} {fx["away_name"]} ({fx["stage"]})')

    update, reason, next_ko = should_update(fixtures)
    print(f'  Should update: {update} -- {reason}')

    print('Running full update...')
    phase         = get_phase(fixtures)
    updated_teams = update_scores(BASE['teams'], finished)
    standings     = compute_standings(finished, BASE['groups'])
    eliminated    = get_eliminated(finished)
    live_probs    = compute_live_probs(live_now, updated_teams)

    for lp in live_probs:
        p = lp['prob']
        hn = BASE['teams'].get(lp['home'],{}).get('name',lp['home'])
        an = BASE['teams'].get(lp['away'],{}).get('name',lp['away'])
        print(f"  In-play: {hn} {lp['hg']}-{lp['ag']} {an} @ {lp['minute']}' -> H:{p['home_win']}% D:{p['draw']}% A:{p['away_win']}%")

    enriched_results = add_predictions_to_results(
        [format_result(fx) for fx in finished[-30:]], BASE['teams'])

    print('Fetching player stats...')
    player_stats = get_player_stats_cached()

    print('Fetching match events...')
    all_events = get_all_events_cached(finished, live_now)
    tournament_goals = build_tournament_goals(all_events)
    print(f'  Tournament goals tracked: {len(tournament_goals)} players')
    player_stats = merge_goals_into_stats(player_stats, tournament_goals, all_events)

    print('Fetching lineups...')
    lineups = get_lineups_cached(finished, live_now)
    print(f'  Lineups available: {len(lineups)} matches')

    print('Running live tournament simulation (10,000 runs)...')
    sim_start = datetime.now(timezone.utc)
    live_sim, live_bracket = run_live_tournament_sims(
        N=10000, updated_teams=updated_teams, base_groups=BASE['groups'],
        finished_fixtures=finished, r32_slots=BASE['bracket']['r32'],
    )
    sim_elapsed = (datetime.now(timezone.utc) - sim_start).total_seconds()
    print(f'  Simulation complete in {sim_elapsed:.1f}s')

    live_ranked = sorted(
        [{'code': c, **live_sim[c]} for c in live_sim if c in updated_teams],
        key=lambda x: -x['win'])

    print('  Top 10 live win probabilities:')
    for r in live_ranked[:10]:
        orig = BASE['teams'].get(r['code'], {}).get('winner', 0)
        delta = round(r['win'] - orig, 2)
        arrow = '↑' if delta > 0 else ('↓' if delta < 0 else '→')
        print(f"    {r['code']}: {r['win']}% ({arrow}{delta:+.2f}% from {orig}%)")

    output = {
        'meta': {
            **BASE['meta'],
            'last_updated':      now.isoformat()+'Z',
            'phase':             phase,
            'matches_completed': len(finished),
            'matches_live':      len(live_now),
            'matches_remaining': len(upcoming),
            'live': True, 'updating': True,
        },
        'teams':   updated_teams,
        'groups':  BASE['groups'],
        'ranked':  BASE['ranked'],
        'bracket': BASE['bracket'],
        'live': {
            'results':          enriched_results,
            'live_now':         [format_result(fx) for fx in live_now],
            'live_probs':       live_probs,
            'remaining':        [format_fixture(fx) for fx in upcoming[:15]],
            'standings':        standings,
            'eliminated':       eliminated,
            'phase':            phase,
            'next_kickoff':     next_ko.isoformat() if next_ko else None,
            'lineups':          lineups,
            'tournament_goals': tournament_goals,
            'player_stats':     player_stats,
            'live_ranked':      live_ranked,
            'live_bracket':     live_bracket,
        }
    }

    with open('olympus_live.json','w') as f:
        json.dump(output, f, separators=(',',':'))

    print(f'Wrote olympus_live.json ({os.path.getsize("olympus_live.json")//1024}KB)')
    print(f'Phase: {phase} | Results: {len(finished)} | Live: {len(live_now)}')
    print('Done.')

if __name__ == '__main__':
    main()
