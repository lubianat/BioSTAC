Adapted from https://github.com/portolan-sdi/portolan-spec/blob/main/specs/portolan/core.md

Originally under the Apache 2.0 license, terms still apply. See https://github.com/portolan-sdi/portolan-spec/blob/main/LICENSE


# BioPortolan Experimental Specification — Core

## Introduction

The goal of Portolan is to make it easier and cheaper for data providers to publish
their data, and to make that data more accessible to both humans and agents.

BioPortolan borrows the general ideas for bio-imaging and OME-Zarr.

The center of Portolan is the [SpatioTemporal Asset Catalog](https://stacspec.org/)
specification - every Portolan implementation is a STAC catalog, and can be used
with any STAC tooling. But where STAC can be used with any data format and can
be implemented as an API or files on cloud storage, Portolan requires well-formed
cloud-native formats, stored as files on browser-accessible online services. All
Portolan implementaions are [static catalogs](https://github.com/radiantearth/stac-spec/blob/master/best-practices.md#static-catalogs)
- there is no 'Portolan API' like the STAC API, as many of the key benefits of Portolan,
like scalability and lower cost, are achieved by the full embrace of cloud-native geospatial.

Portolan further requires that all catalogs follow the best practices to guide
AI agents to make use of them. Today that means adding an agents.md file to every
catalog and collection and building up a set of
['skills'](https://github.com/portolan-sdi/portolan-skills) that guide agents to
make use of the cloud-native formats. In the future this will likely evolve as
the general best practices for agents continue to advance.

The specification aims to standardize the minimum requirements for a 'great' catalog,
and to provide guidance to go beyond that. But really the hope is that everyone
goes well beyond the minimum and tries to make each catalog better than before. The
aspiration of the authors of the specification is to build a real community of
collaborators who are all working together to build great data catalogs and share
tools and best practices so all can benefit.

## Core Structure

A BioPortolan catalog is a directory of STAC metadata and cloud-native geospatial
data. It MUST be a valid STAC catalog following STAC 1.1.0, with a root
`catalog.json` always required, even for a single collection.

A catalog is a tree of catalogs, collections, items, and assets: catalogs and
collections are internal nodes, items are leaves, and assets (data files) MUST sit
at the collection or item level. Catalogs organize only and MAY nest into
sub-catalogs; collections MUST be one level deep, containing only items or assets,
never nested collections. Every catalog and sub-catalog MUST contain a
`catalog.json`, an `AGENTS.md`, and a `README.md`; every collection MUST contain a
`collection.json`, an `AGENTS.md`, and a `README.md`.

A catalog has two entry points: `catalog.json` for machines (required at the root)
and `README.md` for humans. It is fully navigable; every catalog, collection, and
item links to the rest, so any object is reachable from any other (see
[Links](#links)).

```
project/
├── catalog.json
├── AGENTS.md
├── README.md
└── {collection_id}/
    ├── collection.json
    ├── AGENTS.md
    ├── README.md
    └── {item_id}/
        └── data.parquet
```

## Catalogs

The canonical entrypoint is a STAC `catalog.json` in the catalog root, which MUST
be valid. Catalogs MAY use nested sub-catalogs for organization but MUST NOT use
nested collections.

## Collections

Each collection lives in a subdirectory named with its collection ID. For a nested
collection the ID is a POSIX path (e.g. `environment/air-quality`) and the
directory sits under one or more intermediate catalog directories (see [Nested
Catalogs, Flat Collections](#nested-catalogs-flat-collections)). A collection
directory MUST contain a `collection.json` and holds one subdirectory per item.
Collection IDs SHOULD contain only lowercase letters, numbers, hyphens, and
underscores, start with a letter, and be unique within the catalog.

## Nested Catalogs, Flat Collections

BioPortolan organizes hierarchy with nested catalogs, not nested collections:
intermediate levels are catalogs (`catalog.json`) and collections are always
leaves.


> Note: In Portolan, a collection MUST NOT contain a child collection. This keeps collections
flat for STAC API compatibility while still allowing thematic organization above
them. A nested collection's ID is its POSIX path from the catalog root (e.g.
`environment/air-quality`); `portolan add` writes a `catalog.json` at each
intermediate level and links parent to child down to the leaf `collection.json`.
> This is yet to be evaluated for BioPortolan


In directory terms, the root holds the root `catalog.json`, a level above a
collection holds an intermediate (thematic) `catalog.json`, a data directory holds
the leaf `collection.json`, and a subdirectory within a collection may hold a
`catalog.json` that organizes many items. Deep nesting is allowed, with every
level above the leaf a catalog; a catalog may also appear below a collection to
organize its items (for example, a raster collection grouping items by year). A
catalog or collection with twenty or more children SHOULD organize them into
subcatalogs, thematic or otherwise, so users can browse the data.

```
environment/
├── catalog.json              ← intermediate catalog
├── air-quality/
│   ├── collection.json       ← leaf collection (data)
│   └── pm25.parquet
└── water-quality/
    ├── collection.json       ← leaf collection (data)
    └── turbidity.parquet
```


## Items

Most collections represent their data as one or more STAC items, each with its own
metadata and assets. Portolan adds nothing to the STAC 1.1 Item beyond core.

## Assets

Every asset MUST include an `href`, the URI to the data, with relative or absolute
both allowed for now. Where an asset `href` is absolute, it MUST use `https`
rather than `s3`, since browsers cannot fetch `s3` URLs directly. An asset SHOULD
also provide `s3` or other cloud-native URLs through the
[alternate](https://github.com/stac-extensions/alternate-assets) extension, so
tools that prefer direct bucket access can use them.

> Portolan additionally
requires a `type`, meaning the media type, and at least one role on every asset.
STAC leaves both optional, but a validator and a browser cannot do their jobs
without them, so Portolan makes them mandatory. The `title` and `description`
fields are optional but recommended.
> Still being evaluated for BioPortolan


Roles describe what each asset is for. BioPortolan uses the standard STAC role names
wherever they fit and requires at least one per asset: `data` for the primary
OME-Zarr dataset, `thumbnail` for the preview image; `metadata` for sidecar metadata

BioPortolan uses existing  STAC extensions rather than restating their fields: `file` for
`file:values`, `table` for schema and columns, `raster` and `vector` for band and
layer detail, `license` for per-asset license, and `scientific` for citation or
DOI.

Assets SHOULD carry `file:size` and `file:checksum` from the [file
extension](https://github.com/stac-extensions/file). Both are cheap to compute for
bytes the publisher uploads, and they let a client budget a download and verify
what it received. Neither is required, because a catalog that describes data it
does not host cannot always produce them, and a fabricated value is worse than an
absent one.

A `file:checksum` MUST use multihash encoding, not a raw sha256 string. Any
`file:size` and `file:checksum` an asset carries MUST match the bytes its `href`
resolves to. A stale value is a conformance failure, so a publisher that cannot
keep one current should omit it.

## Links

Every catalog, collection, and item MUST include the structural links that make
the tree navigable: a catalog or collection MUST include `root` and `parent` links
(except the root catalog, which has no parent) and a `child` or `item` link for
every object it contains; an item MUST include `root`, `parent`, and `collection`
links. Every structural link MUST carry a `type` of `application/json` (or
`application/geo+json` for links to items).


> In BioPortolan, aggregator catalogs (new roots) are also allowed, and not linked back from its `child` catalogs.


Structural links can be relative or absolute; Portolan takes no position.
Relative links keep a catalog portable, so the same tree of files validates
locally, in staging, and in production without a rewrite. Absolute links name
their location outright, which some hosts and clients handle more reliably.
The [STAC best practices on the use of
links](https://github.com/radiantearth/stac-best-practices/blob/main/best-practices-catalog-and-collection.md#use-of-links)
walk through the choice, and [Git-Backed
Catalogs](../best-practices/git-backed-catalogs.md#links-and-the-publish-step)
covers how it plays out for a catalog maintained in git.

A catalog served over the internet from a single fixed URL SHOULD carry an
absolute `self` link on its root catalog. STAC requires that a `self` link be
[absolute](https://github.com/radiantearth/stac-spec/blob/master/commons/links.md#relation-types).


## Human-Readable Titles

STAC Browser and other clients render `child` and `item` link titles directly;
without them a client must fetch every child just to display its name. Portolan
therefore requires human-readable titles throughout: every `catalog.json` and
`collection.json` MUST have a non-empty `title` and `description`; titles MUST be
human-readable, so a raw slug (`snake_case`) or a technical namespace prefix
(`ns:LayerName`) is not acceptable; and every `child` and `item` link MUST include
a `title`. A validator checks readability heuristically; it MUST flag a title that
fails the check, and because heuristics misfire, the finding is a warning, not an
error.


## Data Storage

Cloud-native formats depend on clients fetching only the bytes they need, so
Portolan catalogs assume data is hosted in cloud object storage reachable over
HTTP range requests (S3-compatible or otherwise).

The requirements in this section apply to servers hosting the catalog's own
cloud-native assets: the copies of the data that the publisher has uploaded and
controls. They do not apply to upstream sources hosted by third parties.

A server hosting the catalog's cloud-native assets MUST support range
requests: honor the `Range` header, return `206 Partial Content`, and advertise
`Accept-Ranges: bytes`; HEAD requests MUST return an accurate `Content-Length`.
The server MUST support HTTP/1.1 or greater; HTTP/2 or /3 is RECOMMENDED. Endpoints
that compress or transform responses in ways that break range semantics are not
conformant.

To let browser clients read data directly, a server hosting the catalog's
cloud-native assets MUST also enable CORS on all
metadata and asset files: `Access-Control-Allow-Origin: *` (or an equivalent
read-permitting policy), allowed methods including `GET` and `HEAD`, allowed
request headers including `Range`, `If-Match`, `If-Modified-Since`,
`If-None-Match`, and `If-Unmodified-Since` (via
`Access-Control-Allow-Headers`), and exposed response headers including
`Content-Type`, `Content-Length`, `Content-Range`, `Accept-Ranges`, and `ETag`
(via `Access-Control-Expose-Headers`).

The conditional-request headers let a browser revalidate a cached range instead
of refetching it, which keeps tile and range readers cheap on repeat views.
Provider-specific headers such as `x-amz-*` and `x-goog-*` fall outside this
requirement, since reading a public catalog takes no signed request. Portolan
leaves cloud-specific configuration to separate guidance.

Catalogs also reference bytes that the publisher does not host, including
upstream sources that a mirror complements and original files carried over from
an upstream source. Because those servers are operated by third parties and are
outside the publisher's control, the requirements above do not apply to them.

A validator MUST probe the servers hosting the catalog's own cloud-native assets
and MUST NOT require upstream servers to satisfy these requirements. An upstream
server that does not support range requests or provide the required CORS headers
limits the capabilities available to clients using that upstream copy, but does
not make the catalog non-conformant.

## Providers

Every collection MUST identify the parties responsible for its data through the
STAC `providers` field. The list MUST include at least one provider with the
`producer` role, the organization that originally captured or created the data,
and exactly one provider with the `host` role, listed as the last element.

Providers with the `processor` and `licensor` roles SHOULD be
included where they apply. A single organization MAY hold multiple roles; a
self-published dataset will typically list one provider as both producer and host.
Catalogs MAY also declare providers, but the collection-level declaration is
authoritative.

## License

Every collection MUST declare a `license` in its `collection.json`. The value MUST
be an SPDX license identifier (e.g. `CC-BY-4.0`, `Apache-2.0`), or the STAC value
`other` when no SPDX identifier fits, in which case the collection MUST include a
license link (`rel: license`) pointing to the license text. The deprecated STAC
1.1 value `proprietary` MUST NOT be used. A collection whose data is genuinely
restricted still declares its license explicitly rather than omitting it.

> Being evaluated if every collection MUST declare for BioPortolan

## AGENTS.md

Every catalog and collection MUST include an `AGENTS.md` in Markdown, referenced in
the STAC `links` array (`rel: "agents"`, `type: text/markdown`). It is a link, not
an asset — it describes the data, it is not the data. Beyond existing and being
linked, its content is open-ended; the aim is to help agents use the data well,
covering access patterns (base URLs, S3 paths, code examples), useful aggregations
and queries, data-quality notes, related collections, and schema or
coordinate-system conventions — anything non-obvious. See
[best-practices](../best-practices/) for guidance on what makes a good `AGENTS.md`.

## README.md

Every catalog and collection MUST have a `README.md` in Markdown, referenced in the
STAC `links` array (`rel: "describedby"`, `type: text/markdown`). Like `AGENTS.md` it
is a link, not an asset — it describes the data, it is not the data. `describedby` is
the IANA-registered relation for a resource carrying a description of the linked
resource, and is already common in STAC. The `README.md` MUST contain at minimum a
title, description, license, and data provenance.

## Catalog Logo

A registry lists many catalogs side by side. A logo makes each one recognizable
before the reader has read a word. The root catalog MAY publish a logo as a link
with `rel: "icon"`.

STAC defines no `logo` relation. `icon` is registered with IANA, and stac-js and
STAC Browser already read it. STAC uses `preview` for a preview of the data
itself, so `preview` is not the relation for a logo. A collection publishes its
data preview as a `thumbnail` asset, described under
[Visualization](#visualization).

An `icon` link MUST declare a `type`, and that type MUST be one of `image/apng`,
`image/avif`, `image/gif`, `image/jpeg`, `image/png`, `image/svg+xml`, or
`image/webp`. A client drops an icon whose media type it does not recognize, so an
undeclared type renders nowhere. stac-js rejects `image/svg+xml`. STAC Browser
therefore does not show an SVG logo.

An `icon` link SHOULD carry a `title`. A page that renders the logo needs the
title as the image's accessible label. Only the publisher knows what the logo
shows.

The `href` SHOULD be relative, which keeps the catalog portable for the reason
[Links](#links) gives. A catalog stores the image under `_assets/` beside the root
`catalog.json`. An absolute `href` to an external host stays valid, and a publisher
who serves one logo across several catalogs will use one.

## Metadata

Collections SHOULD include machine-readable metadata (e.g. [Apache
Ossie](https://ossie.apache.org/)) when they have many coded or categorical
variables or complex classification schemes, and SHOULD include column
descriptions, which will likely become a requirement as tooling matures.
