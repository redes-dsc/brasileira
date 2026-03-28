from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_reporter_loop_captura_excecao_e_continua(monkeypatch: pytest.MonkeyPatch) -> None:
    class DummyConsumer:
        def __init__(self) -> None:
            self._items = iter(
                [
                    {"article_id": "a1"},
                    {"article_id": "a2"},
                ]
            )

        async def start(self) -> None:
            return None

        async def stop(self) -> None:
            return None

        def __aiter__(self):
            return self

        async def __anext__(self):
            try:
                payload = next(self._items)
                return type("M", (), {"value": payload})()
            except StopIteration:
                raise StopAsyncIteration

    class DummyKafka:
        def __init__(self, *_args, **_kwargs) -> None:
            self.sent = []

        async def start_producer(self) -> None:
            return None

        async def stop_producer(self) -> None:
            return None

        def build_consumer(self, *_args, **_kwargs):
            return DummyConsumer()

        async def send(self, topic, value, key=None):
            self.sent.append((topic, value, key))

    class DummyWP:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        async def close(self) -> None:
            return None

    class DummyResult:
        publicado = True
        post_id = 321

    class DummyAgent:
        calls = 0

        def __init__(self, *_args, **_kwargs) -> None:
            pass

        async def processar(self, payload):
            DummyAgent.calls += 1
            if payload.get("article_id") == "a1":
                raise RuntimeError("wp error")
            return DummyResult()

    import reporter.__main__ as main_mod

    monkeypatch.setattr(main_mod, "KafkaClient", DummyKafka)
    monkeypatch.setattr(main_mod, "WordPressClient", DummyWP)
    monkeypatch.setattr(main_mod, "ReporterAgent", DummyAgent)
    monkeypatch.setattr(main_mod, "load_keys", lambda _k: ["k"])

    # Executa main e encerra quando consumer acabar.
    await main_mod.main()
