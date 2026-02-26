# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 0.0.1.x | :white_check_mark: |

## Reporting a Vulnerability

If you discover a security vulnerability in aerospike-py, please report it responsibly:

1. **Do NOT open a public GitHub issue** for security vulnerabilities.
2. Email **KimSoungRyoul@gmail.com** with:
   - Description of the vulnerability
   - Steps to reproduce
   - Potential impact
   - Suggested fix (if any)

You should receive a response within 48 hours. We will work with you to understand the issue and coordinate a fix before any public disclosure.

## Scope

This security policy covers the `aerospike-py` Python package and its Rust native extension. It does not cover the upstream [Aerospike Rust Client](https://github.com/aerospike/aerospike-client-rust) or [Aerospike Server](https://github.com/aerospike/aerospike-server).

## Security Best Practices

When using aerospike-py:

- Keep the package updated to the latest version
- Use authentication when connecting to Aerospike clusters in production
- Do not log or expose client configuration containing passwords
- Use TLS for connections to remote Aerospike clusters
