_log: list[str] = []


def _expensive_default_port():
    _log.append("computing default port")
    return 8080


def get_config_value(key: str, config: dict | None = None) -> int:
    """Return ``config[key]`` if present, else compute and return a default."""
    config = config or {"port": 9090, "timeout": 30}
    return config.get(key, _expensive_default_port())
