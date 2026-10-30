# Pittsburgh Bike(+) Plan midpoint dashboard

Volunteer data project for BikePGH: how much of the 2020 Bike(+) Plan's goal of
**123 new miles of on-street bike facilities** has been built, what is still proposed,
and where the remaining projects overlap the City's High Injury Network.

The dashboard is rebuilt automatically every Monday from the City's public data
(GitHub Actions -> GitHub Pages). It can also be refreshed any time from the
**Actions** tab -> *Refresh dashboard* -> *Run workflow*.

## Layout
```
scripts/01_fetch_data.py       download City data (ArcGIS feature services)
scripts/02_process.py          compute miles, HIN overlap, plan project status
scripts/03_build_dashboard.py  fill scripts/dashboard_template.html -> outputs/
.github/workflows/refresh.yml  weekly refresh + deploy
```
`data/` and `outputs/` are generated and not committed.

## Run locally
```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python scripts/01_fetch_data.py
.venv/bin/python scripts/02_process.py
.venv/bin/python scripts/03_build_dashboard.py   # -> outputs/bike_plan_dashboard.html
```

## Data sources (all public)
- City of Pittsburgh DOMI, *Pittsburgh Bicycle Facilities*: Existing Facilities,
  Proposed Facilities, Bike(+) Plan project list
- City of Pittsburgh DOMI, *High Injury Network 2020–2024*
- City of Pittsburgh, *Bike(+) Plan* (June 2020), for the 123-mile on-street goal (p. 5)

## Definitions
- Centerline miles: a street with bike lanes on both sides counts once.
- Progress counts on-street facilities only; trails and shared use paths are reported
  separately (27-mile trail goal).
- "Future Bike Corridor (Route TBD)" lines mark a corridor of need, not a chosen street,
  so they are shown separately and not counted.
- Facilities with no build year (mostly older riverfront and park trails) are counted as
  built before 2020.
- "On the HIN" = within 60 ft of a High Injury Network street.

## Open questions
- Proposed on-street (~106 mi) + built since 2020 (~32 mi) = ~138 mi, more than the 123-mile
  goal. Expected (e.g. upgrades of existing facilities), or should the proposed layer be filtered?
- The plan's 2019 baseline is 93 mi (57 on-street + 36 trails); DOMI data shows ~81 mi built
  before 2020.
