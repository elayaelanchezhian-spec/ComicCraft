class ComicCraftError(Exception):
    """An expected, user-actionable ComicCraft service error."""

    status_code = 502


class ConfigurationError(ComicCraftError):
    status_code = 503


class GenerationError(ComicCraftError):
    status_code = 502
