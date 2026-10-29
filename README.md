# v1.4 — Discord screenshots between Ninja Road runs and remote `/screenshot`

New in this version:

- **Automatic Discord webhook screenshot**: When a Ninja Road attempt finishes all four results pages and returns to the **Challenge** page, the macro sends a portrait screenshot of the page (including the Granny Cat Coin total). Exactly one notification per completed results sequence, not per map. Also supported for a run limit of 1.
- **Manual webhook test screenshot**: GUI button sends the **selected game region** to the webhook on demand.
- **Remote Discord `/screenshot` slash command**: optional separate Discord bot, restricted to **your Discord user ID** and a configured server/channel. It replies **ephemerally** with a screenshot of the selected game area, from whatever game screen is currently visible, even if farming has stopped while the GUI is open.
- **No arbitrary desktop capture, no remote mouse control.** Keep other windows out of the game region to avoid capturing them by accident.
- **Nonblocking uploads**, Discord connection status in the Activity log, and masked webhook/token GUI fields.

A Discord **incoming webhook can only post messages**, not receive commands. The bot option is required for `/screenshot`. See **`DISCORD-SETUP.md`** for the exact steps to create both and for security cautions. Your bot token and webhook URL are never bundled in the ZIP; when entered they are saved locally in `discord_config.json` in **plain text**, so keep it private.

**Testing disclosure:** Automated offline tests cover screenshot capture bounds, webhook request construction, the one-per-run Challenge trigger, security input checks, and the preexisting battle/image recognition. Real Discord connectivity and live Windows emulator interactions still need testing on your machine.

---

# v1.3 — AUTO PLAY / Ninjutsu recognition fix

**Fix based on your live MuMu screenshot (Map 2/20).** The older build recognized the upper battle menu only while its artwork was visible, and used an overly specific image fragment to locate the AUTO PLAY options. During attack animations the top button was obscured, so it logged “AUTO options panel not visible” and never selected Ninjutsu. The v1.3 build recognizes the **Ninjutsu option box itself**, independent of what the rest of the battle looks like.

- When AUTO PLAY controls appear anywhere in battle, the macro checks the actual selection dots and enables **Ninjutsu only**. If Secret Techniques or Latent Skill are selected, it disables them.
- A shifted selected game area (a few pixels up/down) no longer causes it to sample the wrong part of the option indicator: it finds the panel's exact location first.
- The AUTO toggle is never blindly clicked. If it is obscured by animation, the bot can still configure Ninjutsu, then enable AUTO once the button is visible.
- The **Test detection** button now reports the AUTO PLAY panel and Ninjutsu/Secret/Latent states even if the rest of the battle is classified as `unknown`.

**Updating from v1.2:** Extract v1.3 into its own folder (do not mix files). Run `Run-Windows.bat` and select the game region. On your currently shown Map 2 screenshot, Ninjutsu is OFF (white dot). The v1.3 matcher recognizes the AUTO PLAY panel and should select it. The old screenshots also distinguish orange Ninjutsu ON from white OFF. These checks are local screenshot tests, not verification of live mouse input.

# Naruto Blazing Revival — Ninja Road Macro v1.2 (Upright / Portrait)

A downloadable **Windows Python macro with a graphical interface** built from the Ninja Road screenshots supplied in this conversation. It uses the visible **PC screen and simulated mouse clicks**, **not ADB**. It is not tied to MuMu, BlueStacks, LDPlayer, or any other emulator.

