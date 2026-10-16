import marimo

app = marimo.App(width="full")


@app.cell
def _():
    import csv
    import json
    import pathlib
    import re
    import time

    import duckdb
    import marimo as mo

    import biostac_build as bb

    IDR = pathlib.Path("catalogs/challenge/idr")
    LISTS = f"{IDR}/*/item-list.parquet"  # every study's list: images, plates and now wells
    RAW = "https://raw.githubusercontent.com/IDR"

    # where each study's annotation lives: some sit in idr-metadata, others are submodules with own repos
    ANNOTATIONS = {
        "idr0004": ("idr-metadata/master/idr0004-thorpe-rad52", ["screenA"]),
        "idr0010": ("idr-metadata/master/idr0010-doil-dnadamage", ["screenA"]),
        "idr0011": ("idr-metadata/master/idr0011-ledesmafernandez-dad4",
                    ["screenA", "screenB", "screenC", "screenD", "screenE"]),  # five screens cover all 182 plates
        "idr0012": ("idr0012-fuchs-cellmorph/master", ["screenA"]),
        "idr0033": ("idr0033-rohban-pathways/master", ["screenA"]),
        "idr0035": ("idr-metadata/master/idr0035-caie-drugresponse", ["screenA"]),
        "idr0036": ("idr-metadata/master/idr0036-gustafsdottir-cellpainting", ["screenA"]),
        "idr0090": ("idr0090-ashdown-malaria/master", ["screenA"]),
        # idr0015 has no annotation file
    }
    return ANNOTATIONS, IDR, LISTS, RAW, bb, csv, duckdb, json, mo, re, time


@app.cell
def _(mo):
    mo.md(r"""
    # Plate wells, annotated from IDR

    A plate is one row of its study's `item-list.parquet` (`14_idr_catalog.py`). Below it, the unit worth indexing is the **well**, not the
    field image:

    - IDR's screen annotations are keyed `Plate, Well`. Gene, compound, cell line and control type belong to a
      well, and the several field images of a well share them.
    - Fields cannot be listed without one request per well. OME-NGFF defines `field_count` as the *maximum*
      per well, and in idr0011 many wells hold fewer, so deriving field paths from it invents URLs that 404.

    So this notebook adds one row per well to the same `item-list.parquet`, with a curated set of
    [`idr:` columns](../SPECIFICATION.md). Every row carries `bioimage:level`, and the file is sorted by it, so a
    reader that wants only images and plates skips the wells' row groups by their statistics. It needs
    **no requests to the image server**: wells come from each
    plate's own `zarr.json`, already cached, and the annotations come from IDR's metadata repositories.

    IDR's annotation tables are **not republished** — only the handful of `idr:` columns are carried, and
    the study crate links to IDR for the rest.

    To see the images of a well, read that well's `zarr.json`: one request, when someone actually asks.
    """)
    return


