import io
import time
import os
import httpx
import pytest
from PIL import Image
from likewatch.storage import Store
from likewatch.profiles import demo_profile, save, load
from likewatch.capture import demo_frame
from likewatch.snapshots import incident_snapshot
from likewatch.messaging import deliver, poll_acknowledgements


def configured(tmp_path, monkeypatch):
    monkeypatch.setattr('likewatch.messaging.keyring.get_password',lambda *_:'SECRET')
    profile=demo_profile()
    profile.delivery_enabled=True
    profile.local_alarm=True
    profile.chat_id='123'
    profile.topic_id='7'
    return Store(tmp_path/'db'), profile


def test_photo_delivery_html_and_reply_ack(tmp_path,monkeypatch):
    store,p=configured(tmp_path,monkeypatch)
    picture=incident_snapshot(demo_frame(),p.regions)
    image=Image.open(io.BytesIO(picture))
    assert image.height > 200 and image.width >= 640
    store.enqueue(p,'ALERT','Rule: a < b & c',incident='incident',rule=p.rules[0],attachment=picture)
    def send(request):
        assert request.url.path.endswith('/sendPhoto')
        assert b'parse_mode' in request.content and b'HTML' in request.content
        assert b'&lt;' in request.content and b'&amp;' in request.content
        assert b'incident.jpg' in request.content
        return httpx.Response(200,json={'ok':True,'result':{'message_id':42}})
    with httpx.Client(transport=httpx.MockTransport(send)) as client:
        deliver(store,p.id,client)
    assert store.pending_alarms(p.id)==['incident']
    def updates(request):
        assert request.url.params['offset']=='0'
        return httpx.Response(200,json={'ok':True,'result':[
            {'update_id':8,'message':{'chat':{'id':123},'message_thread_id':7,'text':'ACK received','reply_to_message':{'message_id':42}}}
        ]})
    with httpx.Client(transport=httpx.MockTransport(updates)) as client:
        poll_acknowledgements(store,p,client)
    assert not store.pending_alarms(p.id)
    assert store.history(p.id)[0]['acknowledged']==1
    assert store.update_offset(p.id)==9


@pytest.mark.parametrize('chat,topic,reply,is_bot',[(999,7,42,False),(123,8,42,False),(123,7,99,False),(123,7,42,True)])
def test_unrelated_reply_does_not_ack(tmp_path,monkeypatch,chat,topic,reply,is_bot):
    store,p=configured(tmp_path,monkeypatch)
    store.enqueue(p,'ALERT','test',incident='incident',rule=p.rules[0])
    row=store.claim(p.id)
    store.delivered(row['seq'],'accepted',message_id=42)
    response={'ok':True,'result':[{'update_id':1,'message':{'chat':{'id':chat},'message_thread_id':topic,'from':{'is_bot':is_bot},'text':'ACK','reply_to_message':{'message_id':reply}}}]}
    with httpx.Client(transport=httpx.MockTransport(lambda _:httpx.Response(200,json=response))) as client:
        poll_acknowledgements(store,p,client)
    assert store.pending_alarms(p.id)==['incident']


def test_plain_delivery_escapes_html_and_test_needs_no_route(tmp_path,monkeypatch):
    store,p=configured(tmp_path,monkeypatch)
    p.routes=[]
    store.enqueue(p,'TEST','<b>untrusted</b>')
    row=store.claim(p.id)
    assert row and row['rich']==1 and '&lt;b&gt;' in row['body']
    assert '<b>TEST</b>' in row['body']


def test_caption_stays_valid_with_long_unicode(tmp_path,monkeypatch):
    import html
    import re
    store,p=configured(tmp_path,monkeypatch)
    store.enqueue(p,'ALERT','<&😀'*1000,attachment=b'photo')
    row=store.claim(p.id)
    plain=html.unescape(re.sub('<[^>]*>','',row['body']))
    assert len(plain.encode('utf-16-le'))//2 <= 1024
    assert row['body'].endswith('</code>')


def test_snapshot_insets_have_separate_tiles():
    from dataclasses import replace
    import numpy as np
    from likewatch.domain import Region
    frame=np.zeros((100,200,3),np.uint8)
    frame[:,:100]=(0,0,255)
    frame[:,100:]=(255,0,0)
    regions=[Region('red',[[0,0],[.49,0],[.49,1],[0,1]]),Region('blue',[[.51,0],[1,0],[1,1],[.51,1]])]
    image=Image.open(io.BytesIO(incident_snapshot(frame,regions)))
    red=image.getpixel((160,210));blue=image.getpixel((480,210))
    assert red[0]>200 and red[2]<20
    assert blue[2]>200 and blue[0]<20


def test_new_settings_persist_without_delivery_or_token(tmp_path):
    p=demo_profile();p.attach_snapshot=True;p.local_alarm=True;p.delivery_enabled=True
    save(p,tmp_path/'config.json')
    result=load(tmp_path/'config.json')
    assert result.attach_snapshot and result.local_alarm
    assert not result.delivery_enabled
    assert 'token' not in (tmp_path/'config.json').read_text()


def test_startup_log_retention(tmp_path):
    from datetime import datetime,timedelta
    from likewatch.diagnostics import prune_logs
    old=datetime.now()-timedelta(days=8)
    now=datetime.now()
    fmt=lambda d:d.strftime('%Y-%m-%d %H:%M:%S,000')
    log=tmp_path/'application.log'
    log.write_text(fmt(old)+' INFO old\nold traceback\n'+fmt(now)+' INFO new\n')
    native=tmp_path/'native-123.log';native.write_text('old')
    os.utime(native,(old.timestamp(),old.timestamp()))
    unrelated=tmp_path/'user-file.txt';unrelated.write_text('keep')
    prune_logs(tmp_path)
    assert 'old' not in log.read_text() and 'new' in log.read_text()
    assert not native.exists() and unrelated.exists()
