import { writable, get } from "svelte/store";
import { organismStore, imagingModalityStore } from "./ontologyStore";
import { loadMultiscales } from "./util.js";
export { loadMultiscales };


class NgffTable {
  constructor(sortBy = "index", sortAscending = true) {
    this.store = writable([]);
    this.selectedRow = writable(null);

    this.sortColumn = sortBy;
    this.sortAscending = sortAscending;

    // [{source: "uni1",
    //  url: "http://...csv",
    //  image_count: 10,
    //  "child_csv": [{source: "uni2", url: "http://...csv"}]}
    // ]
    this.csvFiles = [];
  }

  addRows(rows) {
    // Each row is a dict {"url": "http...zarr"}
    rows = rows.map((row, index) => {
      if (row.written) {
        row.written = parseFloat(row.written);
      }
      if (row.shape) {
        let shape = row.shape.split(",").map((dim) => parseInt(dim));
        let dim_names;
        if (row.dimension_names) {
          // e.g "t,c,z,y,x"
          dim_names = row.dimension_names.split(",");
        } else if (shape.length == 5) {
          dim_names = ["t", "c", "z", "y", "x"];
        }
        if (dim_names && dim_names.length == shape.length) {
          dim_names.forEach((dim, idx) => (row["size_" + dim] = shape[idx]));
        }
        // count the number of dimensions with size > 1
        row.dim_count = shape.reduce(
          (prev, curr) => prev + (curr > 1 ? 1 : 0),
          0,
        );
      }
      if (row.chunks) {
        let chunks = row.chunks.split(",").map((dim) => parseInt(dim));
        row.chunk_pixels = chunks.reduce((prev, curr) => prev * curr, 1);
      }
      if (row.shards) {
        let shards = row.shards.split(",").map((dim) => parseInt(dim));
        row.shard_pixels = shards.reduce((prev, curr) => prev * curr, 1);
      }
      // add index for sorting
      row.index = Math.random() * (1 + index);
      return row;
    });

    console.log("Adding rows", rows);

    this.store.update((table) => {
      table.push(...rows);
      table.sort((a, b) => this.compareRows(a, b, true));
      return table;
    });

    let organismIds = rows.map((row) => row.organismId);
    organismStore.addTerms(organismIds);

    let fbbiIds = rows.map((row) => row.fbbiId);
    imagingModalityStore.addTerms(fbbiIds);
  }

  populateRow(zarrUrl, rowValues) {
    this.store.update((table) => {
      table = table.map((row) => {
        if (row.url === zarrUrl) {
          row = { ...row, ...rowValues };
        }
        return row;
      });
      return table;
    });
  }

  async loadNgffMetadata(zarrUrl) {
    const [multiscales, msUrl, plate] = await loadMultiscales(zarrUrl);
    let shape = [];
    let written = 0;
    let well_count = 0;
    let field_count = 0;
    let load_failed = false;
    let loaded = true;
    // TODO: include 'omero' attrs for rendering settings
    let image_attrs = { multiscales };
    let image_url = msUrl;
    if (plate) {
      well_count = plate.wells.length;
      field_count = plate.field_count || 1;
    }
    if (multiscales) {
      // only consider the first multiscale and load highest resolution dataset
      const dataset = multiscales[0]?.datasets[0];
      const path = dataset?.path;
      if (path) {
        const arrayData = await fetch(`${msUrl}/${path}/zarr.json`)
          .then((response) => response.json())
          .catch((error) => {
            console.log(
              `----> Failed to parse ${msUrl}/${path}/zarr.json`,
              error,
            );
          });
        shape = arrayData?.shape;
        // written = arrayData?.attributes?._ome2024_ngff_challenge_stats?.written;
      }
    } else {
      console.log("No multiscales found");
      load_failed = true;
      shape = [0];
    }
    // The data that is added to the Table
    // const total_written = written * (well_count ? well_count * field_count : 1);
    this.populateRow(zarrUrl, {
      image_attrs,
      image_url,
      shape,
      // written,
      well_count,
      field_count,
      // total_written,
      load_failed,
      loaded, // always true - just means we tried to load the data
    });
  }

  compareRows(a, b, isNumber = false) {
    let aVal = a[this.sortColumn];
    let bVal = b[this.sortColumn];

    // Handle number...
    if (isNumber) {
      if (aVal === undefined) {
        aVal = 0;
      }
      if (bVal === undefined) {
        bVal = 0;
      }
      if (aVal < bVal) {
        return this.sortAscending ? -1 : 1;
      } else if (aVal > bVal) {
        return this.sortAscending ? 1 : -1;
      }
      return 0;
    }

    if (aVal === undefined) {
      aVal = "";
    }
    if (bVal === undefined) {
      bVal = "";
    }

    let comp = 0;
    // TODO: handle specific column names, e.g. shape
    if (isNumber) {
      comp = aVal - bVal;
    } else {
      comp = aVal.localeCompare(bVal);
    }
    return this.sortAscending ? comp : -comp;
  }

  sortTable(colName, ascending = true) {
    console.log("sortTable", colName, ascending);
    this.sortColumn = colName;
    this.sortAscending = ascending;
    let isNumber = this.isColumnNumeric(colName);
    this.store.update((table) => {
      table.sort((a, b) => this.compareRows(a, b, isNumber));
      return table;
    });
  }

  isColumnNumeric(colName) {
    // return true if first non-empty value is a number
    let rows = get(this.store);
    for (let row of rows) {
      let val = row[colName];
      if (val !== undefined && val !== "") {
        return !isNaN(val);
      }
    }
  }

  emptyTable() {
    this.store.set([]);
  }

  subscribe(run) {
    return this.store.subscribe(run);
  }

  getRows() {
    return get(this.store);
  }

  getRow(index) {
    return get(this.store)[index];
  }

  subscribeSelectedRow(run) {
    return this.selectedRow.subscribe(run);
  }

  setSelectedRow(rowData) {
    this.selectedRow.set(rowData);
  }
}

export const ngffTable = new NgffTable();
