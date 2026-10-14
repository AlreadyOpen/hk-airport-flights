---
pretty_name: Hong Kong International Airport flights (every 15 minutes)
license: other
license_name: data-gov-hk-terms-of-use
license_link: https://data.gov.hk/en/terms-and-conditions
tags:
  - aviation
  - flights
  - hong-kong
  - airport
---

# Hong Kong International Airport flights

The flight information of Hong Kong International Airport (passenger and cargo, arrivals and departures), fetched every 15
minutes by [AlreadyOpen/hk-airport-flights](https://github.com/AlreadyOpen/hk-airport-flights), with every snapshot kept: how
each flight's status, time, gate, stand and belt changed through the day. Every source field is kept.

The airport's API keeps only about 90 days and refuses requests from a browser origin, so this is also the copy a map can read.

## Files

On the [bucket](https://huggingface.co/buckets/alreadyopen/hk-airport-flights) (CORS open):

| File | Holds |
|---|---|
| `live/flights.json` | The latest snapshot: `{fetched_at, days, source, licence, flights: [...]}`, yesterday, today and tomorrow (Hong Kong days). Null fields are left out. |
| `live/changes-YYYY-MM-DD.parquet` | Every snapshot fetched during that Hong Kong day: one row per flight per snapshot. The last 7 days stay here. |

On Kaggle: each complete day as its own dataset, `helenkwok/hk-airport-flights-YYYY-MM-DD` (the file `live/changes-YYYY-MM-DD.parquet`),
created once and never changed.

## Columns (both files)

| Column | Meaning |
|---|---|
| `date` | The flight's day (Hong Kong) |
| `requested` | The day the API was asked for; it also returns the previous day's late flights, so `date` can differ |
| `arrival`, `cargo` | Arrival or departure; cargo or passenger |
| `fetched_at` | When this snapshot was fetched (Hong Kong time) |
| `time` | Scheduled time, `HH:MM` |
| `flight` | Every flight number: `[{no: 'CX 105', airline: 'CPA'}, ...]`, the operating flight first, then its codeshares |
| `callsigns` | The operating flight as an ICAO callsign in both forms aircraft broadcast (`CPA089` and `CPA89`): joins the `flight` (callsign) of [AlreadyOpen/world-flights](https://huggingface.co/datasets/alreadyopen/world-flights) live aircraft |
| `status` | The status as published, for example `Dep 00:24`, `At gate 08:05 (12/10/2026)`, `Est at 09:15`, `Cancelled` |
| `status_kind`, `status_at` | The status parsed: its words, and its time with the date it gives (else the flight's `date`) |
| `statusCode` | As published (empty so far) |
| `origin` / `destination` | IATA airport codes (arrivals have `origin`, departures `destination`) |
| `terminal`, `aisle`, `gate`, `baggage`, `hall`, `stand` | As published |
| `extra` | Any field the API adds later, as JSON (none so far) |

To see what changed, compare a flight's rows across `fetched_at`; a flight is identified by `requested`, `arrival`, `cargo`,
`date`, `time` and its first `flight` number.

## Source and licence

Flight information: Airport Authority Hong Kong, through [DATA.GOV.HK](https://data.gov.hk/en-data/dataset/aahk-team1-flight-info),
under the [DATA.GOV.HK terms of use](https://data.gov.hk/en/terms-and-conditions). These files are not adsb.lol data and are
not under the ODbL; they are kept apart from AlreadyOpen/world-flights for that reason and join it only by callsign.

Gaps: GitHub may start a scheduled run late or skip one, and a run the API fails is skipped, so some 15-minute snapshots are
missing.
