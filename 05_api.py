import marimo

app = marimo.App(width="full")


@app.cell
def _():
    import json
    import warnings

    import cql2
    import marimo as mo
    from pystac_client import Client

    # pystac-client checks an older sort conformance URI than stac-fastapi advertises; sort works fine
    warnings.filterwarnings("ignore", message=".*does not conform to SORT.*")

    API = "http://localhost:8082"
    return API, Client, cql2, json, mo


@app.cell
def _(API, mo):
    mo.md(f"""
    # IDR OME-Zarr samples over a STAC API

    The static `catalogs/extended/` loaded into **stac-fastapi-pgstac**, the reference STAC API.
    Nothing on this page is custom server code:

    ```bash
    docker compose -f api/docker-compose.yml up -d
    api/load.sh
    ```

    API root: <{API}>
    """)
    return


@app.cell
def _(API, Client, mo):
    client = Client.open(API)
    conformance = [c for c in client.to_dict()["conformsTo"] if "stacspec" in c]
    queryables = client.get_queryables()["properties"]
    mo.hstack([
        mo.vstack([mo.md("### What the API supports (`/conformance`)"), mo.md("\n".join(f"- `{c}`" for c in conformance))]),
        mo.vstack([
            mo.md("### What you can filter on (`/queryables`)"),
            mo.ui.table(
                [{"field": k, "title": v.get("title", ""), "type": v.get("type", "")} for k, v in queryables.items()],
                selection=None, pagination=False,
            ),
        ]),
    ], widths=[1, 1], align="start")
    return (client,)


@app.cell
def _(client, mo):
    examples = {
        "3D time-lapse with labels": "\"ome:size_z\" > 1 AND \"ome:size_t\" > 1 AND \"ome:has_labels\" = true",
        "Many channels (≥ 6)": "\"ome:size_c\" >= 6",
        "HCS plates": "\"ome:plate\" = true",
        "idr0062, NGFF 0.5": "\"idr:study\" = 'idr0062' AND \"ome:version\" = '0.5'",
        "Public domain": "license = 'CC0-1.0'",
        "Big 2D (X > 10000)": "\"ome:size_x\" > 10000 AND \"ome:size_z\" = 1",
        "Deep stacks": "\"ome:size_z\" > 200",
    }
    example = mo.ui.dropdown(examples, value="Deep stacks", label="Example query")
    collections = mo.ui.multiselect([c.id for c in client.get_collections()], label="Collections")
    sortby = mo.ui.dropdown(
        {"none": "", "Z depth ↓": "-properties.ome:size_z", "channels ↓": "-properties.ome:size_c",
         "width ↓": "-properties.ome:size_x", "date added ↓": "-properties.datetime"},
        value="Z depth ↓", label="Sort by",
    )
    mo.hstack([example, collections, sortby], justify="start")
    return collections, example, sortby


@app.cell
def _(example, mo):
    query = mo.ui.text_area(value=example.value, label="CQL2 filter (sent to the API)", full_width=True)
    query
    return (query,)


@app.cell
def _(API, client, collections, cql2, json, mo, query, sortby):
    search = client.search(
        filter=query.value,
        collections=collections.value or None,
        sortby=sortby.value or None,
        max_items=100,
    )
    hits = list(search.items())
    cli = (
        f"stac-client search {API} \\\n  --filter '{json.dumps(cql2.Expr(query.value).to_json())}'"
        + (f" \\\n  --collections {' '.join(collections.value)}" if collections.value else "")
        + (f" \\\n  --sortby {sortby.value}" if sortby.value else "")
    )
    mo.accordion({
        "Same search from the command line (pystac-client CLI takes CQL2-JSON)": mo.md(f"```bash\n{cli}\n```"),
        "Raw request sent to /search": mo.json(search.get_parameters()),
    })
    return (hits,)


@app.cell
def _(hits, mo):
    def card(item):
        p = item.properties
        data = item.assets["data"].href
        meta = item.assets.get("metadata")
        # pgstac drops null properties, so missing axes are simply absent
        dims = " × ".join(f"{d}{p[f'ome:size_{d.lower()}']}" for d in "XYZCT" if p.get(f"ome:size_{d.lower()}"))
        return mo.Html(
            f'<a href="https://hms-dbmi.github.io/vizarr/?source={data}" target="_blank">'
            f'<img src="{item.assets["thumbnail"].href}" width="96"></a>'
            f'<div style="font-size:11px;width:140px;word-break:break-all">{item.id}<br>{dims}<br>{p["license"]}'
            + (" · labels" if p.get("ome:has_labels") else "")
            + (f' · <a href="{meta.href}" target="_blank">OME-XML</a>' if meta else "")
            + "</div>"
        )

    mo.vstack([mo.md(f"**{len(hits)}** matches"), mo.hstack([card(i) for i in hits], wrap=True, justify="start")])
    return


@app.cell
def _(API, mo):
    url = f"https://radiantearth.github.io/stac-browser/#/external/{API}"
    mo.md(f"""
    ## STAC Browser on the API
    [Open the API in STAC Browser]({url}), then go to **Search**.
    Its filter form is built from `/queryables`, so the `ome:*` fields show up with their types and enums.
    """)
    return


if __name__ == "__main__":
    app.run()
