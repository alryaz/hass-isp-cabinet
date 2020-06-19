from typing import Optional, Dict, Union, Tuple

import logging

from homeassistant import config_entries
from homeassistant.const import CONF_USERNAME, CONF_PASSWORD

from .const import CONF_ISP, DOMAIN
from .errors import AuthenticationError, InvalidServerResponseError, ISPCabinetException

_LOGGER = logging.getLogger(__name__)


@config_entries.HANDLERS.register(DOMAIN)
class ISPCabinetFlowHandler(config_entries.ConfigFlow):
    """Handle a config flow for ISP Cabinet config entries."""

    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_CLOUD_POLL

    def __init__(self):
        """Instantiate config flow."""
        self._current_type = None
        self._current_config = None
        self._devices_info = None

        self._schema_user = None

    def _check_entry_exists(self, key: Optional[Tuple[str, str]] = None):
        current_entries = self._async_current_entries()

        if key is None:
            return bool(current_entries)

        isp_identifier, username = key

        for config_entry in current_entries:
            if config_entry.data[CONF_ISP] == isp_identifier and config_entry.data[CONF_USERNAME] == username:
                return True

        return False

    async def _show_user_form(self, errors: Optional[Dict[str, str]] = None,
                              placeholders: Optional[Dict[str, Union[str, int, float]]] = None):
        if self._schema_user is None:
            import voluptuous as vol
            from collections import OrderedDict

            from .supported_isps import ISP_CONNECTORS

            default_isp = None

            if not self._check_entry_exists():
                from aiohttp import ClientSession

                async with ClientSession() as session:
                    async with session.get('http://ip-api.com/json/') as request:
                        ip_api_data = await request.json()

                for connector in ISP_CONNECTORS:
                    if connector.ip_api_belongs(ip_api_data):
                        _LOGGER.debug('Detected current ISP automatically: %s' % connector.isp_title)
                        default_isp = connector.isp_identifiers[0]
                        break

            schema_user = OrderedDict()
            schema_user[vol.Required(CONF_ISP, default=default_isp)] = vol.In({
                connector.isp_identifiers[0]: connector.isp_title
                for connector in ISP_CONNECTORS
            })
            schema_user[vol.Required(CONF_USERNAME)] = str
            schema_user[vol.Required(CONF_PASSWORD)] = str
            self._schema_user = vol.Schema(schema_user)

        return self.async_show_form(step_id="user",
                                    data_schema=self._schema_user,
                                    errors=errors,
                                    description_placeholders=placeholders)

    # Initial step for user interaction
    async def async_step_user(self, user_input=None):
        """Handle a flow start."""
        if user_input is None:
            return await self._show_user_form()

        isp_identifier = user_input[CONF_ISP]
        username = user_input[CONF_USERNAME]
        key = (isp_identifier, username)

        if self._check_entry_exists(key):
            return self.async_abort("already_exists")

        from .supported_isps import ISP_CONNECTORS

        target_connector = None
        for connector in ISP_CONNECTORS:
            if isp_identifier in connector.isp_identifiers:
                target_connector = connector
                break

        if target_connector is None:
            return self.async_abort("isp_not_supported")

        try:
            api = target_connector(username=username, password=user_input[CONF_PASSWORD])
            await api.login()

        except AuthenticationError:  # @TODO: more specific exception handling
            return await self._show_user_form(errors={"base": "invalid_credentials"})

        except InvalidServerResponseError:
            return self.async_abort("invalid_server_response")

        except ISPCabinetException:
            return self.async_abort("unknown_error")

        return self.async_create_entry(title=target_connector.isp_title + ": " + username, data=user_input)

    async def async_step_import(self, user_input=None):
        if user_input is None:
            return self.async_abort("unknown_error")

        isp_identifier = user_input[CONF_ISP]
        username = user_input[CONF_USERNAME]

        if self._check_entry_exists((isp_identifier, username)):
            return self.async_abort("already_exists")

        isp_title = None
        from .supported_isps import ISP_CONNECTORS
        for connector in ISP_CONNECTORS:
            if isp_identifier in connector.isp_identifiers:
                isp_title = connector.isp_title

        if isp_title is None:
            return self.async_abort("isp_not_supported")

        return self.async_create_entry(
            title=isp_title + ": " + username,
            data={
                CONF_ISP: isp_identifier,
                CONF_USERNAME: username
            }
        )