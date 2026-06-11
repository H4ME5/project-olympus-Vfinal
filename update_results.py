#!/usr/bin/env python3
"""
PROJECT OLYMPUS — LIVE UPDATER (API-Football / RapidAPI)
=========================================================
Uses api-football186.p.rapidapi.com for match data.
Runs every minute via GitHub Actions cron.
Smart polling: only updates during/around live matches.
 
Required GitHub secret: RAPIDAPI_KEY
Get key at: rapidapi.com → search API Football
"""
 
import os, json, math, sys, numpy as np
from datetime import datetime, timezone, timedelta
from collections import defaultdict
import urllib.request
 
np.random.seed(int(datetime.now().timestamp()) % 999999)
 
RAPIDAPI_KEY  = os.environ.get('RAPIDAPI_KEY', '')
RAPIDAPI_HOST = 'api-football186.p.rapidapi.com'
BASE_URL      = f'https://{RAPIDAPI_HOST}'
WC_LEAGUE     = 1      # API-Football WC 2026 league ID
WC_SEASON     = 2026
 
# ── API helper ────────────────────────────────────────────────────────
def api_get(path):
    if not RAPIDAPI_KEY:
        print("No RAPIDAPI_KEY found — skipping fetch")
        return None
    try:
        req = urllib.request.Request(
            f"{BASE_URL}{path}",
            headers={
                'x-rapidapi-key':  RAPIDAPI_KEY,
                'x-rapidapi-host': RAPIDAPI_HOST,
                'Content-Type':    'application/json',
            }
        )
        resp = urllib.request.urlopen(req, timeout=10)
        return json.loads(resp.read())
    except Exception as e:
        print(f"API error {path}: {e}")
        return None
 
def parse_utc(s):
    if not s: return None
    try:
        return datetime.fromisoformat(s.replace('Z', '+00:00'))
    except:
        try:
            # API-Football uses format: 2026-06-11T19:00:00+00:00
            return datetime.fromisoformat(s)
        except:
            return None
 
# ── Team name → our 3-letter code ────────────────────────────────────
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
    'Bosnia':'BIH','Bosnia and Herzegovina':'BIH',
    'South Africa':'ZAF','Panama':'PAN','DR Congo':'COD',
    'Congo DR':'COD','Uzbekistan':'UZB','Iraq':'IRQ','Jordan':'JOR',
    'Qatar':'QAT','Saudi Arabia':'KSA','Cape Verde':'CPV',
    'Tunisia':'TUN','New Zealand':'NZL','Curacao':'CUW',
    'Curaçao':'CUW','Haiti':'HAI',
}
def name_to_code(name):
    if not name: return None
    return NAME_MAP.get(name) or NAME_MAP.get(name.strip())
 
# ── Fetch all WC fixtures ─────────────────────────────────────────────
def fetch_fixtures():
    data = api_get(f'/fixtures?league={WC_LEAGUE}&season={WC_SEASON}')
    if not data:
        return []
    return data.get('response', [])
 
# ── Parse fixture into our format ────────────────────────────────────
def parse_fixture(fx):
    fixture  = fx.get('fixture', {})
    teams    = fx.get('teams', {})
    goals    = fx.get('goals', {})
    status   = fixture.get('status', {})
    
    home_name = teams.get('home', {}).get('name', '')
    away_name = teams.get('away', {}).get('name', '')
    home_code = name_to_code(home_name)
    away_code = name_to_code(away_name)
    
    status_short = status.get('short', '')  # NS, 1H, HT, 2H, FT, AET, PEN
    status_long  = status.get('long', '')
    elapsed      = status.get('elapsed') or 0
    
    hg = goals.get('home')
    ag = goals.get('away')
    
    # Map API-Football status to our statuses
    is_live     = status_short in ('1H', 'HT', '2H', 'ET', 'BT', 'P', 'SUSP', 'INT', 'LIVE')
    is_finished = status_short in ('FT', 'AET', 'PEN')
    is_upcoming = status_short in ('NS', 'TBD')
    
    # Get kickoff time
    ko_str = fixture.get('date', '')
    ko     = parse_utc(ko_str)
    
    # Get round/stage
    league = fx.get('league', {})
    round_ = league.get('round', 'Group Stage')
    
    return {
        'fixture_id': fixture.get('id'),
        'home':       home_code,
        'away':       away_code,
        'home_name':  home_name,
        'away_name':  away_name,
        'hg':         hg if hg is not None else 0,
        'ag':         ag if ag is not None else 0,
        'minute':     int(elapsed),
        'status':     status_short,
        'stage':      round_,
        'date':       ko_str[:10] if ko_str else '',
        'kickoff':    ko,
        'live':       is_live,
        'finished':   is_finished,
        'upcoming':   is_upcoming,
    }
 
