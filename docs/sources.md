# RZ/V2L source register

The local documentation collection is indexed in [artifacts/rzv2l/README.md](../artifacts/rzv2l/README.md). It contains the SoC hardware manual Rev.1.50, SMARC module and carrier manuals Rev.2.00, datasheet, Linux startup guide, BSP driver manuals and security guides, plus secondary project notes.

[manifest.json](../artifacts/rzv2l/manifest.json) records original local paths, file hashes, sizes and PDF page counts. Searchable text extracts are under `artifacts/rzv2l/text/`; the original PDFs remain the citation authority.

Follow the specification's source hierarchy: hardware manual, board documentation, guest source, firmware source, then hardware observations. BSP driver manuals describe software interfaces; project notes are secondary context. Confirm document applicability to the physical board revision and chosen BSP before deriving contracts.

Pinned firmware sources studied so far: see `research/boot-chain-firmware.md` (TF-A `f59ed5a31`, U-Boot `4eebfbaa4e`, OP-TEE `82a5cd3b`, kernel 6.12.59-cip14).

This collection does not complete M0. Pinned DTS/driver and firmware sources, standalone board schematics, acceptance guest artifacts and measured board behaviour remain to be registered as they are collected. Device-map and boot-dependency conclusions have not yet been derived.
