"""Process raw layers into dashboard-ready summaries for the Bike(+) Plan midpoint.

Definitions (confirmed with Eric, BikePGH, 2026-10-30 where noted):
- Progress target: the plan's 123 miles of NEW ON-STREET facilities (Bike(+) Plan p. 5).
  BikePGH focuses on the on-street network, so trails / shared use paths are shown for
  context but excluded from progress. [confirmed]
- "Future Bike Corridor (Route TBD)" lines in the proposed layer mark a corridor of need,
  not a chosen street, so they are reported separately and not counted as street miles.
  [per Eric]
- Everything is clipped to the City limits, so facilities and proposals in other
  municipalities do not count toward the City's progress. [per Eric]
- Lengths are centerline miles (a two-sided lane on one street counts once), measured in
  EPSG:2272 (PA South, US feet).
- "Before 2020": existing facilities with yearbuilt < 2020, plus facilities with a missing
  or 0 build year. Those are almost all riverfront / park trails (e.g. Three Rivers
  Heritage Trail) that predate the plan; they are flagged so the assumption is visible.
- "Since 2020": existing facilities with yearbuilt >= 2020 (plan adopted June 2020).
- "Still to build": DOMI's Proposed Facilities layer (only ~3% of it overlaps facilities
  built since 2020, so it reads as the remaining network).
- On the High Injury Network (HIN): length within BUFFER_FT of a HIN centerline.
- Bike(+) Plan projects (project_list) get a status from how much of their length sits
  within BUFFER_FT of existing facilities.
"""
import json
import re
from pathlib import Path

import geopandas as gpd
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW, OUT = ROOT / "data" / "raw", ROOT / "data" / "processed"
OUT.mkdir(parents=True, exist_ok=True)

CRS_FT = 2272
FT_PER_MI = 5280
BUFFER_FT = 60
PLAN_YEAR = 2020
TARGET_ON_STREET_MI = 123  # Bike(+) Plan p. 5: new on-street facilities
TARGET_TRAIL_MI = 27       # Bike(+) Plan p. 5: new trails (context only)
OFF_STREET_EXISTING = {"Shared Use Path"}
OFF_STREET_PROPOSED = {"Proposed Shared Use Path", "Proposed Trail"}
TBD_PROPOSED = {"Future Bike Corridor (Route TBD)"}
TYPE_ORDER = [
    "Protected Bike Lane", "Buffered Bike Lane", "Bike Lane", "Bike Lane / Sharrow",
    "Neighborway", "Sharrow", "Shared Use Path",
]


def load(name, city=None):
    g = gpd.read_file(RAW / f"{name}.geojson").to_crs(CRS_FT)
    g["mi_full"] = g.length / FT_PER_MI
    if city is not None:
        g = gpd.clip(g, city, keep_geom_type=True)
        g = g[~g.geometry.is_empty].copy()
    g["mi"] = g.length / FT_PER_MI
    return g


def miles_within(lines, other):
    """Miles of each line that fall within BUFFER_FT of any geometry in `other`."""
    zone = other.buffer(BUFFER_FT).unary_union
    return lines.geometry.intersection(zone).length / FT_PER_MI


def names_near(g, other, col, buf, min_mi, top):
    """For each line in g, the values of other[col] with the most length near that line."""
    idx, out = other.sindex, []
    for geom in g.geometry:
        zone = geom.buffer(buf)
        near = other.iloc[idx.query(zone, predicate="intersects")]
        miles = (near.intersection(zone).length / FT_PER_MI).groupby(near[col]).sum()
        miles = miles[miles >= min_mi].sort_values(ascending=False)
        out.append(list(miles.index[:top]))
    return out


def tidy_street(name):
    """'40TH ST BRG' -> '40th St Brg'."""
    return re.sub(r"(\d)(St|Nd|Rd|Th)\b", lambda m: m.group(1) + m.group(2).lower(), name.title())


def is_local_street(name):
    return not re.search(r"\bI-\d|RAMP|\bHOV\b|\bPA RT\b|\bUS RT\b", name)