@app.cell
def _(ANNOTATIONS, RAW, bb, re):
    def annotation_file(study, screen):
        """IDR's annotation file for one screen, cached under build_cache/ and never shipped."""
        base, _ = ANNOTATIONS[study]
        path = bb.CACHE / "idr_annotations" / f"{study}-{screen}.csv"
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(bb.fetch_bytes(f"{RAW}/{base}/{screen}/{study}-{screen}-annotation.csv"))
        return path

    def first_value(row, names):
        for name in names:
            if row.get(name):
                return row[name].strip()
        return None

    def term_after(row, columns, characteristic):
        """'Term Source N REF/Accession' qualify the Characteristics column they follow, so read them by
        position rather than by name: NCBITaxon + NCBITaxon_4932 -> NCBITaxon:4932."""
        if characteristic not in columns:
            return None
        start = columns.index(characteristic)
        for name in columns[start + 1:start + 4]:
            if name.endswith("Accession") and row.get(name):
                return bb.to_curie(row[name].strip())
        return None

    PHENOTYPE = re.compile(r"^Phenotype( \d+)?$")

    def idr_fields(row, columns, screen):
        """The curated idr: fields of one annotation row."""
        phenotypes = [row[c].strip() for c in columns if PHENOTYPE.match(c) and row.get(c, "").strip()]
        has_phenotype = (row.get("Has Phenotype") or "").strip().lower()
        return {
            "idr:plate_name": row.get("Plate"),
            "idr:well": row.get("Well"),
            "idr:screen": screen,
            "idr:gene_symbol": first_value(row, ["Gene Symbol", "Comment [Gene Symbol]"]),
            "idr:gene_identifier": first_value(row, ["Gene Identifier", "Comment [Gene Identifier]"]),
            "idr:sirna_identifier": first_value(row, ["siRNA Identifier", "siRNA Pool Identifier"]),
            "idr:compound_name": first_value(row, ["Compound Name", "Compound 1 Name"]),
            "idr:organism": first_value(row, ["Characteristics [Organism]"]),
            "idr:organism_term": term_after(row, columns, "Characteristics [Organism]"),
            "idr:cell_line": first_value(row, ["Characteristics [Cell Line]"]),
            "idr:cell_line_term": term_after(row, columns, "Characteristics [Cell Line]"),
            "idr:control_type": first_value(row, ["Control Type"]),
            "idr:has_phenotype": True if has_phenotype == "yes" else False if has_phenotype == "no" else None,
            "idr:phenotypes": phenotypes or None,
        }
    return annotation_file, idr_fields


@app.cell
def _(ANNOTATIONS, annotation_file, csv, idr_fields):
    def annotations_for(study):
        """{(plate name, well): idr fields} for one study, read row by row so the table is never
        held in memory whole. Where screens overlap, the first one describing a well wins."""
        by_well, overlaps = {}, 0
        for screen in ANNOTATIONS.get(study, ("", []))[1]:
            with open(annotation_file(study, screen), encoding="utf-8-sig", errors="replace", newline="") as f:
                reader = csv.DictReader(f)
                columns = reader.fieldnames or []
                for row in reader:
                    key = (row.get("Plate"), row.get("Well"))
                    if None in key:
                        continue
                    if key in by_well:
                        overlaps += 1
                        continue
                    by_well[key] = idr_fields(row, columns, screen)
        return by_well, overlaps
    return (annotations_for,)


@app.cell
def _(IDR, bb, json):
    # what a well does not inherit from its plate: the plate's own crate, thumbnail and counts
    NOT_INHERITED = ("ro_crate_url", "crate_href", "thumbnail_url", "bioimage:wells", "bioimage:field_count_max")

    def well_rows(plate_row, by_well):
        """One row per well of a plate, with IDR's annotation joined on."""
        zarr_url = plate_row["zarr_url"]
        plate_name = zarr_url.rsplit("/", 1)[-1].removesuffix(".ome.zarr").removesuffix(".zarr")
        plate = json.loads((bb.CACHE / "idr" / plate_row["id"] / "zarr.json").read_text())
        plate = plate["attributes"]["ome"]["plate"]
        inherited = {k: v for k, v in plate_row.items() if k not in NOT_INHERITED and not k.startswith("idr:")}

        for well in plate["wells"]:
            path = well["path"]  # A/1
            flat = path.replace("/", "")  # A1, the form IDR's annotations use
            yield inherited | {
                "id": f"{plate_row['id']}-{flat.lower()}",
                "bioimage:level": "well",  # overrides the plate's own level
                "bioimage:plate_id": plate_row["id"],
                "bioimage:well": path,
                "zarr_url": f"{zarr_url}/{path}",
                "zarr_metadata_url": f"{zarr_url}/{path}/zarr.json",  # lists the well's images
                **by_well.get((plate_name, flat), {}),
            }

    plates_by_study = {}
    for _path in sorted(IDR.glob("*/item-list.parquet")):
        _plates = bb.read_list(_path, level="plate")
        if _plates:
            plates_by_study[_path.parent.name] = _plates
    return plates_by_study, well_rows


