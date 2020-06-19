"""ISP Sensor"""
import asyncio
import logging
from datetime import timedelta, datetime, date
from typing import Callable, Optional, Dict, Any, TYPE_CHECKING, Iterable, Tuple, Union

from homeassistant import config_entries
from homeassistant.components.sensor import PLATFORM_SCHEMA
from homeassistant.const import CONF_USERNAME, CONF_SCAN_INTERVAL, CONF_PASSWORD, ATTR_ATTRIBUTION, STATE_UNAVAILABLE
from homeassistant.exceptions import PlatformNotReady, ConfigEntryNotReady
from homeassistant.helpers import ConfigType
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.typing import HomeAssistantType
from homeassistant.util import dt

from custom_components.isp_cabinet import DATA_CONFIG, CONF_ISP, DOMAIN
from custom_components.isp_cabinet.errors import CredentialsInvalidError, AuthenticationError, \
    ServerTimeoutError, ISPCabinetException

if TYPE_CHECKING:
    # noinspection PyProtectedMember
    from .supported_isps.base import _ISPConnector, _ISPContract

_LOGGER = logging.getLogger(__name__)


def _create_updater(connector_instance: '_ISPConnector',
                    async_add_entities: Callable[[Iterable[Entity], bool], Any],
                    debug_key: Tuple[str, str]):
    created_entities: Dict[str, ISPContractEntity] = dict()

    async def update_contracts(now: datetime):
        isp_identifier, username = debug_key

        _LOGGER.debug('Running updater for ISP "%s" and user "%s" at %s'
                      % (isp_identifier, username, now))

        # Perform authorization routine
        try:
            if connector_instance.is_logged_in:
                await connector_instance.logout()

            await connector_instance.login()
            contracts = await connector_instance.get_contracts()

        except ISPCabinetException:
            _LOGGER.exception('Exception occured:')
            for entity in created_entities.values():
                if entity.available:
                    entity.state = STATE_UNAVAILABLE
                    entity.async_schedule_update_ha_state()
            return False


        # Create new entities
        new_entities: Dict[str, ISPContractEntity] = {
            contract_code: ISPContractEntity(contracts[contract_code])
            for contract_code in contracts.keys() - created_entities.keys()
        }

        # Remove obsolete entities and update new entities
        tasks = []
        for contract_code in created_entities.keys() - contracts.keys():
            del created_entities[contract_code]
            tasks.append(created_entities[contract_code].async_remove())

        for contract_entity in new_entities.values():
            tasks.append(contract_entity.async_update())

        if tasks:
            await asyncio.wait(tasks)

        # Update existing entities
        for contract_code, contract_entity in created_entities.items():
            contract_entity.async_schedule_update_ha_state(force_refresh=True)

        if new_entities:
            async_add_entities(new_entities.values(), True)
            created_entities.update(new_entities)

        new_entity_count = len(new_entities)

        _LOGGER.debug('ISP "%s" for user "%s" completed update procedure at %s. '
                      'Removed %d contract entities. '
                      'Added %d contract entities.'
                      % (isp_identifier, username, dt.utcnow(), len(tasks)-new_entity_count, new_entity_count))

    return update_contracts


# noinspection PyUnusedLocal
async def async_setup_platform(hass: HomeAssistantType, config: ConfigType,
                               async_add_entities: Callable[[Iterable[Entity], bool], Any],
                               discovery_info: Optional[Dict[str, Any]] = None) -> Optional[bool]:
    from .supported_isps import ISP_CONNECTORS

    isp_identifier = config[CONF_ISP]
    username = config[CONF_USERNAME]
    key = (isp_identifier, username)

    instance = None
    for connector in ISP_CONNECTORS:
        if isp_identifier in connector.isp_identifiers:
            instance = connector(username=username, password=config[CONF_PASSWORD])
            break

    if instance is None:
        _LOGGER.error('ISP Identifier "%s" not found in supported connectors' % isp_identifier)
        return False

    if DOMAIN in hass.data and key in hass.data[DOMAIN]:
        _LOGGER.error('ISP "%s" for user "%s" already configured. Please, check your configuration.'
                      % key)
        return False

    updater = _create_updater(instance, async_add_entities, key)

    try:
        await updater(dt.utcnow())

    except ServerTimeoutError:
        raise PlatformNotReady('ISP "%s" for user "%s" timed out while authenticating' % key)

    except CredentialsInvalidError:
        _LOGGER.error('Credentials invalid on ISP identifier "%s" for user "%s". Please, update your'
                      'credentials.' % key)
        return False

    except AuthenticationError:
        _LOGGER.error('Authentication error for user with ISP identifier "%s" and user "%s"' % key)
        return False

    domain_updaters = hass.data.setdefault(DOMAIN, dict())

    update_interval = config.get(CONF_SCAN_INTERVAL)
    if update_interval is None:
        update_interval = instance.scan_interval

    domain_updaters[key] = async_track_time_interval(hass, updater, update_interval)

    _LOGGER.debug('Running updater for ISP "%s" and user "%s" every %d seconds'
                  % (key[0], key[1], update_interval.seconds + update_interval.days * 86400))

    return True


