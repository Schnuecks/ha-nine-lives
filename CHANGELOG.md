# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and the project uses [Semantic Versioning](https://semver.org/).

## 1.2.2

### Fixed
- The list of removed devices no longer fails when an integration stores device
  identifiers with more than two parts.
- A removed device whose own entities were already taken over no longer offers the
  entities of another device removed at the same time.
- When several deleted entries share an entity ID (an earlier device used it too), the
  removed device's own entry is used; the preview no longer refuses it.
- Names and last values of removed entities are also found when the device was
  unavailable for a while before it was removed.
- No more warnings in the log about deprecated device registry access (the device list
  and the list of removed devices). If a future Home Assistant no longer keeps removed
  devices, that option is hidden instead of failing.

### Changed
- The list of removed devices leaves out removals older than 30 days and software such
  as AI assistants, update entries and repositories managed by HACS.
- Pairing ignores numbers Home Assistant appended to an ID (`…_identify_2`).

## 1.2.1

### Fixed
- Devices removed at the same time (for example several lights removed in the
  manufacturer's app at once) no longer share their entities: an entity belongs to a
  removed device when its unique ID contains the device's identifier, as with Matter
  devices. The time of removal is only used when there is no such hint.

## 1.2.0

### Added
- Swaps from a device that is already removed from Home Assistant, for example after
  deleting it in the manufacturer's app: its entities are taken over from the deleted
  entries Home Assistant keeps, found by the time they were removed together with the
  device. Their last name and value come from the history. Such swaps cannot be undone.
- A tidier ID can now be chosen even when the old ID is in use: automations, scripts and
  scenes (including templates), stored dashboards, helpers such as groups, utility meters
  or template sensors, and the energy dashboard are adjusted along, and turned back on
  undo. The option says where. IDs used in YAML files or the settings of other
  integrations still stay.

### Changed
- Pairing also looks at the end of the entity ID (`…_temperature`, `…_energy`).
- The preview heading "Device references rewritten" is now "References rewritten", as it
  also lists entity IDs that change.

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
