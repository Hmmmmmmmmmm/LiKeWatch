"""Telegram delivery; no token appears in persisted profiles or error messages."""

import httpx
import keyring

SERVICE = "LiKeWatch.Telegram"


def save_token(profile_id, token):
    if token.strip():
        keyring.set_password(SERVICE, profile_id, token.strip())


def deliver(store, profile_id, client=None):
    row = store.claim(profile_id)
    if row is None:
        return
    try:
        token = keyring.get_password(SERVICE, profile_id)
    except Exception:
        store.delivered(row["seq"], "failed", detail="Credential store unavailable")
        return
    if not token:
        store.delivered(
            row["seq"], "failed", detail="No bot token in OS credential store"
        )
        return
    photo = row.get("attachment")
    method = "sendPhoto" if photo else "sendMessage"
    payload = {"chat_id": row["chat"], "caption" if photo else "text": row["body"]}
    if row.get("rich"):
        payload["parse_mode"] = "HTML"
    options = {"data": payload, "files": {"photo": ("incident.jpg", photo, "image/jpeg")}} if photo else {"json": payload}
    if row["topic"]:
        payload["message_thread_id"] = int(row["topic"])
    try:
        if client is None:
            with httpx.Client(timeout=12) as owned:
                response = owned.post(
                    f"https://api.telegram.org/bot{token}/{method}", **options
                )
        else:
            response = client.post(
                f"https://api.telegram.org/bot{token}/{method}", **options
            )
        try:
            data = response.json()
        except ValueError:
            store.delivered(
                row["seq"],
                "uncertain",
                detail="Unrecognized server response; acceptance unknown",
            )
            return
        if response.is_success and data.get("ok"):
            store.delivered(row["seq"], "accepted", detail="Accepted by Telegram API", message_id=data.get("result", {}).get("message_id"))
        elif response.status_code == 429 or data.get("error_code") == 429:
            delay = max(
                1, min(86400, int(data.get("parameters", {}).get("retry_after", 30)))
            )
            store.delivered(row["seq"], "retrying", delay, "Rate limited")
        elif response.status_code >= 500:
            store.delivered(
                row["seq"],
                "retrying",
                min(3600, 2 ** min(row["attempts"] + 1, 11)),
                "Server temporarily unavailable",
            )
        else:
            store.delivered(
                row["seq"],
                "failed",
                detail=f"Telegram rejected request (HTTP {response.status_code})",
            )
    except (httpx.ConnectError, httpx.ConnectTimeout):
        store.delivered(
            row["seq"],
            "retrying",
            min(3600, 2 ** min(row["attempts"] + 1, 11)),
            "Connection unavailable",
        )
    except httpx.HTTPError:
        store.delivered(
            row["seq"],
            "uncertain",
            detail="Response lost; inspect Telegram before retrying",
        )
    except Exception:
        store.delivered(
            row["seq"], "failed", detail="Delivery failed; review destination settings"
        )


def poll_acknowledgements(store, profile, client=None):
    """Only replies to accepted incident messages can acknowledge local incidents."""
    if not profile.delivery_enabled or not profile.chat_id:
        return
    token = keyring.get_password(SERVICE, profile.id)
    if not token:
        return
    def poll(session):
        response = session.get(f"https://api.telegram.org/bot{token}/getUpdates", params={
            "offset": store.update_offset(profile.id), "timeout": 0,
            "allowed_updates": '["message"]',
        })
        data = response.json()
        if not response.is_success or not data.get('ok'):
            raise RuntimeError('Telegram reply polling unavailable; check bot webhook or another poller')
        for update in data.get('result', []):
            message = update.get('message', {})
            reply = message.get('reply_to_message', {})
            if ('ACK' in message.get('text', '').upper()
                    and str(message.get('chat', {}).get('id')) == profile.chat_id
                    and not message.get('from', {}).get('is_bot', False)):
                store.ack_reply(profile.id, profile.chat_id,
                    message.get('message_thread_id'), reply.get('message_id'))
            # Advance only after the acknowledgement is durably applied.
            store.update_offset(profile.id, update['update_id'] + 1)
    if client is not None:
        poll(client)
    else:
        with httpx.Client(timeout=5) as session:
            poll(session)