def main():
    districts = gpd.read_file(RAW / "city_districts.geojson").to_crs(CRS_FT)
    city = gpd.GeoDataFrame(geometry=[districts.union_all().buffer(0)], crs=CRS_FT)
    ex, pr, pl, hin = (load(n, city) for n in
                       ["bike_existing", "bike_proposed", "bike_project_list", "high_injury_network"])
    outside = {
        "existing": float(gpd.read_file(RAW / "bike_existing.geojson").to_crs(CRS_FT).length.sum() / FT_PER_MI - ex.mi.sum()),
        "proposed": float(gpd.read_file(RAW / "bike_proposed.geojson").to_crs(CRS_FT).length.sum() / FT_PER_MI - pr.mi.sum()),
    }

    ex, pr = ex.reset_index(drop=True), pr.reset_index(drop=True)
    ex["rid"] = "E" + ex.index.astype(str)
    pr["rid"] = "P" + pr.index.astype(str)

    yb = ex["yearbuilt"].fillna(0).astype(int)
    ex["year_missing"] = yb <= 0
    ex["period"] = (yb >= PLAN_YEAR).map({True: "Since 2020", False: "Before 2020"})
    ex["fac_type"] = ex["fac_type"].fillna("Unknown")

    ex["on_street"] = ~ex.fac_type.isin(OFF_STREET_EXISTING)
    since = ex[ex.period == "Since 2020"]
    before = ex[ex.period == "Before 2020"]
    since_os = since[since.on_street]

    # Remaining network vs HIN
    pr["hin_mi"] = miles_within(pr, hin)
    pr["kind"] = "On-street"
    pr.loc[pr["type"].isin(OFF_STREET_PROPOSED), "kind"] = "Trail / path"
    pr.loc[pr["type"].isin(TBD_PROPOSED), "kind"] = "Corridor, route TBD"
    pr_os = pr[pr.kind == "On-street"]

    # Plan project status
    pl["mi_built_since"] = miles_within(pl, since)
    pl["mi_existing_before"] = miles_within(pl, before)
    pl["hin_mi"] = miles_within(pl, hin)
    share_since = pl.mi_built_since / pl.mi
    share_before = pl.mi_existing_before / pl.mi
    pl["status"] = "Not built yet"
    pl.loc[share_before >= 0.5, "status"] = "On an existing pre-2020 facility"
    pl.loc[share_since >= 0.5, "status"] = "Built since 2020"
    pl.loc[(share_since > 0.1) & (share_since < 0.5), "status"] = "Partly built"

    summary = {
        "outside_city_removed_mi": outside,
        "target_on_street_mi": TARGET_ON_STREET_MI,
        "target_trail_mi": TARGET_TRAIL_MI,
        "on_street_existing_mi": ex[ex.on_street].mi.sum(),
        "on_street_since_2020_mi": since_os.mi.sum(),
        "trail_since_2020_mi": since[~since.on_street].mi.sum(),
        "on_street_proposed_mi": pr_os.mi.sum(),
        "on_street_proposed_on_hin_mi": pr_os.hin_mi.sum(),
        "tbd_corridor_mi": pr[pr.kind == "Corridor, route TBD"].mi.sum(),
        "tbd_corridor_n": int((pr.kind == "Corridor, route TBD").sum()),
        "trail_proposed_mi": pr[pr.kind == "Trail / path"].mi.sum(),
        "on_street_by_year": [
            {"year": int(y), "mi": float(since_os.loc[since_os.yearbuilt.astype(int) == y, "mi"].sum())}
            for y in range(PLAN_YEAR, 2027)
        ],
        "existing_total_mi": ex.mi.sum(),
        "before_2020_mi": before.mi.sum(),
        "before_2020_missing_year_mi": ex[ex.year_missing].mi.sum(),
        "since_2020_mi": since.mi.sum(),
        "proposed_total_mi": pr.mi.sum(),
        "proposed_on_hin_mi": pr.hin_mi.sum(),
        "hin_total_mi": hin.mi.sum(),
        "since_2020_on_plan_list_mi": miles_within(since, pl).sum(),
        "by_type": [
            {"type": t,
             "before": float(before.loc[before.fac_type == t, "mi"].sum()),
             "since": float(since.loc[since.fac_type == t, "mi"].sum())}
            for t in TYPE_ORDER + sorted(set(ex.fac_type) - set(TYPE_ORDER))
            if (ex.fac_type == t).any()
        ],
        "by_year": [
            {"year": int(y), "mi": float(since.loc[since.yearbuilt.astype(int) == y, "mi"].sum())}
            for y in range(PLAN_YEAR, 2027)
        ],
        "proposed_by_type": pr.groupby("type").mi.sum().round(2).to_dict(),
        "plan_projects": {
            "n": int(len(pl)),
            "mi": float(pl.mi.sum()),
            "by_status": pl.groupby("status").mi.agg(["count", "sum"]).round(2)
                           .rename(columns={"sum": "mi"}).to_dict("index"),
        },
        "data_dates": json.loads((RAW / "fetch_log.json").read_text()),
        "buffer_ft": BUFFER_FT,
    }
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2, default=float))

    # Unbuilt plan projects ranked by HIN overlap (advocacy list)
    todo = pl[pl.status == "Not built yet"].copy()
    todo["neighborhoods"] = todo["neighborho"].fillna("")
    cols = ["proj_name", "xst_from", "xst_to", "neighborhoods", "councdist", "mi", "hin_mi"]
    todo = todo.sort_values(["hin_mi", "mi"], ascending=False)[cols]
    todo.round({"mi": 2, "hin_mi": 2}).to_csv(OUT / "unbuilt_plan_projects_by_hin.csv", index=False)
    pl.drop(columns="geometry").round(3).to_csv(OUT / "plan_projects_status.csv", index=False)

    # Record-level comparison tables
    hoods = load("neighborhoods", city)[["hood", "geometry"]].dissolve("hood").reset_index()
    blocks = gpd.read_file(RAW / "street_blocks.geojson").to_crs(CRS_FT)
    blocks = blocks[blocks.geometry.notna() & blocks.Streetname.notna()]
    ex_os = ex[ex.on_street]

    ex["hin_mi"] = miles_within(ex, hin)
    pr["along_existing_mi"] = miles_within(pr, ex_os)
    summary["on_street_proposed_along_existing_mi"] = float(pr.loc[pr.kind == "On-street", "along_existing_mi"].sum())
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2, default=float))

    def hood_names(g):
        return [", ".join(n) for n in names_near(g, hoods, "hood", 1, 0.01, 4)]

    ex["hoods"] = hood_names(ex)
    pr["hoods"] = hood_names(pr)
    named = pr.kind != "Corridor, route TBD"
    projects = [(n[0] if n else "") for n in names_near(pr, pl, "proj_name", BUFFER_FT, 0.05, 1)]
    streets = names_near(pr, blocks, "Streetname", 25, 0.03, 5)
    local = [[tidy_street(s) for s in n if is_local_street(s)][:3] or [tidy_street(s) for s in n][:3] for n in streets]
    pr["project"] = [p if keep else "" for p, keep in zip(projects, named)]
    pr["streets"] = [", ".join(n) if keep else "" for n, keep in zip(local, named)]

    side = ex["road_side"].fillna("").str.strip().str.lower()
    hin_zone = hin.buffer(BUFFER_FT).unary_union
    pr_on = pr[pr.kind == "On-street"]
    hood_rows = []
    for _, h in hoods.iterrows():
        row = {
            "hood": h.hood,
            "existing": ex_os.intersection(h.geometry).length.sum() / FT_PER_MI,
            "since": since_os.intersection(h.geometry).length.sum() / FT_PER_MI,
            "proposed": pr_on.intersection(h.geometry).length.sum() / FT_PER_MI,
            "proposed_hin": pr_on.intersection(h.geometry.intersection(hin_zone)).length.sum() / FT_PER_MI,
            "bounds": list(gpd.GeoSeries([h.geometry], crs=CRS_FT).to_crs(4326).total_bounds),
        }
        hood_rows.append(row)
    in_hoods = {k: sum(r[k] for r in hood_rows) for k in ["existing", "since", "proposed", "proposed_hin"]}
    totals = {"existing": ex_os.mi.sum(), "since": since_os.mi.sum(), "proposed": pr_on.mi.sum(),
              "proposed_hin": float(pr_on.hin_mi.sum())}
    hood_rows.append({"hood": "On bridges and rivers (no neighborhood)", "bounds": None,
                      **{k: max(totals[k] - in_hoods[k], 0) for k in totals}})

    records = {
        "existing": pd.DataFrame({
            "rid": ex.rid, "street": ex.street.fillna(""), "type": ex.fac_type,
            "year": yb.where(yb > 0, 0), "side": side, "hoods": ex.hoods,
            "mi": ex.mi.round(3), "hin_mi": ex.hin_mi.round(3), "on_street": ex.on_street,
        }).to_dict("records"),
        "proposed": pd.DataFrame({
            "rid": pr.rid, "project": pr["project"], "streets": pr.streets, "type": pr["type"], "kind": pr.kind,
            "hoods": pr.hoods, "mi": pr.mi.round(3), "hin_mi": pr.hin_mi.round(3),
            "along_existing_mi": pr.along_existing_mi.round(3),
        }).to_dict("records"),
        "neighborhoods": hood_rows,
    }
    (OUT / "records.json").write_text(json.dumps(records, default=float))

    # Map layers (WGS84, lightly simplified)
    def export(g, name, keep):
        g = g[keep + ["geometry"]].copy()
        g["geometry"] = g.geometry.simplify(8)
        g.to_crs(4326).to_file(OUT / f"{name}.geojson", driver="GeoJSON")

    ex["mi"] = ex.mi.round(3)
    export(ex, "map_existing", ["rid", "street", "fac_type", "yearbuilt", "period", "mi"])
    pr["mi"], pr["hin_mi"] = pr.mi.round(3), pr.hin_mi.round(3)
    export(pr, "map_proposed", ["rid", "type", "kind", "mi", "hin_mi"])
    export(hin, "map_hin", ["streetname", "Count_AllCrash", "Count_BicycleCrash", "Count_PedestrianCrash"])
    city.to_crs(4326)[["geometry"]].to_file(OUT / "map_city.geojson", driver="GeoJSON")

    print(json.dumps({k: (round(v, 1) if isinstance(v, float) else v)
                      for k, v in summary.items() if k not in ("data_dates",)}, indent=1, default=float))


if __name__ == "__main__":
    main()
