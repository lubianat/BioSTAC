"""Write STAC JSON for humans: short objects and lists stay on one line.

Use once per notebook, before saving:

    import pystac
    from readable_stac_io import ReadableStacIO
    pystac.StacIO.set_default(ReadableStacIO)
"""

import json

from pystac.stac_io import DefaultStacIO

LINE_WIDTH = 100


def dumps(value, indent=0):
    """Like json.dumps(indent=2), but any container that fits on one line is kept on one line."""
    flat = json.dumps(value, ensure_ascii=False)
    if not isinstance(value, (dict, list)) or not value or indent + len(flat) <= LINE_WIDTH:
        return flat
    pad = " " * (indent + 2)
    if isinstance(value, dict):
        lines = [f"{pad}{json.dumps(k, ensure_ascii=False)}: {dumps(v, indent + 2)}" for k, v in value.items()]
        return "{\n" + ",\n".join(lines) + "\n" + " " * indent + "}"
    lines = [f"{pad}{dumps(v, indent + 2)}" for v in value]
    return "[\n" + ",\n".join(lines) + "\n" + " " * indent + "]"


class ReadableStacIO(DefaultStacIO):
    def json_dumps(self, json_dict, *args, **kwargs):
        return dumps(json_dict) + "\n"


if __name__ == "__main__":
    sample = {"bbox": [0.0, 0.0, 0.0, 0.0], "nested": {"list": list(range(40))}}
    assert json.loads(dumps(sample)) == sample
    assert dumps(sample["bbox"]) == "[0.0, 0.0, 0.0, 0.0]"
    assert "\n" in dumps(sample)
    print("ok")
