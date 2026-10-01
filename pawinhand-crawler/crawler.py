"""목록 순서 유지 + 실제 상세 페이지 방문. README의 sample 명령부터 실행하세요."""
import argparse
import asyncio
import calendar
from collections import Counter
from datetime import date, datetime, timezone
import json
import logging
from pathlib import Path
import re
import sqlite3
import time
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, unquote
import urllib.robotparser

from playwright.async_api import async_playwright

SITE = 'https://pawinhand.kr/shelter/animal'
API = 'https://pawinhand.net/bridge/'
LIST = API + 'animals/condition'
GAUGES = {'health_state': '건강상태', 'activity': '활동성',
          'sociability': '사회성', 'aggression': '친화도'}
TESTS = {'parvo': '파보', 'corona': '코로나', 'heartworm': '심장사상충', 'measles': '홍역'}


class AccessStopped(RuntimeError):
    pass


def timestamp():
    return datetime.now(timezone.utc).isoformat()


def period(end):
    year, month = divmod(end.year * 12 + end.month - 4, 12)
    return date(year, month + 1, min(end.day, calendar.monthrange(year, month + 1)[1])), end


def write_json(path, value):
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    temp.replace(path)


def check_http(status):
    if status in (401, 403, 429):
        raise AccessStopped(f'HTTP {status}: 접근 제한으로 중단')
    if status != 200:
        raise RuntimeError(f'HTTP {status}: 정상 응답 아님')


async def check_robots(context):
    for base, paths in [('https://pawinhand.kr', ['/shelter/animal', '/shelter/animal/detail/']),
                        ('https://pawinhand.net', ['/bridge/animals/condition', '/bridge/animal/',
                                                 '/bridge/shelter/animal/', '/bridge/animal/tag/'])]:
        response = await context.request.get(base + '/robots.txt', timeout=30000)
        if response.status == 404:
            continue
        check_http(response.status)
        robot = urllib.robotparser.RobotFileParser()
        robot.parse((await response.text()).splitlines())
        if any(not robot.can_fetch('*', base + path) for path in paths):
            raise AccessStopped('robots.txt에서 수집 경로 제한')


def validate_list(rows, start, end):
    if not isinstance(rows, list):
        raise ValueError('목록 응답 형식 변경')
    for row in rows:
        if not isinstance(row, dict) or not row.get('notify_number'):
            raise ValueError('공고번호 누락')
        day = datetime.strptime(row['registration_date'], '%Y%m%d').date()
        if not start <= day <= end:
            raise ValueError(f'조회 범위 밖 등록날짜: {day}')


async def search(context, as_of):
    """Use the real search form and verify rendered list order against its response."""
    page = await context.new_page()
    try:
        await page.goto(SITE, wait_until='networkidle', timeout=60000)
        # A clean first mount may have unpopulated reference lists.
        await page.reload(wait_until='networkidle', timeout=60000)
        await page.get_by_text('최근 3개월', exact=False).first.click()
        checks = page.locator('input[type=checkbox]')
        await checks.nth(0).check()
        await checks.nth(1).uncheck()
        for i, label in enumerate(['모든 지역', '모든 동물', '전체', '전체', '전체']):
            await page.locator('select').nth(i).select_option(label=label)
        start, end = period(as_of)
        expected = [start.isoformat(), end.isoformat()]
        dates = page.locator('input[aria-label="Datepicker input"]')
        actual = [await dates.nth(i).input_value() for i in range(2)]
        if actual != expected:
            # Changing the range through the UI keeps the captured request auditable.
            await checks.nth(0).uncheck()
            for i, value in enumerate(expected):
                await dates.nth(i).fill(value)
                await dates.nth(i).press('Enter')
        async with page.expect_response(lambda r: r.url.startswith(LIST + '?'), timeout=45000) as event:
            await page.get_by_role('button', name='검색하기', exact=True).click()
        response = await event.value
        check_http(response.status)
        rows = await response.json()
        query = dict(parse_qsl(urlsplit(response.url).query))
        expected_query = {'city': '모든 지역', 'country': '전체', 'species': '모든 동물',
                          'breeds': '전체', 'state': '전체', 'sex': '전체', 'neutral': '전체',
                          'start_date': start.strftime('%Y%m%d'), 'end_date': end.strftime('%Y%m%d')}
        if any(query.get(k) != v for k, v in expected_query.items()):
            raise ValueError('화면 검색조건과 요청 기간/필터 불일치')
        validate_list(rows, start, end)
        if rows:
            await page.locator('.animal-list-card').first.wait_for(timeout=15000)
            await page.wait_for_function("id => [...document.querySelectorAll('.animal-list-card')].some(e=>e.innerText.includes(id))", arg=rows[0]['notify_number'])
            cards = await page.locator('.animal-list-card').all_inner_texts()
            if len(cards) != len(rows) or any(r['notify_number'] not in card for r, card in zip(rows, cards)):
                raise ValueError('목록 응답 순서와 화면 카드 순서 불일치')
        proof = {'verified_at': timestamp(), 'period_start': expected[0], 'period_end': expected[1],
                 'query': query, 'request_url': response.url,
                 'first_page_notice_ids': [r['notify_number'] for r in rows],
                 'order': 'site_list_order', 'dom_order_verified': True}
        return proof, rows
    finally:
        await page.close()


