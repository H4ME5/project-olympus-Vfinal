#!/usr/bin/env python3
"""
PROJECT OLYMPUS - LIVE UPDATER (API-Football / RapidAPI)
Uses api-football186.p.rapidapi.com
Required GitHub secret: RAPIDAPI_KEY
"""
 
import os, json, sys, numpy as np
from datetime import datetime, timezone, timedelta, date
from collections import defaultdict
import urllib.request
 
np.random.seed(int(datetime.now().timestamp()) % 999999)
 
RAPIDAPI_KEY  = os.environ.get('RAPIDAPI_KEY', '')
RAPIDAPI_HOST = 'api-football186.p.rapidapi.com'
BASE_URL      = 'https://' + RAPIDAPI_HOST
print('  API key present: ' + str(bool(RAPIDAPI_KEY)) + ' | length: ' + str(len(RAPIDAPI_KEY)))
 
def api_get(path):
    if not RAPIDAPI_KEY:
        print('No RAPIDAPI_KEY - skipping')
        return None
    try:
        req = urllib.request.Request(
            BASE_URL + path,
            headers={
                'x-rapidapi-key':  RAPIDAPI_KEY,
                'x-rapidapi-host': RAPIDAPI_HOST,
                'Content-Type':    'application/json',
            }
        )
        resp = urllib.request.urlopen(req, timeout=10)
        return json.loads(resp.read())
    except Exception as e:
        print('API error ' + path + ': ' + str(e))
        return None
 
def parse_utc(s):
    if not s:
        return None
    try:
        s2 = str(s).strip().replace(' ', 'T')
        if 'T' in s2 and '+' not in s2 and 'Z' not in s2:
            s2 = s2 + '+00:00'
        s2 = s2.replace('Z', '+00:00')
        return datetime.fromisoformat(s2)
    except:
        return None
 
NAME_MAP = {
    'Spain':'ESP','England':'ENG','Germany':'GER','France':'FRA',
    'Portugal':'POR','Brazil':'BRA','Argentina':'ARG','Netherlands':'NED',
    'Japan':'JPN','Norway':'NOR','United States':'USA','Austria':'AUT',
    'Colombia':'COL','Uruguay':'URU','Turkey':'TUR','Turkiye':'TUR',
    'Croatia':'CRO','Switzerland':'SUI','Scotland':'SCO','Mexico':'MEX',
    'Belgium':'BEL','Senegal':'SEN','Morocco':'MAR','Sweden':'SWE',
    'Canada':'CAN','Egypt':'EGY','Ghana':'GHA','Czech Republic':'CZE',
    'Czechia':'CZE','Ivory Coast':'CIV',"Cote d'Ivoire":'CIV',
    'Ecuador':'ECU','Iran':'IRN','South Korea':'KOR','Korea Republic':'KOR',
    'Algeria':'ALG','Australia':'AUS','Paraguay':'PAR',
    'Bosnia':'BIH','Bosnia and Herzegovina':'BIH',
    'South Africa':'ZAF','Panama':'PAN','DR Congo':'COD',
    'Congo DR':'COD','Uzbekistan':'UZB','Iraq':'IRQ','Jordan':'JOR',
    'Qatar':'QAT','Saudi Arabia':'KSA','Cape Verde':'CPV',
    'Tunisia':'TUN','New Zealand':'NZL','Curacao':'CUW',
    'Curacao':'CUW','Haiti':'HAI','Curaçao':'CUW',
}
 
def name_to_code(name):
    if not name:
        return None
    return NAME_MAP.get(str(name).strip())
 
def fetch_fixtures():
    all_matches = []
    seen_ids = set()
    now_date = datetime.now(timezone.utc).date()
    dates = []
    for i in range(0, 8):
        d = now_date - timedelta(days=i)
        if d >= date(2026, 6, 11):
            dates.append(d.strftime('%Y-%m-%d'))
    for i in range(1, 4):
        dates.append((now_date + timedelta(days=i)).strftime('%Y-%m-%d'))
 
    for fetch_date in dates:
        data = api_get('/competition_matches_list?date=' + fetch_date + '&timezone=UTC')
        if not data:
            continue
        response = data.get('response', {})
        if not isinstance(response, dict):
            continue
        items = response.get('items', [])
        for comp in items:
            if not isinstance(comp, dict):
                continue
            if str(comp.get('cid', '')) != '1382':
                continue
            for m in comp.get('matches', []):
                if not isinstance(m, dict):
                    continue
                mid = str(m.get('mid') or m.get('id') or id(m))
                if mid not in seen_ids:
                    seen_ids.add(mid)
                    all_matches.append(m)
 
    print('  Fetched ' + str(len(all_matches)) + ' matches')
    return all_matches
 
