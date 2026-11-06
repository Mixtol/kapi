import json
from typing import Any, Optional

from requests import Response


def _display(value: Any) -> str:
    return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)


def _format_detail(message: Any, params: Any) -> str:
    text = _display(message)
    if not isinstance(params, dict):
        return text if params is None else f"{text} (params={_display(params)})"

    remaining = dict(params)
    if (
        text == "the number of characters must be between"
        and {
            "from",
            "to",
        }
        <= remaining.keys()
    ):
        text += (
            f" {_display(remaining.pop('from'))} and {_display(remaining.pop('to'))}"
        )
    elif text == "must be greater than or equal to" and "greater" in remaining:
        text += f" {_display(remaining.pop('greater'))}"

    if remaining:
        values = ", ".join(
            f"{key}={_display(value)}" for key, value in remaining.items()
        )
        text += f" ({values})"
    return text


class APIError(Exception):
    """API failure with a readable message and the original response data.

    ``details``, ``errors``, ``entity`` and ``params`` retain their server-provided values. The complete
    parsed JSON is available as ``response_data`` and the body as ``response_text``.
    Errors without a response retain ``None`` for these attributes.
    """

    def __init__(
        self,
        message: str,
        status_code: Optional[int] = None,
        *,
        response_data: Any = None,
        response_text: Optional[str] = None,
    ):
        super().__init__(message)
        self.status_code = status_code
        self.response_data = response_data
        self.response_text = response_text
        self.details = (
            response_data.get("details") if isinstance(response_data, dict) else None
        )
        self.params = (
            response_data.get("params") if isinstance(response_data, dict) else None
        )
        self.errors = (
            response_data.get("errors") if isinstance(response_data, dict) else None
        )
        self.entity = (
            response_data.get("entity") if isinstance(response_data, dict) else None
        )

    @classmethod
    def from_response(cls, response: Response) -> "APIError":
        """Decode HTTP errors, falling back to the body for unrecognized formats."""
        response_text = response.text
        try:
            data = response.json()
        except ValueError:
            data = None

        description = response_text
        if isinstance(data, dict) and data.get("authBlocked") is True:
            description = "KUMA authentication is blocked (authBlocked=true)"
        elif isinstance(data, dict) and data.get("mustChangePassword") is True:
            description = (
                "KUMA requires a password change before private API login "
                "(mustChangePassword=true)"
            )
        elif isinstance(data, dict) and (
            isinstance(data.get("message"), str)
            or isinstance(data.get("reason"), str)
            or isinstance(data.get("error"), str)
            or isinstance(data.get("errors"), dict)
        ):
            title = data.get("message")
            if not isinstance(title, str):
                title = data.get("reason")
            if not isinstance(title, str):
                title = data.get("error")
            if not isinstance(title, str):
                title = data.get("entity") or "validation error"
            lines = [_display(title)]
            details = data.get("details", data.get("errors"))
            params = data.get("params")
            if isinstance(details, dict):
                for field, message in details.items():
                    field_params = (
                        params.get(field) if isinstance(params, dict) else None
                    )
                    lines.append(f"{field}: {_format_detail(message, field_params)}")
                if isinstance(params, dict):
                    unmatched = {
                        key: value
                        for key, value in params.items()
                        if key not in details
                    }
                    if unmatched:
                        lines.append(f"params: {_display(unmatched)}")
                elif params is not None:
                    lines.append(f"params: {_display(params)}")
            else:
                if details is not None:
                    lines.append(f"details: {_display(details)}")
                if params is not None:
                    lines.append(f"params: {_display(params)}")
            if "details" in data and "errors" in data:
                lines.append(f"errors: {_display(data['errors'])}")
            description = "\n".join(lines)

        return cls(
            f"Bad response {response.status_code}: {description}",
            status_code=response.status_code,
            response_data=data,
            response_text=response_text,
        )