def open_db(folder, settings):
    folder.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(folder / 'state.sqlite3')
    db.execute('CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY,value TEXT)')
    db.execute('CREATE TABLE IF NOT EXISTS animals (notice_id TEXT PRIMARY KEY,position INTEGER UNIQUE,list_raw TEXT,result TEXT,error TEXT)')
    old = get_meta(db, 'settings')
    if old and old != settings:
        db.close()
        raise ValueError('기간/표본 설정이 다른 작업입니다. 새 출력 폴더를 사용하세요.')
    if not old:
        with db:
            set_meta(db, 'settings', settings)
            set_meta(db, 'started_at', timestamp())
            set_meta(db, 'offset', 0)
    return db


def get_meta(db, key, default=None):
    row = db.execute('SELECT value FROM meta WHERE key=?', (key,)).fetchone()
    return json.loads(row[0]) if row else default


def set_meta(db, key, value):
    db.execute('INSERT OR REPLACE INTO meta VALUES (?,?)', (key, json.dumps(value, ensure_ascii=False)))


async def collect_list(context, db, args):
    if get_meta(db, 'list_finished'):
        return
    proof = get_meta(db, 'filter_proof')
    first = None
    if proof is None:
        proof, first = await search(context, args.as_of)
        with db:
            set_meta(db, 'filter_proof', proof)
    query = proof['query']
    offset = get_meta(db, 'offset', 0)
    start, end = period(args.as_of)
    while True:
        if offset == 0 and first is not None:
            rows = first
        else:
            await asyncio.sleep(args.interval)
            response = await context.request.get(LIST + '?' + urlencode({**query, 'offset': offset}), timeout=45000)
            check_http(response.status)
            rows = await response.json()
        validate_list(rows, start, end)
        if not rows:
            await asyncio.sleep(args.interval)
            response = await context.request.get(LIST + '?' + urlencode({**query, 'offset': offset}), timeout=45000)
            check_http(response.status)
            if await response.json():
                raise RuntimeError('빈 페이지 재확인 결과가 달라짐; 목록 변동 후 재개 필요')
            with db:
                set_meta(db, 'list_exhausted', True)
                set_meta(db, 'list_finished', True)
            break
        count = db.execute('SELECT count(*) FROM animals').fetchone()[0]
        inserted = 0
        with db:
            for row in rows:
                if args.limit and count >= args.limit:
                    break
                changed = db.execute('INSERT OR IGNORE INTO animals (notice_id,position,list_raw) VALUES (?,?,?)',
                                     (row['notify_number'], count + 1, json.dumps(row, ensure_ascii=False))).rowcount
                count += changed
                inserted += changed
            # Duplicate identifiers do not mean pagination is exhausted.
            # Advance by response length even when every identifier is already stored.
            signature = [r['notify_number'] for r in rows]
            repeats = get_meta(db, 'identical_page_repeats', 0) + 1 if signature == get_meta(db, 'last_page_ids') else 0
            if repeats >= 3:
                raise RuntimeError('동일 응답이 다른 위치에서 연속 반복됨; 서버 페이지 처리 확인 필요')
            set_meta(db, 'last_page_ids', signature)
            set_meta(db, 'identical_page_repeats', repeats)
            for row in rows:
                db.execute('UPDATE animals SET list_raw=? WHERE notice_id=?', (json.dumps(row, ensure_ascii=False), row['notify_number']))
            offset += len(rows)
            set_meta(db, 'offset', offset)
            if args.limit and count >= args.limit:
                set_meta(db, 'list_finished', True)
        logging.info('목록 %d건 저장 (사이트 순서)', count)
        if args.limit and count >= args.limit:
            break