def parse_fixture(fx):
    teams  = fx.get('teams', {})
    result = fx.get('result', {})
    status = str(fx.get('status', '0')).strip()
 
    home_name = teams.get('home', {}).get('tname', '') or teams.get('home', {}).get('fullname', '')
    away_name = teams.get('away', {}).get('tname', '') or teams.get('away', {}).get('fullname', '')
    home_code = name_to_code(home_name)
    away_code = name_to_code(away_name)
 
    hg = result.get('home')
    ag = result.get('away')
    winner = result.get('winner', '')
 
    # Status codes: "0"=upcoming, "1"=live, "2"=finished, "3"=postponed
    is_finished = status == '2' or winner in ('home', 'away', 'draw')
    # Check kickoff time
    ko_check = parse_utc(fx.get('datestart') or fx.get('date_time') or fx.get('date') or '')
    now_utc = datetime.now(timezone.utc)
    kickoff_passed = ko_check is not None and ko_check <= now_utc
    # If kickoff was more than 3 hours ago and still showing as live, force finished
    if ko_check and (now_utc - ko_check).total_seconds() > 10800:
        is_finished = True
    is_live     = status == '1' and not is_finished and kickoff_passed
    is_upcoming = not is_finished and not is_live
 
    # Get current match minute
    raw_time = fx.get('elapsed') or fx.get('time') or 0
    try:
        minute = int(str(raw_time).split('+')[0]) if raw_time else 0
    except:
        minute = 0
    ko_str  = fx.get('datestart') or fx.get('date_time') or fx.get('date') or ''
    ko      = parse_utc(ko_str)
    round_  = str(fx.get('round') or fx.get('stage') or 'Group Stage')
    if isinstance(fx.get('round'), dict):
        round_ = fx['round'].get('name', 'Group Stage')
 
    return {
        'fixture_id': fx.get('mid'),
        'home':       home_code,
        'away':       away_code,
        'home_name':  home_name,
        'away_name':  away_name,
        'hg':         int(hg) if hg is not None else 0,
        'ag':         int(ag) if ag is not None else 0,
        'minute':     int(minute) if minute else 0,
        'status':     status,
        'stage':      round_,
        'date':       ko_str[:10] if ko_str else '',
        'kickoff':    ko,
        'live':       is_live,
        'finished':   is_finished,
        'upcoming':   is_upcoming,
    }
 
def should_update(fixtures):
    now = datetime.now(timezone.utc)
    next_kickoff = None
    for fx in fixtures:
        if fx['live']:
            return True, 'Match live: ' + str(fx['home_name']) + ' vs ' + str(fx['away_name']), None
        if fx['upcoming'] and fx['kickoff']:
            mins = (fx['kickoff'] - now).total_seconds() / 60
            if -5 <= mins <= 10:
                return True, 'Kickoff imminent: ' + str(fx['home_name']), fx['kickoff']
            if mins > 0 and (next_kickoff is None or fx['kickoff'] < next_kickoff):
                next_kickoff = fx['kickoff']
    for fx in fixtures:
        if fx['finished'] and fx['kickoff']:
            age_hours = (now - fx['kickoff']).total_seconds() / 3600
            if age_hours < 3:
                return True, 'Recent result: ' + str(fx['home_name']) + ' ' + str(fx['hg']) + '-' + str(fx['ag']) + ' ' + str(fx['away_name']), None
    if next_kickoff:
        mins = (next_kickoff - now).total_seconds() / 60
        return False, 'Next kickoff in ' + str(round(mins)) + 'm', next_kickoff
    return False, 'No active matches', None
 
def compute_standings(finished, base_groups):
    standings = {}
    for g, teams in base_groups.items():
        standings[g] = {t['code']: {'pts':0,'gd':0,'gf':0,'ga':0,'played':0} for t in teams}
    for fx in finished:
        h, a = fx['home'], fx['away']
        if not h or not a:
            continue
        grp = None
        for g, teams in base_groups.items():
            codes = [t['code'] for t in teams]
            if h in codes and a in codes:
                grp = g
                break
        if not grp:
            continue
        if 'Group' not in fx.get('stage', 'Group'):
            continue
        s = standings[grp]
        hg, ag = fx['hg'], fx['ag']
        s[h]['gf']+=hg; s[h]['ga']+=ag; s[h]['gd']+=hg-ag; s[h]['played']+=1
        s[a]['gf']+=ag; s[a]['ga']+=hg; s[a]['gd']+=ag-hg; s[a]['played']+=1
        if hg > ag:
            s[h]['pts'] += 3
        elif ag > hg:
            s[a]['pts'] += 3
        else:
            s[h]['pts'] += 1
            s[a]['pts'] += 1
    return {g: sorted(tbl.items(), key=lambda x: (-x[1]['pts'], -x[1]['gd'], -x[1]['gf']))
            for g, tbl in standings.items()}
 
