"""Tests for setting up and unloading MeshMove."""

from homeassistant.components.frontend import DATA_PANELS
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.meshmove.const import DOMAIN


async def test_panel_is_registered_and_removed(
    hass: HomeAssistant, hass_client
) -> None:
    entry = MockConfigEntry(domain=DOMAIN)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)

    panel = hass.data[DATA_PANELS]["meshmove"]
    assert panel.require_admin
    module_url = panel.config["_panel_custom"]["module_url"]
    client = await hass_client()
    response = await client.get(module_url)
    assert response.status == 200
    assert "customElements.define" in await response.text()

    assert await hass.config_entries.async_unload(entry.entry_id)
    assert "meshmove" not in hass.data[DATA_PANELS]
    assert DOMAIN not in hass.data
