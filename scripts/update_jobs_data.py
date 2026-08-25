#!/usr/bin/env python3
import json
import math
import re
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

BRANCH_TABLE = "LSK11"
SECTOR_TABLE = "LSK12"


def ordered_codes(dimension):
    index = dimension["category"]["index"]
    return [code for code, _ in sorted(index.items(), key=lambda item: item[1])]


def cube_value(dataset, coordinates):
    dimensions = dataset["dimension"]
    ids = dimensions["id"]
    sizes = dimensions["size"]
    flat_index = 0
    for position, dimension_id in enumerate(ids):
        category_index = dimensions[dimension_id]["category"]["index"]
        flat_index += category_index[coordinates[dimension_id]] * math.prod(sizes[position + 1 :])
    values = dataset["value"]
    if isinstance(values, dict):
        return values.get(str(flat_index), values.get(flat_index))
    return values[flat_index] if flat_index < len(values) else None


def fetch_dataset(table, selections):
    query = urllib.parse.urlencode(selections)
    request = urllib.request.Request(
        f"https://api.statbank.dk/v1/data/{table}/JSONSTAT?{query}",
        headers={"User-Agent": "AI-MichelKlos/arbejdsmarked jobs dashboard"},
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.load(response)["dataset"]


def build_payload(branch_dataset, sector_dataset):
    dimensions = branch_dataset["dimension"]
    branch_id = "BRANCHEDB25"
    size_id = next(key for key in dimensions["id"] if key.upper().startswith("ST") and key != "Tid")
    times = ordered_codes(dimensions["Tid"])
    branches = ordered_codes(dimensions[branch_id])
    branch_labels = dimensions[branch_id]["category"]["label"]

    def value(branch, unit, period):
        return cube_value(
            branch_dataset,
            {
                branch_id: branch,
                "ENHED": unit,
                size_id: "000",
                "ContentsCode": BRANCH_TABLE,
                "Tid": period,
            },
        )

    branch_counts = [value("A-V", "LS", period) for period in times]
    latest_index = max(i for i, item in enumerate(branch_counts) if item is not None)
    latest_period = times[latest_index]
    branch_rows = []
    for code in branches:
        if code == "A-V":
            continue
        label = re.sub(r"^[A-Z-]+\s+", "", branch_labels.get(code, code)).strip()
        branch_rows.append(
            {
                "code": code,
                "name": label,
                "count": value(code, "LS", latest_period),
                "rate": value(code, "ALS", latest_period),
            }
        )
    branch_rows.sort(key=lambda row: row["count"] if row["count"] is not None else -1, reverse=True)

    sector_dimensions = sector_dataset["dimension"]
    sector_times = ordered_codes(sector_dimensions["Tid"])

    def sector_value(sector, unit, period):
        return cube_value(
            sector_dataset,
            {
                "REGION": "001",
                "ENHED": unit,
                "SEKTOR": sector,
                "ContentsCode": SECTOR_TABLE,
                "Tid": period,
            },
        )

    all_counts = [sector_value("1000", "LS", period) for period in sector_times]
    all_rates = [sector_value("1000", "ALS", period) for period in sector_times]
    new_private_counts = [sector_value("1040", "LS", period) for period in sector_times]
    new_private_rates = [sector_value("1040", "ALS", period) for period in sector_times]

    return {
        "meta": {
            "source": "Danmarks Statistik",
            "tables": [BRANCH_TABLE, SECTOR_TABLE],
            "sourceUrls": [
                f"https://www.statistikbanken.dk/{BRANCH_TABLE}",
                f"https://www.statistikbanken.dk/{SECTOR_TABLE}",
            ],
            "tableUpdated": max(
                value for value in (branch_dataset.get("updated"), sector_dataset.get("updated")) if value
            ),
            "fetchedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "note": "Dashboardet bruger kun de aktive tabeller LSK11 og LSK12 fra den aktuelle opgørelse.",
        },
        "allVacancies": {
            "labels": sector_times,
            "count": all_counts,
            "rate": all_rates,
            "privateCount": new_private_counts,
            "privateRate": new_private_rates,
            "latestPeriod": sector_times[-1],
        },
        "privateVacancies": {
            "labels": sector_times,
            "count": new_private_counts,
            "rate": new_private_rates,
            "latestPeriod": sector_times[-1],
            "branches": branch_rows,
        },
    }


def main():
    output = Path(__file__).resolve().parents[1] / "data" / "jobs-statbank.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(
            build_payload(
                fetch_dataset(
                    BRANCH_TABLE,
                    {
                        "BRANCHEDB25": "*",
                        "ENHED": "LS,ALS",
                        "STØRRELSE": "000",
                        "Tid": "*",
                    },
                ),
                fetch_dataset(
                    SECTOR_TABLE,
                    {
                        "REGION": "001",
                        "ENHED": "LS,ALS",
                        "SEKTOR": "1000,1040",
                        "Tid": "*",
                    },
                ),
            ),
            ensure_ascii=False,
            separators=(",", ":"),
        )
        + "\n",
        encoding="utf-8",
    )
    print(output)


if __name__ == "__main__":
    main()

