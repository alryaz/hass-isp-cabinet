class ISPCabinetException(BaseException):
    pass


class InvalidServerResponseError(ISPCabinetException):
    pass


class SessionInitializationError(InvalidServerResponseError):
    pass


class AuthenticationError(ISPCabinetException):
    pass


class AuthenticationRequiredError(AuthenticationError):
    pass


class CredentialsInvalidError(AuthenticationError):
    pass


class ServerTimeoutError(ISPCabinetException):
    pass
