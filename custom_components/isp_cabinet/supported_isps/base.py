"""Base integration"""
__all__ = [
    '_ISPConnector',
    '_ISPHTTPConnector',
    '_ISPSingleContractConnector',
    '_ISPGenericSingleContractConnector',
    '_ISPContract',
    '_ISPGenericContract',
    '_ISPTariff',
    '_ISPGenericTariff',
    '_ISPService',
    '_ISPGenericService',
    'Invoice',
    'Payment',
    'register_isp_connector',
    'requires_authentication',
    'ContractDataType',
    'TariffDataType',
    'ServicesDataType',
    'PaymentsDataType',
    'InvoicesDataType',
    'format_float',
    'ISP_CONNECTORS',
]

import asyncio
from abc import ABC
from datetime import timedelta, date, datetime
from enum import IntEnum
from types import MappingProxyType
from typing import Optional, NamedTuple, List, Callable, TypeVar, Type, Union, Dict, Tuple, Any, Mapping

import aiohttp
from fake_useragent import UserAgent

from ..errors import AuthenticationRequiredError


ContractDataType = TypeVar('ContractDataType')
TariffDataType = TypeVar('TariffDataType')
ServiceDataType = TypeVar('ServiceDataType')
InvoiceDataType = TypeVar('InvoiceDataType')
PaymentDataType = TypeVar('PaymentDataType')

InvoiceIDType = Union[str, int]
PaymentIDType = Union[str, int]
ServiceCodeType = Union[str, int]

InvoicesDataType = Dict[InvoiceIDType, InvoiceDataType]
PaymentsDataType = Dict[PaymentIDType, PaymentDataType]
ServicesDataType = Dict[str, ServiceDataType]

ReturnType = TypeVar('ReturnType')


ISP_CONNECTORS: List[Type['_ISPConnector']] = list()

DEFAULT_CURRENCY = 'руб.'
DEFAULT_SPEED_UNIT = 'Мбит/с'


def format_float(float_string: str) -> float:
    return float(float_string.strip().replace(' ', '').replace(',', '.'))


def register_isp_connector(connector: Type['_ISPConnector']) -> Type['_ISPConnector']:
    if connector not in ISP_CONNECTORS:
        ISP_CONNECTORS.append(connector)

    return connector


def requires_authentication(func: Callable[..., ReturnType]) -> Callable[..., ReturnType]:
    def authentication_required_decorator(self, *args, **kwargs):
        if not self.is_logged_in:
            raise AuthenticationRequiredError(self)
        return func(self, *args, **kwargs)

    authentication_required_decorator.__name__ = func.__name__
    authentication_required_decorator.__doc__ = \
        (func.__doc__ or "") + ".. warning::\n    Authentication required to use this method"

    return authentication_required_decorator


class _ISPConnector:
    scan_interval: timedelta = timedelta(hours=2)

    isp_identifiers: List[str] = NotImplemented
    isp_title: str = NotImplemented

    def __init__(self, username: str, password: str, scan_interval: Optional[timedelta] = None) -> None:
        """

        :param username: Имя пользователя
        :param password: Пароль
        :param scan_interval:
        """
        self._username = username
        self._password = password

        if scan_interval is not None:
            self.scan_interval = scan_interval

    @property
    def username(self):
        return self._username

    @property
    def password(self) -> None:
        raise AttributeError('Access to password attribute is restricted for getter')

    @password.setter
    def password(self, value: str):
        # @TODO: implement immediate logout?
        self._password = value

    @property
    def is_logged_in(self):
        raise NotImplementedError

    async def login(self) -> None:
        """Выполнение авторизации"""
        raise NotImplementedError

    async def logout(self) -> None:
        """Очистка авторизации"""
        raise NotImplementedError

    async def refresh_session(self) -> None:
        """Обновление авторизации"""
        await self.logout()
        await self.login()

    @requires_authentication
    async def get_contracts(self) -> Dict[str, '_ISPContract']:
        """
        Получение
        :return:
        """
        raise NotImplementedError

    # Optional to override in inherent ISP Connector classes
    @classmethod
    def ip_api_belongs(cls, ip_api_data: Dict[str, Union[str, float]]):
        search_in = ' '.join([ip_api_data["org"], ip_api_data["isp"], ip_api_data["as"]]).lower()
        return any([p in search_in for p in cls.isp_identifiers])

    async def get_support_phones(self) -> Optional[List[str]]:
        return None


