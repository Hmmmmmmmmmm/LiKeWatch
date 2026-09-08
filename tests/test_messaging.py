import httpx
import pytest
from likewatch.storage import Store
from likewatch.profiles import demo_profile
from likewatch.messaging import deliver


@pytest.mark.parametrize(
    "status,payload,state",
    [
        (200, {"ok": True}, "accepted"),
        (429, {"ok": False, "parameters": {"retry_after": 9}}, "retrying"),
        (500, {"ok": False}, "retrying"),
        (403, {"ok": False}, "failed"),
    ],
)
def test_delivery(tmp_path, monkeypatch, status, payload, state):
    monkeypatch.setattr("likewatch.messaging.keyring.get_password", lambda *_: "SECRET")
    store = Store(tmp_path / "db")
    p = demo_profile()
    p.delivery_enabled = True
    p.chat_id = "123"
    store.enqueue(p, "TEST", "test")
    with httpx.Client(
        transport=httpx.MockTransport(lambda req: httpx.Response(status, json=payload))
    ) as client:
        deliver(store, p.id, client)
    row = store.history(p.id)[0]
    assert row["delivery"] == state
    assert "SECRET" not in str(row)


def test_lost_response_is_uncertain(tmp_path, monkeypatch):
    monkeypatch.setattr("likewatch.messaging.keyring.get_password", lambda *_: "SECRET")
    store = Store(tmp_path / "db")
    p = demo_profile()
    p.delivery_enabled = True
    p.chat_id = "123"
    store.enqueue(p, "TEST", "test")

    def fail(req):
        raise httpx.ReadTimeout("https://example/SECRET", request=req)

    with httpx.Client(transport=httpx.MockTransport(fail)) as client:
        deliver(store, p.id, client)
    row = store.history(p.id)[0]
    assert row["delivery"] == "uncertain"
    assert "SECRET" not in str(row)
