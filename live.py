"""Hong Kong International Airport flight information (Airport Authority Hong Kong, DATA.GOV.HK terms of use), every 15 minutes.
Each run asks the airport's API for yesterday, today and tomorrow (Hong Kong days), passenger and cargo, arrivals and
departures: 12 GETs. The API refuses requests that carry a browser Origin (403), so browsers read this copy instead.
Bucket:
  live/flights.json                 the latest snapshot: {fetched_at, days, source, licence, flights: [row, ...]} (null fields
                                    left out)
  live/changes-YYYY-MM-DD.parquet   every snapshot fetched during that Hong Kong day, appended each run: one row per flight per
                                    snapshot (all snapshots, not only the changed rows, so nothing needs reconstructing)
A row: every source field (time, flight, status, statusCode, origin or destination, terminal, aisle, gate, baggage, hall,
stand; any field the API adds later goes in `extra`), plus date (the flight's day), requested (the day asked for: the API also
returns the previous day's late flights), arrival, cargo, fetched_at, callsigns (the operating, first, flight as an ICAO
callsign in both forms adsb.lol uses: CPA089 and CPA89, to join AlreadyOpen/world-flights' `flight`) and the status parsed:
status_kind ('Dep', 'At gate', 'Est at', 'Landed', 'Cancelled', 'Boarding', ...) and status_at (its time, with the date the
status gives, else the flight's date). kaggle_archive.py archives each complete day and keeps HF_DAYS on the bucket.
On any error the run is skipped (a warning, exit 0): no retry loop. Needs HF_TOKEN.
Usage: python3 live.py   (python3 live.py test: parser self-test, no network)"""
import datetime, json, os, re, sys, tempfile, urllib.request

API = 'https://www.hongkongairport.com/flightinfo-rest/rest/flights/past?date={date}&lang=en&cargo={cargo}&arrival={arrival}'
UA = {'User-Agent': 'AlreadyOpen hk-airport-flights (https://github.com/milleleaf/hk-airport-flights)'}
REPO = 'milleleaf/hk-airport-flights'
HKT = datetime.timezone(datetime.timedelta(hours=8))
SOURCE = 'https://data.gov.hk/en-data/dataset/aahk-team1-flight-info'
LICENCE = 'DATA.GOV.HK terms of use (https://data.gov.hk/en/terms-and-conditions), Airport Authority Hong Kong'
KNOWN = ['time', 'flight', 'status', 'statusCode', 'origin', 'destination', 'terminal', 'aisle', 'gate', 'baggage', 'hall', 'stand']
STATUS = re.compile(r'^(?P<kind>.*?)\s*(?P<hm>\d{1,2}:\d{2})?\s*(?:\((?P<d>\d{2})/(?P<m>\d{2})/(?P<y>\d{4})\))?$')
COLS = """date DATE, requested DATE, arrival BOOLEAN, cargo BOOLEAN, fetched_at TIMESTAMPTZ, callsigns VARCHAR[], "time" VARCHAR,
  flight STRUCT("no" VARCHAR, airline VARCHAR)[], status VARCHAR, status_kind VARCHAR, status_at TIMESTAMPTZ, statusCode VARCHAR,
  origin VARCHAR[], destination VARCHAR[], terminal VARCHAR, aisle VARCHAR, gate VARCHAR, baggage VARCHAR, hall VARCHAR,
  stand VARCHAR, extra JSON"""


def callsigns(f):
    """{'no': 'CX 089', 'airline': 'CPA'} -> ['CPA089', 'CPA89']"""
    n = f['no'].split(' ', 1)[-1]
    return list(dict.fromkeys([f['airline'] + n, f['airline'] + (n.lstrip('0') or n)]))


def status(text, day):
    """'Dep 23:57 (12/10/2026)' -> ('Dep', '2026-10-12T23:57:00+08:00'); 'Cancelled' -> ('Cancelled', None)"""
    m = STATUS.match(text.strip())
    if not m or not m['hm']:
        return text.strip() or None, None
    d = f"{m['y']}-{m['m']}-{m['d']}" if m['y'] else day
    return m['kind'] or None, f"{d}T{int(m['hm'].split(':')[0]):02d}:{m['hm'].split(':')[1]}:00+08:00"


def row(x, day, requested, arrival, cargo, fetched_at):
    kind, at = status(x.get('status') or '', day)
    extra = {k: v for k, v in x.items() if k not in KNOWN}
    return {'date': day, 'requested': requested, 'arrival': arrival, 'cargo': cargo, 'fetched_at': fetched_at,
            'callsigns': callsigns(x['flight'][0]) if x.get('flight') else [], 'status_kind': kind, 'status_at': at,
            **{k: x.get(k) for k in KNOWN}, 'statusCode': None if x.get('statusCode') is None else str(x['statusCode']),
            'extra': json.dumps(extra, ensure_ascii=False) if extra else None}


