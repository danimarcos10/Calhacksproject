class AppError(Exception):
    def __init__(
        self,
        code: str,
        user_message: str,
        status_code: int = 400,
        retryable: bool = False,
    ) -> None:
        super().__init__(user_message)
        self.code = code
        self.user_message = user_message
        self.status_code = status_code
        self.retryable = retryable


class MediaError(AppError):
    pass