class _ISPHTTPConnector(_ISPConnector):
    def __init__(self, *args, user_agent: Optional[str] = None, **kwargs):
        super().__init__(*args, **kwargs)

        self._user_agent: Optional[str] = user_agent
        self._cookies: Optional[aiohttp.CookieJar] = None

    @property
    def is_logged_in(self):
        return self._cookies and len(self._cookies)

    @staticmethod
    def _get_user_agent():
        return UserAgent()['google chrome']

    @property
    def auth_headers(self) -> Optional[Dict[str, str]]:
        return None

    async def login(self) -> None:
        if self._user_agent is None:
            loop = asyncio.get_running_loop()
            self._user_agent = await loop.run_in_executor(None, self._get_user_agent)

        cookie_jar = aiohttp.CookieJar()

        request_headers = {'User-Agent': self._user_agent, }

        auth_headers = self.auth_headers
        if auth_headers:
            request_headers.update(auth_headers)

        async with aiohttp.ClientSession(cookie_jar=cookie_jar, headers=request_headers) as session:
            await self._login(session)

        self._cookies = cookie_jar

    async def _login(self, session: aiohttp.ClientSession):
        raise NotImplementedError

    async def logout(self) -> None:
        await self._logout()

        del self._cookies
        self._cookies = None

    async def _logout(self) -> None:
        pass

    async def get_contracts(self) -> Dict[str, '_ISPContract']:
        raise NotImplementedError


class Payment(NamedTuple):
    contract: '_ISPContract'
    id: PaymentIDType
    amount: float
    paid_at: datetime
    comment: Optional[str] = None


class Invoice(NamedTuple):
    contract: '_ISPContract'
    id: InvoiceIDType
    amount: float
    issued_at: date
    comment: Optional[str] = None


class _ISPContract:
    def __init__(self, connector: _ISPConnector, code: str, isp_identifier: str, initial_data: ContractDataType):
        self._isp_identifier: str = isp_identifier
        self._connector: _ISPConnector = connector
        self._code: str = code
        self._data: ContractDataType = initial_data
        self._tariff: Optional[_ISPTariff] = None

    @property
    def data(self) -> ContractDataType:
        return self._data

    @data.setter
    def data(self, value: ContractDataType) -> None:
        self._data = value

    @property
    def connector(self) -> _ISPConnector:
        return self._connector

    @property
    def code(self) -> str:
        return self._code

    @property
    def isp_identifier(self) -> str:
        return self._isp_identifier

    # Necessary to override in inherent ISP Contract classes
    @property
    def current_balance(self) -> float:
        raise NotImplementedError

    @property
    def payment_required(self) -> float:
        """
        Требуемый платёж для поддержания активности услуг.
        :return: Float - размер платежа
        """
        raise NotImplementedError

    @property
    def payment_until(self) -> Optional[date]:
        raise NotImplementedError

    @property
    def services(self) -> Optional[Mapping[ServiceCodeType, '_ISPService']]:
        raise NotImplementedError

    def set_services_data(self, services_data: ServicesDataType) -> None:
        raise NotImplementedError

    @property
    def invoices(self) -> Optional[Mapping[InvoiceIDType, Invoice]]:
        raise NotImplementedError

    def set_invoices_data(self, invoices_data: InvoicesDataType) -> None:
        raise NotImplementedError

    @property
    def payments(self) -> Optional[Mapping[PaymentIDType, Payment]]:
        raise NotImplementedError

    def set_payments_data(self, payments_data: PaymentsDataType) -> None:
        raise NotImplementedError

    # Optional to override in inherent ISP Contract classes

    @property
    def payment_suggested(self) -> float:
        payment_required = self.payment_required
        if payment_required:
            return payment_required
        return max(0.0, self._tariff.monthly_cost - self.current_balance)

    @property
    def address(self) -> Optional[str]:
        return None

    @property
    def tariff(self) -> Optional['_ISPTariff']:
        return self._tariff

    @tariff.setter
    def tariff(self, value: '_ISPTariff'):
        self._tariff = value

    @property
    def client(self) -> Optional[str]:
        return None

    @property
    def currency(self) -> str:
        return DEFAULT_CURRENCY

    @property
    def bonuses(self) -> Optional[float]:
        return None

    @property
    def automatic_payment(self) -> Optional[bool]:
        return None


