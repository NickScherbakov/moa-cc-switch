import os
import pytest


def test_lru_cache_file_exists():
    assert os.path.exists("lru_cache.py"), "Файл артефакта должен быть создан"


def test_lru_cache_functionality():
    if not os.path.exists("lru_cache.py"):
        pytest.skip("lru_cache.py не существует")

    import importlib.util

    spec = importlib.util.spec_from_file_location("lru_cache", "lru_cache.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    LRUCache = getattr(module, "LRUCache")
    cache = LRUCache(2)

    cache.put(1, 1)
    cache.put(2, 2)
    assert cache.get(1) == 1

    cache.put(3, 3)  # evicts key 2
    assert cache.get(2) == -1

    cache.put(4, 4)  # evicts key 1
    assert cache.get(1) == -1
    assert cache.get(3) == 3
    assert cache.get(4) == 4