# ── Schedule check ────────────────────────────────────────────────────
def should_update(fixtures):
    now = datetime.now(timezone.utc)
    next_kickoff = None
 
    for fx in fixtures:
        if fx['live']:
            return True, f"Match live: {fx['home_name']} vs {fx['away_name']} ({fx['minute']}')", None
        if fx['upcoming'] and fx['kickoff']:
            mins = (fx['kickoff'] - now).total_seconds() / 60
            if -5 <= mins <= 10:
                return True, f"Kickoff imminent: {fx['home_name']} vs {fx['away_name']} in {mins:.0f}m", fx['kickoff']
            if mins > 0 and (next_kickoff is None or fx['kickoff'] < next_kickoff):
                next_kickoff = fx['kickoff']
 
    if next_kickoff:
        mins = (next_kickoff - now).total_seconds() / 60
        return False, f"Next kickoff in {mins:.0f}m ({next_kickoff.strftime('%Y-%m-%d %H:%M UTC')})", next_kickoff
 
    # Check if there were recent matches in the last 2 hours (just finished)
    for fx in fixtures:
        if fx['finished'] and fx['kickoff']:
            age_hours = (now - fx['kickoff']).total_seconds() / 3600
            if age_hours < 3:
                return True, f"Recent match result: {fx['home_name']} {fx['hg']}-{fx['ag']} {fx['away_name']}", None
 
    return False, "No active or upcoming matches", None
 
# ── Group standings from completed results ────────────────────────────
def compute_standings(finished, base_groups):
    standings = {}
    for g, teams in base_groups.items():
        tbl = {t['code']: {'pts':0,'gd':0,'gf':0,'ga':0,'played':0} for t in teams}
        standings[g] = tbl
 
    for fx in finished:
        h, a = fx['home'], fx['away']
        if not h or not a: continue
        grp = None
        for g, teams in base_groups.items():
            codes = [t['code'] for t in teams]
            if h in codes and a in codes:
                grp = g; break
        if not grp: continue
        if 'Group' not in fx.get('stage', 'Group'): continue
 
        hg, ag = fx['hg'], fx['ag']
        s = standings[grp]
        s[h]['gf']+=hg; s[h]['ga']+=ag; s[h]['gd']+=hg-ag; s[h]['played']+=1
        s[a]['gf']+=ag; s[a]['ga']+=hg; s[a]['gd']+=ag-hg; s[a]['played']+=1
        if hg>ag:   s[h]['pts']+=3
        elif ag>hg: s[a]['pts']+=3
        else:       s[h]['pts']+=1; s[a]['pts']+=1
 
    return {g: sorted(tbl.items(), key=lambda x:(-x[1]['pts'],-x[1]['gd'],-x[1]['gf']))
            for g, tbl in standings.items()}
 
# ── Bayesian score update ─────────────────────────────────────────────
BASE_GOALS = 1.35
EXP        = 1.15
 
def get_lambdas(home, away, teams):
    hd = teams[home]; ad = teams[away]
    h_att = ((hd['P2']*0.50+hd['P1']*0.28+hd['P3']*0.12+hd['P4']*0.10)/100)**EXP
    a_def = ((ad['P1']*0.50+ad['P2']*0.22+ad['P4']*0.18+ad['P3']*0.10)/100)**EXP
    a_att = ((ad['P2']*0.50+ad['P1']*0.28+ad['P3']*0.12+ad['P4']*0.10)/100)**EXP
    h_def = ((hd['P1']*0.50+hd['P2']*0.22+hd['P4']*0.18+hd['P3']*0.10)/100)**EXP
    return max(0.1, BASE_GOALS*h_att/max(a_def,0.1)), max(0.1, BASE_GOALS*a_att/max(h_def,0.1))
 
