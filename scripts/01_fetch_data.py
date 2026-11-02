"""Download raw datasets for the Bike(+) Plan midpoint dashboard.

Sources (all public, City of Pittsburgh ArcGIS Online org):
- DOMI "Pittsburgh Bicycle Facilities" feature service
    layer 9  Existing Facilities
    layer 10 Proposed Facilities
    layer 11 project_list (Bike(+) Plan project list)
- DOMI High Injury Network 2020-2024 (the layer shown on the City's official HIN map,
  https://pittsburghpa.maps.arcgis.com/apps/instant/interactivelegend/index.html?appid=e9a7cec4ad854b6e9afde646b44575e8)
Outputs GeoJSON files to data/raw/ plus a fetch log with layer edit dates.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
RAW.mkdir(parents=True, exist_ok=True)

BASE = "https://services1.arcgis.com/YZCmUqbcsUpOKfj7/arcgis/rest/services"
LAYERS = {
    "bike_existing": f"{BASE}/Pittsburgh_Bicycle_Facilities_WFL1/FeatureServer/9",
    "bike_proposed": f"{BASE}/Pittsburgh_Bicycle_Facilities_WFL1/FeatureServer/10",
    "bike_project_list": f"{BASE}/Pittsburgh_Bicycle_Facilities_WFL1/FeatureServer/11",
    "high_injury_network": f"{BASE}/HIN_20_24/FeatureServer/36",
    # City boundary: union of council districts (58.3 sq mi, rivers included). The City's
    # "City_Limits" layer is a mask of everything outside the city, not a usable boundary.
    "city_districts": f"{BASE}/CouncilDistricts2022/FeatureServer/0",
    # Used only to label records: the proposed layer has no street or neighborhood names.
    "neighborhoods": f"{BASE}/PGHWebNeighborhoods/FeatureServer/0",
    "street_blocks": f"{BASE}/Sidewalks_Blocks/FeatureServer/22",
}
FIELDS = {"neighborhoods": "hood", "street_blocks": "Streetname"}


def layer_info(url):
    return requests.get(url, params={"f": "json"}, timeout=60).json()


def fetch_geojson(url, page=1000, fields="*"):
    """Page through a feature layer and return one GeoJSON FeatureCollection (WGS84)."""
    feats, offset = [], 0
    while True:
        r = requests.get(
            f"{url}/query",
            params={
                "where": "1=1",
                "outFields": fields,
                "outSR": 4326,
                "f": "geojson",
                "resultOffset": offset,
                "resultRecordCount": page,
            },
            timeout=120,
        ).json()
        batch = r.get("features", [])
        feats += batch
        if len(batch) < page:
            break
        offset += page
    return {"type": "FeatureCollection", "features": feats}


def main():
    log = {"fetched_at": datetime.now(timezone.utc).isoformat(), "layers": {}}
    for name, url in LAYERS.items():
        info = layer_info(url)
        gj = fetch_geojson(url, fields=FIELDS.get(name, "*"))
        (RAW / f"{name}.geojson").write_text(json.dumps(gj))
        edit = (info.get("editingInfo") or {}).get("dataLastEditDate")
        log["layers"][name] = {
            "url": url,
            "layer_name": info.get("name"),
            "n_features": len(gj["features"]),
            "data_last_edit": datetime.fromtimestamp(edit / 1000, timezone.utc).date().isoformat() if edit else None,
        }
        print(name, log["layers"][name])
    (RAW / "fetch_log.json").write_text(json.dumps(log, indent=2))


if __name__ == "__main__":
    main()
