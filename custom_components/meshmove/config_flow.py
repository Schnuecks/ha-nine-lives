"""Config flow for MeshMove: one instance, nothing to configure."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult

from .const import DOMAIN


class MeshMoveConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the setup of MeshMove."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm the setup."""
        if user_input is not None:
            return self.async_create_entry(title="MeshMove", data={})
        return self.async_show_form(step_id="user")