@app.cell
def _(IDR, annotations_for, bb, mo, plates_by_study, time, well_rows):
    # one study at a time: its annotations, its rows, written into its own item-list.parquet
    started = time.perf_counter()
    per_study = {}
    for _study, _plates in sorted(plates_by_study.items()):
        _by_well, _overlaps = annotations_for(_study)
        _rows = [row for plate in _plates for row in well_rows(plate, _by_well)]
        _list = IDR / _study / "item-list.parquet"
        bb.write_list(_rows, _list, keep_from=_list)
        bb.register_file(IDR / _study, _list, "Items of this study, one row each: images, plates and their wells")
        per_study[_study] = {
            "study": _study, "plates": len(_plates), "wells": len(_rows),
            "annotated": sum(1 for r in _rows if r.get("idr:plate_name")),
            "annotation rows": len(_by_well), "wells in two screens": _overlaps,
        }
        del _rows, _by_well
    write_seconds = round(time.perf_counter() - started, 1)

    well_count = sum(s["wells"] for s in per_study.values())
    mo.vstack([
        mo.md(f"**{well_count:,}** wells from **{sum(s['plates'] for s in per_study.values())}** plates, "
              f"**{sum(s['annotated'] for s in per_study.values()):,}** with IDR annotations, in "
              f"{write_seconds} s, added to each plate study's `item-list.parquet` and registered again in its "
              "crate (size and checksum changed). `idr0015` has no annotation file, so its wells carry none."),
        mo.ui.table(list(per_study.values()), selection=None, pagination=False),
    ])
    return per_study, well_count


@app.cell
def _(IDR, mo, per_study, well_count):
    # the built folder is generated and git-ignored, so its README is written here, next to the data
    _readme = f"""# IDR, as indexed here

Built by `14_idr_catalog.py` (plates and images) and `15_plate_wells.py` (wells).

## What the levels are

- `ro-crate-metadata.json` — the IDR resource: its studies as nested crates, and `study-list.parquet`
- `<study>/ro-crate-metadata.json` — one study: IDR's own study crate, attached, listing one data file:
- `<study>/item-list.parquet` — one row per OME-Zarr in the challenge list (a plain image, a bioformats2raw
  image, or a **whole plate**), and one per well of those plates: **{well_count:,} wells** of the
  {sum(s['plates'] for s in per_study.values())} plates, with a curated set of IDR's well annotations (see
  `SPECIFICATION.md` at the repository root). `bioimage:level` says which a row is, and the file is sorted by it.
- `<study>/<image>/` — BioSTAC's crate of that image, and its thumbnail where one was rendered

## Below a plate

A plate's wells are indexed; its individual field images are not. IDR's annotations (gene, compound, cell
line, control type) are keyed by plate and well, and the field images of a well share them, so the well is
the smallest unit that carries metadata.

Field images are also not listable without asking the server once per well: OME-NGFF defines `field_count`
as the *maximum* number of fields per well, and some wells hold fewer. To list the images of a well, read
that well's own `zarr.json`, which each row links as `zarr_metadata_url`.

A small number of wells listed in IDR's plate metadata are not present on the server (4 of 1,905 sampled).
Rows come from that metadata as published.

## Not republished

Only the `idr:` columns are carried. IDR's full annotation tables stay at IDR; each study crate links to its
study page.
"""
    (IDR / "README.md").write_text(_readme)
    mo.md(f"Wrote `{IDR}/README.md` describing the levels and what is deliberately absent.")
    return