def normalize(notice_id, base, more, tags, position, as_of, rendered):
    if not isinstance(base, dict) or base.get('notify_number') != notice_id:
        raise ValueError('기본 상세 공고번호 불일치')
    if more is not None and not isinstance(more, dict):
        raise ValueError('추가 정보 응답 형식 변경')
    if more and (more.get('notify_number') != notice_id or not set(GAUGES).union(TESTS).issubset(more)):
        raise ValueError('추가 정보 공고번호/필드 불일치')
    if not isinstance(tags, list) or any(not isinstance(t, dict) or t.get('notify_number') != notice_id or 'tag_name' not in t for t in tags):
        raise ValueError('태그 응답 형식/공고번호 불일치')
    raw = more or {}
    values = [raw.get(k) for k in list(GAUGES) + list(TESTS) + ['personality_comment', 'medical_comment']]
    present = bool(tags) or any(v is not None and v != '' for v in values)
    start, end = period(as_of)
    return {
        'schema_version': 2, 'notice_id': notice_id, 'list_position': position,
        'source_url': SITE + '/detail/' + quote(notice_id, safe=''),
        'period_start': start.isoformat(), 'period_end': end.isoformat(), 'collected_at': timestamp(),
        'species': base.get('species'), 'breed': base.get('breeds'), 'sex_raw': base.get('sex'),
        'neutered_raw': base.get('neutral'), 'age_raw': base.get('age'), 'weight_raw': base.get('weight'),
        'color': base.get('color'), 'status_raw': base.get('state'),
        'registration_date': base.get('registration_date'), 'notice_start': base.get('notify_sdt'),
        'notice_end': base.get('notify_edt'), 'found_location': base.get('find_location'),
        'shelter_name': base.get('shelter_name'), 'shelter_address': base.get('shelter_address'),
        'shelter_tel': base.get('shelter_tel'), 'office_name': base.get('office_name'),
        'special_mark': base.get('feature'), 'animal_name': raw.get('animal_name') or base.get('animal_name'),
        'image_urls': list(dict.fromkeys(
            [base[k] for k in ('image','image2','image3') if base.get(k)] +
            [('https://d12l2mexpetzlh.cloudfront.net/images/shelter/' + raw[k])
             if not raw[k].startswith(('https://','http://')) else raw[k]
             for k in ('more_image1','more_image2','more_image3','more_image4') if raw.get(k)])),
        'detail_status': 'present' if present else 'not_provided',
        'personality': {
            'gauges': {label: raw.get(k) for k, label in GAUGES.items()} if more else {},
            'tags': list(dict.fromkeys(t['tag_name'] for t in tags if t.get('tag_name'))),
            'comment': raw.get('personality_comment')},
        'health': {'tests': {label: raw.get(k) for k, label in TESTS.items()} if more else {},
                   'comment': raw.get('medical_comment')},
    }


def section_text(text, title, ends):
    lines = text.splitlines()
    try:
        begin = next(i for i, line in enumerate(lines) if line.strip() == title) + 1
    except StopIteration:
        return None
    end = next((i for i in range(begin, len(lines)) if lines[i].strip() in ends), len(lines))
    return '\n'.join(lines[begin:end]).strip()