# Tariffs section
class _ISPTariff:
    def __init__(self, contract: '_ISPContract', initial_data: TariffDataType) -> None:
        self._contract = contract
        self._data = initial_data

    @property
    def contract(self):
        return self._contract

    @property
    def data(self) -> TariffDataType:
        return self._data

    @data.setter
    def data(self, value: TariffDataType) -> None:
        self._data = value

    # Necessary to override in inherent ISP Tariff classes
    @property
    def monthly_cost(self) -> float:
        raise NotImplementedError

    @property
    def name(self) -> str:
        raise NotImplementedError

    @property
    def speed(self) -> int:
        raise NotImplementedError

    # Optional to override in inherent ISP Tariff classes
    @property
    def status(self) -> Optional[str]:
        """
        Текущий статус по тарифу
        :return:
        """
        return None

    @property
    def speed_unit(self) -> str:
        return DEFAULT_SPEED_UNIT

    @property
    def ip_address(self) -> Optional[Union[str, bool]]:
        """
        Получить IP-адрес по тарифу.
        :return: IP адрес / True - неизвестный статический / False - динамический / None - без реализации
        """
        return None


class _ISPGenericTariff(_ISPTariff):
    @property
    def monthly_cost(self) -> float:
        return self._data['monthly_cost']

    @property
    def name(self) -> str:
        return self._data['name']

    @property
    def speed(self) -> int:
        return self._data['speed']

    @property
    def status(self) -> Optional[str]:
        return self._data.get('status')

    @property
    def speed_unit(self) -> str:
        return self._data.get('speed_unit', DEFAULT_SPEED_UNIT)


# Services section
class _ISPService:
    class Period(IntEnum):
        SINGLE = 0
        MONTH = 1
        DAY = 2
        HOUR = 3

    def __init__(self, contract: '_ISPContract', code: str, initial_data: ServiceDataType) -> None:
        self._code = code
        self._contract = contract
        self._data = initial_data

    @property
    def code(self) -> str:
        return self._code

    @property
    def contract(self):
        return self._contract

    @property
    def data(self) -> ServiceDataType:
        return self._data

    @data.setter
    def data(self, value: ServiceDataType):
        self._data = value

    # Necessary to override in inherent ISP Service classes
    @property
    def name(self) -> str:
        raise NotImplementedError

    @property
    def cost(self) -> float:
        raise NotImplementedError

    @property
    def period(self) -> Period:
        raise NotImplementedError

    @property
    def initial_payment(self) -> float:
        raise NotImplementedError


class _ISPGenericService(_ISPService):
    @property
    def name(self) -> str:
        return self._data['name']

    @property
    def cost(self) -> float:
        return self._data.get('cost', 0.0)

    @property
    def period(self) -> '_ISPService.Period':
        if isinstance(self._data['period'], self.Period):
            return self._data['period']
        return self.Period(self._data['period'])

    @property
    def initial_payment(self) -> float:
        return self._data.get('initial_payment', 0.0)


