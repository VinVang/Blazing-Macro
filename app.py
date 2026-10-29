"""Windows-friendly Tk GUI for Ninja Road screen automation."""
from __future__ import annotations

import json
import queue
import sys
import time
from pathlib import Path

import cv2
import numpy as np
import tkinter as tk
from tkinter import messagebox, ttk
from PIL import Image, ImageTk

from runner import NinjaRoadRunner
from discord_integration import (DEFAULT_DISCORD, load_discord, save_discord,
    capture_game_png, validate_webhook, parse_id, WebhookSender, ScreenshotBot)
from vision import ImageReader, best_rotation, map_number, stamina_number

ROOT_DIR=Path(__file__).resolve().parent
CONFIG=ROOT_DIR/'settings.json'
DEFAULTS={'area':None,'orientation':'Auto','display':0,'dry_run':True,
          'threshold':0.80,'click_delay':1.0,'max_runs':0}


def load_config():
    obj=DEFAULTS.copy()
    if CONFIG.exists():
        try:
            data=json.loads(CONFIG.read_text(encoding='utf-8'))
            if isinstance(data,dict): obj.update(data)
        except Exception: pass
    return obj


class RegionPicker(tk.Toplevel):
    def __init__(self, owner, monitor, on_picked):
        super().__init__(owner)
        self.withdraw()
        self.title('Select the visible game area')
        self.on_picked=on_picked
        self.monitor=monitor
        self.start=None
        self.box=None
        import mss
        from PIL import Image
        # Hide the launcher for the snapshot so the game behind it is visible.
        owner.withdraw()
        owner.update_idletasks()
        time.sleep(0.4)
        try:
            with mss.mss() as s:
                raw=np.array(s.grab(monitor))[:,:,:3][:,:,::-1].copy()
        finally:
            owner.deiconify()
        src=Image.fromarray(raw)
        # Fit monitor screenshot to a manageable view (no input scaling assumptions).
        width=min(1240,max(650,owner.winfo_screenwidth()-110))
        height=min(740,max(360,owner.winfo_screenheight()-200))
        scale=min(width/src.width,height/src.height,1.0)
        self.scale=scale
        self.pimage=ImageTk.PhotoImage(src.resize((round(src.width*scale),round(src.height*scale))))
        ttk.Label(self,text='Drag from the top-left to bottom-right of the GAME IMAGE (exclude emulator borders, tabs, toolbars).').pack(pady=(7,3))
        self.canvas=tk.Canvas(self,width=self.pimage.width(),height=self.pimage.height(),
                              cursor='crosshair',highlightthickness=1,highlightbackground='#999')
        self.canvas.pack(padx=10,pady=7)
        self.canvas.create_image(0,0,image=self.pimage,anchor='nw')
        self.canvas.bind('<ButtonPress-1>',self.on_down)
        self.canvas.bind('<B1-Motion>',self.on_move)
        self.canvas.bind('<ButtonRelease-1>',self.on_up)
        self.info=ttk.Label(self,text='No selection yet. Use the buttons below to confirm.')
        self.info.pack(pady=3)
        commands=ttk.Frame(self);commands.pack(pady=8)
        ttk.Button(commands,text='Use selected area',command=self.accept).pack(side='left',padx=5)
        ttk.Button(commands,text='Use entire display',command=self.full).pack(side='left',padx=5)
        ttk.Button(commands,text='Cancel',command=self.destroy).pack(side='left',padx=5)
        self.selection=None
        self.transient(owner)
        self.deiconify()
        self.grab_set()
        self.protocol('WM_DELETE_WINDOW',self.destroy)

    def on_down(self,event):
        self.start=(event.x,event.y)
        if self.box is not None:self.canvas.delete(self.box)
        self.box=self.canvas.create_rectangle(event.x,event.y,event.x,event.y,outline='#f23d3d',width=3)

    def on_move(self,event):
        if self.start is not None:
            x,y=self.start
            self.canvas.coords(self.box,x,y,event.x,event.y)

    def on_up(self,event):
        if self.start is None:return
        x,y=self.start
        x1,x2=sorted((x,event.x));y1,y2=sorted((y,event.y))
        if x2-x1<120 or y2-y1<80:
            self.selection=None
            self.info.config(text='Selection too small; drag a larger rectangle.')
            return
        m=self.monitor;s=self.scale
        self.selection=(m['left']+int(x1/s),m['top']+int(y1/s),
                        int((x2-x1)/s),int((y2-y1)/s))
        self.info.config(text=f'Selected: {self.selection[2]} × {self.selection[3]} pixels')

    def accept(self):
        if not self.selection:
            messagebox.showwarning('Area not selected','Drag a rectangle around the game first.',parent=self)
            return
        self.on_picked(self.selection)
        self.destroy()

    def full(self):
        m=self.monitor
        self.on_picked((m['left'],m['top'],m['width'],m['height']))
        self.destroy()


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('Blazing Revival — Ninja Road Macro v1.4 (Discord)')
        self.geometry('890x880')
        self.minsize(760,750)
        self.config_data=load_config()
        self.worker=None
        self.events=queue.Queue()
        self.discord_data=load_discord()
        self.discord_sender=WebhookSender(lambda msg:self.events.put(('log',msg)))
        self.discord_bot=None
        self._create_ui()
        self.after(200,self._pump)
        self.protocol('WM_DELETE_WINDOW',self._on_close)
        if self.discord_data.get('bot_autostart'):
            self.after(1000,self.start_discord_bot)

    def _create_ui(self):
        p=ttk.Frame(self,padding=14);p.pack(fill='both',expand=True)
        ttk.Label(p,text='NARUTO BLAZING REVIVAL  |  NINJA ROAD',font=('Segoe UI',17,'bold')).pack(anchor='w')
        ttk.Label(p,text='Screen-recognition macro — works with MuMu, BlueStacks, LDPlayer and other visible game windows.',wraplength=770).pack(anchor='w',pady=(0,12))

        box=ttk.LabelFrame(p,text='1 · Select the game image',padding=9)
        box.pack(fill='x',pady=4)
        row=ttk.Frame(box);row.pack(fill='x')
        ttk.Label(row,text='Display:').pack(side='left')
        try:
            import mss
            with mss.mss() as s:self.displays=list(s.monitors[1:])
        except Exception:
            self.displays=[]
        display_labels=[f'Display {i+1}  ({a["width"]}×{a["height"]})' for i,a in enumerate(self.displays)]
        self.display=ttk.Combobox(row,values=display_labels,state='readonly',width=29)
        if display_labels:self.display.current(min(int(self.config_data.get('display',0)),len(display_labels)-1))
        self.display.pack(side='left',padx=(8,10))
        ttk.Button(row,text='Select game area…',command=self.pick_area).pack(side='left',padx=3)
        ttk.Button(row,text='Test detection',command=self.test).pack(side='left',padx=3)
        self.area_label=ttk.Label(box,text='Game area: '+str(self.config_data.get('area') or 'NOT SET'))
        self.area_label.pack(anchor='w',pady=(6,0))
        ttk.Label(box,text='Important: keep the emulator visible, and capture the upright 9:16 GAME picture only (no borders).').pack(anchor='w')

        opts=ttk.LabelFrame(p,text='2 · Macro settings',padding=9)
        opts.pack(fill='x',pady=7)
        row=ttk.Frame(opts);row.pack(fill='x',pady=2)
        self.orientation=tk.StringVar(value=self.config_data.get('orientation','Auto'))
        ttk.Label(row,text='Rotation:').pack(side='left')
        ttk.Combobox(row,textvariable=self.orientation,state='readonly',width=21,
                     values=['Auto','0°','90° clockwise','180°','90° counterclockwise']).pack(side='left',padx=(7,26))
        self.run_count=tk.StringVar(value=str(self.config_data.get('max_runs',0)))
        ttk.Label(row,text='Run limit (0 = forever):').pack(side='left')
        ttk.Entry(row,textvariable=self.run_count,width=7).pack(side='left',padx=6)
        row2=ttk.Frame(opts);row2.pack(fill='x',pady=(5,2))
        self.dry_run=tk.BooleanVar(value=self.config_data.get('dry_run',True))
        ttk.Checkbutton(row2,text='Dry run (recognize but do not click)',variable=self.dry_run).pack(side='left')
        self.confidence=tk.StringVar(value=str(self.config_data.get('threshold',0.80)))
        ttk.Label(row2,text='Match threshold:').pack(side='left',padx=(24,4))
        ttk.Entry(row2,textvariable=self.confidence,width=6).pack(side='left')
        ttk.Label(opts,text='Safety: never spends Ninja Pearls. On insufficient stamina: clicks No, waits, then retries.').pack(anchor='w',pady=(6,0))

        action=ttk.LabelFrame(p,text='3 · Run Ninja Road',padding=9)
        action.pack(fill='x',pady=6)
        buttons=ttk.Frame(action);buttons.pack(fill='x')
        self.start_button=ttk.Button(buttons,text='▶  Start',command=self.start)
        self.start_button.pack(side='left',padx=4)
        self.pause_button=ttk.Button(buttons,text='Ⅱ  Pause',command=self.pause,state='disabled')
        self.pause_button.pack(side='left',padx=4)
        self.continue_button=ttk.Button(buttons,text='▶  Resume',command=self.resume,state='disabled')
        self.continue_button.pack(side='left',padx=4)
        self.stop_button=ttk.Button(buttons,text='■  Stop',command=self.stop,state='disabled')
        self.stop_button.pack(side='left',padx=4)
        self.status_label=ttk.Label(action,text='Status: Not running',font=('Segoe UI',10,'bold'))
        self.status_label.pack(anchor='w',pady=(8,2))
        stats=ttk.Frame(action);stats.pack(fill='x')
        self.map_label=ttk.Label(stats,text='Current map: —',width=21)
        self.map_label.pack(side='left')
        self.runs_label=ttk.Label(stats,text='Runs: 0',width=16)
        self.runs_label.pack(side='left')
        self.failures_label=ttk.Label(stats,text='Failures: 0',width=16)
        self.failures_label.pack(side='left')
        self.stamina_label=ttk.Label(stats,text='Stamina: —')
        self.stamina_label.pack(side='left')

        discord_box=ttk.LabelFrame(p,text='4 · Discord screenshots (optional)',padding=7)
        discord_box.pack(fill='x',pady=6)
        self.webhook=tk.StringVar(value=self.discord_data.get('webhook_url',''))
        self.bot_token=tk.StringVar(value=self.discord_data.get('bot_token',''))
        self.guild_id=tk.StringVar(value=str(self.discord_data.get('guild_id','')))
        self.user_id=tk.StringVar(value=str(self.discord_data.get('user_id','')))
        self.channel_id=tk.StringVar(value=str(self.discord_data.get('channel_id','')))
        self.send_between=tk.BooleanVar(value=bool(self.discord_data.get('send_between_runs',False)))
        self.bot_autostart=tk.BooleanVar(value=bool(self.discord_data.get('bot_autostart',False)))
        drow=ttk.Frame(discord_box); drow.pack(fill='x',pady=2)
        ttk.Label(drow,text='Webhook URL:').pack(side='left')
        ttk.Entry(drow,textvariable=self.webhook,width=57,show='•').pack(side='left',padx=8,fill='x',expand=True)
        ttk.Checkbutton(drow,text='Send after every run',variable=self.send_between).pack(side='left')
        drow2=ttk.Frame(discord_box); drow2.pack(fill='x',pady=3)
        ttk.Label(drow2,text='Bot token:').pack(side='left')
        ttk.Entry(drow2,textvariable=self.bot_token,width=35,show='•').pack(side='left',padx=(8,12))
        ttk.Label(drow2,text='Server ID:').pack(side='left')
        ttk.Entry(drow2,textvariable=self.guild_id,width=23).pack(side='left',padx=5)
        drow3=ttk.Frame(discord_box); drow3.pack(fill='x',pady=3)
        ttk.Label(drow3,text='Your User ID:').pack(side='left')
        ttk.Entry(drow3,textvariable=self.user_id,width=23).pack(side='left',padx=5)
        ttk.Label(drow3,text='Channel ID (optional):').pack(side='left',padx=(10,0))
        ttk.Entry(drow3,textvariable=self.channel_id,width=23).pack(side='left',padx=5)
        ttk.Checkbutton(drow3,text='Auto-connect bot',variable=self.bot_autostart).pack(side='left',padx=(9,0))
        dbuttons=ttk.Frame(discord_box); dbuttons.pack(fill='x',pady=4)
        ttk.Button(dbuttons,text='Save Discord settings',command=self.save_discord_settings).pack(side='left',padx=4)
        ttk.Button(dbuttons,text='Send test screenshot',command=self.send_test_discord).pack(side='left',padx=4)
        self.discord_start_btn=ttk.Button(dbuttons,text='Connect Discord bot',command=self.start_discord_bot)
        self.discord_start_btn.pack(side='left',padx=4)
        self.discord_stop_btn=ttk.Button(dbuttons,text='Disconnect bot',command=self.stop_discord_bot)
        self.discord_stop_btn.pack(side='left',padx=4)
        ttk.Label(discord_box,text='Webhook = automatic uploads. /screenshot = separate Discord bot; only YOUR user ID can use it. Captures selected game area only.').pack(anchor='w')
        ttk.Label(discord_box,text='Keep discord_config.json private — it contains your webhook and bot token.',foreground='#a64b00').pack(anchor='w')

        console=ttk.LabelFrame(p,text='Activity log',padding=5)
        console.pack(fill='both',expand=True,pady=5)
        self.output=tk.Text(console,height=11,wrap='word',state='disabled',font=('Consolas',9))
        bar=ttk.Scrollbar(console,command=self.output.yview)
        self.output.configure(yscrollcommand=bar.set)
        bar.pack(side='right',fill='y')
        self.output.pack(fill='both',expand=True)
        ttk.Label(p,text='TIP: Start from the Ninja Road Challenge page or Team Selection. Move your mouse to the screen’s top-left for PyAutoGUI emergency stop.',wraplength=790).pack(anchor='w',pady=(4,0))
        self.log('Ready. Pick the visible game area, then Test detection. Dry run is initially enabled for safety.')

    def log(self,message):
        self.output.configure(state='normal')
        self.output.insert('end',time.strftime('%H:%M:%S')+'  '+str(message)+'\n')
        self.output.see('end')
        self.output.configure(state='disabled')

    def pick_area(self):
        if not self.displays:
            messagebox.showerror('Missing module','Run the Windows launcher first to install screen-capture dependencies.')
            return
        RegionPicker(self,self.displays[max(self.display.current(),0)],self.set_area)

    def set_area(self,area):
        self.config_data['area']=list(area)
        self.area_label.config(text='Game area: '+str(area))
        self.save()

    def save(self):
        self.config_data.update({'orientation':self.orientation.get(),'display':max(0,self.display.current()),
                                'dry_run':self.dry_run.get()})
        try:
            self.config_data['max_runs']=int(self.run_count.get())
            self.config_data['threshold']=float(self.confidence.get())
        except ValueError:pass
        CONFIG.write_text(json.dumps(self.config_data,indent=2),encoding='utf-8')

    def _settings_valid(self):
        area=self.config_data.get('area')
        if not area or any(n<=0 for n in area[2:]):
            messagebox.showwarning('Select game area','Press Select game area first.')
            return False
        try:
            runs=int(self.run_count.get());score=float(self.confidence.get())
            if runs<0 or runs>100000:raise ValueError('run limit must be 0 to 100000')
            if not .68<=score<=.97:raise ValueError('confidence must be between 0.68 and 0.97')
        except ValueError as exc:
            messagebox.showerror('Invalid settings',str(exc));return False
        return True

    def _capture(self):
        import mss
        area=self.config_data['area']
        with mss.mss() as s:raw=np.asarray(s.grab({'left':area[0],'top':area[1],
                                                 'width':area[2],'height':area[3]}))
        return cv2.cvtColor(raw,cv2.COLOR_BGRA2BGR)

    def test(self):
        if not self._settings_valid():return
        self.save()
        try:
            reader=ImageReader(float(self.confidence.get()))
            raw=self._capture()
            rotation,frame,score=best_rotation(raw,reader,self.orientation.get())
            found=reader.identify(frame)
            stamina=stamina_number(frame)
            wave=map_number(frame)
            panel=reader.options_visible(frame)
            auto=reader.auto_on(frame) if reader.present(frame,'battle_menu') or panel else None
            choices={key:reader.option_state(frame,key) for key in ('ninjutsu','secret','latent')} if panel else None
            self.log(f'Test: {found.name} ({found.score:.3f}), rotation={rotation*90}°, stamina={stamina}, map={wave}, AUTO={auto}, AUTO PLAY panel={panel}, options={choices}')
            if found.name=='unknown' and not panel:
                messagebox.showwarning('No screen recognized',
                    f'No trained screen matched (top confidence {score:.2f}).\n\n'
                    'Select the game picture more precisely, keep the game visible, or choose a rotation manually.\n'
                    'This build has reference images for the screens you supplied.')
            else:
                messagebox.showinfo('Recognition test',
                    f'Screen: {found.name}\nConfidence: {found.score:.2f}\n'
                    f'Rotation: {rotation*90}° clockwise\n'
                    f'Stamina: {stamina if stamina is not None else "OCR unavailable / unreadable"}\n'
                    f'Map: {wave if wave is not None else "tracked during runs"}\n'
                    f'AUTO: {auto if auto is not None else "not visible"}\n'
                    f'AUTO PLAY panel: {panel}\nOptions: {choices}')
        except Exception as exc:
            self.log('Test error: '+repr(exc))
            messagebox.showerror('Detection failed',str(exc))

    def _discord_options(self):
        return {
            'webhook_url': self.webhook.get().strip(),
            'send_between_runs': self.send_between.get(),
            'bot_token': self.bot_token.get().strip(),
            'guild_id': self.guild_id.get().strip(),
            'user_id': self.user_id.get().strip(),
            'channel_id': self.channel_id.get().strip(),
            'bot_autostart': self.bot_autostart.get(),
        }

    def save_discord_settings(self):
        settings=self._discord_options()
        if settings['webhook_url'] and not validate_webhook(settings['webhook_url']):
            messagebox.showerror('Discord webhook', 'Enter a valid https://discord.com/api/webhooks/... URL.')
            return False
        if settings['send_between_runs'] and not settings['webhook_url']:
            messagebox.showerror('Discord webhook', 'Enter a webhook URL before enabling automatic run screenshots.')
            return False
        try:
            if settings['bot_autostart'] or (settings['bot_token'] and (settings['guild_id'] or settings['user_id'])):
                if not settings['bot_token']:
                    raise ValueError('A bot token is required for auto-connect.')
                parse_id(settings['guild_id'], 'Server ID')
                parse_id(settings['user_id'], 'Your User ID')
                if settings['channel_id']:
                    parse_id(settings['channel_id'], 'Channel ID')
        except ValueError as exc:
            messagebox.showerror('Discord settings', str(exc))
            return False
        self.discord_data=settings
        try:
            save_discord(settings)
            self.log('Saved Discord settings locally (not included in downloads).')
            return True
        except OSError as exc:
            messagebox.showerror('Saving failed', str(exc))
            return False

    def _capture_for_discord(self):
        # Obtain a region-only screenshot; no desktop-wide capture.
        area=self.config_data.get('area')
        if not area:
            raise ValueError('Select game area in the app first.')
        # Use the farming macro's locked rotation when available.
        rotation=self.worker.rotation if self.worker else None
        return capture_game_png(area, self.config_data.get('orientation','Auto'), rotation)

    def _report_challenge(self, png_bytes, run_number):
        settings=self.discord_data
        if not (settings['send_between_runs'] and settings['webhook_url']):
            return
        self.discord_sender.enqueue(settings['webhook_url'], png_bytes,
            f'🍥 **Ninja Road — Run #{run_number} complete!**\n'
            'Challenge screen / current total Granny Cat Coins:')

    def send_test_discord(self):
        if not self._settings_valid(): return
        if not self.save_discord_settings(): return
        url=self.webhook.get().strip()
        if not url:
            messagebox.showwarning('Missing webhook', 'Add a Discord webhook URL to send test images.')
            return
        try:
            self.save()
            pic=self._capture_for_discord()
            if self.discord_sender.enqueue(url,pic,'🍥 **Blazing Revival — manual game screenshot test**'):
                self.log('Queued test game-area screenshot for Discord.')
        except Exception as exc:
            self.log('Discord screenshot error: '+str(exc))
            messagebox.showerror('Discord screenshot failed',str(exc))

    def start_discord_bot(self):
        if self.discord_bot and self.discord_bot.thread and self.discord_bot.thread.is_alive():
            self.log('Discord bot already connected or connecting.')
            return
        if not self._settings_valid(): return
        if not self.save_discord_settings(): return
        settings=self._discord_options()
        try:
            self.discord_bot=ScreenshotBot(
                settings['bot_token'],settings['guild_id'],settings['user_id'],
                settings['channel_id'],capture=self._capture_for_discord,
                log=lambda msg:self.events.put(('log',msg)))
            self.discord_bot.start()
            self.log('Discord bot connecting; /screenshot available once synced.')
        except Exception as exc:
            messagebox.showerror('Discord bot setup',str(exc))

    def stop_discord_bot(self):
        if self.discord_bot:
            self.discord_bot.stop()
            self.log('Disconnecting Discord bot…')

    def start(self):
        if self.worker and self.worker.thread and self.worker.thread.is_alive():return
        if not self._settings_valid():return
        self.save()
        if not self.save_discord_settings():return
        self.worker=NinjaRoadRunner(area=self.config_data['area'],
                     orientation=self.orientation.get(),dry_run=self.dry_run.get(),
                     max_runs=int(self.run_count.get()),threshold=float(self.confidence.get()),
                     click_delay=1.0,event=lambda typ,val:self.events.put((typ,val)),
                     discord_report=self._report_challenge)
        self.start_button.configure(state='disabled')
        self.pause_button.configure(state='normal')
        self.stop_button.configure(state='normal')
        self.continue_button.configure(state='disabled')
        self.worker.start()

    def pause(self):
        if self.worker:self.worker.pause()
        self.pause_button.configure(state='disabled')
        self.continue_button.configure(state='normal')

    def resume(self):
        if self.worker:self.worker.resume()
        self.pause_button.configure(state='normal')
        self.continue_button.configure(state='disabled')

    def stop(self):
        if self.worker:self.worker.stop()
        self.log('Stopping macro…')

    def _pump(self):
        try:
            while True:
                typ,value=self.events.get_nowait()
                if typ=='log':self.log(value)
                elif typ=='status':self.status_label.config(text='Status: '+value)
                elif typ=='stage':self.map_label.config(text='Current map: '+str(value)+'/20')
                elif typ=='runs':self.runs_label.config(text='Runs: '+value)
                elif typ=='failures':self.failures_label.config(text='Failures: '+value)
                elif typ=='stamina':self.stamina_label.config(text='Stamina: '+value)
                elif typ=='stopped':
                    self.start_button.configure(state='normal')
                    self.pause_button.configure(state='disabled')
                    self.continue_button.configure(state='disabled')
                    self.stop_button.configure(state='disabled')
        except queue.Empty:pass
        self.after(200,self._pump)

    def _on_close(self):
        if self.worker:self.worker.stop()
        if self.discord_bot:self.discord_bot.stop()
        self.save()
        self.destroy()


def main():
    if sys.platform=='win32':
        # Coordinate system of MSS and PyAutoGUI must agree with Windows scaling.
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            try:ctypes.windll.user32.SetProcessDPIAware()
            except Exception:pass
    root=App()
    root.mainloop()


if __name__=='__main__':main()
