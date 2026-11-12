from __future__ import annotations

import time

from app.pool import KeyPool
from app.util import key_fingerprint

from support import make_provider


def build_pool(tmp_path=None, **provider_kwargs) -> tuple[KeyPool, object]:
    provider = make_provider("p1", keys=("k1", "k2"), **provider_kwargs)
    providers = {provider.id: provider}
    pool = KeyPool(providers, (tmp_path / "state.json") if tmp_path else None, bool(tmp_path))
    return pool, provider


def test_pick_round_robin_and_accounting():
    pool, provider = build_pool()
    first = pool.pick("p1")
    second = pool.pick("p1")
    assert first is not None and second is not None
    assert first.key_id != second.key_id
    assert first.uses_today == 1
    assert first.total_uses == 1
    assert pool.pick("p1") is not None  # vuelve a la primera


def test_rpm_limit_blocks_provider():
    pool, _ = build_pool(rpm=1)
    assert pool.pick("p1") is not None
    assert pool.pick("p1") is not None
    assert pool.pick("p1") is None
    assert pool.has_available("p1") is False


def test_rate_limit_moves_to_other_key_and_backs_off():
    pool, _ = build_pool()
    key = pool.pick("p1")
    assert key is not None
    pool.mark_rate_limited(key, 60, "429")
    assert key.available(pool.providers["p1"], time.time()) is False
    other = pool.pick("p1")
    assert other is not None and other.key_id != key.key_id
    pool.mark_rate_limited(other, 60, "429")
    assert pool.pick("p1") is None
    assert pool.available_at("p1") > time.time()


def test_invalid_key_is_disabled_until_reset():
    pool, _ = build_pool()
    key = pool.pick("p1")
    pool.mark_invalid(key, "401")
    assert key.disabled is True
    assert key.key_id not in {k.key_id for k in pool.keys_for("p1") if k.available(pool.providers["p1"], time.time())}
    pool.reset()
    assert key.disabled is False
    assert pool.has_available("p1") is True


def test_daily_counters_reset_on_new_day():
    pool, provider = build_pool()
    key = pool.pick("p1")
    key.uses_today = 999
    key.tokens_today = 123456
    key.day = "2000-01-01"
    assert key.available(provider, time.time()) is True
    assert key.uses_today == 0 and key.tokens_today == 0


def test_daily_limit_blocks_when_reached():
    pool, provider = build_pool(rpd=1)
    pool.pick("p1")
    pool.pick("p1")
    assert pool.has_available("p1") is False


def test_persistence_restores_cooldowns(tmp_path):
    provider = make_provider("p1", keys=("k1",))
    pool = KeyPool({provider.id: provider}, tmp_path / "state.json", True)
    key = pool.pick("p1")
    pool.mark_rate_limited(key, 120, "cuota")
    pool.save()

    restored = KeyPool({provider.id: provider}, tmp_path / "state.json", True)
    state = restored.keys[key_fingerprint("p1", "k1")]
    assert state.cooldown_until > time.time()
    assert restored.has_available("p1") is False


def test_runtime_keys_persist_and_can_be_removed(tmp_path):
    provider = make_provider("p1", keys=())
    pool = KeyPool({provider.id: provider}, tmp_path / "state.json", True)
    state = pool.add_key("p1", "sk-live-123", "manual")
    assert state.source == "runtime"

    restored = KeyPool({provider.id: provider}, tmp_path / "state.json", True)
    assert state.key_id in restored.keys

    assert restored.remove_key(state.key_id) is True
    assert state.key_id not in restored.keys


def test_env_key_is_disabled_not_deleted():
    pool, _ = build_pool()
    key = pool.pick("p1")
    pool.remove_key(key.key_id)
    assert key.key_id in pool.keys
    assert key.disabled is True


def test_snapshot_hides_secret():
    pool, _ = build_pool()
    snapshot = pool.snapshot()
    row = snapshot["providers"][0]
    assert row["keys_total"] == 2
    assert "secret" not in row["keys"][0]
    assert row["keys"][0]["masked"]
