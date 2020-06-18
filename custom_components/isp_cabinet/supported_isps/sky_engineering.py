from datetime import datetime
from typing import Dict, List, Tuple, Any

import aiohttp
from lxml import html

from custom_components.isp_cabinet.errors import InvalidServerResponseError
from custom_components.isp_cabinet.supported_isps.base import _ISPHTTPConnector, register_isp_connector, \
    _ISPSingleContractConnector, _ISPGenericContract, Payment, Invoice, _ISPGenericTariff, _ISPService

ContractDataType = Dict[str, Any]
TariffDataType = Dict[str, Any]


@register_isp_connector
class SkyEngineeringConnector(_ISPSingleContractConnector, _ISPHTTPConnector):
    isp_identifiers = ['sky_engineering', 'sky_en']
    isp_title = "Sky Engineering"

    BASE_URL = 'http://lk.sky-en.ru'
    BASE_LK_URL = BASE_URL + '/cabinet'

    async def _login(self, session: aiohttp.ClientSession):
        login_url = self.BASE_LK_URL + '/welcome-2'
        async with session.get(login_url) as request:
            if request.status != 200:
                raise InvalidServerResponseError(self)

            html_content = await request.text()

            parsed_object = html.fromstring(html_content, base_url=login_url)

            try:
                login_form = parsed_object.find_class('ca-login-panel')[0].find('form')

                tokens = {
                    k: login_form.find('input[@name="%s"]' % k).get('value')
                    for k in ['module_token_unique', 'module_token']
                }

                username_key = login_form.get_element_by_id('login-field').get('name')
                password_key = login_form.get_element_by_id('pass-field').get('name')

            except (IndexError, KeyError):
                raise InvalidServerResponseError(self)

        async with session.post(login_url, data={
            **tokens,
            username_key: self._username,
            password_key: self._password,
        }) as request:
            if request.status != 200:
                raise InvalidServerResponseError(self)

    @staticmethod
    def _format_float(float_string: str) -> float:
        return float(float_string.strip().replace(' ', '').replace(',', '.'))

    async def _get_contract_tariff_data(self) -> Tuple[str, 'ContractDataType', 'TariffDataType']:
        async with aiohttp.ClientSession(cookie_jar=self._cookies) as session:
            lk_welcome_url = self.BASE_LK_URL + '/welcome-2/'
            async with session.get(lk_welcome_url) as request:
                if request.status != 200:
                    raise InvalidServerResponseError(self)

                html_content = await request.text()

            parsed_object = html.fromstring(html_content, base_url=lk_welcome_url)

            try:
                contract_data = dict()

                contract_info_root = parsed_object.find_class('contract-info')[0]
                contract_info_parts_roots = contract_info_root.find_class('user-data')

                contract_code = contract_info_parts_roots[1].find('p').text.strip()

                contract_data['client'] = contract_info_parts_roots[0].find('p').text.strip()

                current_balance_parts = contract_info_parts_roots[2].findall('p')
                contract_data['current_balance'] = self._format_float(
                    current_balance_parts[1].text
                )
                contract_data['payment_until'] = datetime.strptime(
                    current_balance_parts[2].find('small').text.strip().split(' ')[-1],
                    '%d.%m.%Y'
                ).date()
                contract_data['payment_suggested'] = self._format_float(
                    contract_info_parts_roots[3].findall('p')[1].text
                )

                tariff_data = dict()

                tariff_current_root = parsed_object.find_class('tarif-current')[0]
                tariff_name_parts = list(map(str.strip, list(tariff_current_root)[0].text.split(':')))
                tariff_name_speed = tariff_name_parts[0]
                tariff_data['name'] = tariff_name_speed
                tariff_data['speed'] = int(tariff_name_speed.split(' ')[1])

                monthly_cost_parts = tariff_name_parts[1].split(' ')
                tariff_data['monthly_cost'] = float(monthly_cost_parts[0])
                tariff_data['currency'] = monthly_cost_parts[-1].lower()

            except (IndexError, KeyError):
                raise InvalidServerResponseError(self)

            return contract_code, contract_data, tariff_data


class SkyEngineeringContract(_ISPGenericContract):
    @property
    def invoices(self) -> List[Invoice]:
        return []

    @property
    def services(self) -> List['SkyEngineeringService']:
        return []

    @property
    def payments(self) -> List[Payment]:
        return []


SkyEngineeringConnector.contract_class = SkyEngineeringContract


class SkyEngineeringTariff(_ISPGenericTariff):
    pass


class SkyEngineeringService(_ISPService):
    pass


SkyEngineeringConnector.tariff_class = SkyEngineeringTariff
