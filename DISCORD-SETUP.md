# Discord setup for Ninja Road Macro v1.4

The two Discord features use **different Discord mechanisms**:

- **Incoming webhook** (no bot): automatically posts a portrait screenshot of the Ninja Road **Challenge** page **once after each completed results sequence**, before the macro clicks Challenge again. This lets you see the running Granny Cat Coin total.
- **Discord bot** (optional, requires a bot token): provides the private `/screenshot` command. You can use this from Discord on your phone or another PC **while the macro application remains open on your gaming PC**, and it captures the current **selected game area**, regardless of which game screen is showing. The bot does **not** control your PC or capture the entire desktop.

**A webhook URL alone cannot receive slash commands.** To ask for a screenshot remotely, you need the bot.

## Part A — Automatically upload the Challenge screenshot after each run

1. In a private channel of your Discord server, choose **Edit Channel → Integrations → Webhooks → New Webhook** (labels vary). Copy the **Webhook URL**.
2. Launch the macro with `Run-Windows.bat`. Select the *portrait game area*, as before.
3. In **4 · Discord screenshots**, paste the URL in **Webhook URL**. The entry is masked for privacy.
4. Check **Send after every run** and click **Save Discord settings**.
5. Click **Send test screenshot** to check whether a picture arrives. If it fails, inspect the macro's Activity log for HTTP errors.
6. Run Ninja Road as usual. After retreating and passing through all the results/EXP screens, when it returns to Challenge, the macro will **queue one screenshot** tagged with the run number. It does not upload after every battle/map.

The sender runs on a separate thread so the macro doesn't block on Discord network delays. Keep the macro app running until the Activity log reports that the image was sent. The image shows the total Granny Cat Coin value; the app does not attempt OCR transcription of this value.

## Part B — Remote `/screenshot` command

1. Open [Discord Developer Portal](https://discord.com/developers/applications), create an application, and create a **Bot** for it. Copy its **bot token**. Keep the token private.
2. In the application’s **Installation** / OAuth2 settings, generate an install URL for **Guild Install** with scopes **`bot`** and **`applications.commands`**. Give it at least **View Channels**, **Send Messages** and **Attach Files** where appropriate. Invite it to your server. You do *not* need the privileged **Message Content Intent** for slash commands.
3. In Discord **User Settings → Advanced**, enable **Developer Mode**. Right-click your server to **Copy Server ID**, right-click your own account to **Copy User ID**. Optional: right-click a channel to **Copy Channel ID** to restrict commands to that channel.
4. In the macro's Discord section, paste **Bot token**, **Server ID**, **Your User ID**, and optionally **Channel ID**. Click **Save Discord settings**.
5. Click **Connect Discord bot**. Wait for `Discord bot: /screenshot command synced to server` and `Discord bot connected` in Activity log.
6. In that server, from the authorized account, type **`/screenshot`**. The bot sends you an **ephemeral/private reply with the current game-region screenshot**. No one else can request an image from this bot using this command. There is a 10-second cooldown.
7. Optionally check **Auto-connect bot** so the bot starts when you launch the application the next time. For remote access, **the app must remain running and your PC must be awake, online, and displaying the emulator in the selected rectangle**. The Ninja Road farming loop itself can be stopped; the bot can still respond while the GUI remains open.

You can run Part A without Part B, or Part B without Part A.

## Security and troubleshooting

- **Only your configured Discord user ID** is authorized to run `/screenshot`. If you set a Channel ID, it's additionally limited to that channel. Unauthorized requests get `Not authorized.` The image reply is ephemeral.
- The capture area is **only the rectangle you select**, never the entire monitor. Keep unrelated windows away from that rectangle: screenshots will include anything visible inside it, even if the emulator is covered.
- The bot is **read-only** (remote commands do not click or control Windows). Only `/screenshot` is provided.
- **Never publish** your webhook URL, bot token, or `discord_config.json`. This local file stores secrets **in plain text** so the app can restart easily; it is not included in the downloadable ZIP. Keep the extracted folder in your private user directory. If exposed, rotate the token in the Developer Portal and delete/recreate the webhook.
- The app must stay running to send reports or answer slash commands. Discord requires an internet connection.
- If `/screenshot` does not appear: verify server ID, that the bot was invited with `applications.commands`, and that Activity log says it synced successfully. Try restarting bot connection. If Discord says **Missing Permissions**, check the bot's channel access and Attach Files permission.
- If `Send test screenshot` works but run reports do not, wait until the **Character EXP → OK → Challenge** transition; the notification is sent there, not on each map.
- Automatic reports, Discord bot and secret storage are optional. **No tokens/webhooks are included with the application.**

## Start-up

Extract the ZIP, double-click **`Run-Windows.bat`**. First launch automatically creates `.venv` and installs Python libraries (`requests` and `discord.py` included). Windows requires Python 3.10+. As with previous builds, leave the emulator visible, select its game area and disable Dry Run before starting farming.