async def async_setup_entry(hass: HomeAssistantType, config_entry: config_entries.ConfigEntry,
                            async_add_entities: Callable[[Iterable[Entity], bool], Any]) -> bool:
    isp_conf = config_entry.data

    if config_entry.source == config_entries.SOURCE_IMPORT:
        isp_conf = hass.data[DATA_CONFIG][(isp_conf[CONF_ISP], isp_conf[CONF_USERNAME])]

    else:
        isp_conf: Dict[str, Any] = {**isp_conf}

        if CONF_SCAN_INTERVAL in isp_conf:
            isp_conf[CONF_SCAN_INTERVAL] = timedelta(seconds=isp_conf[CONF_SCAN_INTERVAL])

    try:
        if await async_setup_platform(hass, isp_conf, async_add_entities) is False:
            return False

    except PlatformNotReady as e:
        raise ConfigEntryNotReady(str(e)) from None

    return True


class ISPContractEntity(Entity):
    def __init__(self, contract: '_ISPContract') -> None:
        self._contract = contract
        self._icon = 'mdi:web'
        self._state = None
        self._attributes = None
        self._unit_of_measurement = None

    @property
    def should_poll(self) -> bool:
        return False

    @property
    def contract_code(self) -> str:
        return self._contract.code

    @property
    def name(self) -> Optional[str]:
        return self._contract.connector.isp_title + ' ' + self.contract_code

    @staticmethod
    def _set_attr(input_dict: Dict[str, Any], key: str, value: Any, false_empty: bool = True,
                  converter: Optional[Callable[[Any], str]] = None):
        if value is not None:
            if value is False:
                value = None if false_empty else "false"
            elif value is True:
                value = "true"
            elif converter is not None:
                value = converter(value)

            input_dict[key] = value

    async def async_update(self) -> None:
        attributes = {
            'code': self._contract.code,
        }

        for attr, false_empty, converter in [
            ('address', True, None),
            ('client', False, None),
            ('payment_required', False, None),
            ('payment_suggested', False, None),
            ('payment_until', True, date.isoformat)
        ]:
            self._set_attr(attributes, attr, getattr(self._contract, attr), false_empty, converter)

        bonuses = self._contract.bonuses
        if bonuses is not None:
            attributes['bonuses'] = bonuses

        tariff = self._contract.tariff
        if tariff:
            attributes.update({
                'tariff_name': tariff.name,
                'tariff_speed': tariff.speed,
                'tariff_speed_unit': tariff.speed_unit,
                'tariff_monthly_cost': tariff.monthly_cost,
            })

        attributes[ATTR_ATTRIBUTION] = 'Data provided by %s' % self._contract.connector.isp_title

        self._attributes = attributes
        self._state = self._contract.current_balance
        self._unit_of_measurement = self._contract.currency

    @property
    def unit_of_measurement(self) -> Optional[str]:
        return self._unit_of_measurement

    @property
    def icon(self) -> Optional[str]:
        return self._icon

    @property
    def device_state_attributes(self) -> Optional[Dict[str, Any]]:
        return self._attributes

    @property
    def state(self) -> Optional[float]:
        return self._state

    @state.setter
    def state(self, value: str) -> None:
        self._state = value

    @property
    def unique_id(self) -> Optional[str]:
        return self._contract.isp_identifier + '_' + self._contract.code
