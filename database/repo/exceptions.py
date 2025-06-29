class InsufficientFundsError(Exception):
    pass

class UserNotFoundError(Exception):
    pass


class InvalidAmountError(Exception):
    def __init__(self, message: str):
        self.message = message
        super().__init__(message)