async def visit_detail(context, notice_id, position, as_of, timeout):
    """Actually visit every detail URL; wait for additional responses, including empty responses."""
    page = await context.new_page()
    payloads = {}
    tasks = set()
    issues = []
    paths = {'/bridge/animal/' + notice_id: 'base',
             '/bridge/shelter/animal/' + notice_id: 'more',
             '/bridge/animal/tag/' + notice_id: 'tags'}

    async def capture(response):
        key = paths.get(unquote(urlsplit(response.url).path))
        if not key:
            return
        try:
            check_http(response.status)
            body = await response.body()
            payloads[key] = json.loads(body) if body.strip() else None
        except Exception as exc:
            issues.append(exc)

    def on_response(response):
        task = asyncio.create_task(capture(response))
        tasks.add(task)
        task.add_done_callback(tasks.discard)

    page.on('response', on_response)
    try:
        response = await page.goto(SITE + '/detail/' + quote(notice_id, safe=''), wait_until='domcontentloaded', timeout=timeout * 1000)
        if response:
            check_http(response.status)
        deadline = time.monotonic() + timeout
        while len(payloads) < 3:
            if issues:
                raise issues[0]
            if time.monotonic() > deadline:
                raise TimeoutError(f'상세 응답 확인 실패: {sorted(payloads)}')
            await asyncio.sleep(0.05)
        if issues:
            raise issues[0]
        await page.get_by_text('공고번호', exact=True).wait_for(timeout=10000)
        more = payloads['more']
        if isinstance(more, dict) and more.get('idx'):
            await page.get_by_text('성향정보', exact=True).wait_for(timeout=10000)
            await page.get_by_text('건강정보', exact=True).wait_for(timeout=10000)
        text = await page.locator('body').inner_text()
        rendered = {'personality': section_text(text, '성향정보', {'건강정보', '입양절차', '추가지원'}),
                    'health': section_text(text, '건강정보', {'입양절차', '입양지원', '추가지원'})}
        # Ensure delayed rendering has not caused a false "missing" result.
        for key in ('personality_comment', 'medical_comment'):
            comment = (more or {}).get(key)
            if comment and ''.join(comment.split()) not in ''.join(text.split()):
                raise ValueError(f'화면에 추가 설명이 아직 반영되지 않음: {key}')
        return normalize(notice_id, payloads['base'], more, payloads['tags'], position, as_of, rendered)
    finally:
        page.remove_listener('response', on_response)
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        await page.close()


def export(db, folder):
    counts = Counter(); files = []; batch = []; failures = []
    for notice, position, raw, result, error in db.execute('SELECT * FROM animals ORDER BY position'):
        if result:
            row = json.loads(result)
        else:
            row = {'notice_id': notice, 'list_position': position, 'list_raw': json.loads(raw),
                   'detail_status': 'failed' if error else 'pending', 'error': error}
        counts[row['detail_status']] += 1
        if error:
            failures.append({'notice_id': notice, 'error': error})
        batch.append(row)
        if len(batch) == 1000:
            name = f'animals-{len(files)+1:04d}.json'; write_json(folder/name,batch)
            files.append({'file':name,'count':len(batch)}); batch=[]
    if batch:
        name = f'animals-{len(files)+1:04d}.json'; write_json(folder/name,batch)
        files.append({'file':name,'count':len(batch)})
    settings = get_meta(db,'settings')
    report = {'settings':settings, 'counts':dict(counts), 'total':sum(counts.values()),
              'list_exhausted':get_meta(db,'list_exhausted',False),
              'sample': bool(settings['limit']), 'exported_at':timestamp(),
              'all_details_checked':not counts['failed'] and not counts['pending'] and bool(sum(counts.values())),
              'order':'site_list_order', 'files':files}
    report['complete'] = not report['sample'] and report['list_exhausted'] and report['all_details_checked']
    write_json(folder/'report.json',report); write_json(folder/'failures.json',failures)
    proof = get_meta(db,'filter_proof')
    if proof: write_json(folder/'filter-proof.json',proof)
    return report


async def collect_details(context, db, args):
    pending = db.execute('SELECT notice_id,position FROM animals WHERE result IS NULL ORDER BY position').fetchall()
    queue = asyncio.Queue()
    for item in pending: queue.put_nowait(item)
    stop = asyncio.Event(); errors = []; completed = 0
    async def worker():
        nonlocal completed
        consecutive = 0
        while not queue.empty() and not stop.is_set():
            try: notice, position = queue.get_nowait()
            except asyncio.QueueEmpty: return
            try:
                result = await visit_detail(context,notice,position,args.as_of,args.timeout)
                with db: db.execute('UPDATE animals SET result=?,error=NULL WHERE notice_id=?',(json.dumps(result,ensure_ascii=False),notice))
                consecutive = 0
            except Exception as exc:
                with db: db.execute('UPDATE animals SET error=? WHERE notice_id=?',(f'{type(exc).__name__}: {exc}',notice))
                logging.error('%s: %s',notice,exc); consecutive += 1
                if isinstance(exc, AccessStopped) or consecutive >= 3:
                    stop.set(); errors.append(exc)
            finally:
                completed += 1; queue.task_done()
            if completed % 10 == 0:
                logging.info('상세 %d/%d 처리',completed,len(pending))
                export(db,args.output)
            await asyncio.sleep(args.interval)
    await asyncio.gather(*(worker() for _ in range(args.workers)))
    if errors: raise RuntimeError(f'연속 실패 또는 접근 제한으로 중단: {errors[0]}')


