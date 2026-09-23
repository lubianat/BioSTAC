#!/usr/bin/env node
/**
 * Pre-cache thumbnails for NGFF .zarr images using ome-zarr.js directly (Node).
 * - Polyfills a minimal DOM canvas for ome-zarr.js
 * - Renders PNG data URLs, then converts to JPEG on save
 */

import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";
import { performance } from "perf_hooks";
import { createCanvas, Image, ImageData } from "canvas";
import * as omezarr from "ome-zarr.js";

// ────────────────────────────────────────────────────────────────
// Minimal DOM/canvas polyfill for ome-zarr.js (Node environment)
global.ImageData = ImageData;
global.document = {
    createElement: (name) => {
        if (name !== "canvas") {
            throw new Error(`Unsupported element requested: ${name}`);
        }
        // Return a node-canvas instance; width/height will be set later
        const cnv = createCanvas(1, 1);
        // node-canvas already provides getContext("2d"), toDataURL, etc.
        return cnv;
    },
};

// ────────────────────────────────────────────────────────────────
// Setup paths
const __dirname = path.dirname(fileURLToPath(import.meta.url));
const OUTPUT_DIR = path.join(__dirname, "../public/thumbs");
const CSV_FILE = path.join(__dirname, "../public/samples/zarrs_metadata.csv");

// Ensure output folder
fs.mkdirSync(OUTPUT_DIR, { recursive: true });

// ────────────────────────────────────────────────────────────────
// Load CSV
if (!fs.existsSync(CSV_FILE)) {
    console.error(`❌ CSV file not found at: ${CSV_FILE}`);
    process.exit(1);
}
const csvLines = fs.readFileSync(CSV_FILE, "utf8").trim().split("\n");
const header = csvLines.shift().split(",");
const urlIndex = header.indexOf("url");
if (urlIndex === -1) {
    console.error("❌ CSV missing 'url' column header");
    process.exit(1);
}

console.log(`📂 Loaded ${csvLines.length} entries from CSV`);
console.log(`📸 Output directory: ${OUTPUT_DIR}`);
console.log("─────────────────────────────────────────────");

// Counters
let total = 0;
let skipped = 0;
let errors = 0;
let saved = 0;

// Settings (match your app defaults)
const TARGET_SIZE = 120; // desired longest side
const AUTO_BOOST = true;
const MAX_SIZE = 512; // if smallest level > MAX_SIZE^2, ome-zarr throws

// ────────────────────────────────────────────────────────────────
// Helpers
function dataUrlToJPEGBuffer(dataUrl, { quality = 0.85 } = {}) {
    // dataUrl is PNG from ome-zarr.js; draw to canvas and encode JPEG
    const pngBuf = Buffer.from(dataUrl.split(",")[1], "base64");
    const img = new Image();
    img.src = pngBuf;

    const w = img.width;
    const h = img.height;
    const canvas = createCanvas(w, h);
    const ctx = canvas.getContext("2d");
    ctx.drawImage(img, 0, 0);

    // node-canvas: encode to JPEG
    return canvas.toBuffer("image/jpeg", { quality });
}

// ────────────────────────────────────────────────────────────────
// Main loop
for (const [i, line] of csvLines.entries()) {
    const cols = line.split(",");
    const zarrUrl = cols[urlIndex]?.trim();
    if (!zarrUrl || !zarrUrl.endsWith(".zarr")) continue;
    total++;

    const outFile = path.join(OUTPUT_DIR, `${path.basename(zarrUrl)}.jpg`);

    if (fs.existsSync(outFile)) {
        console.log(`🟡 [${i + 1}/${csvLines.length}] Skip (exists): ${path.basename(outFile)}`);
        skipped++;
        continue;
    }

    console.log(`🔹 [${i + 1}/${csvLines.length}] Processing: ${zarrUrl}`);
    const t0 = performance.now();

    try {
        // Direct call into ome-zarr.js; it will resolve multiscale/axes/etc.
        // Throws if the lowest-resolution plane is larger than MAX_SIZE^2.
        const dataUrl = await omezarr.renderThumbnail(zarrUrl, TARGET_SIZE, AUTO_BOOST, MAX_SIZE);

        const jpegBuf = dataUrlToJPEGBuffer(dataUrl, { quality: 0.85 });
        fs.writeFileSync(outFile, jpegBuf);

        // Grab w/h for logging by decoding once (cheap)
        const img = new Image();
        img.src = Buffer.from(dataUrl.split(",")[1], "base64");
        const dt = (performance.now() - t0).toFixed(0);
        console.log(`✅  Saved ${path.basename(outFile)} (${img.width}×${img.height}) in ${dt} ms`);
        saved++;
    } catch (err) {
        console.warn(`❌ [${i + 1}] Error: ${zarrUrl}`);
        console.warn(`   ${err.message}`);
        errors++;
    }
}

console.log("\n─────────────────────────────────────────────");
console.log(`🏁 Done!`);
console.log(`   ✅ Saved: ${saved}`);
console.log(`   🟡 Skipped: ${skipped}`);
console.log(`   ❌ Errors: ${errors}`);
console.log(`   📊 Total attempted: ${total}`);
console.log("─────────────────────────────────────────────\n");