This is an independent implementation inspired by the easy-launch workflow of [BlazingAutomation](https://github.com/MrScopes/BlazingAutomation), **not a copy** of its code. Unlike the earlier generic template-training prototype, **this build already includes cropped reference images from your actual Ninja Road screenshots**.

## Run it

1. Extract **every file** from the ZIP to a regular folder (for example, your Desktop).
2. If you don't already have it, install **Python 3.10 or later** from [python.org](https://www.python.org/downloads/). Check **Add Python to PATH** during installation if prompted. Python must include Tkinter (default on Windows).
3. Open Naruto Blazing Revival in your emulator, and leave the game on the **Ninja Road screen with the red Challenge button** (or on its Team Selection screen).
4. Double-click **`Run-Windows.bat`**. On the first launch, this creates a `.venv` folder and downloads Python dependencies from PyPI. On later launches, it goes directly to the app.
5. Select which **display** contains your emulator. Press **Select game area**. Drag a rectangle over the visible **upright (portrait) game picture only**, with the same orientation as the screenshot you supplied (roughly 9:16). Do not include the window title bar, emulator toolbar, or black borders.
6. Select **Test detection** and verify it reads `challenge` (or `start_mission`). Keep **Screen rotation = Auto**. An upright emulator capture is recognized at **0°**, with no rotation needed; old sideways game captures are still supported.
7. **Dry run** is enabled at first. To actually click, **uncheck Dry run**, then press **Start**. You can Pause, Resume, and Stop from the app.
8. Set the **Run limit** to `0` for repeated farming until stopped, or a positive number for a limited number of completed result sequences.

**Keep the game visible and unobstructed.** Do not resize the emulator or move it after selecting the area. The program can adapt to different resolutions or 90° rotations but needs the game crop to remain the same during a session. To emergency-stop the clicks, move the mouse to the top-left of the main display (PyAutoGUI failsafe).

## Exact intended Ninja Road flow

| Game state | Macro behavior |
| --- | --- |
| Ninja Road starting page | Click **Challenge** |
| Team Selection | Click **Start Mission** |
| Initial battle setup | Click **Ready!!!** |
| AUTO disabled (white dot) | Click **AUTO** |
| AUTO enabled (yellow/orange dot) | **Leave AUTO alone** |
| Auto Play options visible | Select **Ninjutsu ON**, **Secret Techniques OFF**, **Latent Skill OFF** |
| During battle | Let the game's **built-in Auto** play |
| Post-battle, Ready available | Compare the new **enabled Ready!!** image and bright lettering; click Ready to advance |
| Post-battle, Ready disabled | Compare the **disabled Ready!!** image and dim lettering; click Retreat |
| Map 16/20 reached | **MENU → Retreat → Yes** (do not advance to 17) |
| Retreat popup | Click **Yes** |
| Mission Results | Click screen center 3×, then **Next** |
| Map Rewards | Click screen center 3×, then **Next** |
| Final Rewards | Click screen center 3×, then **Next** |
| Character EXP | Click screen center 3×, then **OK** |
| Returns to Ninja Road page | Restart at **Challenge** |
| Not Enough Stamina popup | Click **No**, never **Yes** / never spend Ninja Pearls |
| After insufficient stamina | Wait for stamina regeneration, then try Start Mission again |

### How it knows the current stage

The app **tracks map progression** from the Ninja Road start and every successful `Ready!!` transition. If **Tesseract OCR** is installed, it also tries to read the live `MAP 16/20` number for a cross-check. Since the only reference screenshots currently available show Map 1/20 and 13/20, stage reading without Tesseract relies on the tracker's progression rather than a visual Map 16/20 template. **Always begin a new run from the Challenge or Team Selection screen**; starting in the middle of a run may confuse the count.

### How it handles stamina

The supplied images include the **Not Enough Stamina** popup. The macro recognizes it and automatically clicks **No**. It then remains on Team Selection:

- If **Tesseract OCR** is installed and the stamina number can be read, it waits until the visible number is **at least 20** before pressing Start Mission.
- Without a usable OCR result, it makes a **safe Start Mission attempt roughly every four minutes**, rather than requiring any external OCR installation. If stamina is still insufficient, the game reopens the popup, it clicks **No**, and the wait repeats. This **does not spend Ninja Pearls**, but may restart slightly after the exact moment stamina reaches 20.

To enable optional direct numeric reading, install **Tesseract OCR for Windows** (the standard Windows installer by UB Mannheim) in `C:\Program Files\Tesseract-OCR\`. `pytesseract` (the Python wrapper) is installed by the launcher. OCR is optional and sometimes misreads the game's ornate numeric font; a timed safe attempt is retained as a fallback.

## v1.2 update — Portrait reference images

All bundled reference images are now **upright like your latest example**. The matching grid is now **900×1600 portrait**. Mouse targets, AUTO indicator sampling, menu buttons, results buttons, numeric stamina/map OCR zones, and Ready enabled/disabled classification were all migrated to the portrait coordinate system. A portrait screenshot is detected at **0°** by default; landscape/sideways screenshots can still be auto-rotated to the portrait grid.

The game-area selector now explicitly asks for the **portrait game picture**, rather than the former 16:9 landscape wording. A newly supplied upright Challenge screenshot was used to confirm the detection path; automated tests verify the upright templates and all four image orientations. This is not a live emulator validation.

## v1.1 update — Ready detection

Added the **Ready!! enabled** screenshot supplied later, alongside the existing disabled image. This prevents a bug where the brighter enabled button could still score highly against the old disabled-only template and incorrectly trigger Retreat. When the two references disagree, the macro waits rather than guessing.

## Important limits (read before leaving unattended)

- **The source code and matching assets have been checked against the screenshots provided**, but **I can't test mouse input in your live emulator** from here. The first live run should be supervised and have Dry run disabled only after checking Test Detection.
- **Post-battle Ready ON and OFF screenshots are both included** as cropped reference templates. The bot checks both images **and** the text brightness before choosing Ready or Retreat. These cases pass screenshot-based tests at several simulated display sizes; real-emulator testing is still needed.
- Some screens contain animated backgrounds or updates that may change the assets. Use **Test detection** to diagnose if the app stops recognizing the game.
- Auto Play options may be hidden depending on game state. The app changes options **only if their panel is actually visible**; otherwise it logs a warning. You can open/set the options once manually if necessary.
- The game must be visible and the selected crop kept stable. Overlay windows, changing display scaling while running, or minimizing the emulator may prevent image recognition.
- This is *Ninja Road only* — Phantom Castle, Impact and Resource stages are intentionally **not included** yet.
- If no screen is recognized for 120 seconds, the app pauses and saves a diagnostic image in `logs/`. Screenshots and other data stay local on your PC.
- The project's UI only uses mouse clicks; it cannot ensure teams can win a difficult Ninja Road map on Auto.
- Check your community server's policies on automation before running it.

## Troubleshooting

**It doesn't recognize anything:** Make sure the selected rectangle includes the entire game picture but excludes emulator/OS UI. Try full-screen game view and Test detection again. Auto-rotation works by image matching.

**It clicks in the wrong place:** Re-select the game area precisely. The reference screenshots and templates are now 900×1600 upright; the program scales and, only when needed, rotates your selected area, but any cropped game edges or included title bar will throw coordinates off. Avoid moving the window while running.

**AUTO controls aren't configured:** Wait until the Auto Play settings panel is visible, or toggle options manually once. The app won't click unknown controls.

**It isn't advancing after a won map:** Use Test Detection and review the log. The app compares both enabled and disabled Ready reference images, and deliberately waits if confidence is low. Send the saved log/screenshot for tuning if needed.

**Stamina isn't displayed numerically in the macro:** Tesseract OCR is optional. The timed safe retry works without it. The game must still be open and not minimized.

**Missing dependency / Python error:** Rerun `Run-Windows.bat` with internet access; if needed delete `.venv` and rerun. Run `python -m unittest discover -s tests -v` after installing requirements to check basic image matching logic.

## Folder contents

```
Run-Windows.bat      # double-click Windows launcher
app.py               # Tkinter GUI
runner.py            # Ninja Road and stamina state machine
vision.py            # image recognition, crop rotation and numeric reading
assets/              # trained templates from your screenshots
requirements.txt     # dependencies installed by launcher
QuickStart.txt       # installation in 60 seconds
README.md            # this guide
logs/                # local diagnostic screenshots if an error happens
```