# Additional abstract classes
class _ISPGenericContract(_ISPContract):
    service_class: Type[_ISPGenericService] = _ISPGenericService
    payment_class: Type[Payment] = Payment
    invoice_class: Type[Invoice] = Invoice

    def __init__(self, *args,
                 initial_invoices_data: Optional[InvoicesDataType] = None,
                 initial_payments_data: Optional[PaymentsDataType] = None,
                 initial_services_data: Optional[ServicesDataType] = None,
                 **kwargs):
        super().__init__(*args, **kwargs)

        self._payments: Dict[PaymentIDType, Payment] = dict()
        self._invoices: Dict[InvoiceIDType, Invoice] = dict()
        self._services: Dict[ServiceCodeType, _ISPGenericService] = dict()

        if initial_payments_data:
            self.set_payments_data(initial_payments_data)

        if initial_invoices_data:
            self.set_invoices_data(initial_invoices_data)

        if initial_services_data:
            self.set_services_data(initial_services_data)

    # Contract-bound entity generators
    def set_payments_data(self, payments_data: PaymentsDataType) -> None:
        for payment_id, payment_data in payments_data.items():
            if payment_id in self._payments:
                payment = self._payments[payment_id]
                payment.amount = payment_data['amount']
                payment.paid_at = payment_data['paid_at']
                payment.comment = payment_data.get('comment')

            else:
                self._payments[payment_id] = self.payment_class(
                    contract=self,
                    id=payment_data['id'],
                    amount=payment_data['amount'],
                    paid_at=payment_data['paid_at'],
                    comment=payment_data.get('comment')
                )

    def set_invoices_data(self, invoices_data: InvoicesDataType) -> None:
        for invoice_id, invoice_data in invoices_data.items():
            if invoice_id in self._invoices:
                invoice = self._invoices[invoice_id]
                invoice.amount = invoice_data['amount']
                invoice.issued_at = invoice_data['issued_at']
                invoice.comment = invoice_data.get('comment')

            else:
                self._invoices[invoice_id] = self.invoice_class(
                    contract=self,
                    id=invoice_data['id'],
                    amount=invoice_data['amount'],
                    issued_at=invoice_data['issued_at'],
                    comment=invoice_data.get('comment')
                )

    def set_services_data(self, services_data: ServicesDataType) -> None:
        for service_code, service_data in services_data.items():
            if service_code in self._services:
                self._services[service_code].data = service_data
            else:
                self._services[service_code] = self.service_class(
                    contract=self,
                    code=service_code,
                    initial_data=service_data
                )

    # Contract-bound entities
    @property
    def services(self) -> Optional[Mapping[ServiceCodeType, '_ISPService']]:
        if self._services is None:
            return None
        return MappingProxyType(self._services)

    @property
    def invoices(self) -> Optional[Mapping[InvoiceIDType, Invoice]]:
        if self._invoices is None:
            return None
        return MappingProxyType(self._invoices)

    @property
    def payments(self) -> Optional[Mapping[PaymentIDType, Payment]]:
        if self._payments is None:
            return None
        return MappingProxyType(self._payments)

    # Contract properties
    @property
    def address(self) -> Optional[str]:
        return self._data.get('address')

    @property
    def current_balance(self) -> float:
        return self._data['current_balance']

    @property
    def payment_required(self) -> float:
        return self._data.get('payment_required', 0.0)

    @property
    def payment_suggested(self) -> float:
        if 'payment_suggested' not in self._data:
            return super().payment_suggested
        return self._data['payment_suggested']

    @property
    def payment_until(self) -> Optional[date]:
        return self._data.get('payment_until')

    @property
    def currency(self) -> str:
        return self._data.get('currency', DEFAULT_CURRENCY)

    @property
    def client(self) -> Optional[str]:
        return self._data.get('client')

    @property
    def automatic_payment(self) -> Optional[bool]:
        return self.data.get('automatic_payment')


class _ISPSingleContractConnector(_ISPConnector, ABC):
    contract_class: Type['_ISPContract'] = NotImplemented
    tariff_class: Type['_ISPTariff'] = NotImplemented

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self._bound_contract: Optional['_ISPContract'] = None

    # Override in inherent ISP Single Contract classes
    async def _get_contract_tariff_data(self) -> Tuple[str,
                                                       ContractDataType,
                                                       TariffDataType,
                                                       Optional[ServicesDataType],
                                                       Optional[PaymentsDataType],
                                                       Optional[InvoicesDataType]]:
        raise NotImplementedError

    # Helper method - overriding not implied
    @requires_authentication
    async def get_contracts(self) -> Dict[str, '_ISPContract']:
        result = await self._get_contract_tariff_data()
        contract_code, contract_data, tariff_data, services_data, invoices_data, payments_data = result

        if self._bound_contract is not None and self._bound_contract.code == contract_code:
            del self._bound_contract
            self._bound_contract = None

        if self._bound_contract is None:
            contract = self.contract_class(
                connector=self,
                code=contract_code,
                isp_identifier=self.isp_identifiers[0],
                initial_data=contract_data
            )
            contract.tariff = self.tariff_class(
                contract=contract,
                initial_data=tariff_data
            )
            self._bound_contract = contract

        else:
            contract = self._bound_contract
            contract.data = contract_data
            contract.tariff.data = tariff_data

        if services_data is not None:
            contract.set_services_data(services_data)

        if payments_data is not None:
            contract.set_payments_data(payments_data)

        if invoices_data is not None:
            contract.set_invoices_data(invoices_data)

        return {contract_code: contract}


class _ISPGenericSingleContractConnector(_ISPSingleContractConnector, ABC):
    contract_class = _ISPGenericContract
    tariff_class = _ISPGenericTariff
