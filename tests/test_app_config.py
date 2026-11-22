from pathlib import Path

from words_generator.storage.app_config import AppConfig, AppConfigStore


def test_app_config_round_trip(tmp_path: Path) -> None:
    store = AppConfigStore(tmp_path)
    config = AppConfig(api_base_url="http://localhost:8080/v1", model="qwen", recent_projects=["/tmp/demo"])
    store.save(config)
    loaded = store.load()
    assert loaded.api_base_url == config.api_base_url
    assert loaded.model == config.model
    assert loaded.recent_projects == config.recent_projects
    assert loaded.sampling.temperature == 0.9
