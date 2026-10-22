"""The notification shown after a swap, in German or English."""

from __future__ import annotations

from homeassistant.components import persistent_notification
from homeassistant.core import HomeAssistant, callback

from .const import DOMAIN

_TEXTS = {
    "en": {
        "title": "Nine Lives: {old} replaced",
        "body": "**{new}** now continues **{old}**: {count} entities took over"
        " their IDs, settings and history.",
        "manual": "Please adjust by hand: {places}.",
        "next": "Once everything works, remove the old device from its integration."
        " The swap can be undone in [Nine Lives](/nine-lives).",
    },
    "de": {
        "title": "Nine Lives: {old} ersetzt",
        "body": "**{new}** führt **{old}** fort: {count} Entitäten haben IDs,"
        " Einstellungen und Verlauf übernommen.",
        "manual": "Bitte von Hand anpassen: {places}.",
        "next": "Wenn alles läuft, entferne das alte Gerät aus seiner Integration."
        " Rückgängig machen geht in [Nine Lives](/nine-lives).",
    },
}


def _notification_id(backup_id: str) -> str:
    return f"{DOMAIN}_{backup_id}"


@callback
def async_swapped(
    hass: HomeAssistant,
    backup_id: str,
    old: str,
    new: str,
    count: int,
    manual: list[str],
) -> None:
    """Tell the user what happened and what is left to do."""
    texts = _TEXTS["de" if hass.config.language.startswith("de") else "en"]
    parts = [texts["body"].format(old=old, new=new, count=count)]
    if manual:
        parts.append(texts["manual"].format(places=", ".join(manual)))
    parts.append(texts["next"])
    persistent_notification.async_create(
        hass,
        "\n\n".join(parts),
        texts["title"].format(old=old),
        _notification_id(backup_id),
    )


@callback
def async_undone(hass: HomeAssistant, backup_id: str) -> None:
    persistent_notification.async_dismiss(hass, _notification_id(backup_id))