@app.cell
def _(LISTS, duckdb, mo):
    def table(title, query):
        result = duckdb.sql(query)
        rows = [dict(zip(result.columns, r)) for r in result.fetchall()]
        return mo.vstack([mo.md(f"**{title}**"), mo.md(f"```sql\n{query.strip()}\n```"),
                          mo.ui.table(rows, selection=None, pagination=False)])

    mo.vstack([
        mo.md("## Searching wells\nThis is the point of the level: IDR's own search finds images by gene, "
              "and so can this file."),
        table("Gene PAU8, as in IDR's own search", f"""
SELECT study, "idr:plate_name" AS plate, "idr:well" AS well,
       "idr:gene_identifier" AS gene_id, zarr_url AS well_url
FROM read_parquet('{LISTS}', union_by_name := true)
WHERE "bioimage:level" = 'well' AND "idr:gene_symbol" = 'PAU8'
ORDER BY study, plate, well
"""),
        table("Compounds, across the two cell-painting screens", f"""
SELECT study, "idr:compound_name" AS compound, count(*) AS wells
FROM read_parquet('{LISTS}', union_by_name := true)
WHERE "bioimage:level" = 'well' AND "idr:compound_name" IS NOT NULL
GROUP BY 1, 2 ORDER BY wells DESC LIMIT 8
"""),
        table("Annotated wells per study", f"""
SELECT study, count(*) AS wells,
       count("idr:gene_symbol") AS with_gene, count("idr:compound_name") AS with_compound,
       count(*) FILTER (WHERE "idr:has_phenotype") AS with_phenotype
FROM read_parquet('{LISTS}', union_by_name := true)
WHERE "bioimage:level" = 'well'
GROUP BY 1 ORDER BY 1
"""),
        table("Every level in one query: images, plates and wells together", f"""
SELECT "bioimage:level" AS row_denotes, count(*) AS rows,
       count(DISTINCT study) AS studies, count("idr:gene_symbol") AS with_gene
FROM read_parquet('{LISTS}', union_by_name := true)
GROUP BY 1 ORDER BY rows DESC
"""),
        table("Gene search across levels, as a user would ask it", f"""
SELECT "bioimage:level" AS row_denotes, study, id, zarr_url AS url
FROM read_parquet('{LISTS}', union_by_name := true)
WHERE "idr:gene_symbol" = 'PAU8'
ORDER BY row_denotes, id
"""),
        table("A well joined to its plate row", f"""
SELECT w."idr:gene_symbol" AS gene, w.id AS well, i.title AS plate_title, i."bioimage:field_count_max" AS max_fields
FROM read_parquet('{LISTS}', union_by_name := true) w JOIN read_parquet('{LISTS}', union_by_name := true) i ON w."bioimage:plate_id" = i.id
WHERE w."idr:gene_symbol" = 'PAU8'
"""),
    ])
    return


@app.cell
def _(IDR, duckdb, mo):
    _biggest = max(IDR.glob("*/item-list.parquet"), key=lambda p: p.stat().st_size)
    _groups = duckdb.sql(f"""SELECT row_group_id AS row_group, row_group_num_rows AS rows,
                                    stats_min_value AS first_level, stats_max_value AS last_level
                             FROM parquet_metadata('{_biggest}') WHERE path_in_schema = 'bioimage:level'
                             ORDER BY 1""")
    _groups = [dict(zip(_groups.columns, r)) for r in _groups.fetchall()]
    mo.vstack([
        mo.md(
            "## How it is laid out for search\n"
            f"- each list is sorted by `bioimage:level`, then id (plate, then well); `{_biggest}` has "
            f"{len(_groups)} row groups, below. Statistics on `bioimage:level` let a reader that asks for "
            "images and plates fetch only the groups whose range includes them\n"
            "- the `idr:` columns are flat, so they can be filtered and skipped on; `idr:phenotypes` is a list, "
            "which DuckDB searches with `list_contains`\n"
            "- a plate and its wells both match a metadata filter, since a well inherits the plate's columns: "
            "filter on `bioimage:level` when counting, or the same image counts twice\n"
            "- no field-image rows: see the notebook header, and `catalogs/challenge/idr/README.md`"),
        mo.ui.table(_groups, selection=None, pagination=False),
    ])
    return


if __name__ == "__main__":
    app.run()
