#!/usr/bin/env python3
"""
PROJECT OLYMPUS — LIVE UPDATER (Smart polling)
================================================
GitHub Actions runs this every minute via cron.
The script itself decides whether to actually fetch/update based on
whether a match is currently in play or about to start.

Logic:
  - Match in play (IN_PLAY / PAUSED)  → update + write JSON
  - Match starting within 10 minutes  → update + write JSON
  - No match active or imminent       → skip update, write nothing
  - Between matchdays                 → skip

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
WC_ID    = 2000  # WC 2026 competition ID — verify once tournament is announced

# ── Helpers ───────────────────────────────────────────────────────────
def api_get(path):
    if not API_KEY:
        print("No API key found — skipping fetch")
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
    """Parse ISO datetime string to UTC datetime."""
    if not s: return None
    try:
        s = s.replace('Z', '+00:00')
        return datetime.fromisoformat(s)
    except:
        return None

# ── Schedule check ────────────────────────────────────────────────────
def should_update(matches):
    """
    Returns (should_update: bool, reason: str, next_kickoff: datetime|None)
    Update if:
      - Any match is IN_PLAY or PAUSED right now
      - Any match kicks off within the next 10 minutes
    Skip if:
      - All matches are SCHEDULED/FINISHED and next kickoff is >10 min away
    """
    now = datetime.now(timezone.utc)
    next_kickoff = None

    for m in matches:
        status = m.get('status', '')

        # Currently live
        if status in ('IN_PLAY', 'PAUSED'):
            return True, f"Match in play: {m['homeTeam']['name']} vs {m['awayTeam']['name']}", None

        # Check kickoff time
        if status in ('SCHEDULED', 'TIMED'):
            ko = parse_utc(m.get('utcDate'))
            if ko:
                mins_until = (ko - now).total_seconds() / 60
                if -5 <= mins_until <= 10:
                    # Starting very soon or just kicked off (API sometimes lags)
                    return True, f"Kickoff imminent: {m['homeTeam']['name']} vs {m['awayTeam']['name']} in {mins_until:.0f}m", ko
                if mins_until > 0:
                    if next_kickoff is None or ko < next_kickoff:
                        next_kickoff = ko

    if next_kickoff:
        mins = (next_kickoff - now).total_seconds() / 60
        return False, f"No active matches. Next kickoff in {mins:.0f} minutes ({next_kickoff.strftime('%Y-%m-%d %H:%M UTC')})", next_kickoff

    return False, "No active or upcoming matches found", None

# ── Team name → code mapping ──────────────────────────────────────────
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
def name_to_code(name):
    return NAME_MAP.get(name)

# ── Parse completed results ───────────────────────────────────────────
def parse_results(matches):
    results = []
    for m in matches:
        status = m.get('status', '')
        score  = m.get('score', {})
        ft     = score.get('fullTime', {})
        hg     = ft.get('home')
        ag     = ft.get('away')

        home_code = name_to_code(m['homeTeam']['name'])
        away_code = name_to_code(m['awayTeam']['name'])
        if not home_code or not away_code:
            continue

        # Include in-play matches with current score too
        if status in ('IN_PLAY', 'PAUSED'):
            live_score = score.get('halfTime', ft)
            hg = live_score.get('home', 0) or 0
            ag = live_score.get('away', 0) or 0
            results.append({
                'home': home_code, 'away': away_code,
                'hg': hg, 'ag': ag, 'live': True,
                'stage': m.get('stage', 'GROUP_STAGE'),
                'date': m.get('utcDate','')[:10],
                'status': status,
            })
        elif status == 'FINISHED' and hg is not None and ag is not None:
            results.append({
                'home': home_code, 'away': away_code,
                'hg': hg, 'ag': ag, 'live': False,
                'stage': m.get('stage', 'GROUP_STAGE'),
                'date': m.get('utcDate','')[:10],
                'status': 'FINISHED',
            })
    return results

def get_remaining(matches):
    remaining = []
    now = datetime.now(timezone.utc)
    for m in matches:
        if m.get('status') not in ('SCHEDULED', 'TIMED'):
            continue
        home_code = name_to_code(m['homeTeam']['name'])
        away_code = name_to_code(m['awayTeam']['name'])
        if not home_code or not away_code:
            continue
        ko = parse_utc(m.get('utcDate'))
        remaining.append({
            'home': home_code, 'away': away_code,
            'date': m.get('utcDate','')[:16].replace('T',' ') + ' UTC',
            'stage': m.get('stage',''),
            'mins_until': round((ko - now).total_seconds()/60) if ko else 9999,
        })
    remaining.sort(key=lambda x: x['mins_until'])
    return remaining[:15]

# ── Live group standings ──────────────────────────────────────────────
def compute_standings(results, base_groups):
    standings = {}
    for g, teams in base_groups.items():
        tbl = {t['code']: {'pts':0,'gd':0,'gf':0,'ga':0,'played':0}
               for t in teams}
        standings[g] = tbl

    for r in results:
        if 'GROUP' not in r.get('stage', 'GROUP_STAGE'):
            continue
        h, a = r['home'], r['away']
        grp  = None
        for g, teams in base_groups.items():
            codes = [t['code'] for t in teams]
            if h in codes and a in codes:
                grp = g; break
        if not grp:
            continue

        hg, ag = r['hg'], r['ag']
        if r.get('live'):
            continue  # Don't count in-play matches in standings yet

        s = standings[grp]
        s[h]['gf']+=hg; s[h]['ga']+=ag; s[h]['gd']+=hg-ag; s[h]['played']+=1
        s[a]['gf']+=ag; s[a]['ga']+=hg; s[a]['gd']+=ag-hg; s[a]['played']+=1
        if hg>ag:   s[h]['pts']+=3
        elif ag>hg: s[a]['pts']+=3
        else:       s[h]['pts']+=1; s[a]['pts']+=1

    # Sort each group
    sorted_standings = {}
    for g, tbl in standings.items():
        sorted_standings[g] = sorted(
            tbl.items(),
            key=lambda x: (-x[1]['pts'], -x[1]['gd'], -x[1]['gf'])
        )
    return sorted_standings

# ── Bayesian score update ─────────────────────────────────────────────
def update_scores(base_teams, finished_results):
    teams = {code: dict(t) for code, t in base_teams.items()}
    BASE_GOALS = 1.35; EXP = 1.15

    def pred_xg(home, away):
        hd=teams[home]; ad=teams[away]
        h_att=((hd['P2']*0.50+hd['P1']*0.28+hd['P3']*0.12+hd['P4']*0.10)/100)**EXP
        a_def=((ad['P1']*0.50+ad['P2']*0.22+ad['P4']*0.18+ad['P3']*0.10)/100)**EXP
        a_att=((ad['P2']*0.50+ad['P1']*0.28+ad['P3']*0.12+ad['P4']*0.10)/100)**EXP
        h_def=((hd['P1']*0.50+hd['P2']*0.22+hd['P4']*0.18+hd['P3']*0.10)/100)**EXP
        return max(0.1, BASE_GOALS*h_att/max(a_def,0.1)), max(0.1, BASE_GOALS*a_att/max(h_def,0.1))

    actual   = defaultdict(lambda:{'gf':0,'ga':0,'n':0})
    expected = defaultdict(lambda:{'gf':0.0,'ga':0.0})

    for r in finished_results:
        h,a = r['home'],r['away']
        if h not in teams or a not in teams or r.get('live'): continue
        ph,pa = pred_xg(h,a)
        actual[h]['gf']+=r['hg']; actual[h]['ga']+=r['ag']; actual[h]['n']+=1
        actual[a]['gf']+=r['ag']; actual[a]['ga']+=r['hg']; actual[a]['n']+=1
        expected[h]['gf']+=ph; expected[h]['ga']+=pa
        expected[a]['gf']+=pa; expected[a]['ga']+=ph

    LEARN = 0.08
    for code in teams:
        n = actual[code]['n']
        if n == 0: continue
        att_d = (actual[code]['gf']/n - expected[code]['gf']/n) * LEARN * 10
        def_d = (expected[code]['ga']/n - actual[code]['ga']/n) * LEARN * 8
        nudge = max(-8.0, min(6.0, att_d + def_d))
        teams[code]['score']      = round(teams[code]['score'] + nudge, 2)
        teams[code]['form_nudge'] = round(nudge, 2)
        teams[code]['played']     = n
    return teams

# ── Eliminated teams ──────────────────────────────────────────────────
def get_eliminated(results, base_groups):
    """Teams knocked out in KO rounds, or mathematically eliminated from groups."""
    elim = set()
    for r in results:
        stage = r.get('stage','')
        if r.get('live') or 'GROUP' in stage:
            continue
        # KO loss
        if r['hg'] < r['ag']:  elim.add(r['home'])
        elif r['ag'] < r['hg']: elim.add(r['away'])
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

    # Load base predictions
    with open('olympus_v2p_results.json') as f:
        BASE = json.load(f)

    # Fetch all WC matches
    print("Fetching schedule from football-data.org...")
    data = api_get(f'/competitions/{WC_ID}/matches')
    if not data:
        print("Could not fetch schedule — aborting")
        sys.exit(0)

    matches = data.get('matches', [])
    print(f"  Total matches in competition: {len(matches)}")

    # ── Smart polling: decide whether to actually update ──────────────
    update, reason, next_ko = should_update(matches)
    print(f"  Should update: {update} — {reason}")

    if not update:
        # Write a minimal status file so the dashboard knows when next match is
        status = {
            'meta': {
                'last_checked': now.isoformat()+'Z',
                'next_kickoff': next_ko.isoformat() if next_ko else None,
                'phase': get_phase(matches),
                'live': False,
                'updating': False,
                'reason': reason,
            }
        }
        # Only write if file doesn't exist yet (avoid constant commits)
        if not os.path.exists('olympus_live.json'):
            with open('olympus_live.json','w') as f:
                json.dump(status, f, separators=(',',':'))
            print("Wrote initial status file")
        else:
            print("No update needed — skipping commit")
        sys.exit(0)

    # ── Active match window — do the full update ──────────────────────
    print("Active match window — running full update...")

    results   = parse_results(matches)
    remaining = get_remaining(matches)
    finished  = [r for r in results if not r.get('live')]
    live_now  = [r for r in results if r.get('live')]
    phase     = get_phase(matches)

    print(f"  Finished: {len(finished)} | Live now: {len(live_now)} | Remaining: {len(remaining)}")

    updated_teams = update_scores(BASE['teams'], finished)
    standings     = compute_standings(results, BASE['groups'])
    eliminated    = get_eliminated(results, BASE['groups'])

    output = {
        'meta': {
            **BASE['meta'],
            'last_updated':       now.isoformat()+'Z',
            'phase':              phase,
            'matches_completed':  len(finished),
            'matches_live':       len(live_now),
            'matches_remaining':  len(remaining),
            'live':               True,
            'updating':           True,
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
            'results':    results[-30:],   # last 30 results
            'live_now':   live_now,        # in-play right now
            'remaining':  remaining,
            'standings':  standings,
            'eliminated': eliminated,
            'phase':      phase,
            'next_kickoff': next_ko.isoformat() if next_ko else None,
        }
    }

    with open('olympus_live.json','w') as f:
        json.dump(output, f, separators=(',',':'))

    size = os.path.getsize('olympus_live.json')
    print(f"Wrote olympus_live.json ({size//1024}KB)")
    print(f"Phase: {phase} | Live matches: {len(live_now)}")
    print("Done.")

if __name__ == '__main__':
    main()
