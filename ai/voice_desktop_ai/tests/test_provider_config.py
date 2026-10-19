from brain.providers.provider_config import load_provider_config


def test_missing_key_is_unconfigured_without_secret_in_status():
    config = load_provider_config({})

    assert config.configured is False
    assert config.model == "grok-4.6"
    assert config.safe_status() == {"provider": "xai", "configured": False, "model": "grok-4.6"}


def test_configured_key_is_not_exposed_by_repr_or_status():
    secret = "test-only-secret"
    config = load_provider_config({"XAI_API_KEY": secret})

    assert config.configured is True
    assert secret not in repr(config)
    assert secret not in str(config.safe_status())


def test_custom_model_and_malformed_values_are_handled_safely():
    assert load_provider_config({"XAI_API_KEY": "key", "XAI_MODEL": "grok-test"}).model == "grok-test"
    config = load_provider_config({"XAI_API_KEY": "  ", "XAI_MODEL": "  "})

    assert config.configured is False
    assert config.model == "grok-4.6"