BASE_GOALS = 1.35
EXP = 1.15
 
def get_lambdas(home, away, teams):
    hd = teams[home]; ad = teams[away]
    h_att = ((hd['P2']*0.50+hd['P1']*0.28+hd['P3']*0.12+hd['P4']*0.10)/100)**EXP
    a_def = ((ad['P1']*0.50+ad['P2']*0.22+ad['P4']*0.18+ad['P3']*0.10)/100)**EXP
    a_att = ((ad['P2']*0.50+ad['P1']*0.28+ad['P3']*0.12+ad['P4']*0.10)/100)**EXP
    h_def = ((hd['P1']*0.50+hd['P2']*0.22+hd['P4']*0.18+hd['P3']*0.10)/100)**EXP
    return max(0.1, BASE_GOALS*h_att/max(a_def,0.1)), max(0.1, BASE_GOALS*a_att/max(h_def,0.1))
 
def update_scores(base_teams, finished):
    teams = {code: dict(t) for code, t in base_teams.items()}
    actual = defaultdict(lambda: {'gf':0,'ga':0,'n':0})
    expected = defaultdict(lambda: {'gf':0.0,'ga':0.0})
    for fx in finished:
        h, a = fx['home'], fx['away']
        if not h or not a or h not in teams or a not in teams:
            continue
        lh, la = get_lambdas(h, a, teams)
        actual[h]['gf']+=fx['hg']; actual[h]['ga']+=fx['ag']; actual[h]['n']+=1
        actual[a]['gf']+=fx['ag']; actual[a]['ga']+=fx['hg']; actual[a]['n']+=1
        expected[h]['gf']+=lh; expected[h]['ga']+=la
        expected[a]['gf']+=la; expected[a]['ga']+=lh
    LEARN = 0.08
    for code in teams:
        n = actual[code]['n']
        if n == 0:
            continue
        att_d = (actual[code]['gf']/n - expected[code]['gf']/n) * LEARN * 10
        def_d = (expected[code]['ga']/n - actual[code]['ga']/n) * LEARN * 8
        nudge = max(-8.0, min(6.0, att_d + def_d))
        teams[code]['score'] = round(teams[code]['score'] + nudge, 2)
        teams[code]['form_nudge'] = round(nudge, 2)
        teams[code]['played'] = n
    return teams
 
def live_win_probability(home, away, hg_now, ag_now, minute, teams):
    if home not in teams or away not in teams:
        return None
    lh_90, la_90 = get_lambdas(home, away, teams)
    mins_played = max(1, min(int(minute), 89))
    remaining = (90 - mins_played) / 90
    extra_h = np.random.poisson(lh_90 * remaining, 10000)
    extra_a = np.random.poisson(la_90 * remaining, 10000)
    final_h = hg_now + extra_h
    final_a = ag_now + extra_a
    h_wins = int(np.sum(final_h > final_a))
    draws  = int(np.sum(final_h == final_a))
    a_wins = int(np.sum(final_a > final_h))
    return {
        'home_win':  round(h_wins/10000*100, 1),
        'draw':      round(draws /10000*100, 1),
        'away_win':  round(a_wins/10000*100, 1),
        'minute':    mins_played,
        'remaining': round(remaining*90, 0),
    }
 
def compute_live_probs(live_fixtures, teams):
    probs = []
    for fx in live_fixtures:
        if not fx['home'] or not fx['away']:
            continue
        prob = live_win_probability(fx['home'], fx['away'], fx['hg'], fx['ag'], fx['minute'], teams)
        if prob:
            probs.append({
                'home': fx['home'], 'away': fx['away'],
                'hg': fx['hg'], 'ag': fx['ag'],
                'minute': fx['minute'], 'stage': fx['stage'],
                'prob': prob,
            })
    return probs
 
def get_eliminated(finished):
    elim = set()
    for fx in finished:
        if 'Group' in fx.get('stage', 'Group'):
            continue
        if fx['hg'] < fx['ag']:
            elim.add(fx['home'])
        elif fx['ag'] < fx['hg']:
            elim.add(fx['away'])
    return [e for e in elim if e]
 
