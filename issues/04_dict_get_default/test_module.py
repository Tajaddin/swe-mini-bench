import module
from module import get_config_value


def setup_function(_):
    module._log.clear()


def test_existing_key_does_not_compute_default():
    assert get_config_value("port") == 9090
    assert module._log == []


def test_missing_key_computes_default():
    assert get_config_value("missing") == 8080
    assert module._log == ["computing default port"]
