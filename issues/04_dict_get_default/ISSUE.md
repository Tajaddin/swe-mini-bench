`get_config_value("port")` always logs `"computing default port"` even when the key already exists in the config. The expensive default should only be evaluated when the key is missing.
