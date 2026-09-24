# Zowser

Zowser separates the gallery logic in the [OME-NGFF 2024 challenge](https://github.com/ome/ome2024-ngff-challenge) into a standalone application.

It is similar in spirit and purpose to other open-source OME-Zarr galleries, like:

- [Zallery](https://github.com/openssbd/zallery)
- [Zarrcade](https://github.com/JaneliaSciComp/zarrcade)

and to some extent, with the "sharing" part of

- [BioFileFinder](https://bff.allencell.org/)

Each of them has slightly different user experiences, use cases, tech stacks and UI.

And they all collaborate with each other.

## General design goals

- (D0) Allow deployment of small, custom sets of images for sharing

- (D1) Work with any set of public OME-Zarr Image available on S3-like storage. Coverage of data in versions 0.4 and 0.5 (and later depending on capacity)

- (D2) Use only GitHub infrastructure

- (D3) Deploy new instances changing only a single configuration file

- (D4) Fast load and browsing

- (D5) Stretch goal of supporting machine-readable documentation of the data (e.g. via RO-Crate)

## Implementation

- Build upon [OME-NGFF 2024 challenge](https://github.com/ome/ome2024-ngff-challenge), Svelte, deploy on GH Pages (D1, D2)

- Add a config file `config.yaml` that describes metadata for the instance and basic metadata for the files (D0, D2, D3)

- A "hydration" step for caching metadata (zarr.json, ro-crate-metadata.json) and thumbnails (D4, D5)

## Supports:

- OME-Zarr v0.5 (https://ngff.openmicroscopy.org/specifications/0.5/)
- The RO-Crate convention of the OME 2024 NGFF challenge (https://ome.github.io/ome2024-ngff-challenge/)
- The Zarr convention for thumbnails (v1) (https://github.com/clbarnes/zarr-convention-thumbnails)

## Code

This is a Svelte.js app for loading CSV file(s) that list NGFF samples and
displaying a summary.

Development: cd into this directory, then...

```
$ npm install
$ npm run dev
```
