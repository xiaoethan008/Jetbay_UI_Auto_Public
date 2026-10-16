"""TC-135..139: real search against independent, read-only DB entities."""
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from playwright.sync_api import expect

from framework.regression_database import regression_db
from framework.regression_evidence import case_evidence
from framework.website_regression import goto
from pages.search_results_page import SearchResultsPage
from runtime_environments import get_sos_api_base_url


def leg_rows(db, condition, params=()):
    return db.select(f'''SELECT e.id, e.aircraft_id, e.start_time, e.end_time,
        e.dep_city_id, e.arr_city_id, e.dep_airport_id, e.arr_airport_id,
        e.status, e.delete_tag, e.price, e.currency,
        c.zone_id, c.en_name AS dep_city_name, c.country_id AS dep_country_id,
        r.en_name AS arr_city_name, a.icao_code AS dep_icao, b.icao_code AS arr_icao,
        f.status AS aircraft_status, f.delete_tag AS aircraft_deleted,
        COALESCE(e.dep_city_id,a.city_id) AS search_dep_city_id,
        COALESCE(e.arr_city_id,b.city_id) AS search_arr_city_id
        FROM {db.table('dc_empty_leg')} e
        LEFT JOIN {db.table('dc_city')} c ON c.id=e.dep_city_id
        LEFT JOIN {db.table('dc_city')} r ON r.id=e.arr_city_id
        LEFT JOIN {db.table('dc_airport')} a ON a.id=e.dep_airport_id
        LEFT JOIN {db.table('dc_airport')} b ON b.id=e.arr_airport_id
        LEFT JOIN {db.table('dc_aircraft')} f ON f.id=e.aircraft_id
        WHERE {condition} ORDER BY e.start_time,e.id LIMIT 1''', params)


@pytest.fixture(scope='module')
def valid_leg(regression_db):
    minimum = int((datetime.now(timezone.utc)+timedelta(days=5)).timestamp()*1000)
    rows = leg_rows(regression_db, '''e.status=1 AND e.delete_tag=0 AND e.price>0
        AND e.start_time>=%s AND e.end_time>=e.start_time
        AND e.dep_city_id IS NOT NULL AND e.arr_city_id IS NOT NULL
        AND e.dep_city_id<>e.arr_city_id AND e.dep_airport_id IS NOT NULL
        AND e.arr_airport_id IS NOT NULL AND f.status=1 AND f.delete_tag=0
        AND c.zone_id IS NOT NULL''', (minimum,))
    if not rows:
        pytest.skip('DB_FIXTURE_MISSING: need a saleable Empty Leg at least five days in the future; no shared records were modified')
    return rows[0]


def local_date(leg, field='start_time'):
    return datetime.fromtimestamp(leg[field]/1000, timezone.utc).astimezone(ZoneInfo(leg['zone_id'])).date()


def payload(leg, *, trip_type=1, departure=None, origin_airport=None, origin_city=None):
    departure = departure or local_date(leg)
    first = {'depCity':str(origin_city or leg['search_dep_city_id']),
             'arrCity':str(leg['search_arr_city_id']),
             'depAirport':str(origin_airport) if origin_airport else '',
             'arrAirport':'', 'depTime':departure.isoformat(), 'returnTime':'', 'pax':2}
    if trip_type==3:
        first['returnTime']=(departure+timedelta(days=1)).isoformat()
    trips=[first]
    if trip_type==2:
        trips.append({**first,'depCity':first['arrCity'],'arrCity':first['depCity'],
                      'depAirport':'','depTime':(departure+timedelta(days=1)).isoformat()})
    return {'tripType':trip_type,'trips':trips,'currencyType':'USD','charterType':'', 'queryType':4}


def query(page, params, evidence):
    response=page.request.post(get_sos_api_base_url()+'/web/search/searchList', data=params, timeout=90000)
    assert response.ok, 'Real search HTTP failure'
    body=response.json()
    assert body.get('code')==1000 and body.get('success') is True, 'Real search business failure'
    assert isinstance(body.get('data',{}).get('result'),list), 'Search must return a result array'
    rows=body['data']['result']
    evidence.json_evidence(evidence.step_id, {'verification_layer':'real search + independent read-only DB fixture',
        'tripType':params['tripType'],'trips':params['trips'],
        'result_ids':[str(r.get('id')) for r in rows],
        'empty_leg_ids':[str(r.get('emptyLegId')) for r in rows if r.get('emptyLeg')==1]})
    return rows


