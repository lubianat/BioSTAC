import { writable, get } from "svelte/store";
import { getJson } from "./util";

// Term ids are written in several ways: NCBITaxon:9606, obo:FBbi_00000246, NCBI:txid9606.
// OLS4 wants the ontology and the OBO form of the id, doubly encoded, as its own docs spell it.
function olsUrl(termId) {
  const id = termId.replace(/^obo:/, "").replace(/^NCBI:txid/, "NCBITaxon:");
  const [, ontology, local] = id.match(/^([A-Za-z]+)[:_](\w+)$/) || [];
  if (!ontology) return null;
  const iri = `http://purl.obolibrary.org/obo/${ontology}_${local}`;
  return `https://www.ebi.ac.uk/ols4/api/ontologies/${ontology.toLowerCase()}/terms/${encodeURIComponent(
    encodeURIComponent(iri),
  )}`;
}

class OntologyMetadataField {
  constructor() {
    this.store = writable({});
  }

  /** The catalog carries labels; this is only for a term that arrives without one. */
  async lookupOntologyTerm(termId) {
    const url = olsUrl(termId);
    if (!url) return termId;
    try {
      const term = await getJson(url);
      return term.label || termId;
    } catch (error) {
      console.warn(`No OLS4 label for ${termId}`, error);
      return termId;
    }
  }

  addTerms(terms) {
    // {id, label} pairs: a label from the catalog is taken as given, and only a
    // term that arrives without one costs a request.
    let storeDict = get(this.store);

    const seen = new Set();
    terms.forEach(({ id, label }) => {
      if (!id || seen.has(id) || storeDict[id]) {
        return;
      }
      seen.add(id);
      if (label) {
        this.addEntry(id, label);
        return;
      }
      // placeholder to avoid making duplicate requests at once
      storeDict[id] = "Loading...";
      setTimeout(() => {
        this.lookupOntologyTerm(id).then((name) => this.addEntry(id, name));
      }, Math.random() * 5000);
    });
  }

  addEntry(termId, name) {
    this.store.update((lookup) => {
      lookup[termId] = name;
      return lookup;
    });
  }

  subscribe(run) {
    return this.store.subscribe(run);
  }
}

export const organismStore = new OntologyMetadataField();
export const imagingModalityStore = new OntologyMetadataField();