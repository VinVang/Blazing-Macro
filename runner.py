"""State machine for Ninja Road, relying on game Auto rather than controlling combat."""
from __future__ import annotations

import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Callable

import cv2
import numpy as np

from vision import ImageReader, POINTS, best_rotation, map_number, norm_screen, point_to_screen, stamina_number

LOGS=Path(__file__).resolve().parent/'logs'

class NinjaRoadRunner:
    def __init__(self, area, orientation, dry_run, max_runs, threshold, click_delay,
                 event: Callable[[str, str],None], discord_report=None):
        self.area=tuple(area)
        self.orientation=orientation
        self.dry_run=dry_run
        self.max_runs=max_runs
        self.threshold=threshold
        self.click_delay=click_delay
        self.event=event
        self.discord_report=discord_report
        self.pending_discord_run_number=None
        self.stop_event=threading.Event()
        self.pause_event=threading.Event()
        self.thread=None
        self.reader=ImageReader(threshold)
        self.stage=0
        self.runs=0
        self.failures=0
        self.waiting_for_stamina=False
        self.next_stamina_probe=0.0
        self.rotation=None
        self.last_step=''
        self.last_step_at=0.0
        self.last_seen_at=time.monotonic()
        self.last_results=''
        self.last_results_at=0.0
        self.auto_configuration_warned=False
        self.exp_counted=False  # only count once for each return to Challenge

    def log(self, message): self.event('log',message)
    def status(self, value): self.event('status',value)
    def start(self):
        self.thread=threading.Thread(target=self._main,name='NinjaRoadBot',daemon=True)
        self.thread.start()
    def stop(self): self.stop_event.set()
    def pause(self): self.pause_event.set(); self.status('Paused')
    def resume(self): self.pause_event.clear(); self.status('Running')

    def _wait(self, seconds):
        end=time.monotonic()+seconds
        while time.monotonic()<end:
            if self.stop_event.is_set(): return False
            time.sleep(min(0.15,end-time.monotonic()))
        return not self.stop_event.is_set()

    def _raw_frame(self):
        import mss
        left,top,width,height=self.area
        with mss.mss() as s:
            img=np.asarray(s.grab({'left':left,'top':top,'width':width,'height':height}))
        return cv2.cvtColor(img,cv2.COLOR_BGRA2BGR)

    def _capture(self):
        raw=self._raw_frame()
        if self.rotation is None:
            rot,normal,score=best_rotation(raw,self.reader,self.orientation)
            if self.orientation=='Auto' and score<self.threshold:
                raise RuntimeError('Cannot detect game orientation. Select the exact game display area and try Test Detection, or set rotation manually.')
            self.rotation=rot
            self.log(f'Orientation locked: {rot*90}° clockwise (initial confidence {score:.2f})')
            return normal
        return norm_screen(raw,self.rotation)

    def _click(self, name, delay=None):
        x,y=POINTS[name]
        sx,sy=point_to_screen(x,y,self.area,self.rotation)
        self.log(f'{"[DRY RUN] Would click" if self.dry_run else "Click"}: {name} ({sx}, {sy})')
        if not self.dry_run:
            import pyautogui
            pyautogui.click(sx,sy)
        return self._wait(self.click_delay if delay is None else delay)

    def _step(self, tag, seconds=1.7):
        now=time.monotonic()
        if self.last_step==tag and now-self.last_step_at<seconds: return False
        self.last_step=tag
        self.last_step_at=now
        return True

    def _image_on_error(self):
        try:
            LOGS.mkdir(exist_ok=True)
            f=LOGS/('last-issue-'+datetime.now().strftime('%Y%m%d-%H%M%S')+'.png')
            cv2.imwrite(str(f),self._capture())
            self.log('Saved diagnostic image: '+str(f))
        except Exception as exc:
            self.log(f'Could not save error screenshot: {exc}')

    def _maybe_configure_auto(self, image):
        """Configure Ninjutsu-only even when animations hide the top AUTO bar.

        The AUTO PLAY popup is often visible while the screen classifier calls
        the frame 'unknown'. Handle its options independently of battle_menu
        recognition, and never blindly toggle an indicator.
        """
        visible=self.reader.options_visible(image)
        if visible:
            # Always check and correct the three options first. AUTO button
            # may be covered by an attack animation; that must not prevent us
            # from selecting Ninjutsu.
            correct=True
            for option,needed in (('ninjutsu',True),('secret',False),('latent',False)):
                state=self.reader.option_state(image,option)
                if state is None:
                    correct=False
                    continue
                if state != needed:
                    correct=False
                    if self._step('toggle_'+option,2.5):
                        self.log(f'AUTO Play: {option} is {"ON" if state else "OFF"}; '
                                 f'clicking to turn it {"ON" if needed else "OFF"}.')
                        self._click(option,0.9)
                        return True
            if correct and not self.auto_configuration_warned:
                self.log('AUTO Play: Ninjutsu ON, Secret Techniques OFF, Latent Skill OFF.')
                self.auto_configuration_warned=True
            # Now (not before!) try enabling the main AUTO toggle if definitely
            # disabled. If attack animation obscures it, wait for a clear frame.
            if correct:
                state=self.reader.auto_on(image)
                if state is False and self._step('auto_on',3):
                    self.log('AUTO is OFF; enabling it.')
                    self._click('auto_button')
                    return True
            return False
        state=self.reader.auto_on(image)
        if state is False and self._step('auto_on',3):
            self.log('AUTO is OFF; enabling it.')
            self._click('auto_button')
            return True
        return False

    def _battle_actions(self, image, screen):
        # Stage counter should come from screen OCR if available. If OCR isn't
        # installed we use the observed progression of Next Ready transitions.
        detected=map_number(image)
        if detected is not None:
            if self.stage and abs(self.stage-detected)>1:
                self.status(f'Paused: map counter mismatch (tracked {self.stage}, screen {detected})')
                self.log('Map mismatch. Paused to avoid ending the wrong wave.')
                self.pause_event.set();return
            if detected > self.stage or not self.stage:
                self.stage=detected
                self.event('stage',str(self.stage))
            elif detected < self.stage and self._step('map_counter_lag',30):
                # Never regress the map after clicking Next Ready; a delayed
                # counter redraw or an OCR mistake could otherwise force Map 17.
                self.log(f'Map counter {detected} is behind tracked {self.stage}; using monotonic progression.')

        if self.stage>=16:
            if self._step('quit_at_16',4.0):
                self.log('Reached Map 16/20 (detected or tracked); opening MENU to retreat.')
                self._click('menu_button')
            return

        if screen=='post_retreat':
            # Compare the two user-provided postbattle Ready screenshots.
            # The enabled image still matches the DISABLED template at ~0.88,
            # so relying on a single >=0.87 match would mistakenly retreat.
            # The combined state classifier also checks text brightness.
            ready_enabled=self.reader.post_ready_state(image)
            if ready_enabled is False:
                if self._step('cannot_continue',4.0):
                    self.log('Postbattle Ready is disabled; retreating.')
                    self.failures+=1; self.event('failures',str(self.failures))
                    self._click('post_retreat')
            elif ready_enabled is True:
                if self._step('next_map_ready',4.0):
                    self.log('Postbattle Ready is enabled; advancing.')
                    self._click('next_ready')
                    self.stage+=1
                    self.event('stage',str(self.stage))
            elif self._step('unclear_next_ready',15):
                self.log('Postbattle Ready state uncertain (image templates/brightness disagree); waiting instead of guessing.')
            return

        if screen=='ready_initial':
            if not self.stage:
                self.stage=1
                self.event('stage','1')
            if self._step('initial_ready',4.0):
                self._click('ready_initial',3.0)
            return

        if screen=='battle_menu':
            # The AUTO settings appear at the right side of battle. No tap
            # whatsoever while battling unless one of the toggles is wrong.
            self._maybe_configure_auto(image)

    def _process_results(self, image, screen):
        # Distinguish screens with separate image templates. The center-click
        # animation skip is deliberately done before pressing Next / OK.
        if screen==self.last_results and time.monotonic()-self.last_results_at<5.0:
            return
        self.last_results=screen
        self.last_results_at=time.monotonic()
        self.status('Rewards: '+screen.replace('results_',''))
        for _ in range(3):
            if not self._click('results_middle',0.35): return
        # Don't blindly press Next after the reward screen has changed.
        current=self._capture()
        if not self.reader.present(current,screen):
            self.log('Reward screen changed during animations; re-detecting.')
            return
        self._click('results_advance',2.1)
        if screen=='results_exp' and not self.exp_counted:
            self.exp_counted=True
            self.runs+=1
            self.event('runs',str(self.runs))
            self.log(f'Completed results sequence #{self.runs}.')
            # Do not send the EXP result. Capture the Challenge page AFTER
            # returning to it, before beginning the next run.
            self.pending_discord_run_number=self.runs
            self.stage=0
            self.event('stage','0')
            self.waiting_for_stamina=False

    def _check_stamina(self, image):
        current=stamina_number(image)
        if current is not None:
            self.event('stamina',str(current))
            if current>=20:
                if self._step('stamina_enough',4):
                    self.log(f'Stamina={current} (>=20), restarting Ninja Road.')
                    self.waiting_for_stamina=False
                    self._click('start')
            else:
                self.status(f'Waiting for stamina ({current}/20)')
                if time.monotonic()>=self.next_stamina_probe and self._step('stamina_periodic_probe',4):
                    self.log('Performing periodic safe Start Mission probe in case number recognition was inaccurate.')
                    self.waiting_for_stamina=False
                    self._click('start')
            return
        # No system Tesseract/OCR: safe cooldown before probing Start Mission.
        # The game itself will reject an underfunded start, and we always hit
        # NO, never Yes. This works on every emulator without extra setup.
        if time.monotonic()>=self.next_stamina_probe:
            if self._step('stamina_periodic_probe',4):
                self.log('Could not read stamina number. Safely probing Start Mission; under 20 will be rejected and retried later.')
                self.waiting_for_stamina=False
                self._click('start')
        else:
            left=round(self.next_stamina_probe-time.monotonic())
            self.status(f'Waiting for stamina; safe retry in {left}s (optional OCR improves accuracy)')

    def _main(self):
        try:
            import pyautogui
            pyautogui.FAILSAFE=True  # move mouse to screen top-left to force stop
            pyautogui.PAUSE=0.12
            self.log('Started. Focus the emulator; do not interact while automation is running.')
            self.status('Finding Ninja Road screen')
            initial_state=''
            while not self.stop_event.is_set():
                if self.pause_event.is_set():
                    self._wait(.35)
                    continue
                if self.max_runs and self.runs>=self.max_runs and self.pending_discord_run_number is None:
                    self.log(f'Finished configured run count: {self.runs}.')
                    break
                image=self._capture()
                result=self.reader.identify(image)
                screen=result.name
                if screen!='unknown': self.last_seen_at=time.monotonic()
                if screen!=initial_state:
                    self.log(f'Screen: {screen} (confidence {result.score:.2f})')
                    initial_state=screen
                if self.dry_run:
                    self.status(f'DRY RUN: {screen}')
                elif screen=='stamina_popup':
                    if self._step('stamina_no',2.5):
                        self._click('stamina_no',1.4)
                        self.waiting_for_stamina=True
                        self.next_stamina_probe=time.monotonic()+240
                        self.status('Waiting for 20 stamina')
                elif screen=='retreat_popup':
                    if self._step('retreat_yes',3):
                        self._click('retreat_yes',2.0)
                elif screen=='menu_title':
                    if self._step('menu_retreat',3):
                        self._click('menu_retreat')
                elif screen.startswith('results_'):
                    self._process_results(image,screen)
                elif screen=='start_mission':
                    if self.waiting_for_stamina: self._check_stamina(image)
                    elif self._step('start',4):
                        self.status('Starting a run')
                        self._click('start',2.5)
                elif screen=='challenge':
                    if self.pending_discord_run_number is not None:
                        completed_run=self.pending_discord_run_number
                        self.pending_discord_run_number=None
                        if self.discord_report is not None:
                            try:
                                ok, png=cv2.imencode('.png',image)
                                if ok:
                                    self.discord_report(png.tobytes(), completed_run)
                                else:
                                    self.log('Discord: could not encode Challenge screenshot.')
                            except Exception as exc:
                                self.log(f'Discord: could not prepare Challenge screenshot: {exc}')
                        if self.max_runs and self.runs>=self.max_runs:
                            self.log('Reached run limit; reported final Challenge screenshot, stopping.')
                            break
                    if self.exp_counted:
                        self.exp_counted=False  # next run may count its EXP screen
                    if self.stage:
                        self.stage=0
                        self.event('stage','0')
                    if self._step('challenge',3):
                        self.status('Starting a run')
                        self._click('challenge',2.5)
                elif screen in ('ready_initial','post_retreat'):
                    self._battle_actions(image,screen)
                elif screen=='battle_menu' or self.reader.options_visible(image):
                    # Crucial: the old build only adjusted Ninjutsu when
                    # 'battle_menu' matched. Combat animations frequently hide
                    # the upper menu, leaving AUTO PLAY fully visible below.
                    # Detect the bottom panel independently on every frame.
                    if self.stage>=16:
                        self._battle_actions(image,'battle_menu')
                    else:
                        self._maybe_configure_auto(image)
                else:
                    if time.monotonic()-self.last_seen_at>120:
                        self.log('Unrecognized screen for 2 minutes: paused. Check the game and run Test Detection.')
                        self._image_on_error()
                        self.pause()
                self._wait(1.4)
        except Exception as exc:
            self.log(f'ERROR: {type(exc).__name__}: {exc}')
            self._image_on_error()
        finally:
            self.status('Stopped')
            self.event('stopped','')
