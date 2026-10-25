# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and the project uses [Semantic Versioning](https://semver.org/).

## Unreleased

### Added
- Swaps from a device that is already removed from Home Assistant, for example after
  deleting it in the manufacturer's app: its entities are taken over from the deleted
  entries Home Assistant keeps, found by the time they were removed together with the
  device. Their last name and value come from the history. Such swaps cannot be undone.

### Changed
- Pairing also looks at the end of the entity ID (`…_temperature`, `…_energy`).

## 1.1.1

### Changed
- Undo is only offered while the old device still exists. After it was removed from its
  integration, the swap is shown as final ("old device removed").

## 1.1.0

### Added
- Telling old and new apart in the device lists: when each device was added ("new, today
  18:46"), whether it is unavailable and which integration it belongs to. The list for the
  new device shows the most recent first, and a hint offers to swap the two if the old one
  was added after the new one.
- An **Identify** button for devices that support it, to make them blink or beep.
- The current value of every entity in the pairing step.
- Completed swaps stay listed, also after an undo, and a click shows what each one did:
  entity IDs taken over, references rewritten, places flagged or left for manual editing,
  and meter corrections with their status.

### Changed
- Services such as Sun or Backup no longer appear in the device lists.
- "Recent swaps" is now called "Completed swaps".

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
