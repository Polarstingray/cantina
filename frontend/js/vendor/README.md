# Vendored third-party code

These files are committed (not fetched at runtime) so the app stays self-hosted
and works under the strict `default-src 'self'` CSP — no CDN dependency in the
browser. They provide camera barcode scanning on browsers without the native
`BarcodeDetector` API (iOS Safari, Firefox, desktop). See Chapter 5 of the build
guide and `app.js` `getBarcodeDetectorCtor()` for how they're loaded.

| File | Source package | Version | License |
|------|----------------|---------|---------|
| `ponyfill.js` | [`barcode-detector`](https://www.npmjs.com/package/barcode-detector) `dist/es/ponyfill.js` | 3.2.0 | MIT |
| `zxing-exported.js` | `barcode-detector` `dist/es/zxing-exported.js` (bundles the zxing-wasm JS glue) | 3.2.0 | MIT |
| `zxing_reader.wasm` | [`zxing-wasm`](https://www.npmjs.com/package/zxing-wasm) `dist/reader/zxing_reader.wasm` | 3.1.0 | MIT |

`ponyfill.js` imports only its sibling `./zxing-exported.js`; that file is
self-contained JavaScript with no further imports. The WASM binary is fetched at
runtime via the glue's `locateFile` hook — which we override in `app.js` to point
at this directory (the upstream default would fetch it from jsdelivr).

## Updating
Re-download the three files at a pinned version and update the table:

    BD=barcode-detector@<ver>; ZW=zxing-wasm@<ver>
    curl -sS -o ponyfill.js       https://cdn.jsdelivr.net/npm/$BD/dist/es/ponyfill.js
    curl -sS -o zxing-exported.js https://cdn.jsdelivr.net/npm/$BD/dist/es/zxing-exported.js
    curl -sS -o zxing_reader.wasm https://cdn.jsdelivr.net/npm/$ZW/dist/reader/zxing_reader.wasm

If `barcode-detector` bumps its `zxing-wasm` dependency, match `$ZW` to the version
in its `package.json` so the JS glue and the `.wasm` agree.

## SHA-256 (as committed)
```
2b72435d8174bac202ccc3d0854529eb9ad06b7212af6c8ff47034f1b3dec564  ponyfill.js
0d38f4e88033e9d75826df06372dbf66745d7781e046362565fe427c1e9c7967  zxing-exported.js
b03d35cd265123b9f75a0c476c204714663a1e85ba908acc3f50eae7824dfcf6  zxing_reader.wasm
```
