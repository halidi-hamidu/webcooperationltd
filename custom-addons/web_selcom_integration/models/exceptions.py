"""Dedicated Selcom exceptions."""


class SelcomException(Exception):
    """Base exception for all Selcom integration errors."""
    def __init__(self, message, endpoint=None, http_status=None,
                 result_code=None):
        super().__init__(message)
        self.endpoint = endpoint
        self.http_status = http_status
        self.result_code = result_code

    def __str__(self):
        parts = [super().__str__()]
        if self.endpoint:
            parts.append(f"endpoint={self.endpoint}")
        if self.http_status:
            parts.append(f"http={self.http_status}")
        if self.result_code:
            parts.append(f"code={self.result_code}")
        return " ".join(parts)


class SelcomAuthenticationException(SelcomException):
    """Invalid credentials / signing failure (HTTP 401/403)."""


class SelcomValidationException(SelcomException):
    """Invalid request payload or parameters (client-side validation)."""


class SelcomApiException(SelcomException):
    """Selcom API returned an error resultcode."""


class SelcomTimeoutException(SelcomException):
    """Request timed out."""


class SelcomOrderException(SelcomException):
    """Order operation not allowed (e.g. cancelling a completed order)."""


class SelcomWebhookException(SelcomException):
    """Invalid or unprocessable webhook payload."""
