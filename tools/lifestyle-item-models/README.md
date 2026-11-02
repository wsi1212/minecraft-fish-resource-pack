This bundle restores only the assets referenced by the current lifestyle dex.
The canonical JVM census contains 162 entries: 78 dishes, 14 crop seed/harvest
variants, 13 traps, and 57 tools. Seven retired crop-bundle entries remain
excluded; existing legacy bundle handling is preserved. The actual offline creators returned
161 previews: 137 have item_model (135 distinct references) and 24 use the
separate vanilla/legacy path. The only unavailable preview is ce:barkan:scarecrow,
whose CraftEngine runtime is absent from the offline test. Its exact unavailable
record stays pinned; a source/asset closure cannot prove live CE item creation.

79 missing item_model definitions were recovered from the existing local
CraftEngine generated/resource_pack_unprotected.zip. The selected dependency
closure is 240 original files (53,960 bytes): 79 definitions, 80 models, 80
textures and one animated drill texture .mcmeta. Every definition property,
selected/unselected drill branch, display transform, pixel and animation byte
is retained. No art is created or redrawn. The full unused food library and
unreferenced legacy aliases are not imported.

manifest.json pins the original pack, selected CE YAMLs, normalized model
bindings, canonical census, original payload hashes, native PNG sizes/RGBA
hashes, and relevant Java authority sources. The inputs directory is a small
self-contained original-byte bundle; no CraftEngine installation, network or
PyYAML is required to build/check it. Supplementary official project notices
are retained with source URLs and commit pins. The local selected sources did
not contain bundled food license notices; project notices do not falsely
attribute locally customized icons to an exact upstream revision.

Run `python3 tools/build-lifestyle-item-models.py` to copy missing owned assets;
it refuses to overwrite different existing assets. `--check` is read-only.
`--zip <pack.zip>` verifies delivered JSON/.mcmeta bytes and decoded PNG pixels
(size + RGBA, allowing lossless PNG compression). `--census <fresh-json>`
compares fresh canonical IDs/materials/item_models. An adjacent blockship-plugin
checkout is checked for source drift when present; `--java-root` requires an
explicit checkout. The actual runtime recipe file recorded by the JVM census
is checked when available. RP-only CI always checks the pinned inputs, output
chain and all canonical explicit item_model dependencies, but cannot claim
fresh Java coverage without current sources/a fresh JVM census.

The pack builder can call `runpy.run_path(...)["validate"](root, zip_path=None)`
before and after writing the ZIP. The eight small corruption fixtures are run
with `python3 tools/test-lifestyle-item-models.py`; they cover missing required
assets, one altered pixel, animation changes, new canonical entry drift and
omitted/faked offline CE preview state.

This verifies local files/JSON/pixels, not live Minecraft client rendering.
