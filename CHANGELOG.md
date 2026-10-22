# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and the project uses [Semantic Versioning](https://semver.org/).

## 1.0.1

### Changed
- The HACS validation now runs with all checks, including the one for the icon. The
  integration itself is unchanged; this release exists so the version listed in HACS has
  passed the full validation.

## 1.0.0

First release.

### Added
- Sidebar panel for admins (English and German): pick the old and the new device, adjust
  the proposed entity pairs, check the preview, swap, and undo recent swaps.
- The new entities take over the entity IDs, names, icons, areas, labels, aliases and
  options of the old ones, so automations, dashboards, templates and history keep working.
- Device references (device triggers, conditions and actions, device targets) are rewritten
  in automations, scripts, scenes and dashboards stored by Home Assistant. YAML files such
  as packages and YAML dashboards are listed for manual editing instead.
- Meter sums (energy, gas, water) continue without a jump: the step from the old meter's
  reading to the new one's is subtracted once the recorder has compiled that period, also
  when the old device is already unavailable.
- Old entity IDs that no longer match their name can get a tidier ID, but only when nothing
  refers to them.
- A notification after each swap lists what is left to do; undo dismisses it.
- Undo from a backup kept in Home Assistant's storage, keeping edits made after the swap.
