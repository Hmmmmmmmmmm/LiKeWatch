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
        store.delivered(row['seq'], 'failed', detail='Credential store unavailable')
        return
    if not token:
        store.delivered(row['seq'], 'failed', detail='No bot token in OS credential store')
        return
    payload = {'chat_id': row['chat'], 'text': row['body']}
    if row['topic']:
        payload['message_thread_id'] = int(row['topic'])
    try:
        if client is None:
            with httpx.Client(timeout=12) as owned:
                response = owned.post(f'https://api.telegram.org/bot{token}/sendMessage', json=payload)
        else:
            response = client.post(f'https://api.telegram.org/bot{token}/sendMessage', json=payload)
        try:
            data = response.json()
        except ValueError:
            store.delivered(row['seq'], 'uncertain', detail='Unrecognized server response; acceptance unknown')
            return
        if response.is_success and data.get('ok'):
            store.delivered(row['seq'], 'accepted', detail='Accepted by Telegram API')
        elif response.status_code == 429 or data.get('error_code') == 429:
            delay = max(1, min(86400, int(data.get('parameters', {}).get('retry_after', 30))))
            store.delivered(row['seq'], 'retrying', delay, 'Rate limited')
        elif response.status_code >= 500:
            store.delivered(row['seq'], 'retrying', min(3600, 2**min(row['attempts']+1, 11)), 'Server temporarily unavailable')
        else:
            store.delivered(row['seq'], 'failed', detail=f"Telegram rejected request (HTTP {response.status_code})")
    except (httpx.ConnectError, httpx.ConnectTimeout):
        store.delivered(row['seq'], 'retrying', min(3600, 2**min(row['attempts']+1, 11)), 'Connection unavailable')
    except httpx.HTTPError:
        store.delivered(row['seq'], 'uncertain', detail='Response lost; inspect Telegram before retrying')
    except Exception:
        store.delivered(row['seq'], 'failed', detail='Delivery failed; review destination settings')