def assert_leg_present(rows, leg):
    found=[r for r in rows if r.get('emptyLeg')==1 and str(r.get('emptyLegId'))==str(leg['id'])]
    assert len(found)==1, 'Expected one independently seeded Empty Leg in actual search'
    assert str(found[0]['id'])==str(leg['aircraft_id'])
    assert found[0].get('emptyLegInfo') and found[0].get('aircraftModelName')
    return found[0]


def open_search_ui(page, params, leg):
    # Resolve the DB-selected identities through the public city directory.
    # Do not invent country codes or reverse IDs while retaining old labels.
    cities={}
    for city_id,name in ((str(leg['search_dep_city_id']),leg['dep_city_name']),
                         (str(leg['search_arr_city_id']),leg['arr_city_name'])):
        response=page.request.get(get_sos_api_base_url()+'/data/cityQuery',params={'q':name},timeout=60000)
        assert response.ok
        body=response.json()
        assert body.get('code')==1000
        matches=[c for c in body.get('data',[]) if str(c.get('id'))==city_id]
        assert len(matches)==1, 'DB-selected city must resolve to one public directory entry'
        assert matches[0].get('countryCode') and matches[0].get('cityName')
        cities[city_id]=matches[0]
    search_id='qa-'+uuid4().hex
    legs=[{'id':str(i),'fromSelect':cities[trip['depCity']], 'toSelect':cities[trip['arrCity']],
           'depDate':trip['depTime'],'returnDate':trip['returnTime'] or None,**trip}
          for i,trip in enumerate(params['trips'])]
    cache={'searchId':search_id,'params':{'tripType':{1:'single',2:'muti',3:'round'}[params['tripType']],
           'trip':params['trips'],'legs':legs,'currencyType':'USD','charterType':''}}
    goto(page,'/en-us')
    page.evaluate('(value)=>localStorage.setItem("latest_search_params",JSON.stringify(value))',cache)
    goto(page,'/en-us/search?id='+search_id)
    results=SearchResultsPage(page);results.wait_for_page()
    assert results.has_results()
    expect(page.get_by_text('Empty Leg',exact=True).filter(visible=True).first).to_be_visible()
    return results


@pytest.mark.parametrize('case_id,trip_type', [pytest.param('TC-135',kind,id=f'TC-135-type-{kind}') for kind in (1,3,2)])
def test_normal_search_merges_empty_legs(case_evidence, regression_db, valid_leg, page, case_id, trip_type):
    params=payload(valid_leg,trip_type=trip_type)
    rows=query(page,params,case_evidence)
    assert_leg_present(rows,valid_leg)
    assert any(r.get('emptyLeg')!=1 for r in rows), 'Mixed search must retain ordinary capacity'
    open_search_ui(page,params,valid_leg)


@pytest.mark.parametrize('case_id,origin', [pytest.param('TC-136',v,id='TC-136-'+v) for v in ('airport','city','same-city-airport','other-city')])
def test_empty_leg_origin_matching(case_evidence, regression_db, valid_leg, page, case_id, origin):
    airport=None;city=valid_leg['search_dep_city_id'];expected=True
    if origin=='airport':airport=valid_leg['dep_airport_id']
    elif origin=='same-city-airport':
        alternatives=regression_db.select(f'SELECT id FROM {regression_db.table("dc_airport")} WHERE city_id=%s AND id<>%s AND delete_tag=0 ORDER BY id LIMIT 1', (city,valid_leg['dep_airport_id']))
        if not alternatives:pytest.skip('DB_FIXTURE_MISSING: no second airport in the fixture departure city')
        airport=alternatives[0]['id']
    elif origin=='other-city':city=valid_leg['search_arr_city_id'];expected=False
    rows=query(page,payload(valid_leg,origin_airport=airport,origin_city=city),case_evidence)
    if expected:assert_leg_present(rows,valid_leg)
    else:assert str(valid_leg['id']) not in {str(r.get('emptyLegId')) for r in rows}