def update_scores(base_teams, finished):
    teams    = {code: dict(t) for code,t in base_teams.items()}
    actual   = defaultdict(lambda:{'gf':0,'ga':0,'n':0})
    expected = defaultdict(lambda:{'gf':0.0,'ga':0.0})
 
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
N_LIVE = 10000
 
def live_win_probability(home, away, hg_now, ag_now, minute, teams):
    if home not in teams or away not in teams: return None
    lh_90, la_90 = get_lambdas(home, away, teams)
    mins_played = max(1, min(int(minute), 89))
    remaining   = (90 - mins_played) / 90
    extra_h = np.random.poisson(lh_90*remaining, N_LIVE)
    extra_a = np.random.poisson(la_90*remaining, N_LIVE)
    final_h = hg_now + extra_h
    final_a = ag_now + extra_a
    h_wins = int(np.sum(final_h > final_a))
    draws  = int(np.sum(final_h == final_a))
    a_wins = int(np.sum(final_a > final_h))
    return {
        'home_win':  round(h_wins/N_LIVE*100, 1),
        'draw':      round(draws /N_LIVE*100, 1),
        'away_win':  round(a_wins/N_LIVE*100, 1),
        'minute':    mins_played,
        'remaining': round(remaining*90, 0),
    }
 
def compute_live_probs(live_fixtures, teams):
    probs = []
    for fx in live_fixtures:
        if not fx['home'] or not fx['away']: continue
        prob = live_win_probability(fx['home'], fx['away'],
                                    fx['hg'], fx['ag'],
                                    fx['minute'], teams)
        if prob:
            probs.append({
                'home': fx['home'], 'away': fx['away'],
                'hg': fx['hg'], 'ag': fx['ag'],
                'minute': fx['minute'], 'stage': fx['stage'],
                'prob': prob,
            })
    return probs
 
# ── Eliminated teams ──────────────────────────────────────────────────
def get_eliminated(finished):
    elim = set()
    for fx in finished:
        if 'Group' in fx.get('stage', 'Group'): continue
        if fx['hg'] < fx['ag']: elim.add(fx['home'])
        elif fx['ag'] < fx['hg']: elim.add(fx['away'])
    return list(e for e in elim if e)
 
# ── Tournament phase ──────────────────────────────────────────────────
def get_phase(fixtures):
    stages = set(fx['stage'] for fx in fixtures if fx['finished'] or fx['live'])
    if any('Final' in s and 'Semi' not in s and 'Quarter' not in s for s in stages): return 'FINAL'
    if any('Semi' in s for s in stages): return 'SEMI_FINALS'
    if any('Quarter' in s for s in stages): return 'QUARTER_FINALS'
    if any('Round of 32' in s or 'Last 32' in s for s in stages): return 'ROUND_OF_32'
    if any('Group' in s for s in stages): return 'GROUP_STAGE'
    return 'PRE_TOURNAMENT'
 
# ── Format results for dashboard ─────────────────────────────────────
def format_result(fx):
    return {
        'home': fx['home'], 'away': fx['away'],
        'hg': fx['hg'], 'ag': fx['ag'],
        'live': fx['live'], 'stage': fx['stage'],
        'date': fx['date'], 'status': fx['status'],
        'minute': fx['minute'],
    }
 
def format_fixture(fx):
    return {
        'home': fx['home'], 'away': fx['away'],
        'date': fx['date'] + ' UTC',
        'stage': fx['stage'],
        'mins_until': round((fx['kickoff'] - datetime.now(timezone.utc)).total_seconds()/60)
                      if fx['kickoff'] else 9999,
    }
 
