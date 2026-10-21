# hk-airport-flights

An [Milleleaf](https://github.com/milleleaf) pipeline: Hong Kong International Airport's flight information (Airport
Authority Hong Kong, [DATA.GOV.HK](https://data.gov.hk/en-data/dataset/aahk-team1-flight-info), DATA.GOV.HK terms of use) every
15 minutes, every snapshot kept, published to a Hugging Face [bucket](https://huggingface.co/buckets/milleleaf/hk-airport-flights)
(`live/`, the last 7 days) and archived on Kaggle, one dataset per Hong Kong day. Its `callsigns` column joins the live aircraft of
[milleleaf/world-flights](https://github.com/milleleaf/world-flights); the two are separate datasets because their licences
differ (ODbL there). Files and columns: `hf/README.md`.

    python3 live.py             # one snapshot: live/flights.json and today's live/changes-<D>.parquet (HF_TOKEN); every 15 min in live.yml
    python3 kaggle_archive.py   # complete days to Kaggle, days older than 7 off the bucket, card refresh (HF_TOKEN, KAGGLE_API_TOKEN); daily in archive.yml
    python3 check.py            # data-free checks (CI)

| File | Does |
|---|---|
| `live.py`, `live.yml` | 12 GETs (yesterday, today, tomorrow x passenger/cargo x arrivals/departures), no browser Origin (the API refuses one with 403) |
| `kaggle_archive.py`, `archive.yml` | Daily at 00:40 HKT; commits `status/last-run.json` so GitHub keeps the schedules on |
| `kaggle_mirror.py`, `manifest.py`, `check.py` | Shared pipeline-template files |

The [heartbeat](https://github.com/milleleaf/heartbeat) can start live.yml on time once its GitHub App has this repo; the
GitHub schedule here is the backup (it starts runs late or drops them under load).

Code: Apache-2.0. Data: Airport Authority Hong Kong, DATA.GOV.HK terms of use, see `sources.json`.