async def run(args):
    args.output.mkdir(parents=True,exist_ok=True)
    logging.basicConfig(level=logging.INFO,format='%(asctime)s %(levelname)s %(message)s',
                        handlers=[logging.StreamHandler(),logging.FileHandler(args.output/'crawler.log',encoding='utf-8')])
    settings = {'as_of':args.as_of.isoformat(),'limit':args.limit,'scope':'모든 지역·모든 동물·전체 상태', 'version':2}
    db = open_db(args.output,settings) if args.command != 'inspect' else None
    began = time.monotonic()
    try:
        if args.command == 'status':
            print(json.dumps(export(db,args.output),ensure_ascii=False,indent=2)); return
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True, **({'channel':args.channel} if args.channel else {}))
            context = await browser.new_context(locale='ko-KR',timezone_id='Asia/Seoul',service_workers='block')
            # Images/videos/fonts are not needed to extract text or public JSON values.
            static_cache = {}
            static_lock = asyncio.Lock()
            async def route(request_route):
                if request_route.request.resource_type in ('image','media','font'):
                    await request_route.abort()
                    return
                url = request_route.request.url
                # Routing disables Chromium's HTTP cache. Reuse immutable hashed site assets,
                # but never cache animal/API responses: each detail remains a live lookup.
                if url.startswith(('https://pawinhand.kr/js/', 'https://pawinhand.kr/css/')):
                    async with static_lock:
                        if url not in static_cache:
                            response = await request_route.fetch(timeout=30000)
                            if response.status != 200:
                                await request_route.fulfill(response=response)
                                return
                            headers = {k:v for k,v in response.headers.items() if k.lower() not in ('content-encoding','content-length','transfer-encoding')}
                            static_cache[url] = (headers, await response.body())
                        headers, body = static_cache[url]
                    await request_route.fulfill(status=200,headers=headers,body=body)
                    return
                await request_route.continue_()
            await context.route('**/*',route)
            try:
                await check_robots(context)
                if args.command == 'inspect':
                    value = await visit_detail(context,args.notice,None,args.as_of,args.timeout)
                    value['scope_note'] = '개별 페이지 기능검증: 최근 3개월 목록 수집 결과에 포함한 것이 아님'
                    write_json(args.output/'detail-example.json',value)
                else:
                    await collect_list(context,db,args)
                    await collect_details(context,db,args)
            finally:
                await context.close(); await browser.close()
    finally:
        if db:
            report = export(db,args.output); db.close()
            logging.info('결과 %s / complete=%s / %.1f초',report['counts'],report['complete'],time.monotonic()-began)
    if db and (report['counts'].get('failed') or report['counts'].get('pending')):
        raise SystemExit(1)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['collect','status','inspect'])
    parser.add_argument('--as-of',type=date.fromisoformat,default=date(2026,9,30))
    parser.add_argument('--output',type=Path,default=Path('data/2026-09-30'))
    parser.add_argument('--limit',type=int,default=0,help='0=전체, 양수=목록 위에서부터 표본 N건')
    parser.add_argument('--workers',type=int,default=2,help='상세 페이지 동시 방문 수 (1~3)')
    parser.add_argument('--interval',type=float,default=0.5,help='작업별 방문 간 대기 (최소 0.5초)')
    parser.add_argument('--timeout',type=int,default=25)
    parser.add_argument('--channel',choices=['chrome','msedge'])
    parser.add_argument('--notice',help='inspect용 공고번호')
    args=parser.parse_args()
    if args.limit<0 or not 1<=args.workers<=3 or args.interval<0.5 or args.timeout<5:
        parser.error('limit>=0, workers=1~3, interval>=0.5, timeout>=5')
    if args.command=='inspect' and not args.notice: parser.error('inspect에는 --notice 필요')
    asyncio.run(run(args))


if __name__=='__main__':
    main()
