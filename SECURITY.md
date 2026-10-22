# Security policy

## Reporting a vulnerability

Please do not open a public issue for security problems. Report them privately through
GitHub instead: on the repository page open **Security → Report a vulnerability**. You will
get an answer within a few days, and a fix is released as soon as possible.

If that option is not shown, contact the maintainer [@Schnuecks](https://github.com/Schnuecks)
through GitHub and ask for a private channel, without describing the problem publicly.

Helpful details: the Nine Lives and Home Assistant versions, which integrations the old and
the new device belong to, and the steps to reproduce.

## What Nine Lives can change

Nine Lives runs inside Home Assistant and only admins can use it. It changes the entity and
device registries, `automations.yaml`, `scripts.yaml`, `scenes.yaml`, dashboards stored by
Home Assistant and the recorder's long-term statistics (sum corrections). It never edits
other YAML files and does not talk to anything outside Home Assistant.
