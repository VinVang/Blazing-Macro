"""Offline tests (never contact Discord)."""
import io
import sys
from pathlib import Path
from unittest.mock import Mock, patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

import cv2
import numpy as np

from discord_integration import validate_webhook, post_webhook, capture_game_png, parse_id, ScreenshotBot
from runner import NinjaRoadRunner


def test_webhook_url_only_official_discord():
    good='https://discord.com/api/webhooks/123456789012345678/abc-XYZ_123'
    assert validate_webhook(good)
    assert validate_webhook('https://discord.com/api/v10/webhooks/123456789012345678/ABC')
    for url in ('http://discord.com/api/webhooks/1/x',
                'https://discord.com.evil.com/api/webhooks/1/xxx',
                'https://example.com/a',
                'file:///etc/passwd',
                'https://discord.com/api/webhooks/123/token/extra'):
        assert not validate_webhook(url), url


def test_id_validation():
    assert parse_id('123456789012345678','ID')==123456789012345678
    import pytest
    with pytest.raises(ValueError):parse_id('abc','ID')


def test_webhook_posts_png_and_never_echoes_url():
    url='https://discord.com/api/webhooks/123456789012345678/tokenxyz'
    res=Mock(status_code=204)
    with patch('requests.post',return_value=res) as post:
        post_webhook(url,b'pngbytes','A message')
        args, kwargs=post.call_args
        assert args[0]==url
        assert kwargs['files']['file'][1]==b'pngbytes'
        assert 'allowed_mentions' in kwargs['data']['payload_json']


def test_region_capture_uses_selected_rectangle_only(monkeypatch):
    import sys
    class MSS:
        def __enter__(self): return self
        def __exit__(self,*args):return None
        def grab(self, rectangle):
            assert rectangle=={'left':12,'top':34,'width':400,'height':700}
            return np.zeros((700,400,4),np.uint8)
    class FakeModule:
        def mss(self):return MSS()
    monkeypatch.setitem(sys.modules,'mss',FakeModule())
    data=capture_game_png([12,34,400,700],'Auto')
    img=cv2.imdecode(np.frombuffer(data,np.uint8),1)
    assert img.shape[:2]==(1600,900)


def test_bot_requires_owner_ids():
    # No real Discord process starts during this test.
    import pytest
    with pytest.raises(ValueError):
        ScreenshotBot('x'*50,'badid','123456789012345678','',lambda:b'x',print)


def test_results_schedule_challenge_report_and_only_once():
    reports=[]
    runner=NinjaRoadRunner([0,0,900,1600],'0°',False,1,.8,.0,
           lambda *args:None,discord_report=lambda pic,run: reports.append((pic,run)))
    # When EXP results complete the report is PENDING, not sent on EXP.
    runner._click=lambda name,delay=None:True
    runner._capture=lambda:np.zeros((1600,900,3),np.uint8)
    runner.reader.present=lambda img,screen:True
    runner._process_results(runner._capture(),'results_exp')
    assert runner.runs==1 and runner.pending_discord_run_number==1
    assert reports==[]


def test_end_to_end_report_on_challenge_not_exp(monkeypatch):
    # Simulated sequence: results EXP, then main Challenge page; should capture
    # once before next run and, with max_runs=1, stop without clicking Challenge.
    reports=[]
    events=[]
    runner=NinjaRoadRunner([0,0,900,1600],'0°',False,1,.8,0,
                           lambda kind,value:events.append((kind,value)),
                           discord_report=lambda pic,run:reports.append((pic,run)))
    runner.rotation=0
    clicks=[]
    runner._click=lambda name,delay=None:clicks.append(name) or True
    runner._wait=lambda seconds:True
    screens=iter(('results_exp','challenge'))
    from types import SimpleNamespace
    runner.reader.identify=lambda image:SimpleNamespace(name=next(screens),score=.99)
    runner.reader.present=lambda image,name:True
    runner._capture=lambda:np.zeros((1600,900,3),np.uint8)
    monkeypatch.setitem(sys.modules,'pyautogui',SimpleNamespace(FAILSAFE=False,PAUSE=0))
    runner._main()
    assert len(reports)==1 and reports[0][1]==1
    assert reports[0][0].startswith(b'\x89PNG')
    assert 'challenge' not in clicks
    assert runner.runs==1
