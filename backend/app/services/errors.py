class ApplicationServiceError(Exception):
    status_code = 502
    public_message = "Un service externe est temporairement indisponible."

    def __init__(self, public_message: str | None = None) -> None:
        super().__init__(public_message or self.public_message)
        if public_message:
            self.public_message = public_message


class ServiceConfigurationError(ApplicationServiceError):
    status_code = 503
    public_message = "La configuration du service est incomplète."


class ClaudeServiceError(ApplicationServiceError):
    status_code = 502
    public_message = "L’analyse de la demande est temporairement indisponible."


class MCPServiceError(ApplicationServiceError):
    status_code = 502
    public_message = "Le catalogue de films est temporairement indisponible."

