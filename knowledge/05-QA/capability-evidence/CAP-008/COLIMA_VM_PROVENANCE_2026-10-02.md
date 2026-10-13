---
doc: CAP-008_COLIMA_VM_PROVENANCE
status: LOCAL PROVENANCE EVIDENCE — pending independent CAP-008 re-review
observed_at: 2026-10-01 22:56 UTC (2026-10-02 01:56 Asia/Amman)
---

# Colima VM image and Docker Engine provenance

This supplements the Sonnet stage-5 drills and the first independent Opus review. It is not approval. All host/VM checks below were read-only; no VM was started or changed for this record.

| Component | Observed identity and source |
|---|---|
| Colima host application | Homebrew 0.10.3, arm64, using macOS Virtualization.Framework (`vz`); [official v0.10.3 image manifest](https://raw.githubusercontent.com/abiosoft/colima/v0.10.3/embedded/images/images.txt). |
| Lima | Homebrew 2.2.0; [tagged licence](https://raw.githubusercontent.com/lima-vm/lima/v2.2.0/LICENSE) is Apache-2.0. |
| VM image | [colima-core v0.10.4 `ubuntu-24.04-minimal-cloudimg-arm64-docker.raw.gz`](https://github.com/abiosoft/colima-core/releases/download/v0.10.4/ubuntu-24.04-minimal-cloudimg-arm64-docker.raw.gz); [colima-core's v0.10.4 licence](https://raw.githubusercontent.com/abiosoft/colima-core/v0.10.4/LICENSE) is MIT. The official Colima 0.10.3 manifest pins SHA-512 `32242674b046b5057e60c4aba334b51e3665f05412cda89ed081cc2de153ae5c41f6b105b5c442cbe48d78e2cc21e9ba1950e406b6fb4fc2fd1dd2259240abbd`. |
| Local image verification | `shasum -a 512 ~/Library/Caches/colima/caches/b0992ab88f5a3c0c436bbb3065c01466f20dc1dd0eb0a60299d410176f21a1c3` returned that exact SHA-512; cache file is 332354401 bytes. The first-round Opus reviewer independently matched the cached hash to the upstream `.sha512sum` as well. |
| Guest OS | `colima ssh -- cat /etc/os-release` returned Ubuntu 24.04.4 LTS (Noble); `colima ssh -- uname -r` returned `6.8.0-117-generic`. [Canonical's Ubuntu policy](https://ubuntu.com/legal/intellectual-property-policy) permits free internal use; this is an internal, synthetic-data-only local VM, not redistribution. |
| In-VM Engine package | `colima ssh -- apt-cache policy docker-ce` returned installed/candidate `5:29.5.2-1~ubuntu.24.04~noble`; the version table currently points to `/var/lib/dpkg/status` (the installed package, not a retained apt index). `colima ssh -- dpkg-query -W` identifies the maintainer as `Docker <support@docker.com>` and the same version for `docker-ce-cli`. `/etc/apt/sources.list.d/docker.list` names `https://download.docker.com/linux/ubuntu noble stable` with Docker's apt keyring. These corroborate the vendor package origin; they do not by themselves constitute a binary signature audit. |
| Engine and host CLI licence | The exact [`moby/moby` `docker-v29.5.2` licence](https://raw.githubusercontent.com/moby/moby/docker-v29.5.2/LICENSE) and [`docker/cli` v29.6.0 licence](https://raw.githubusercontent.com/docker/cli/v29.6.0/LICENSE) are Apache-2.0. The proposal's default-branch caveat was due to trying `v29.5.2` instead of Moby's `docker-v29.5.2` tag; it is superseded by this per-tag check. [Docker's Engine documentation](https://docs.docker.com/engine/) distinguishes its Apache-2.0 Engine from the paid-subscription condition for Engine *obtained via Docker Desktop* in larger enterprises; Docker Desktop is not this binding. |

The VM has a writable home-directory mount under Colima's current default configuration. This is a wider filesystem reach than the Postgres fixture needs and must be disclosed in CAP-008's effective scope; the harness's own database traffic remains loopback-bound. This record does not assert that Colima's whole supply chain is perfectly immutable or that all VM packages have been individually hashed. The capability is host/version-specific and stage-9 requalification is required if any bound component changes.