def fetch(now):
    fetched_at = now.isoformat(timespec='seconds')
    days = [str((now + datetime.timedelta(days=k)).date()) for k in (-1, 0, 1)]
    rows = []
    for requested in days:
        for arrival in (False, True):
            for cargo in (False, True):
                url = API.format(date=requested, cargo=str(cargo).lower(), arrival=str(arrival).lower())
                with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
                    for d in json.load(r):
                        rows += [row(x, d['date'], requested, arrival, cargo, fetched_at) for x in d['list']]
    assert rows, 'no flights at all'
    return days, fetched_at, rows


def main():
    import duckdb
    from huggingface_hub import batch_bucket_files, create_bucket, download_bucket_files
    now = datetime.datetime.now(HKT)
    try:
        days, fetched_at, rows = fetch(now)
    except Exception as e:                                             # 4xx/5xx, timeout, bad JSON: wait for the next run
        print(f'::warning::airport API: {e}; skipping this run'); sys.exit(0)
    w = tempfile.mkdtemp()
    latest, nd, old, out = (os.path.join(w, f) for f in ('flights.json', 'snap.ndjson', 'old.parquet', 'new.parquet'))
    json.dump({'fetched_at': fetched_at, 'days': days, 'source': SOURCE, 'licence': LICENCE,      # null fields left out
               'flights': [{k: v for k, v in r.items() if v is not None} for r in rows]}, open(latest, 'w'), ensure_ascii=False, separators=(',', ':'))
    with open(nd, 'w') as f: f.writelines(json.dumps(r, ensure_ascii=False) + '\n' for r in rows)
    remote = f'live/changes-{now.date()}.parquet'                      # the Hong Kong day this snapshot was fetched in
    create_bucket(REPO, private=False, exist_ok=True)
    download_bucket_files(REPO, [(remote, old)], raise_on_missing_files=False)   # absent on the day's first run
    con = duckdb.connect()
    new = f"SELECT * FROM read_json('{nd}', format='newline_delimited', columns={cols()})"
    q = f"SELECT * FROM read_parquet('{old}') UNION ALL BY NAME {new}" if os.path.exists(old) else new
    con.execute(f"COPY ({q} ORDER BY fetched_at, requested, arrival, cargo, date, \"time\") TO '{out}' (FORMAT parquet, COMPRESSION zstd)")
    n, snaps = con.execute(f"SELECT count(*), count(DISTINCT fetched_at) FROM '{out}'").fetchone()
    batch_bucket_files(REPO, add=[(latest, 'live/flights.json'), (out, remote)])
    print(json.dumps({'fetched_at': fetched_at, 'flights': len(rows), 'file': remote, 'rows': n, 'snapshots': snaps}))


def cols():
    """COLS as a DuckDB read_json columns struct: {'date': 'DATE', ...}"""
    parts = re.findall(r'"?(\w+)"? ((?:STRUCT\([^)]*\)|\w+)(?:\[\])?)', COLS)
    return '{' + ', '.join(f"'{k}': '{t}'" for k, t in parts) + '}'


if __name__ == '__main__':
    if sys.argv[1:] == ['test']:
        assert callsigns({'no': 'CX 089', 'airline': 'CPA'}) == ['CPA089', 'CPA89']
        assert callsigns({'no': 'ZE 862', 'airline': 'ESR'}) == ['ESR862'] and callsigns({'no': 'CX 0', 'airline': 'CPA'}) == ['CPA0']
        assert status('Dep 23:57 (12/10/2026)', '2026-10-13') == ('Dep', '2026-10-12T23:57:00+08:00')
        assert status('At gate 8:05', '2026-10-13') == ('At gate', '2026-10-13T08:05:00+08:00')
        assert status('Cancelled', '2026-10-13') == ('Cancelled', None) and status('', '2026-10-13') == (None, None)
        r = row({'time': '00:05', 'flight': [{'no': 'ZE 862', 'airline': 'ESR'}], 'status': 'Final Call', 'new': 1}, '2026-10-13', '2026-10-13', False, False, 'x')
        assert r['callsigns'] == ['ESR862'] and r['status_kind'] == 'Final Call' and r['extra'] == '{"new": 1}' and r['destination'] is None
        assert "'flight': 'STRUCT(\"no\" VARCHAR, airline VARCHAR)[]'" in cols() and cols().count(':') == 21, cols()
        print('live: self-test ok')
    else:
        main()
