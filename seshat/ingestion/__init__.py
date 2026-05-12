from .csv_source import CSVAlertSource
from .email_csv_source import EmailCsvAlertSource

# Registry maps source_type string → adapter class.
# To add a new source: subclass BaseAlertSource, then add one line here.
SOURCE_REGISTRY: dict = {
    "csv": CSVAlertSource,
    "email_csv": EmailCsvAlertSource,
}


def get_source(config: dict):
    """Instantiate and return the correct alert source adapter for *config*.

    Raises ``ValueError`` for unknown source types.
    """
    source_type = config.get("source_type")
    if source_type not in SOURCE_REGISTRY:
        raise ValueError(
            f"Unknown source type: {source_type!r}. "
            f"Available types: {sorted(SOURCE_REGISTRY)}"
        )
    return SOURCE_REGISTRY[source_type](config)
