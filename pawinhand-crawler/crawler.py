"""포인핸드 최근 3개월 전체 보호동물 수집. python crawler.py collect

웹사이트가 실제 호출하는 공개 JSON 응답을 사용합니다. 정부 OpenAPI가 아닙니다.
필터 선택값과 요청 날짜를 검증하고 페이지별로 저장해 중단 후 이어받습니다.
"""
import argparse
import calendar
import hashlib
import json
import logging
import re
import sqlite3
import time
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser
from datetime import date, datetime, timezone
from pathlib import Path

SITE = 'https://pawinhand.kr/shelter/animal'
ENDPOINT = 'https://pawinhand.net/bridge/animals/condition'
UA = 'CapstonePawinhandCollector/0.3'

def now():
    return datetime.now(timezone.utc).isoformat()

def dump(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    temp.replace(path)

def three_months_before(end):
    month_index = end.year * 12 + end.month - 1 - 3
    year, month = divmod(month_index, 12)
    month += 1
    return date(year, month, min(end.day, calendar.monthrange(year, month)[1]))

def validate_proof(proof):
    url = urllib.parse.urlsplit(proof['request_url'])
    if url.scheme != 'https' or url.netloc != 'pawinhand.net' or url.path != '/bridge/animals/condition':
        raise ValueError('Unexpected website data endpoint')
    query = dict(urllib.parse.parse_qsl(url.query))
    expected = {'city':'모든 지역','country':'전체','species':'모든 동물','breeds':'전체',
                'state':'전체','sex':'전체','neutral':'전체'}
    if any(query.get(k) != v for k,v in expected.items()):
        raise ValueError('Request filters are not all regions/species/statuses')
    if proof['checkboxes'] != [True, False]:
        raise ValueError('Recent-three-months checkbox must be checked; protected-only unchecked')
    if proof['selects'] != ['모든 지역','모든 동물','전체','전체','전체']:
        raise ValueError('Actual selected filter values do not match')
    start, end = map(date.fromisoformat, proof['dates'])
    if start != three_months_before(end):
        raise ValueError('Selected range is not three calendar months')
    if query.get('start_date') != start.strftime('%Y%m%d') or query.get('end_date') != end.strftime('%Y%m%d'):
        raise ValueError('UI dates and network request dates disagree')
    return query

def bootstrap(channel):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        options = {'headless':True}
        if channel:
            options['channel'] = channel
        browser = p.chromium.launch(**options)
        try:
            page = browser.new_page(locale='ko-KR')
            with page.expect_response(lambda r: r.url.startswith(ENDPOINT+'?'), timeout=45000) as wait, \
                 page.expect_response(lambda r: r.url == 'https://pawinhand.net/bridge/location', timeout=45000) as locations, \
                 page.expect_response(lambda r: r.url == 'https://pawinhand.net/bridge/breeds', timeout=45000) as breeds:
                page.goto(SITE, wait_until='domcontentloaded', timeout=45000)
            response = wait.value
            locations.value.body()
            breeds.value.body()
            page.wait_for_timeout(500)
            # The site initializes filter options from its cached reference lists.
            # A clean browser's first mount can keep the modal options empty.
            page.reload(wait_until='networkidle', timeout=45000)
            if response.status != 200:
                raise RuntimeError(f'Initial data response: HTTP {response.status}')
            page.get_by_text(re.compile('최근 3개월')).click(timeout=30000)
            page.get_by_role('button', name='검색하기', exact=True).wait_for()
            page.locator('input[type=checkbox]').nth(0).check()
            page.locator('input[type=checkbox]').nth(1).uncheck()
            for i,value in enumerate(['모든 지역','모든 동물','전체','전체','전체']):
                page.locator('select').nth(i).select_option(label=value)
            proof = page.evaluate("""() => ({
              checkboxes:[...document.querySelectorAll('input[type=checkbox]')].map(e=>e.checked),
              dates:[...document.querySelectorAll('input[aria-label="Datepicker input"]')].map(e=>e.value),
              selects:[...document.querySelectorAll('select')].map(e=>e.value)
            })""")
            with page.expect_response(lambda r: r.url.startswith(ENDPOINT+'?'), timeout=45000) as applied:
                page.get_by_role('button',name='검색하기',exact=True).click()
            response=applied.value
            if response.status != 200:
                raise RuntimeError(f'Applied filter response: HTTP {response.status}')
            proof.update(request_url=response.url, verified_at=now())
            validate_proof(proof)
            return proof
        finally:
            browser.close()

def robots_allowed(base, path):
    try:
        request = urllib.request.Request(base+'/robots.txt',headers={'User-Agent':UA})
        with urllib.request.urlopen(request,timeout=30) as r:
            text = r.read().decode('utf-8')
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return  # No robots.txt published, not a grant of republication rights.
        raise
    robot = urllib.robotparser.RobotFileParser()
    robot.parse(text.splitlines())
    if not robot.can_fetch(UA,base+path):
        raise PermissionError('robots.txt disallows collection')

def fetch(query, offset, limit, delay):
    params = {**query,'offset':str(offset),'limit':str(limit)}
    url = ENDPOINT+'?'+urllib.parse.urlencode(params)
    for attempt in range(3):
        time.sleep(delay*(attempt+1))
        try:
            request=urllib.request.Request(url,headers={'User-Agent':UA,'Accept':'application/json','Referer':SITE})
            with urllib.request.urlopen(request,timeout=45) as response:
                rows=json.load(response)
            if not isinstance(rows,list):
                raise ValueError('Expected an array of public animal records')
            return rows,url
        except urllib.error.HTTPError as exc:
            if exc.code in (401,403,429):
                raise PermissionError(f'HTTP {exc.code}: stop, do not bypass') from exc
            if attempt==2:
                raise
        except (urllib.error.URLError,TimeoutError):
            if attempt==2:
                raise
        logging.warning('Retry page offset=%s attempt=%s',offset,attempt+2)

def validate_rows(rows, start, end):
    for row in rows:
        if not isinstance(row,dict) or not row.get('notify_number'):
            raise ValueError('Missing notice identifier')
        for required in ('feature','age','weight','shelter_name','registration_date'):
            if required not in row:
                raise ValueError('Response schema changed: '+required)
        stamp=row['registration_date']
        try:
            actual=datetime.strptime(stamp,'%Y%m%d').date()
        except (TypeError,ValueError) as exc:
            raise ValueError('Invalid registration_date: '+str(stamp)) from exc
        if not start <= actual <= end:
            raise ValueError(f'Out-of-range registration date: {stamp}')

def record(row, period, stamp):
    return {'notice_id':row['notify_number'], 'source':'pawinhand',
            'source_url':SITE+'/detail/'+urllib.parse.quote(row['notify_number'],safe=''),
            'collection_scope':'최근 3개월 · 모든 지역 · 모든 동물 · 전체 상태',
            'period_start':period[0], 'period_end':period[1], 'collected_at':stamp,
            'registration_date':row['registration_date'], 'species':row.get('species'),
            'breed':row.get('breeds'), 'sex_raw':row.get('sex'), 'neutered_raw':row.get('neutral'),
            'age_raw':row.get('age'), 'weight_raw':row.get('weight'), 'color':row.get('color'),
            'status_raw':row.get('state'), 'special_mark':row.get('feature'),
            'notice_start':row.get('notify_sdt'),'notice_end':row.get('notify_edt'),
            'found_location':row.get('find_location'), 'shelter_name':row.get('shelter_name'),
            'shelter_address':row.get('shelter_address'),'shelter_tel':row.get('shelter_tel'),
            'office_name':row.get('office_name'),
            'image_urls':list(dict.fromkeys(row[k] for k in ('image','image2','image3','more_image1') if row.get(k))),
            'raw':row, 'schema_version':3}

def database(path):
    db=sqlite3.connect(path)
    db.execute('CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)')
    db.execute('CREATE TABLE IF NOT EXISTS animals (notice_id TEXT PRIMARY KEY, payload TEXT)')
    db.execute('CREATE TABLE IF NOT EXISTS pages (offset INTEGER PRIMARY KEY, row_count INTEGER, fetched_at TEXT, url TEXT, digest TEXT)')
    return db

def get_state(db):
    row=db.execute("SELECT value FROM meta WHERE key='state'").fetchone()
    return json.loads(row[0]) if row else None

def set_state(db,state):
    db.execute("INSERT INTO meta VALUES ('state',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(json.dumps(state,ensure_ascii=False),))

def save_page(db,state,rows,url):
    start,end=map(date.fromisoformat,state['proof']['dates'])
    validate_rows(rows,start,end)
    stamp=now();old_count=db.execute('SELECT count(*) FROM animals').fetchone()[0]
    new_state={**state,'next_offset':state['next_offset']+len(rows),'updated_at':stamp,'error':None}
    with db:
        for row in rows:
            value=record(row,state['proof']['dates'],stamp)
            db.execute('INSERT INTO animals VALUES (?,?) ON CONFLICT(notice_id) DO UPDATE SET payload=excluded.payload',
                       (row['notify_number'],json.dumps(value,ensure_ascii=False)))
        total=db.execute('SELECT count(*) FROM animals').fetchone()[0]
        if total==old_count and rows:
            raise RuntimeError('Page added no new notice identifiers; stop rather than loop')
        digest=hashlib.sha256(json.dumps(rows,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
        db.execute('INSERT OR REPLACE INTO pages VALUES (?,?,?,?,?)',(state['next_offset'],len(rows),stamp,url,digest))
        new_state['unique_count']=total
        new_state['duplicate_rows']=state.get('duplicate_rows',0)+len(rows)-(total-old_count)
        set_state(db,new_state)
    return new_state

def export_data(db,state,folder):
    # Fixed-size chunks keep individual files reviewable and uploadable.
    cursor=db.execute('SELECT payload FROM animals ORDER BY notice_id')
    files=[];part=1;count=0
    while True:
        batch=cursor.fetchmany(1000)
        if not batch: break
        values=[json.loads(r[0]) for r in batch]
        name=f'animals-{part:04d}.json';dump(folder/name,values)
        files.append({'file':name,'count':len(values),'sha256':hashlib.sha256((folder/name).read_bytes()).hexdigest()})
        part+=1;count+=len(values)
    pages=[dict(zip(('offset','row_count','fetched_at','url','sha256'),r)) for r in db.execute('SELECT * FROM pages ORDER BY offset')]
    summary={**state,'exported_at':now(),'exported_count':count,'files':files,
             'collection_complete':state.get('complete',False) and count==state.get('unique_count',0)}
    dump(folder/'manifest.json',summary)
    dump(folder/'progress.json',state)
    dump(folder/'requests.json',pages)
    dump(folder/'failures.json',[{'offset':state['next_offset'],'error':state['error']}] if state.get('error') else [])
    return summary

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['collect','resume','retry','status'],nargs='?',default='collect')
    parser.add_argument('--output-dir',type=Path,default=Path('data/three_months'))
    parser.add_argument('--channel',choices=['chrome','msedge'])
    parser.add_argument('--delay',type=float,default=1.5)
    parser.add_argument('--page-size',type=int,default=100)
    parser.add_argument('--max-pages',type=int,default=5000)
    args=parser.parse_args()
    if args.delay<1 or not 1<=args.page_size<=100 or args.max_pages<1:
        parser.error('delay >= 1; page-size between 1 and 100; max-pages positive')
    folder=args.output_dir;folder.mkdir(parents=True,exist_ok=True)
    logging.basicConfig(level=logging.INFO,format='%(asctime)s %(levelname)s %(message)s',
                        handlers=[logging.StreamHandler(),logging.FileHandler(folder/'crawler.log',encoding='utf-8')])
    db=database(folder/'state.sqlite3');state=get_state(db)
    if args.command=='status':
        print(json.dumps(export_data(db,state,folder) if state else {'state':'not_started'},ensure_ascii=False,indent=2));db.close();return
    if args.command in ('resume','retry') and not state:
        parser.error('No saved job to resume; run collect first')
    if state and state.get('complete'):
        export_data(db,state,folder);logging.info('Already complete: %s',state['unique_count']);db.close();return
    robots_allowed('https://pawinhand.kr','/shelter/animal')
    robots_allowed('https://pawinhand.net','/bridge/animals/condition')
    if not state:
        proof=bootstrap(args.channel)
        state={'schema_version':3,'scope':'최근 3개월 · 모든 지역 · 모든 동물 · 전체 상태',
               'proof':proof,'started_at':now(),'next_offset':0,'unique_count':0,'duplicate_rows':0,'complete':False,'error':None}
        with db:set_state(db,state)
        dump(folder/'filter-proof.json',proof)
    query=validate_proof(state['proof'])
    try:
        for _ in range(args.max_pages):
            rows,url=fetch(query,state['next_offset'],args.page_size,args.delay)
            if not rows:
                # A second empty response confirms pagination exhaustion.
                confirm,_=fetch(query,state['next_offset'],args.page_size,args.delay)
                if confirm:
                    rows=confirm
                else:
                    state.update(complete=True,error=None,finished_at=now(),end_evidence={'offset':state['next_offset'],'url':url,'empty_responses':2})
                    with db:set_state(db,state)
                    break
            state=save_page(db,state,rows,url)
            dump(folder/'progress.json',state)
            logging.info('Saved offset=%d unique=%d',state['next_offset'],state['unique_count'])
        else:
            raise RuntimeError('Safety page limit reached; resume to continue')
    except BaseException as exc:
        state=get_state(db)
        state.update(error=f'{type(exc).__name__}: {exc}',complete=False,updated_at=now())
        with db:set_state(db,state)
        raise
    finally:
        summary=export_data(db,state,folder);db.close()
        logging.info('Finished: exported=%d complete=%s',summary['exported_count'],summary['collection_complete'])

if __name__=='__main__':
    main()
