# Security Policy

## Reporting a vulnerability

Please **do not open a public issue** for security vulnerabilities.

Instead, use GitHub's private vulnerability reporting on this repository
(Security tab → "Report a vulnerability"). You'll get an acknowledgement
within a few days.

Please include:

- A description of the issue and its impact
- Steps to reproduce (a proof of concept helps a lot)
- The version/commit you tested against

## Scope notes for self-hosters

- opama is designed to be run on a trusted network or behind a reverse proxy
  that terminates TLS. Don't expose the raw API to the internet without HTTPS.
- Local-auth accounts may be passwordless for low-friction local use; the UI
  prompts you to set a password as soon as the instance is reachable from a
  non-loopback origin. Set one before exposing the instance.
- Set strong values for `POSTGRES_PASSWORD`, `LOCAL_AUTH_SECRET`, and
  `WEBSITE_EXPORT_KEY`, and keep `.env.local` out of version control (the
  repo's `.gitignore` already excludes it).

## Supported versions

Security fixes land on `main`. Until versioned releases begin, run the latest
`main`.
