# Changelog

All notable changes to this project are documented in this file. Earlier releases: the git history.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.6] - 2026-10-28

### Security

- `X-Real-IP` / `X-Forwarded-For` were taken from any private, loopback or link-local peer, so a neighbour on the same docker network or LAN could name its own address and get a fresh rate-limit bucket per request. They now count only from `PLATON_TRUSTED_PROXIES`: addresses, CIDRs, host names (looked up again every minute) and `gateway` (the container's default route, i.e. the host's nginx for a published port); the default is loopback only. Reported by Vulnetix (GCVE-110-VULN-PYPI-2026-000636). The compose file names the frontend's nginx (`platon-frontend`).
- Keyless HTTP now requires explicit `PLATON_LOCAL_RELAY=1` trust, even for a same-user loopback socket. A multiprocess proxy or tunnel cannot be reliably distinguished from a local client by process name or listening sockets; the old heuristic missed workers whose listener belonged to a parent. The default therefore refuses both. With explicit trust, the caller socket must still belong to the server user; without the socket table (macOS/Windows), the additional `PLATON_LOCAL_UNVERIFIED=1` opt-in is required. A configured token and production authentication always take precedence. Addresses, Host, Origin and forwarding-header restrictions still apply. Reported by Vulnetix (GCVE-110-VULN-PYPI-2026-000643).
