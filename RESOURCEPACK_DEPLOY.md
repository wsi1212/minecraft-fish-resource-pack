# 리소스팩 배포

`develop` is the integration branch and `main` is production. The phone does
not need an SSH key: the production server pulls a validated GitHub Release.

## Normal flow

1. Push changes to `develop` while working.
2. GitHub Actions builds and validates `develop`; it does **not** publish a
   Release and does not touch prod.
3. Merge `develop` into `main`.
4. The `main` push automatically builds, validates, publishes a production
   Release with `MOBILE_RP_PROMOTE` and `APPLY_NOW`, and prod applies it within
   the five-minute pull interval.

The automatic `main` path warns connected players for 60 seconds before the
restart. A failed build or validation produces no Release and cannot reach
prod.

## Manual path

1. Open the repository Actions page on GitHub.
2. Run **Mobile production resource pack**.
3. Set `promote` to `true`.
4. Set `apply_now` to `true` for an immediate restart, or `false` to apply at
   the next scheduled maintenance restart.

Manual promotion is accepted only when the workflow is run against `main`.
Running it from `develop` can validate the branch but cannot publish to prod.

Only Releases containing the `MOBILE_RP_PROMOTE` marker are accepted by prod.
The automatic `main` path adds `APPLY_NOW`; the manual path adds it only when
the checkbox is enabled. Ordinary Releases and the `latest` development asset
are ignored.

The workflow builds the deterministic production pack, validates it, and only
then publishes the Release. The server downloads the public asset, verifies
its ZIP and SHA1, updates `server.properties`, and restarts only for
`APPLY_NOW`.
