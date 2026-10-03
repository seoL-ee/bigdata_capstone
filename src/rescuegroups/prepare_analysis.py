"""Build Parquet snapshots and full-data profiles from RescueGroups raw JSON."""

import csv
import json
from collections import Counter
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq


ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = ROOT / "data" / "rescuegroups" / "raw"
PROCESSED_DIR = ROOT / "data" / "rescuegroups" / "processed"
RESULTS_DIR = ROOT / "results" / "rescuegroups"
BASE_URL = "https://api.rescuegroups.org/v5"
MAX_DISTRIBUTION_CARDINALITY = 100

CANDIDATE_FIELDS = [
    "ageGroup",
    "sex",
    "sizeGroup",
    "coatLength",
    "breedPrimary",
    "activityLevel",
    "energyLevel",
    "exerciseNeeds",
    "newPeopleReaction",
    "isDogsOk",
    "isCatsOk",
    "isKidsOk",
    "isSeniorsOk",
    "isHousetrained",
    "obedienceTraining",
    "ownerExperience",
    "isYardRequired",
    "fenceNeeds",
    "indoorOutdoor",
    "vocalLevel",
    "groomingNeeds",
    "isSpecialNeeds",
]


def present(value):
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    return value not in ([], {})


def parquet_value(value):
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def build_columns(animals, species, source_name):
    attribute_names = sorted(
        {name for animal in animals for name in (animal.get("attributes") or {})}
    )
    names = ["snapshot_species", "animal_id", "animal_type"]
    names += [f"attr__{name}" for name in attribute_names]
    names += ["relationships_json", "links_json", "meta_json", "source_file"]
    columns = {name: [] for name in names}

    for animal in animals:
        attributes = animal.get("attributes") or {}
        columns["snapshot_species"].append(species)
        columns["animal_id"].append(str(animal.get("id")))
        columns["animal_type"].append(animal.get("type"))
        for name in attribute_names:
            columns[f"attr__{name}"].append(parquet_value(attributes.get(name)))
        for source_key, column_name in (
            ("relationships", "relationships_json"),
            ("links", "links_json"),
            ("meta", "meta_json"),
        ):
            value = animal.get(source_key)
            columns[column_name].append(
                json.dumps(value, ensure_ascii=False, sort_keys=True)
                if value is not None
                else None
            )
        columns["source_file"].append(source_name)

    for name, values in columns.items():
        types = {type(value) for value in values if value is not None}
        if len(types) > 1 and not types <= {int, float}:
            columns[name] = [None if value is None else str(value) for value in values]
        elif types <= {int, float} and float in types:
            columns[name] = [None if value is None else float(value) for value in values]
    return columns, attribute_names


def profile_attributes(animals, attribute_names):
    profile = {}
    for name in attribute_names:
        values = [(animal.get("attributes") or {}).get(name) for animal in animals]
        populated = [parquet_value(value) for value in values if present(value)]
        counts = Counter(populated)
        dominant_share_pct = (
            round(100 * counts.most_common(1)[0][1] / len(populated), 2)
            if populated
            else None
        )
        profile[name] = {
            "non_null_n": len(populated),
            "null_n": len(values) - len(populated),
            "cardinality": len(counts),
            "dominant_share_pct": dominant_share_pct,
            "distribution": counts if len(counts) <= MAX_DISTRIBUTION_CARDINALITY else None,
        }
    return profile


def read_and_convert(path):
    payload = json.loads(path.read_text(encoding="utf-8"))
    metadata = payload.get("metadata") or {}
    animals = payload.get("data") or []
    species = metadata.get("species") or path.name.split("_")[0]
    ids = [str(animal.get("id")) for animal in animals]
    raw_count = metadata.get("raw_count") or len(animals) + metadata.get("duplicate_count", 0)
    unique_count = len(set(ids))

    columns, attribute_names = build_columns(animals, species, path.name)
    table = pa.table(columns)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    parquet_path = PROCESSED_DIR / path.with_suffix(".parquet").name
    pq.write_table(table, parquet_path, compression="zstd", use_dictionary=True)

    endpoint = f"{BASE_URL}/public/animals/search/available/{species}/"
    manifest = {
        "snapshot_file": str(path.relative_to(ROOT)),
        "parquet_file": str(parquet_path.relative_to(ROOT)),
        "collection_time": metadata.get("collection_time"),
        "species": species,
        "reported_count": metadata.get("reported_available_count"),
        "raw_count": raw_count,
        "unique_count": unique_count,
        "duplicates": metadata.get("duplicate_count", raw_count - unique_count),
        "retries": metadata.get("retry_count"),
        "elapsed_seconds": metadata.get("elapsed_seconds"),
        "api_base_url": metadata.get("api_base_url", BASE_URL),
        "source_endpoint": metadata.get("source_endpoint", endpoint),
        "raw_file_bytes": path.stat().st_size,
        "parquet_file_bytes": parquet_path.stat().st_size,
    }
    return manifest, profile_attributes(animals, attribute_names), len(animals)


