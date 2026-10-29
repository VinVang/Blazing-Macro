"""Opt-in Discord integration: one-way webhook reports and restricted slash command.

Only the user-selected game rectangle is captured, never the whole desktop.
Incoming webhooks cannot accept commands: the slash command uses a Discord bot.
"""
from __future__ import annotations

import asyncio
import io
import json
import queue
import re
import threading
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit
from typing import Callable

import cv2
import numpy as np

DISCORD_CONFIG = Path(__file__).resolve().parent / 'discord_config.json'
DEFAULT_DISCORD = {
    'webhook_url': '',
    'send_between_runs': False,
    'bot_token': '',
    'guild_id': '',
    'user_id': '',
    'channel_id': '',
    'bot_autostart': False,
}


def load_discord():
    result = DEFAULT_DISCORD.copy()
    if DISCORD_CONFIG.is_file():
        try:
            obj = json.loads(DISCORD_CONFIG.read_text(encoding='utf-8'))
            if isinstance(obj, dict):
                result.update({k: v for k, v in obj.items() if k in result})
        except (OSError, json.JSONDecodeError):
            pass
    return result


def save_discord(settings):
    obj = {k: settings.get(k, value) for k, value in DEFAULT_DISCORD.items()}
    DISCORD_CONFIG.write_text(json.dumps(obj, indent=2), encoding='utf-8')
    # Windows permissions inherit from user's profile, avoid putting this folder
    # in a shared location; on POSIX restrict access for convenience.
    import os
    if os.name != 'nt':
        DISCORD_CONFIG.chmod(0o600)


def validate_webhook(url):
    """Refuse to POST screenshots/tokens to non-Discord hosts."""
    parts = urlsplit((url or '').strip())
    if parts.scheme != 'https' or parts.netloc not in ('discord.com', 'discordapp.com'):
        return False
    return bool(re.fullmatch(r'/api/(?:v\d+/)?webhooks/\d+/[\w.-]+', parts.path)) and not parts.username and not parts.password


def parse_id(value, label):
    text = str(value or '').strip()
    if not re.fullmatch(r'\d{15,22}', text):
        raise ValueError(f'{label} must be a Discord numeric ID (15–22 digits).')
    return int(text)


def capture_game_png(area, orientation='Auto', rotation=None):
    """Capture ONLY selected game region and encode upright game image as PNG.

    When Auto rotation has not yet been locked by the macro, the selected
    portrait region is assumed upright (0°), as recommended by the setup UI.
    """
    import mss
    from vision import norm_screen
    if not area or len(area) != 4:
        raise ValueError('Select game area first.')
    x, y, width, height = map(int, area)
    if width < 120 or height < 120 or width > 10000 or height > 10000:
        raise ValueError('Selected game rectangle is invalid.')
    with mss.mss() as s:
        raw = np.asarray(s.grab({'left': x, 'top': y, 'width': width, 'height': height}))
    raw = cv2.cvtColor(raw, cv2.COLOR_BGRA2BGR)
    if rotation is None:
        rotations = {'0°': 0, '90° clockwise': 1,
                     '180°': 2, '90° counterclockwise': 3}
        rotation = rotations.get(orientation, 0 if height >= width else 1)
    picture = norm_screen(raw, rotation)
    ok, encoded = cv2.imencode('.png', picture)
    if not ok:
        raise RuntimeError('PNG encoding failed.')
    return encoded.tobytes()


def post_webhook(url: str, png_bytes: bytes, caption: str):
    """Send a single PNG attachment to an existing Discord incoming webhook."""
    import requests
    if not validate_webhook(url):
        raise ValueError('Webhook URL must be an official discord.com/api/webhooks/ URL.')
    payload = {'username': 'Blazing Revival — Ninja Road',
               'content': caption[:1900],
               'allowed_mentions': {'parse': []}}
    filename = datetime.now().strftime('ninja-road-%Y%m%d-%H%M%S.png')
    response = requests.post(
        url, data={'payload_json': json.dumps(payload)},
        files={'file': (filename, png_bytes, 'image/png')},
        timeout=25,
    )
    # Don't show response body: it might contain sensitive setup information.
    if response.status_code not in (200, 204):
        raise RuntimeError(f'Discord webhook rejected image (HTTP {response.status_code}).')