@pytest.mark.parametrize('case_id,edge,offset,expected', [
    pytest.param('TC-137','start',-4,False,id='TC-137-minus4'),pytest.param('TC-137','start',-3,True,id='TC-137-minus3'),
    pytest.param('TC-137','start',0,True,id='TC-137-zero'),pytest.param('TC-137','end',3,True,id='TC-137-plus3'),
    pytest.param('TC-137','end',4,False,id='TC-137-plus4')])
def test_empty_leg_date_window(case_evidence, regression_db, valid_leg, page, case_id, edge, offset, expected):
    day=local_date(valid_leg,'start_time' if edge=='start' else 'end_time')+timedelta(days=offset)
    rows=query(page,payload(valid_leg,departure=day),case_evidence)
    if expected:assert_leg_present(rows,valid_leg)
    else:assert str(valid_leg['id']) not in {str(r.get('emptyLegId')) for r in rows}


@pytest.mark.parametrize('case_id,kind', [pytest.param('TC-138',v,id='TC-138-'+v) for v in ('expired','disabled','unavailable','missing-field')])
def test_invalid_empty_legs_excluded(case_evidence, regression_db, valid_leg, page, case_id, kind):
    now=int(datetime.now(timezone.utc).timestamp()*1000)
    clauses={'expired':('e.end_time BETWEEN %s AND %s',(now-2*86400000,now)), 'disabled':('e.status=0 AND e.end_time>%s',(now,)),
             'unavailable':('(f.status=0 OR f.delete_tag=1) AND e.end_time>%s',(now,)),
             'missing-field':('(e.aircraft_id IS NULL OR e.start_time IS NULL OR e.end_time IS NULL OR e.price IS NULL)',())}
    condition,args=clauses[kind]
    rows=leg_rows(regression_db,'('+condition+') AND COALESCE(e.dep_city_id,a.city_id) IS NOT NULL AND COALESCE(e.arr_city_id,b.city_id) IS NOT NULL',args)
    if not rows:pytest.skip('DB_FIXTURE_MISSING: no '+kind+' Empty Leg; no records were modified')
    invalid=rows[0]
    seed={**valid_leg,**invalid}
    seed['zone_id']=invalid['zone_id'] or valid_leg['zone_id']
    today=datetime.now(ZoneInfo(seed['zone_id'])).date()
    day=today if kind=='expired' else max(today, local_date(seed) if seed.get('start_time') else local_date(valid_leg))
    result=query(page,payload(seed,departure=day),case_evidence)
    assert str(invalid['id']) not in {str(r.get('emptyLegId')) for r in result}, 'Invalid Empty Leg leaked into search'


@pytest.mark.parametrize('case_id', ['TC-139'], ids=['TC-139'])
def test_mixed_search_deduplicates_and_orders(case_evidence, regression_db, valid_leg, page, case_id):
    params=payload(valid_leg)
    first=query(page,params,case_evidence);second=query(page,params,case_evidence)
    assert_leg_present(first,valid_leg)
    ids=[str(r['id']) for r in first]
    assert len(ids)==len(set(ids)), 'Repeated aircraft cards in mixed results'
    assert ids==[str(r['id']) for r in second], 'Identical requests must preserve ordering'
    prices=[float(r['usdPrice']) for r in first if r.get('usdPrice') and float(r['usdPrice'])>0]
    assert prices==sorted(prices), 'Cheapest query must sort valid prices ascending'
    assert 0<len(first)<=30, 'Normal-search result limit is thirty'
    results=open_search_ui(page,params,valid_leg)
    assert results.get_result_count()==len(first), 'Rendered card count must match the real API results'
    results.select_aircraft(requested_count=1)
    assert results.get_selected_aircraft_count()==1
    results.open_quote_dialog();results.wait_for_quote_dialog()
    case_evidence.json_evidence(case_evidence.step_id,{'card_count':results.get_result_count(),
        'api_count':len(first),'selected_count':1,'quote_dialog_open':True,
        'scope_gap':'A guaranteed duplicate-source DB fixture and pagination/detail baseline remain unverified; this is partial TC-139 coverage'})
