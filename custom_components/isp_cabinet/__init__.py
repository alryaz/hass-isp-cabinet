from typing import Any, Optional, Dict

import pkg_resources
import logging
import voluptuous as vol

from homeassistant import config_entries
import homeassistant.helpers.config_validation as cv
from homeassistant.const import CONF_USERNAME, CONF_PASSWORD, CONF_SCAN_INTERVAL, CONF_DEVICE_ID, CONF_DEVICE
from homeassistant.core import callback
from homeassistant.helpers.typing import HomeAssistantType, ConfigType

from .const import DOMAIN, CONF_ISP, DATA_CONFIG

_LOGGER = logging.getLogger(__name__)


def _check_isp_config(value: Dict[str, Any]) -> Dict[str, Any]:
    from .supported_isps import ISP_CONNECTORS

    isp_identifier = value[CONF_ISP]

    for connector in ISP_CONNECTORS:
        if isp_identifier in connector.isp_identifiers:
            if CONF_SCAN_INTERVAL not in value:
                value[CONF_SCAN_INTERVAL] = connector.scan_interval

            return value

    raise vol.Invalid('ISP "%s" is not supported' % isp_identifier, [CONF_ISP])


ISP_SCHEMA = vol.All(vol.Schema({
    vol.Required(CONF_ISP): cv.string,
    vol.Required(CONF_USERNAME): cv.string,
    vol.Required(CONF_PASSWORD): cv.string,
    vol.Optional(CONF_SCAN_INTERVAL): vol.All(cv.time_period, cv.positive_timedelta)
}), _check_isp_config)

CONFIG_SCHEMA = vol.Schema({
    DOMAIN: vol.All(cv.ensure_list, [ISP_SCHEMA])
}, extra=vol.ALLOW_EXTRA)


@callback
def _find_existing_entry(hass: HomeAssistantType, isp_identifier: str, username: str) \
        -> Optional[config_entries.ConfigEntry]:
    existing_entries = hass.config_entries.async_entries(DOMAIN)

    for config_entry in existing_entries:
        if config_entry.data[CONF_ISP] == isp_identifier \
                and config_entry.data[CONF_USERNAME] == username:
            return config_entry


async def async_setup(hass: HomeAssistantType, yaml_config: ConfigType) -> bool:
    if DOMAIN not in yaml_config:
        return True

    domain_config = hass.data.setdefault(DATA_CONFIG, dict())

    for isp_conf in yaml_config[DOMAIN]:
        isp_identifier = isp_conf[CONF_ISP]
        username = isp_conf[CONF_USERNAME]
        key = (isp_identifier, username)

        if key in domain_config:
            _LOGGER.warning('ISP "%s" entry for user "%s" has duplicate configuration in YAML. Please, remove'
                            'duplicate configuration from your YAML config and restart HA!' % key)
            continue

        existing_entry = _find_existing_entry(hass, *key)
        if existing_entry:
            if existing_entry.source == config_entries.SOURCE_IMPORT:
                domain_config[key] = isp_conf
                _LOGGER.debug('ISP "%s" entry for user "%s" already added as import entry, not adding' % key)

            else:
                _LOGGER.warning('ISP "%s" entry for user "%s" is overridden by one configured from Home Assistant'
                                'user interface.' % key)
            continue

        _LOGGER.debug('Adding ISP "%s" entry for user "%s"' % key)

        domain_config[key] = isp_conf

        hass.async_create_task(
            hass.config_entries.flow.async_init(
                DOMAIN,
                context={"source": config_entries.SOURCE_IMPORT},
                data={CONF_ISP: isp_identifier, CONF_USERNAME: username},
            )
        )

    return True


async def async_setup_entry(hass: HomeAssistantType, config_entry: config_entries.ConfigEntry) -> bool:
    isp_conf = config_entry.data
    isp_identifier = isp_conf[CONF_ISP]
    username = isp_conf[CONF_USERNAME]
    key = (isp_identifier, username)

    if config_entry.source == config_entries.SOURCE_IMPORT:
        isp_conf = hass.data.get(DATA_CONFIG, {}).get(key)
        if not isp_conf:
            _LOGGER.info('Removing ISP "%s" entry for user "%s" after removal from YAML configuration'
                         % key)
            hass.async_create_task(
                hass.config_entries.async_remove(config_entry.entry_id)
            )
            return False

    hass.async_create_task(
        hass.config_entries.async_forward_entry_setup(
            config_entry, "sensor"
        )
    )

    return True


async def async_unload_entry(hass: HomeAssistantType, config_entry: config_entries.ConfigEntry) -> bool:
    isp_identifier = config_entry.data[CONF_ISP]
    username = config_entry.data[CONF_USERNAME]
    key = (isp_identifier, username)

    _LOGGER.debug('Unloading entry "%s" for ISP "%s" with user "%s"'
                  % (config_entry.entry_id, isp_identifier, username))

    updater = hass.data[DOMAIN].pop(key, None)
    if updater:
        _LOGGER.debug('Cancelling updater for entry "%s"' % config_entry.entry_id)
        updater()

    return await hass.config_entries.async_forward_entry_unload(
        config_entry, "sensor"
    )