class WebhookSender:
    """Nonblocking bounded queue so network delays don't interrupt battles."""
    def __init__(self, log: Callable[[str], None]):
        self.log = log
        self.jobs = queue.Queue(maxsize=5)
        self.thread = threading.Thread(target=self._work, name='DiscordWebhook', daemon=True)
        self.thread.start()

    def enqueue(self, url: str, image: bytes, message: str):
        if not validate_webhook(url):
            self.log('Discord: invalid webhook URL; cannot upload screenshot.')
            return False
        try:
            self.jobs.put_nowait((url, image, message))
            return True
        except queue.Full:
            self.log('Discord: screenshot queue full; skipped notification.')
            return False

    def _work(self):
        while True:
            item = self.jobs.get()
            try:
                post_webhook(*item)
                self.log('Discord: screenshot sent to webhook.')
            except Exception as exc:
                self.log(f'Discord: screenshot upload failed: {type(exc).__name__}: {exc}')
            finally:
                self.jobs.task_done()


class ScreenshotBot:
    """Slash-command listener, only for the explicitly allowed user and server.

    The bot is a separate thread and works independently from the farming loop.
    """
    def __init__(self, token, guild_id, user_id, channel_id,
                 capture: Callable[[], bytes], log: Callable[[str], None]):
        self.token = (token or '').strip()
        self.guild = parse_id(guild_id, 'Server ID')
        self.user = parse_id(user_id, 'Your Discord User ID')
        self.channel = parse_id(channel_id, 'Channel ID') if str(channel_id).strip() else None
        if not self.token or len(self.token) < 25:
            raise ValueError('Discord bot token is missing or too short.')
        self.capture = capture
        self.log = log
        self.thread = None
        self.client = None
        self.last_command = 0.0
        self._rate_lock = threading.Lock()

    def start(self):
        if self.thread and self.thread.is_alive():
            return
        self.thread = threading.Thread(target=self._run, name='DiscordSlashBot', daemon=True)
        self.thread.start()

    def _run(self):
        try:
            import discord
            from discord import app_commands
            owner = self
            guild_obj = discord.Object(id=self.guild)

            class Client(discord.Client):
                def __init__(self):
                    super().__init__(intents=discord.Intents.default())
                    self.tree = app_commands.CommandTree(self)
                    self.tree.add_command(app_commands.Command(
                        name='screenshot',
                        description='Privately capture the selected Blazing Revival game area.',
                        callback=owner._on_screenshot,
                    ), guild=guild_obj)

                async def setup_hook(self):
                    # Guild commands sync promptly; global commands can take longer.
                    await self.tree.sync(guild=guild_obj)
                    owner.log('Discord bot: /screenshot command synced to server.')

                async def on_ready(self):
                    owner.log('Discord bot connected. Use /screenshot from your authorized account.')

            self.client = Client()
            self.client.run(self.token, log_handler=None)
        except Exception as exc:
            self.log(f'Discord bot: {type(exc).__name__}: {exc}')
        finally:
            self.client = None
            self.log('Discord bot disconnected.')

    async def _on_screenshot(self, interaction):
        # Authorization is enforced inside code; slash-command visibility alone
        # does NOT constitute security. Never remotely click or operate the PC.
        if (interaction.guild_id != self.guild or interaction.user.id != self.user or
            (self.channel and interaction.channel_id != self.channel)):
            await interaction.response.send_message('Not authorized.', ephemeral=True)
            return
        with self._rate_lock:
            now = time.monotonic()
            limited = (now - self.last_command < 10)
            if not limited:
                self.last_command = now
        if limited:
            await interaction.response.send_message('Wait 10 seconds between screenshots.', ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            png_bytes = await asyncio.to_thread(self.capture)
            import discord
            await interaction.followup.send(
                content='Current Blazing Revival game area (private screenshot):',
                file=discord.File(io.BytesIO(png_bytes), filename='blazing-current.png'),
                ephemeral=True)
            self.log('Discord bot: delivered a private /screenshot.')
        except Exception as exc:
            self.log(f'Discord screenshot failed: {type(exc).__name__}: {exc}')
            await interaction.followup.send('Could not capture the selected game area. Check that the emulator is visible and the region is still valid.', ephemeral=True)

    def stop(self):
        client = self.client
        if client is not None and not client.is_closed():
            try:
                asyncio.run_coroutine_threadsafe(client.close(), client.loop)
            except (RuntimeError, AttributeError):
                pass
