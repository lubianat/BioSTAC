import { writable, get } from "svelte/store";
import { organismStore, imagingModalityStore } from "./ontologyStore";


class NgffTable {
  constructor(sortBy = "index", sortAscending = true) {
    this.store = writable([]);
    this.selectedRow = writable(null);

    this.sortColumn = sortBy;
    this.sortAscending = sortAscending;

  }

  addRows(rows) {
    // Each row is a dict {"url": "http...zarr"}
    rows = rows.map((row, index) => {
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
      // add index for sorting
      row.index = Math.random() * (1 + index);
      return row;
    });

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