def write_csv(path, fieldnames, rows):
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main():
    snapshots = {
        species: max(RAW_DIR.glob(f"{species}_available_all_*.json"), key=lambda p: p.stat().st_mtime)
        for species in ("dogs", "cats")
    }
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    manifests = []
    profiles = {}
    totals = {}
    for species, path in snapshots.items():
        manifest, profile, total = read_and_convert(path)
        manifests.append(manifest)
        profiles[species] = profile
        totals[species] = total
        print(f"species={species} parquet_rows={total} file={manifest['parquet_file']}")

    common_fields = sorted(set(profiles["dogs"]) & set(profiles["cats"]))
    coverage_rows = []
    distribution_rows = []
    comparison_rows = []
    for field in common_fields:
        comparison = {"feature": field}
        for species in ("dogs", "cats"):
            item = profiles[species][field]
            total = totals[species]
            coverage_pct = round(100 * item["non_null_n"] / total, 2)
            null_rate_pct = round(100 * item["null_n"] / total, 2)
            coverage_rows.append(
                {
                    "species": species,
                    "feature": field,
                    "total_n": total,
                    "non_null_n": item["non_null_n"],
                    "null_n": item["null_n"],
                    "coverage_pct": coverage_pct,
                    "null_rate_pct": null_rate_pct,
                    "cardinality": item["cardinality"],
                    "dominant_share_pct": item["dominant_share_pct"],
                }
            )
            comparison[f"{species}_coverage_pct"] = coverage_pct
            comparison[f"{species}_cardinality"] = item["cardinality"]
            comparison[f"{species}_dominant_share_pct"] = item["dominant_share_pct"]
            if field in CANDIDATE_FIELDS and item["distribution"] is not None:
                for value, count in item["distribution"].most_common():
                    distribution_rows.append(
                        {
                            "species": species,
                            "feature": field,
                            "value": value,
                            "count": count,
                            "share_pct": round(100 * count / total, 2),
                        }
                    )
        comparison["coverage_gap_pct_points"] = round(
            abs(comparison["dogs_coverage_pct"] - comparison["cats_coverage_pct"]), 2
        )
        comparison_rows.append(comparison)

    candidate_rows = []
    comparison_by_field = {row["feature"]: row for row in comparison_rows}
    for field in CANDIDATE_FIELDS:
        item = comparison_by_field.get(field)
        if not item:
            item = {
                "feature": field,
                "dogs_coverage_pct": 0.0,
                "dogs_cardinality": 0,
                "dogs_dominant_share_pct": None,
                "cats_coverage_pct": 0.0,
                "cats_cardinality": 0,
                "cats_dominant_share_pct": None,
                "coverage_gap_pct_points": 0.0,
            }
        minimum_coverage = min(item["dogs_coverage_pct"], item["cats_coverage_pct"])
        maximum_cardinality = max(item["dogs_cardinality"], item["cats_cardinality"])
        dominant_shares = [
            value
            for value in (
                item["dogs_dominant_share_pct"],
                item["cats_dominant_share_pct"],
            )
            if value is not None
        ]
        maximum_dominant_share = max(dominant_shares, default=100.0)
        if (
            minimum_coverage >= 70
            and 2 <= maximum_cardinality <= 50
            and maximum_dominant_share < 90
        ):
            recommendation = "candidate"
        elif minimum_coverage >= 10 and 2 <= maximum_cardinality <= 250:
            recommendation = "experimental"
        else:
            recommendation = "exclude_or_text_only"
        candidate_rows.append(
            {
                **item,
                "minimum_species_coverage_pct": minimum_coverage,
                "recommendation": recommendation,
            }
        )

    (RESULTS_DIR / "snapshot_manifest.json").write_text(
        json.dumps({"snapshots": manifests}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    write_csv(
        RESULTS_DIR / "coverage.csv",
        ["species", "feature", "total_n", "non_null_n", "null_n", "coverage_pct", "null_rate_pct", "cardinality", "dominant_share_pct"],
        coverage_rows,
    )
    write_csv(
        RESULTS_DIR / "distributions.csv",
        ["species", "feature", "value", "count", "share_pct"],
        distribution_rows,
    )
    write_csv(
        RESULTS_DIR / "species_coverage_comparison.csv",
        ["feature", "dogs_coverage_pct", "dogs_cardinality", "dogs_dominant_share_pct", "cats_coverage_pct", "cats_cardinality", "cats_dominant_share_pct", "coverage_gap_pct_points"],
        comparison_rows,
    )
    write_csv(
        RESULTS_DIR / "recommendation_candidates.csv",
        ["feature", "dogs_coverage_pct", "dogs_cardinality", "dogs_dominant_share_pct", "cats_coverage_pct", "cats_cardinality", "cats_dominant_share_pct", "coverage_gap_pct_points", "minimum_species_coverage_pct", "recommendation"],
        candidate_rows,
    )
    print(f"common_fields={len(common_fields)} manifest={RESULTS_DIR / 'snapshot_manifest.json'}")


if __name__ == "__main__":
    main()
