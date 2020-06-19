import asyncio
import json
import re
from datetime import datetime
from typing import Optional, Dict, Tuple

import aiohttp
from lxml import html

from .base import register_isp_connector, \
    _ISPGenericSingleContractConnector, _ISPHTTPConnector, TariffDataType, ContractDataType, ServicesDataType, \
    PaymentsDataType, InvoicesDataType, format_float
from ..errors import SessionInitializationError, AuthenticationError, InvalidServerResponseError


@register_isp_connector
class MGTSConnector(_ISPGenericSingleContractConnector, _ISPHTTPConnector):
    isp_identifiers = ['mgts', 'mts']
    isp_title = 'MGTS'

    BASE_URL_LK = 'https://lk.mgts.ru'
    BASE_URL_LOGIN = 'https://login.mgts.ru'
    URL_LOGIN = BASE_URL_LOGIN + '/amserver/UI/Login'

    @property
    def auth_headers(self) -> Optional[Dict[str, str]]:
        return {
            'Referer': self.URL_LOGIN,
            'Origin': self.BASE_URL_LOGIN,
            'Connection': 'keep-alive',
            'Cache-Control': 'max-age=0',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'same-origin',
            'Sec-Fetch-User': '?1'
        }

    async def _login(self, session: aiohttp.ClientSession) -> None:
        login_url = self.URL_LOGIN
        async with session.get(login_url) as request:
            if request.status != 200:
                raise SessionInitializationError(self)

            html_content = await request.text()

        parsed_object = html.fromstring(html_content)

        login_form_root = parsed_object.get_element_by_id('login')

        request_data = {
            elem.get('name'): elem.get('value')
            for elem in login_form_root.findall('input')
        }

        request_data['IDToken1'] = self._username
        request_data['IDToken2'] = self._password

        async with session.post(login_url, data=request_data, allow_redirects=False) as request:
            if request.status != 302:
                raise AuthenticationError(self)

    async def _process_main_data(self, session: aiohttp.ClientSession):
        async with session.get(self.BASE_URL_LK, allow_redirects=False) as request:
            if request.status != 200:
                raise AuthenticationError(self)

            html_content = await request.text()

        parsed_object = html.fromstring(html_content)

        account_info_root = parsed_object.find_class('account-info')[0]

        contract_code = account_info_root.find_class('account-info_item_value')[-1].text.strip()

        contract_data = dict()
        contract_data['current_balance'] = float(
            account_info_root.find_class('account-info_balance_value')[0].text_content().strip().split(' ')[0].replace(
                ',', '.'))
        contract_data['client'] = ' '.join([
            p.text.capitalize()
            for p in list(account_info_root.find_class('account-info_title')[0])
        ])

        tariff_data = dict()

        matched_widgets = re.search(r'mgts\.data\.widgets\s*=\s*(\[[^;]+);\s*', html_content)
        widgets_data = json.loads(matched_widgets.group(1))

        for widget in widgets_data:
            if widget['relatedPageUrl'] == '/internet/':
                data_parts = widget['value'].split('-')
                tariff_data['name'] = data_parts[0].strip()
                tariff_data['speed'], tariff_data['speed_unit'] = data_parts[1].strip().split(' ')
                break

        return contract_code, contract_data, tariff_data

    async def _process_auxiliary_data(self, session: aiohttp.ClientSession):
        async with session.get(self.BASE_URL_LOGIN + '/CustomerSelfCare2/account-status.aspx') as request:
            if request.status != 200:
                raise InvalidServerResponseError(self)

            html_content = await request.text()

            parsed_object = html.fromstring(html_content)

            payment_parts = parsed_object.get_element_by_id('paymentsTable').find('tbody').find_class('right')
            contract_data = {'payment_required': max(-format_float(payment_parts[-1].text), 0.0)}

            comment = payment_parts[-1].getparent().find_class('comment')
            if comment:
                contract_data['payment_until'] = datetime.strptime(
                    comment[0].text.strip().split(' ')[-1][:-1],
                    '%d.%m.%Y'
                )
            else:
                contract_data['payment_until'] = None

            tariff_data = {'monthly_cost': format_float(payment_parts[0].text)}
            return contract_data, tariff_data

    async def _get_contract_tariff_data(self) -> Tuple[str,
                                                       ContractDataType,
                                                       TariffDataType,
                                                       Optional[ServicesDataType],
                                                       Optional[PaymentsDataType],
                                                       Optional[InvoicesDataType]]:
        async with aiohttp.ClientSession(cookie_jar=self._cookies) as session:
            results = await asyncio.gather(*[
                self._process_main_data(session),
                self._process_auxiliary_data(session)
            ], return_exceptions=False)

        contract_code, contract_data, tariff_data = results[0]

        contract_data.update(results[1][0])
        tariff_data.update(results[1][1])

        return contract_code, contract_data, tariff_data, None, None, None
