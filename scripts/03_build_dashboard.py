"""Fill dashboard_template.html with processed data -> outputs/bike_plan_dashboard.html."""
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PROC = ROOT / "data" / "processed"


def main():
    projects = pd.read_csv(PROC / "unbuilt_plan_projects_by_hin.csv").fillna("")
    html = (ROOT / "scripts" / "dashboard_template.html").read_text()
    for key, value in {
        "__SUMMARY__": (PROC / "summary.json").read_text(),
        "__PROJECTS__": projects.to_json(orient="records"),
        "__EXISTING__": (PROC / "map_existing.geojson").read_text(),
        "__PROPOSED__": (PROC / "map_proposed.geojson").read_text(),
        "__HIN__": (PROC / "map_hin.geojson").read_text(),
    }.items():
        html = html.replace(key, value)
    out = ROOT / "outputs" / "bike_plan_dashboard.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html)
    print(out, f"{out.stat().st_size / 1e3:.0f} KB")


if __name__ == "__main__":
    main()