# ── Main ──────────────────────────────────────────────────────────────
def main():
    now = datetime.now(timezone.utc)
    print(f"Project Olympus Live Updater — {now.isoformat()}")
 
    with open('olympus_v2p_results.json') as f:
        BASE = json.load(f)
 
    print(f"Fetching WC 2026 fixtures (league={WC_LEAGUE}, season={WC_SEASON})...")
    raw_fixtures = fetch_fixtures()
    if not raw_fixtures:
        print("No fixtures returned — aborting")
        sys.exit(0)
 
    # Parse all fixtures
    fixtures = []
    for fx in raw_fixtures:
        parsed = parse_fixture(fx)
        if parsed['home'] and parsed['away']:
            fixtures.append(parsed)
        else:
            # Log unmapped teams
            teams = fx.get('teams', {})
            h = teams.get('home', {}).get('name', '?')
            a = teams.get('away', {}).get('name', '?')
            if not parsed['home'] or not parsed['away']:
                print(f"  Unmapped: {h} vs {a}")
 
    print(f"  Total fixtures parsed: {len(fixtures)}")
 
    # Categorise
    finished  = [fx for fx in fixtures if fx['finished']]
    live_now  = [fx for fx in fixtures if fx['live']]
    upcoming  = sorted([fx for fx in fixtures if fx['upcoming'] and fx['kickoff']],
                        key=lambda x: x['kickoff'])
 
    print(f"  Finished: {len(finished)} | Live: {len(live_now)} | Upcoming: {len(upcoming)}")
 
    # Should we update?
    update, reason, next_ko = should_update(fixtures)
    print(f"  Should update: {update} — {reason}")
 
    if not update:
        if not os.path.exists('olympus_live.json'):
            status = {'meta': {
                'last_checked': now.isoformat()+'Z',
                'next_kickoff': next_ko.isoformat() if next_ko else None,
                'phase': get_phase(fixtures),
                'live': False, 'updating': False, 'reason': reason,
            }}
            with open('olympus_live.json', 'w') as f:
                json.dump(status, f, separators=(',',':'))
            print("Wrote initial status file")
        else:
            print("No update needed — skipping commit")
        sys.exit(0)
 
    # ── Full update ───────────────────────────────────────────────────
    print("Running full update...")
    phase         = get_phase(fixtures)
    updated_teams = update_scores(BASE['teams'], finished)
    standings     = compute_standings(finished, BASE['groups'])
    eliminated    = get_eliminated(finished)
    live_probs    = compute_live_probs(live_now, updated_teams)
 
    if live_probs:
        for lp in live_probs:
            p = lp['prob']
            hn = BASE['teams'].get(lp['home'],{}).get('name', lp['home'])
            an = BASE['teams'].get(lp['away'],{}).get('name', lp['away'])
            print(f"  In-play: {hn} {lp['hg']}-{lp['ag']} {an} @ {lp['minute']}' "
                  f"→ H:{p['home_win']}% D:{p['draw']}% A:{p['away_win']}%")
 
    if finished:
        print(f"  Latest result: {finished[-1]['home_name']} "
              f"{finished[-1]['hg']}-{finished[-1]['ag']} {finished[-1]['away_name']}")
 
    output = {
        'meta': {
            **BASE['meta'],
            'last_updated':      now.isoformat()+'Z',
            'phase':             phase,
            'matches_completed': len(finished),
            'matches_live':      len(live_now),
            'matches_remaining': len(upcoming),
            'live':              True,
            'updating':          True,
        },
        'teams':   updated_teams,
        'groups':  BASE['groups'],
        'ranked':  sorted(
            [{'code':c, 'win':t.get('winner',0), 'final':t.get('final',0),
              'sf':t.get('sf',0), 'qf':t.get('qf',0), 'r16':t.get('r16',0),
              'adv':t.get('advanced',0)}
             for c,t in updated_teams.items()],
            key=lambda x: -x['win']
        ),
        'bracket': BASE['bracket'],
        'live': {
            'results':    [format_result(fx) for fx in finished[-30:]],
            'live_now':   [format_result(fx) for fx in live_now],
            'live_probs': live_probs,
            'remaining':  [format_fixture(fx) for fx in upcoming[:15]],
            'standings':  standings,
            'eliminated': eliminated,
            'phase':      phase,
            'next_kickoff': next_ko.isoformat() if next_ko else None,
        }
    }
 
    with open('olympus_live.json', 'w') as f:
        json.dump(output, f, separators=(',',':'))
 
    size = os.path.getsize('olympus_live.json')
    print(f"Wrote olympus_live.json ({size//1024}KB)")
    print(f"Phase: {phase} | Results: {len(finished)} | Live: {len(live_now)}")
    print("Done.")
 
if __name__ == '__main__':
    main()
