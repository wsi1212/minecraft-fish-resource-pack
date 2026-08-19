# Mobile production deploy

The phone does not need an SSH key. The production server pulls an explicitly
promoted GitHub Release every five minutes.

1. Open the repository Actions page on GitHub.
2. Run **Mobile production resource pack**.
3. Set `promote` to `true`.
4. Set `apply_now` to `true` for an immediate restart, or `false` to apply at
   the next scheduled maintenance restart.

Only Releases containing the `MOBILE_RP_PROMOTE` marker are accepted by prod.
`APPLY_NOW` is added only when the checkbox is enabled. Ordinary Releases and
the `latest` development asset are ignored.

The workflow builds the same deterministic production pack as the Mac deploy
path, validates the pack, and only then publishes the Release. The server
downloads the public asset, verifies its ZIP and SHA1, updates
`server.properties`, and restarts only for `APPLY_NOW`.
