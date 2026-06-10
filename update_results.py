#!/usr/bin/env python3
"""
PROJECT OLYMPUS — LIVE UPDATER (Smart polling + In-play win probability)
=========================================================================
GitHub Actions runs this every minute via cron.
The script decides whether to actually fetch/update based on match state.
 
Logic:
  - Match IN_PLAY / PAUSED       → update every minute + in-play win prob
  - Match starting within 10 min → update
  - Nothing active               → skip, write nothing
 
Required GitHub secret: FOOTBALL_API_KEY
Free key: https://www.football-data.org/client/register
"""
 
import os, json, math, sys, numpy as np
from datetime import datetime, timezone, timedelta
from collections import defaultdict
import urllib.request
 
np.random.seed(int(datetime.now().timestamp()) % 999999)
 
API_KEY  = os.environ.get('FOOTBALL_API_KEY', '')
BASE_URL = 'https://api.football-data.org/v4'
WC_ID    = 2000  # Verify on football-data.org once WC 2026 is in their system
 
# ── API helper ────────────────────────────────────────────────────────
def api_get(path):
    if not API_KEY:
        print("No API key — skipping fetch")
        return None
    try:
        req = urllib.request.Request(
            f"{BASE_URL}{path}",
            headers={'X-Auth-Token': API_KEY}
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
        return None
 
# ── Team name → code ──────────────────────────────────────────────────
NAME_MAP = {
    'Spain':'ESP','England':'ENG','Germany':'GER','France':'FRA',
    'Portugal':'POR','Brazil':'BRA','Argentina':'ARG','Netherlands':'NED',
    'Japan':'JPN','Norway':'NOR','United States':'USA','Austria':'AUT',
    'Colombia':'COL','Uruguay':'URU','Türkiye':'TUR','Turkey':'TUR',
    'Croatia':'CRO','Switzerland':'SUI','Scotland':'SCO','Mexico':'MEX',
    'Belgium':'BEL','Senegal':'SEN','Morocco':'MAR','Sweden':'SWE',
    'Canada':'CAN','Egypt':'EGY','Ghana':'GHA','Czechia':'CZE',
    'Czech Republic':'CZE',"Côte d'Ivoire":'CIV','Ivory Coast':'CIV',
    'Ecuador':'ECU','Iran':'IRN','South Korea':'KOR','Korea Republic':'KOR',
    'Algeria':'ALG','Australia':'AUS','Paraguay':'PAR',
    'Bosnia and Herzegovina':'BIH','Bosnia & Herzegovina':'BIH',
    'South Africa':'ZAF','Panama':'PAN','DR Congo':'COD',
    'Congo DR':'COD','Uzbekistan':'UZB','Iraq':'IRQ','Jordan':'JOR',
    'Qatar':'QAT','Saudi Arabia':'KSA','Cape Verde':'CPV',
    'Tunisia':'TUN','New Zealand':'NZL','Curaçao':'CUW','Haiti':'HAI',
}
def name_to_code(name): return NAME_MAP.get(name)
 
# ── Schedule check ────────────────────────────────────────────────────
def should_update(matches):
    now = datetime.now(timezone.utc)
    next_kickoff = None
    for m in matches:
        status = m.get('status','')
        if status in ('IN_PLAY','PAUSED'):
            return True, f"Match live: {m['homeTeam']['name']} vs {m['awayTeam']['name']}", None
        if status in ('SCHEDULED','TIMED'):
            ko = parse_utc(m.get('utcDate'))
            if ko:
                mins = (ko - now).total_seconds() / 60
                if -5 <= mins <= 10:
                    return True, f"Kickoff imminent: {m['homeTeam']['name']} in {mins:.0f}m", ko
                if mins > 0 and (next_kickoff is None or ko < next_kickoff):
                    next_kickoff = ko
    if next_kickoff:
        mins = (next_kickoff - now).total_seconds() / 60
        return False, f"Next kickoff in {mins:.0f}m ({next_kickoff.strftime('%Y-%m-%d %H:%M UTC')})", next_kickoff
    return False, "No active or upcoming matches", None
 
# ── Parse match results ───────────────────────────────────────────────
def parse_results(matches):
    results = []
    for m in matches:
        status = m.get('status','')
        score  = m.get('score',{})
        hc     = name_to_code(m['homeTeam']['name'])
        ac     = name_to_code(m['awayTeam']['name'])
        if not hc or not ac: continue
 
        if status in ('IN_PLAY','PAUSED'):
            # Use current score (regularTime or fullTime, fallback to 0)
            cur = score.get('regularTime') or score.get('fullTime') or {}
            hg  = cur.get('home') or 0
            ag  = cur.get('away') or 0
            # Get current minute from API
            minute = m.get('minute') or m.get('currentPeriod',{}).get('minute') or 0
            results.append({
                'home':hc,'away':ac,'hg':hg,'ag':ag,
                'minute': int(minute),
                'live':True,'stage':m.get('stage','GROUP_STAGE'),
                'date':m.get('utcDate','')[:10],'status':status,
            })
        elif status == 'FINISHED':
            ft = score.get('fullTime',{})
            hg = ft.get('home'); ag = ft.get('away')
            if hg is None or ag is None: continue
            results.append({
                'home':hc,'away':ac,'hg':hg,'ag':ag,
                'minute':90,'live':False,
                'stage':m.get('stage','GROUP_STAGE'),
                'date':m.get('utcDate','')[:10],'status':'FINISHED',
            })
    return results
 
def get_remaining(matches):
    now = datetime.now(timezone.utc)
    rem = []
    for m in matches:
        if m.get('status') not in ('SCHEDULED','TIMED'): continue
        hc = name_to_code(m['homeTeam']['name'])
        ac = name_to_code(m['awayTeam']['name'])
        if not hc or not ac: continue
        ko = parse_utc(m.get('utcDate'))
        rem.append({
            'home':hc,'away':ac,
            'date':m.get('utcDate','')[:16].replace('T',' ')+' UTC',
            'stage':m.get('stage',''),
            'mins_until': round((ko-now).total_seconds()/60) if ko else 9999,
        })
    rem.sort(key=lambda x: x['mins_until'])
    return rem[:15]
 
# ── In-play win probability ───────────────────────────────────────────
BASE_GOALS = 1.35
EXP        = 1.15
N_LIVE     = 10000  # simulations for in-play probability
 
def get_lambdas(home, away, teams):
    """Expected goals per 90 min for each team based on model scores."""
    hd = teams[home]; ad = teams[away]
    h_att = ((hd['P2']*0.50+hd['P1']*0.28+hd['P3']*0.12+hd['P4']*0.10)/100)**EXP
    a_def = ((ad['P1']*0.50+ad['P2']*0.22+ad['P4']*0.18+ad['P3']*0.10)/100)**EXP
    a_att = ((ad['P2']*0.50+ad['P1']*0.28+ad['P3']*0.12+ad['P4']*0.10)/100)**EXP
    h_def = ((hd['P1']*0.50+hd['P2']*0.22+hd['P4']*0.18+hd['P3']*0.10)/100)**EXP
    lh = max(0.1, BASE_GOALS * h_att / max(a_def, 0.1))
    la = max(0.1, BASE_GOALS * a_att / max(h_def, 0.1))
    return lh, la
 
def live_win_probability(home, away, hg_now, ag_now, minute, teams):
    """
    Given current scoreline and match minute, simulate the remaining
    time and return win/draw/loss probabilities for the home team.
    """
    if home not in teams or away not in teams:
        return None
 
    lh_90, la_90 = get_lambdas(home, away, teams)
 
    # Remaining fraction of match
    mins_played = max(1, min(int(minute), 89))
    remaining   = (90 - mins_played) / 90
 
    # Scaled lambdas for remaining time
    lh_rem = lh_90 * remaining
    la_rem = la_90 * remaining
 
    # Simulate N_LIVE completions from current scoreline
    extra_h = np.random.poisson(lh_rem, N_LIVE)
    extra_a = np.random.poisson(la_rem, N_LIVE)
 
    final_h = hg_now + extra_h
    final_a = ag_now + extra_a
 
    h_wins = int(np.sum(final_h > final_a))
    draws  = int(np.sum(final_h == final_a))
    a_wins = int(np.sum(final_a > final_h))
 
    # For knockout matches, draws go to ET/pens
    # For group stage, draws are valid — show as draw
    h_pen  = teams[home].get('penalty_rec', 50)
    a_pen  = teams[away].get('penalty_rec', 50)
    pen_h  = h_pen / (h_pen + a_pen)
 
    return {
        'home_win':  round(h_wins / N_LIVE * 100, 1),
        'draw':      round(draws  / N_LIVE * 100, 1),
        'away_win':  round(a_wins / N_LIVE * 100, 1),
        'pen_home':  round(pen_h * 100, 1),  # if it goes to pens
        'minute':    mins_played,
        'remaining': round(remaining * 90, 0),
    }
 
def compute_all_live_probs(live_matches, teams):
    """Compute in-play win probability for every currently live match."""
    probs = []
    for r in live_matches:
        if not r.get('live'): continue
        prob = live_win_probability(
            r['home'], r['away'],
            r['hg'], r['ag'],
            r.get('minute', 45),
            teams
        )
        if prob:
            probs.append({
                'home':    r['home'],
                'away':    r['away'],
                'hg':      r['hg'],
                'ag':      r['ag'],
                'minute':  r.get('minute', 45),
                'stage':   r.get('stage',''),
                'prob':    prob,
            })
    return probs
 
# ── Group standings ───────────────────────────────────────────────────
def compute_standings(results, base_groups):
    standings = {}
    for g, teams in base_groups.items():
        tbl = {t['code']:{'pts':0,'gd':0,'gf':0,'ga':0,'played':0} for t in teams}
        standings[g] = tbl
 
    for r in results:
        if 'GROUP' not in r.get('stage','GROUP_STAGE'): continue
        if r.get('live'): continue  # don't count in-play in standings
        h,a = r['home'],r['away']
        grp = None
        for g,teams in base_groups.items():
            if h in [t['code'] for t in teams] and a in [t['code'] for t in teams]:
                grp=g; break
        if not grp: continue
        hg,ag = r['hg'],r['ag']
        s = standings[grp]
        s[h]['gf']+=hg;s[h]['ga']+=ag;s[h]['gd']+=hg-ag;s[h]['played']+=1
        s[a]['gf']+=ag;s[a]['ga']+=hg;s[a]['gd']+=ag-hg;s[a]['played']+=1
        if hg>ag:   s[h]['pts']+=3
        elif ag>hg: s[a]['pts']+=3
        else:       s[h]['pts']+=1;s[a]['pts']+=1
 
    return {g: sorted(tbl.items(), key=lambda x:(-x[1]['pts'],-x[1]['gd'],-x[1]['gf']))
            for g,tbl in standings.items()}
 
# ── Bayesian score update ─────────────────────────────────────────────
def update_scores(base_teams, finished_results):
    teams = {code: dict(t) for code,t in base_teams.items()}
    actual   = defaultdict(lambda:{'gf':0,'ga':0,'n':0})
    expected = defaultdict(lambda:{'gf':0.0,'ga':0.0})
 
    for r in finished_results:
        h,a = r['home'],r['away']
        if h not in teams or a not in teams or r.get('live'): continue
        lh,la = get_lambdas(h,a,teams)
        actual[h]['gf']+=r['hg'];actual[h]['ga']+=r['ag'];actual[h]['n']+=1
        actual[a]['gf']+=r['ag'];actual[a]['ga']+=r['hg'];actual[a]['n']+=1
        expected[h]['gf']+=lh;expected[h]['ga']+=la
        expected[a]['gf']+=la;expected[a]['ga']+=lh
 
    LEARN = 0.08
    for code in teams:
        n = actual[code]['n']
        if n==0: continue
        att_d = (actual[code]['gf']/n - expected[code]['gf']/n)*LEARN*10
        def_d = (expected[code]['ga']/n - actual[code]['ga']/n)*LEARN*8
        nudge = max(-8.0, min(6.0, att_d+def_d))
        teams[code]['score']      = round(teams[code]['score']+nudge,2)
        teams[code]['form_nudge'] = round(nudge,2)
        teams[code]['played']     = n
    return teams
 
# ── Eliminated teams ──────────────────────────────────────────────────
def get_eliminated(results):
    elim = set()
    for r in results:
        if r.get('live') or 'GROUP' in r.get('stage',''): continue
        if r['hg']<r['ag']: elim.add(r['home'])
        elif r['ag']<r['hg']: elim.add(r['away'])
    return list(elim)
 
# ── Tournament phase ──────────────────────────────────────────────────
def get_phase(matches):
    stages = set(m.get('stage','') for m in matches
                 if m.get('status') in ('IN_PLAY','PAUSED','FINISHED'))
    if any('FINAL' in s and 'SEMI' not in s and 'QUARTER' not in s for s in stages): return 'FINAL'
    if any('SEMI'    in s for s in stages): return 'SEMI_FINALS'
    if any('QUARTER' in s for s in stages): return 'QUARTER_FINALS'
    if any('ROUND_OF' in s or 'LAST_32' in s for s in stages): return 'ROUND_OF_32'
    if any('GROUP'   in s for s in stages): return 'GROUP_STAGE'
    return 'PRE_TOURNAMENT'
 
# ── Main ──────────────────────────────────────────────────────────────
def main():
    now = datetime.now(timezone.utc)
    print(f"Project Olympus Live Updater — {now.isoformat()}")
 
    with open('olympus_v2p_results.json') as f:
        BASE = json.load(f)
 
    print("Fetching schedule from football-data.org...")
    data = api_get(f'/competitions/{WC_ID}/matches')
    if not data:
        print("Could not fetch schedule — aborting")
        sys.exit(0)
 
    matches   = data.get('matches',[])
    print(f"  Total matches: {len(matches)}")
 
    update, reason, next_ko = should_update(matches)
    print(f"  Should update: {update} — {reason}")
 
    if not update:
        if not os.path.exists('olympus_live.json'):
            status = {'meta':{
                'last_checked':now.isoformat()+'Z',
                'next_kickoff':next_ko.isoformat() if next_ko else None,
                'phase':get_phase(matches),'live':False,'updating':False,'reason':reason,
            }}
            with open('olympus_live.json','w') as f:
                json.dump(status,f,separators=(',',':'))
            print("Wrote initial status file")
        else:
            print("No update needed — skipping commit")
        sys.exit(0)
 
    # ── Active window — full update ───────────────────────────────────
    print("Active match window — running full update...")
 
    results   = parse_results(matches)
    remaining = get_remaining(matches)
    finished  = [r for r in results if not r.get('live')]
    live_now  = [r for r in results if r.get('live')]
    phase     = get_phase(matches)
 
    print(f"  Finished: {len(finished)} | Live: {len(live_now)} | Remaining: {len(remaining)}")
 
    updated_teams = update_scores(BASE['teams'], finished)
    standings     = compute_standings(results, BASE['groups'])
    eliminated    = get_eliminated(results)
 
    # ── In-play win probabilities ─────────────────────────────────────
    live_probs = compute_all_live_probs(live_now, updated_teams)
    if live_probs:
        print(f"  In-play probabilities computed for {len(live_probs)} match(es):")
        for lp in live_probs:
            p = lp['prob']
            hn = BASE['teams'].get(lp['home'],{}).get('name',lp['home'])
            an = BASE['teams'].get(lp['away'],{}).get('name',lp['away'])
            print(f"    {hn} {lp['hg']}-{lp['ag']} {an} @ {lp['minute']}' → "
                  f"H:{p['home_win']}% D:{p['draw']}% A:{p['away_win']}%")
 
    output = {
        'meta': {
            **BASE['meta'],
            'last_updated':      now.isoformat()+'Z',
            'phase':             phase,
            'matches_completed': len(finished),
            'matches_live':      len(live_now),
            'matches_remaining': len(remaining),
            'live':              True,
            'updating':          True,
        },
        'teams':   updated_teams,
        'groups':  BASE['groups'],
        'ranked':  sorted(
            [{'code':c,'win':t.get('winner',0),'final':t.get('final',0),
              'sf':t.get('sf',0),'qf':t.get('qf',0),'r16':t.get('r16',0),
              'adv':t.get('advanced',0)}
             for c,t in updated_teams.items()],
            key=lambda x:-x['win']
        ),
        'bracket': BASE['bracket'],
        'live': {
            'results':    results[-30:],
            'live_now':   live_now,
            'live_probs': live_probs,   # ← in-play win probabilities
            'remaining':  remaining,
            'standings':  standings,
            'eliminated': eliminated,
            'phase':      phase,
            'next_kickoff': next_ko.isoformat() if next_ko else None,
        }
    }
 
    with open('olympus_live.json','w') as f:
        json.dump(output,f,separators=(',',':'))
 
    size = os.path.getsize('olympus_live.json')
    print(f"Wrote olympus_live.json ({size//1024}KB)")
    print(f"Phase: {phase} | Live: {len(live_now)} | In-play probs: {len(live_probs)}")
    print("Done.")
 
if __name__ == '__main__':
    main()
