class APIError(Exception):
    """Exception for API errors with status code support."""
    def __init__(self, message: str, status_code: int = None):
        super().__init__(message)
        self.status_code = status_code
