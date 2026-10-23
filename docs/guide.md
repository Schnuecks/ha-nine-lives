# Nine Lives guide

**English** · [Deutsch](anleitung.md)

This guide explains a swap step by step and what exactly happens behind it. For a short
overview and the installation see the [README](../README.md).

- [Before the swap](#before-the-swap)
- [The swap step by step](#the-swap-step-by-step)
- [What exactly happens](#what-exactly-happens)
- [After the swap](#after-the-swap)
- [Undo](#undo)
- [Typical cases](#typical-cases)
- [Troubleshooting](#troubleshooting)

## Before the swap

1. **Pair the new device** with its integration as usual. Its name and entity IDs do not
   matter, they are replaced in the swap.
2. **Leave the old device in Home Assistant.** Nine Lives can only pick devices that Home
   Assistant still knows. Do not delete it from its integration before the swap.
3. **Unplugged or broken is fine.** The old device may already be unavailable. For meters
   Nine Lives then uses the last reading the statistics recorded.
4. **A backup does not hurt.** Nine Lives keeps its own backup for undo, but a Home Assistant
   backup before the first swap gives extra safety.

## The swap step by step

Open **Nine Lives** in the sidebar. Only admins see it.

### 1. Pick the devices

Choose the old and the new device. To tell them apart even when both have the same name and
model, each entry shows:

- manufacturer, model, area and integration,
- when the device was added: **new, today 18:46** for devices added within a week,
  otherwise **since** the date. The list for the new device shows the most recent first,
- **unavailable** if the device does not respond, for example because it is unplugged.

If the device chosen as old was added after the one chosen as new, Nine Lives asks whether
they are mixed up and offers to swap them. Devices with an identify function (many plugs and
lights) get an **Identify** button: it makes the device blink or beep, so you can check in
the room which one it is. The filter field narrows the list down.

### 2. Check the pairs

Nine Lives proposes which new entity replaces which old one:

- Only entities of the same type are paired (a sensor with a sensor, a switch with a switch).
- If both have a device class, it must be the same: a temperature never replaces a humidity.
- If only one of them has a device class, the unit must match. That keeps a signal strength
  sensor from being paired with an illuminance sensor.
- Among the remaining candidates, matching unit, state class and name decide.

Below each entity you see its current value, for example `21.3 °C` or `4.2 W`, which helps
to check that the right sensors are paired. You can change every pair or choose **skip**. Skipped old entities stay with the old device.
New entities without a partner are listed below the table; they keep their own IDs.

**New ID:** some old IDs no longer fit, for example after a device was renamed
(`button.plug_anker_identify` on a plug that now powers a printer). If nothing in Home
Assistant refers to such an ID, Nine Lives offers the ID Home Assistant would give the entity
today. The option is ticked; untick it to keep the old ID. It is only offered when the old ID
appears nowhere: not in automations, scripts, scenes, dashboards, YAML files, the energy
dashboard or the settings of other integrations.

### 3. Read the preview

The preview lists everything before it happens:

- **Entity IDs taken over:** which new entity ends up under which ID.
- **Devices:** what happens to the area, labels and the old device.
- **Device references rewritten:** every place in automations, scripts, scenes and dashboards
  where the old device's ID is replaced.
- **Please check afterwards:** device triggers, conditions and actions that may not exist on
  the new device (see [Remotes and buttons](#remotes-and-buttons)).
- **Please adjust by hand:** places Nine Lives does not edit, such as YAML packages.

### 4. Swap

After **Swap devices** and the confirmation, Nine Lives first writes a backup and then makes
the changes. It takes a second or two.

## What exactly happens

### Entities

For each pair:

1. The new entity gets what you set on the old one: name, icon, area, labels, voice
   assistant aliases and options such as display precision, unit or voice assistant
   exposure.
2. The old entity is removed from the entity registry. Home Assistant keeps it as a deleted
   entity, which matters for [undo](#undo).
3. The new entity takes over the old entity ID.

Because the ID stays the same, everything that uses entity IDs keeps working without any
change: automations, scripts, dashboards, templates, groups, helpers, the energy dashboard.

### History and statistics

The old history stays under the entity ID, and the new entity simply continues it. In the
history graph you see a short gap at the moment of the swap. What the new device recorded
under its own ID before the swap stays there and is removed by Home Assistant's usual purge.

### Meters

Energy, gas and water meters keep a running sum in the long-term statistics. When the new
meter takes over, Home Assistant would count the step from the old reading to the new one:

- A new meter far below the old one (less than 90 %) counts as a reset, so its whole reading
  is added as consumption. A used smart plug at 50 kWh would add 50 kWh to your energy
  dashboard.
- A meter above the old one adds the difference.

Nine Lives works out this step with the same rules and subtracts it again. Home Assistant
compiles statistics every five minutes; the correction is applied right after that period
has been compiled, so usually within five to six minutes. Until then the panel lists it under
**Meter corrections in progress**. Pending corrections survive a restart. Different units
(Wh and kWh) are converted.

### Devices

- The new device gets the area of the old one if it has none, and the old device's labels in
  addition to its own.
- The old device is disabled, so its remaining entities do not clutter Home Assistant.

### Automations, scripts, scenes and dashboards

Most references use entity IDs and need no change. Device triggers, conditions and actions,
and device targets such as "turn on the device", use the device ID and the entity's internal
registry ID instead. Nine Lives replaces those:

- in `automations.yaml`, `scripts.yaml` and `scenes.yaml`, the files the Home Assistant editor
  writes, which are reloaded afterwards,
- in dashboards that Home Assistant stores (everything edited in the dashboard editor).

It does not edit:

- YAML packages, files included with `!include` and other YAML files: they are listed under
  **Please adjust by hand**,
- YAML dashboards: listed as well,
- `automations.yaml`, `scripts.yaml` or `scenes.yaml` if they contain `!secret`, `!include` or
  similar tags. Rewriting them would put the secret values into the file in plain text.

### Notification

After the swap Home Assistant shows a notification: which device continues which, what is
left to adjust by hand and the hint to remove the old device. It appears in the system
language, German or English.

## After the swap

1. **Check** a dashboard or two and the automations that use the device. The places listed
   under "Please check afterwards" are worth a look.
2. **Adjust by hand** what the preview listed, if anything.
3. **Wait for meter corrections** if there are any; the panel shows when they are due.
4. **Remove the old device** from its integration (for example in the Zigbee hub or under
   Settings → Devices). Before that, the swap can be undone completely.

## Undo

Every swap is listed under **Completed swaps**, also after it was undone. Click an entry to
see what it did: which entity IDs were taken over (and tidier IDs), which references were
rewritten, what was flagged or left for manual editing, and the meter corrections with their
status. Undone swaps show when they were undone.

Swaps that can still be undone have an **Undo** button. Undo:

- gives the new entities their own IDs and settings back,
- re-enables the old device and restores its entities. Home Assistant brings them back with
  their old registry ID and settings when their integration creates them again,
- turns the device references in automations, scripts, scenes and dashboards back. If you
  edited one of them after the swap, your edits are kept and only the device references are
  turned back,
- corrects the meter sums again, now for the step from the new meter back to the old one,
- dismisses the notification.

Undo needs the old device. If you already removed it from its integration, undo still gives
the new device its own IDs back, but the old device does not return.

## Typical cases

### From Zigbee to Thread/Matter

The classic: a sensor on a Zigbee hub or ZHA is replaced by one on Thread. Pair the new
sensor, swap, check, then remove the old one from the Zigbee network.

### A broken device replaced by the same model

Works the same way. The broken device may be unavailable; it only has to be in Home
Assistant.

### Smart plug with an energy meter

Leave it to Nine Lives: switch, power, current and energy are paired, and the energy
dashboard continues without a jump. If the new plug measures more (for example voltage),
those entities simply stay with their own IDs.

### Remotes and buttons

Automations triggered by a button press usually use a device trigger like
"remote_button_short_press" of the old integration. Nine Lives points the trigger to the new
device but flags it under **Please check afterwards**, because the new device may name its
buttons differently. Open the automation and choose the button again if needed.

## Troubleshooting

### The panel does not appear

Reload the browser page after adding the integration. The panel is only shown to admins.

### An automation no longer works

Look at the notification and the preview's lists: device triggers of the old integration and
YAML files need a manual touch. If the automation is in a YAML file Nine Lives did not edit,
replace the old device ID there.

### Debug log

Turn on debug logging for Nine Lives, repeat the swap or undo and attach the log to a
[bug report](https://github.com/Schnuecks/ha-nine-lives/issues/new/choose):

```yaml
logger:
  logs:
    custom_components.nine_lives: debug
```

### Where is the backup?

In Home Assistant's storage under `.storage/nine_lives.backups`. It holds the old and new
entities' settings, the original texts of the changed files and dashboards and the pending
meter corrections. A swap's entry stays until you undo that swap. Please do not edit the
file by hand.
