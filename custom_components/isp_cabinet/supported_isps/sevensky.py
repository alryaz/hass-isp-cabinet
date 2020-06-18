import asyncio
import json
import re
from datetime import date
from typing import Dict, List, Tuple, Any, Optional

import aiohttp
from lxml import html

from .base import register_isp_connector, _ISPHTTPConnector, \
    Invoice, Payment, _ISPGenericContract, _ISPSingleContractConnector, _ISPGenericTariff, _ISPService
from ..errors import SessionInitializationError, AuthenticationError, \
    InvalidServerResponseError

ContractDataType = Dict[str, Any]
TariffDataType = Dict[str, Any]


@register_isp_connector
class SevenSkyConnector(_ISPSingleContractConnector, _ISPHTTPConnector):
    isp_identifiers = ['sevensky', 'gorcom']
    isp_title_ru = 'SevenSky'
    isp_title = 'SevenSky'

    BASE_URL_LK = 'https://lk.seven-sky.net'

    async def _login(self, session: aiohttp.ClientSession) -> None:
        async with session.get(self.BASE_URL_LK) as request:
            if request.status != 200:
                raise SessionInitializationError(self)

        async with session.post(self.BASE_URL_LK + '/ajax/login.jsp', data={
            'login': self._username,
            'password': self._password,
        }) as request:
            if request.status != 200:
                raise AuthenticationError(self)

            try:
                response = await request.text()
                response_json = json.loads(response)

                if not response_json.get('res'):
                    raise AuthenticationError(self)

            except json.JSONDecodeError:
                raise InvalidServerResponseError(self) from None

    async def logout(self) -> None:
        pass

    async def _retrieve_contract_main(self, session: aiohttp.ClientSession) \
            -> Tuple[str, Dict[str, Any], Dict[str, Any]]:
        home_page_url = self.BASE_URL_LK + '/index.jsp'

        async with session.get(home_page_url) as request:
            if request.status != 200:
                raise InvalidServerResponseError(self)

            html_content = await request.text()

            parsed_object = html.fromstring(html_content, base_url=home_page_url)

            try:
                contract_data = dict()

                account_header_root = parsed_object.get_element_by_id('inner-table')

                contract_code_root = account_header_root.get_element_by_id('info-header-1')
                contract_code = list(contract_code_root)[1].text.strip().split(' ')[-1]
                current_balance_value_root = account_header_root.find_class('info-table-content')[0]\
                    .find('li').find('span')
                contract_data['current_balance'] = float(current_balance_value_root.text.strip())
                contract_data['currency'] = current_balance_value_root.getnext().text.strip()

                try:
                    payment_required_root = account_header_root.find_class('block-message')[0]
                    contract_data['payment_required'] = float(re.search(
                        r'\d+(\.\d+)?',
                        payment_required_root.find('strong').text
                    ).group(0))
                    contract_data['status'] = payment_required_root.text

                except (IndexError, KeyError):
                    pass

                tariff_data = dict()
                tariff_name_speed_root = parsed_object.find_class('tarif')[0]
                internet_tariff_parts = list(tariff_name_speed_root)
                tariff_data['name'] = internet_tariff_parts[0].text.strip()[7:-1]
                tariff_data['speed'] = int(re.findall(r'\d+', internet_tariff_parts[2].text)[0])
                tariff_data['monthly_cost'] = float(
                    re.findall(
                        r'\d+',
                        tariff_name_speed_root.getparent().find_class('price')[0].text
                    )[0]
                )

                return contract_code, contract_data, tariff_data

            except (IndexError, KeyError):

                raise InvalidServerResponseError(self)

    async def _retrieve_personal_details(self, session: aiohttp.ClientSession) -> Dict[str, Any]:
        personal_details_url = self.BASE_URL_LK + '/settings.jsp'

        async with session.get(personal_details_url) as request:
            if request.status != 200:
                raise InvalidServerResponseError(self)

            html_content = await request.text()

            parsed_object = html.fromstring(html_content, base_url=personal_details_url)

            try:
                contract_data = dict()

                page_content = parsed_object.get_element_by_id('page-content')
                data_table_root = page_content.xpath('//table[@class="data-table"]/tr')
                data_table_rows = list(data_table_root)

                contract_data['client'] = list(data_table_rows[0])[1].text.strip()
                contract_data['address'] = list(data_table_rows[1])[1].text.strip()

                return contract_data

            except (IndexError, KeyError):
                raise InvalidServerResponseError(self)

    async def _get_contract_tariff_data(self) -> Tuple[str, 'ContractDataType', 'TariffDataType']:
        async with aiohttp.ClientSession(cookie_jar=self._cookies, headers={
            'Connection': 'keep-alive',
            'User-Agent': self._user_agent,
            'Referer': self.BASE_URL_LK + '/login.jsp',
        }) as session:
            results = await asyncio.gather(*[
                self._retrieve_contract_main(session),
                self._retrieve_personal_details(session)
            ])

        contract_code, contract_data, tariff_data = results[0]

        contract_data.update(results[1])

        return contract_code, contract_data, tariff_data


class SevenSkyContract(_ISPGenericContract):
    @property
    def payments(self) -> List[Payment]:
        return []

    @property
    def invoices(self) -> List[Invoice]:
        return []

    @property
    def services(self) -> List['SevenSkyService']:
        return []

    @property
    def payment_until(self) -> Optional[date]:
        return None


SevenSkyConnector.contract_class = SevenSkyContract


class SevenSkyTariff(_ISPGenericTariff):
    pass


SevenSkyConnector.tariff_class = SevenSkyTariff


class SevenSkyService(_ISPService):
    pass
