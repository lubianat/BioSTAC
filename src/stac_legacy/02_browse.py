import marimo

app = marimo.App(width="full")


@app.cell
def _():
    import http.server
    import threading
    from functools import partial

    import marimo as mo
    import pystac
    return http, mo, partial, pystac, threading


@app.cell
def _(mo, pystac):
    catalog = pystac.Catalog.from_file("catalogs/basic/catalog.json")
    items = list(catalog.get_items())
    version = mo.ui.dropdown(sorted({i.id.split("-")[0] for i in items}), label="NGFF version", value="v0.4")
    mo.vstack([mo.md(f"# {catalog.id}\n{catalog.description}\n\n**{len(items)}** items"), version])
    return items, version


@app.cell
def _(items, mo, version):
    def card(item):
        data = item.assets["data"].href
        meta = item.assets.get("metadata")
        return mo.Html(
            f'<a href="https://hms-dbmi.github.io/vizarr/?source={data}" target="_blank">'
            f'<img src="{item.assets["thumbnail"].href}" width="96"></a>'
            f'<div style="font-size:11px;width:120px;word-break:break-all">{item.id}<br>{item.datetime:%Y-%m-%d}'
            + (f' · <a href="{meta.href}" target="_blank">OME-XML</a>' if meta else "")
            + "</div>"
        )

    mo.hstack([card(i) for i in items if i.id.startswith(version.value + "-")], wrap=True, justify="start")
    return


@app.cell
def _(http, mo, partial, threading):
    # ponytail: stdlib server with CORS so STAC Browser (a web app) can fetch local files
    class CORS(http.server.SimpleHTTPRequestHandler):
        def end_headers(self):
            self.send_header("Access-Control-Allow-Origin", "*")
            super().end_headers()

    try:
        server = http.server.ThreadingHTTPServer(("localhost", 8000), partial(CORS, directory="."))
        threading.Thread(target=server.serve_forever, daemon=True).start()
    except OSError:
        pass  # already serving (cell re-run)

    url = "https://radiantearth.github.io/stac-browser/#/external/http://localhost:8000/catalogs/basic/catalog.json"
    mo.md(f"## STAC Browser\nServing `catalogs/basic/` on localhost:8000 → [open in STAC Browser]({url})")
    return


if __name__ == "__main__":
    app.run()
