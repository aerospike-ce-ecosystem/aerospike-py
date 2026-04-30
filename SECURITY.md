# Security Policy

## Supported Versions

Security fixes are issued for the **latest minor release** and the **previous
minor release** (`N` and `N-1`).

| Version | Supported          |
| ------- | ------------------ |
| 0.7.x   | :white_check_mark: |
| 0.6.x   | :white_check_mark: |
| < 0.6   | :x:                |

When a new minor (e.g. `0.8.0`) is published, `0.6.x` falls out of support and
users are expected to upgrade to a still-supported line.

## Reporting a Vulnerability

If you discover a security vulnerability in `aerospike-py`, please report it
**privately** — do **not** open a public GitHub issue.

Preferred channel:

- **Private GitHub Security Advisory** —
  https://github.com/aerospike-ce-ecosystem/aerospike-py/security/advisories/new

Backup channel:

- Email **KimSoungRyoul@gmail.com** with:
  - Description of the vulnerability
  - Steps to reproduce
  - Potential impact
  - Suggested fix (if any)

You should receive an acknowledgment within 48 hours. We will work with you
privately to confirm the issue, prepare a fix, and coordinate disclosure
before any public announcement.

## Scope

This policy covers the `aerospike-py` Python package and its Rust native
extension (`rust/`). It does **not** cover:

- The upstream
  [Aerospike Rust Client](https://github.com/aerospike/aerospike-client-rust)
- The
  [Aerospike Server](https://github.com/aerospike/aerospike-server)

For vulnerabilities in those projects, report directly upstream.

## RUSTSEC Advisory Ignore List

`cargo audit` is run on every CI build (`.github/workflows/ci.yaml` —
`security` job). When an advisory cannot be remediated by upgrading a
dependency (e.g. it is structural to the upstream crate, or the unsound
trigger is unreachable through `aerospike-py`'s public API), the advisory
ID is added to an explicit ignore list with the rationale documented
below.

### `RUSTSEC-2026-0097` — `rand` unsound case

- **Advisory**: an application-defined custom logger that itself calls
  `rand::rng()` while the `rand` crate is reseeding can observe an
  inconsistent RNG state.
- **Where `rand` is used in `aerospike-py`**: a single call site, in the
  exponential-backoff jitter path:
  - `rust/src/client_ops.rs:290` — `rand::rng().random_range(0..=max_backoff)`
    inside `compute_backoff_ms()`, used purely to add jitter to the
    Full-Jitter retry delay between transient transport errors
    (`Timeout`, `DeviceOverload`, `KeyBusy`, `ServerMemError`,
    `PartitionUnavailable`).
- **Why the unsound trigger cannot be reached**: the unsoundness requires
  a custom logger that calls `rand::rng()` during reseeding.
  `aerospike-py`'s log bridge (`rust/src/logging.rs`) forwards records
  to Python via PyO3 and never touches `rand`. There is no public API
  that lets a user inject a logger which calls `rand::rng()` from inside
  the `rand` reseed path.
- **Crypto context**: the jittered backoff is **not** a security primitive.
  It is **not** used for nonce generation, key derivation, session IDs,
  password hashing, or any cryptographic purpose. A predictable backoff
  value would have no security impact — the worst case is slightly less
  desirable retry timing, which `total_timeout` already bounds.

For this reason the advisory is ignored in CI; see
`.github/workflows/ci.yaml` (`security` job, `ignore: RUSTSEC-2026-0097`).

If you believe this analysis is wrong, please file a security advisory
through the channels above so we can re-evaluate.

## Security Best Practices

When using `aerospike-py`:

- Keep the package up to date with the latest patch release.
- Use authentication when connecting to Aerospike clusters in production.
- Never log or expose client configuration containing passwords; redact
  the `policies.user` / `policies.password` fields before emitting logs.
- Use TLS for connections to remote Aerospike clusters.
- Pin dependency versions in production; review changes before upgrading.
- Run `cargo audit` and `pip-audit` (or equivalent) as part of your own
  CI pipeline if you vendor `aerospike-py`.