def get_phase(fixtures):
    stages = set(fx['stage'] for fx in fixtures if fx['finished'] or fx['live'])
    if any('Final' in s and 'Semi' not in s and 'Quarter' not in s for s in stages):
        return 'FINAL'
    if any('Semi' in s for s in stages):
        return 'SEMI_FINALS'
    if any('Quarter' in s for s in stages):
        return 'QUARTER_FINALS'
    if any('Round of 32' in s or 'Last 32' in s for s in stages):
        return 'ROUND_OF_32'
    if any('Group' in s for s in stages):
        return 'GROUP_STAGE'
    return 'PRE_TOURNAMENT'
 
def format_result(fx):
    return {
        'home': fx['home'], 'away': fx['away'],
        'hg': fx['hg'], 'ag': fx['ag'],
        'live': fx['live'], 'stage': fx['stage'],
        'date': fx['date'], 'status': fx['status'],
        'minute': fx['minute'],
    }
 
def format_fixture(fx):
    now = datetime.now(timezone.utc)
    mins = round((fx['kickoff'] - now).total_seconds()/60) if fx['kickoff'] else 9999
    return {
        'home': fx['home'], 'away': fx['away'],
        'date': fx['date'] + ' UTC',
        'stage': fx['stage'],
        'mins_until': mins,
    }
 
def main():
    now = datetime.now(timezone.utc)
    print('Project Olympus Live Updater -- ' + now.isoformat())
 
    with open('olympus_v2p_results.json') as f:
        BASE = json.load(f)
 
    print('Fetching WC 2026 fixtures by date...')
    raw = fetch_fixtures()
    if not raw:
        print('No fixtures -- aborting')
        sys.exit(0)
 
    fixtures = []
    for fx in raw:
        p = parse_fixture(fx)
        if p['home'] and p['away']:
            fixtures.append(p)
        else:
            print('  Unmapped: ' + str(fx.get('teams',{}).get('home',{}).get('tname','?')) +
                  ' vs ' + str(fx.get('teams',{}).get('away',{}).get('tname','?')))
 
    finished = [fx for fx in fixtures if fx['finished']]
    live_now = [fx for fx in fixtures if fx['live']]
    upcoming = sorted([fx for fx in fixtures if fx['upcoming'] and fx['kickoff']],
                      key=lambda x: x['kickoff'])
 
    print('  Total fixtures: ' + str(len(fixtures)))
    print('  Finished: ' + str(len(finished)) + ' | Live: ' + str(len(live_now)) + ' | Upcoming: ' + str(len(upcoming)))
 
    update, reason, next_ko = should_update(fixtures)
    print('  Should update: ' + str(update) + ' -- ' + reason)
 
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
            print('Wrote initial status file')
        else:
            print('No update needed -- skipping commit')
        sys.exit(0)
 
    print('Running full update...')
    phase         = get_phase(fixtures)
    updated_teams = update_scores(BASE['teams'], finished)
    standings     = compute_standings(finished, BASE['groups'])
    eliminated    = get_eliminated(finished)
    live_probs    = compute_live_probs(live_now, updated_teams)
 
    for lp in live_probs:
        p = lp['prob']
        hn = BASE['teams'].get(lp['home'],{}).get('name', lp['home'])
        an = BASE['teams'].get(lp['away'],{}).get('name', lp['away'])
        print('  In-play: ' + hn + ' ' + str(lp['hg']) + '-' + str(lp['ag']) + ' ' + an +
              ' @ ' + str(lp['minute']) + "' -> H:" + str(p['home_win']) +
              '% D:' + str(p['draw']) + '% A:' + str(p['away_win']) + '%')
 
    print('  All finished results:')
    for fx in finished:
        print('    ' + str(fx['home_name']) + ' ' + str(fx['hg']) + '-' + str(fx['ag']) + ' ' + str(fx['away_name']) + ' (status=' + str(fx['status']) + ')')
 
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
            [{'code':c,'win':t.get('winner',0),'final':t.get('final',0),
              'sf':t.get('sf',0),'qf':t.get('qf',0),'r16':t.get('r16',0),
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
 
    print('Wrote olympus_live.json (' + str(os.path.getsize('olympus_live.json')//1024) + 'KB)')
    print('Phase: ' + phase + ' | Results: ' + str(len(finished)) + ' | Live: ' + str(len(live_now)))
    print('Done.')
 
if __name__ == '__main__':
    main()
