import json
import re
from datetime import datetime
from typing import List, Optional, Dict, Tuple, Any

import aiohttp
from lxml import html

from .base import _ISPContract, requires_authentication, register_isp_connector, _ISPService, \
    _ISPHTTPConnector, _ISPSingleContractConnector, _ISPGenericContract, _ISPGenericTariff, Invoice, Payment
from ..errors import SessionInitializationError, AuthenticationError, InvalidServerResponseError

ContractDataType = Dict[str, Any]
TariffDataType = Dict[str, Any]


@register_isp_connector
class AlmatelConnector(_ISPSingleContractConnector, _ISPHTTPConnector):
    isp_identifiers = ["almatel", "2kom"]
    isp_title_ru = "Альмател"
    isp_title = "Almatel"

    BASE_URL = "https://almatel.ru"
    BASE_LK_URL = BASE_URL + "/lk"

    XHR_HEADERS = {
        'X-Requested-With': 'XMLHttpRequest',
        'Accept': 'application/json, text/javascript, */*; q=0.01',
        'Sec-Fetch-Dest': 'empty',
        'Sec-Fetch-Mode': 'cors',
        'Sec-Fetch-Site': 'same-origin',
        'Origin': BASE_URL,
        'Referer': BASE_LK_URL + '/login.php',
    }

    @property
    def auth_headers(self) -> Optional[Dict[str, str]]:
        return self.XHR_HEADERS

    async def _login(self, session: aiohttp.ClientSession) -> None:
        login_url = self.BASE_LK_URL + '/login.php'

        async with session.get(login_url) as request:
            if request.status != 200:
                raise SessionInitializationError(self)

        async with session.post(login_url, data={
            "login": self._username,
            "password": self._password,
        }) as request:
            if request.status != 200:
                raise AuthenticationError(self)

            try:
                response = await request.text()
                response_json = json.loads(response)

                if not response_json.get('ok'):
                    raise AuthenticationError(self, response_json.get('error'))

            except json.JSONDecodeError:
                raise InvalidServerResponseError(self) from None

    async def _get_contract_tariff_data(self) -> Tuple[str, 'ContractDataType', 'TariffDataType']:
        async with aiohttp.ClientSession(cookie_jar=self._cookies) as session:
            home_page_url = self.BASE_LK_URL + '/index.php'
            async with session.get(home_page_url) as request:
                if request.status != 200:
                    raise InvalidServerResponseError(self)

                html_content = await request.text()

                parsed_object = html.fromstring(html_content, base_url=home_page_url)

                try:
                    contract_data = dict()

                    question_block_value = 'question-block-value'

                    profile_root = parsed_object.get_element_by_id('lk--profile')

                    contract_code_address_root = profile_root.find_class('lk__profile--name_act')[0]
                    contract_code_text, contract_data['address'] = \
                        map(lambda x: x.replace('&nbsp;', ' ').strip(), contract_code_address_root.text.split('|'))
                    contract_code = re.findall(r'\d+', contract_code_text)[0]

                    current_balance_root = profile_root.find_class('lk__profile-balance')[0]
                    current_balance_value_root = current_balance_root.find_class(question_block_value)[0]
                    contract_data['current_balance'] = float(current_balance_value_root.text.strip())

                    payment_roots = profile_root.find_class('lk__profile-payment')

                    payment_required_root = payment_roots[0]
                    payment_required_value_root = payment_required_root.get_element_by_id('need-sum')
                    contract_data['payment_suggested'] = float(payment_required_value_root.text.strip())

                    bonuses_root = payment_roots[1]
                    bonuses_value_root = bonuses_root.find_class(question_block_value)[0]
                    contract_data['bonuses'] = int(bonuses_value_root.text.strip())

                    payment_until_root = profile_root.find_class('lk__profile-date')[0]
                    payment_until_value_root = payment_until_root.find_class(question_block_value)[0]
                    contract_data['payment_until'] = datetime.strptime(
                        payment_until_value_root.text.strip(),
                        "%d.%m.%Y"
                    ).date()

                    internet_tariff_root = parsed_object.get_element_by_id('internet')
                    internet_tariff_parts_root = internet_tariff_root.find_class('lk__billing-content-item-row')[0]

                    tariff_data = dict()
                    internet_tariff_parts = list(internet_tariff_parts_root)

                    lk_billing_value = 'lk__billing--val'
                    tariff_data['name'] = internet_tariff_parts[1].find_class(lk_billing_value)[0].text.strip()
                    tariff_data['status'] = internet_tariff_parts[2].find_class(lk_billing_value)[0].text.strip()
                    tariff_data['monthly_cost'] = float(internet_tariff_parts[3]
                                                        .find_class(lk_billing_value)[0]
                                                        .text.strip().split(' ')[0])

                    speed_parts = internet_tariff_parts[4].find_class(lk_billing_value)[0].text.strip().split(' ')
                    tariff_data['speed'] = int(speed_parts[0])
                    tariff_data['speed_unit'] = speed_parts[1]

                except KeyError:
                    raise InvalidServerResponseError(self)

            return contract_code, contract_data, tariff_data

    @requires_authentication
    async def update_contract(self, contract: '_ISPContract') -> None:
        pass

    async def get_support_phones(self) -> Optional[List[str]]:
        async with aiohttp.ClientSession(cookie_jar=self._cookies) as session:
            async with session.get(self.BASE_URL + '/ajax/utmphone/get.php') as request:
                if request.status != 200:
                    raise InvalidServerResponseError(self)

                single_phone = await request.text()

                if single_phone:
                    return [single_phone]


class AlmatelContract(_ISPGenericContract):
    @property
    def payments(self) -> List[Payment]:
        return []

    @property
    def invoices(self) -> List[Invoice]:
        return []

    @property
    def bonuses(self) -> int:
        return self._data['bonuses']

    @property
    def services(self) -> List['AlmatelService']:
        return []  # self._data['services']


AlmatelConnector.contract_class = AlmatelContract


class AlmatelTariff(_ISPGenericTariff):
    @property
    def speed_unit(self) -> str:
        return self._data['speed_unit']


AlmatelConnector.tariff_class = AlmatelTariff


class AlmatelService(_ISPService):
    pass
