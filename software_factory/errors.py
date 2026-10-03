"""Expected failures, suitable for CLI output without a traceback."""


class FactoryError(Exception):
    def __init__(self, message: str, code: str = "invalid") -> None:
        super().__init__(message)
        self.code = code
