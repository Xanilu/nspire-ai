"""Application-level request processing, separate from transport and providers."""

from nspire_ai.protocol import ProtocolRequest, ProtocolResponse
from nspire_ai.providers.base import AIProvider


def handle_request(request: ProtocolRequest, provider: AIProvider) -> ProtocolResponse:
    """Run a validated request through a provider and map its result to Protocol v1."""
    try:
        result = provider.generate(request.input)
    except Exception:
        return ProtocolResponse(
            request_id=request.request_id,
            status="error",
            text="The request could not be processed.",
            error={
                "code": "provider_error",
                "message": "The configured provider could not process the request.",
            },
            protocol_version=request.protocol_version,
        )
    return ProtocolResponse(
        request_id=request.request_id,
        status="success",
        text=result.text,
        metadata={"provider": result.provider},
        protocol_version=request.protocol_version,
    )
