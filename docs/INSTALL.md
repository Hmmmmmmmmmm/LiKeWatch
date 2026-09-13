# Install LiKeWatch

## Windows 10/11 x64
Download [LiKeWatch-0.2.0-Windows-x64-portable.exe](https://github.com/Hmmmmmmmmmm/LiKeWatch/releases/download/v0.2/LiKeWatch-0.2.0-Windows-x64-portable.exe) and double-click it.
No installer or archive extraction is required. No Python, Tesseract, administrator install, or separate OCR download is
needed. The single executable extracts its runtime to a temporary folder at
launch. Profiles/history live in your local application-data directory.

The executable is not Authenticode-signed. Windows may show an unknown-publisher
prompt. Check the release source and SHA-256 before choosing to run it.

## macOS 15 or newer, Apple Silicon
Open `LiKeWatch-0.2.0-macOS-arm64.dmg`, drag LiKeWatch to Applications, then launch.
This release is locally ad-hoc signed, not Apple Developer ID signed or notarized.
If macOS blocks it, use System Settings → Privacy & Security → Open Anyway for
the downloaded application you have verified. Do not disable Gatekeeper globally.

Camera access and screen recording need OS permission. Enable LiKeWatch under
Privacy & Security → Camera and Screen & System Audio Recording as applicable,
then quit/reopen it. The app does not request camera/screen access in demo mode.

Keep the installed app in `/Applications` or your local `~/Applications` folder,
not in a cloud-synced folder. When upgrading, replace the old Applications copy
and point launchers to the updated app so an older version is not opened by mistake.

## First run
1. Choose **Snapshot** in Demo mode, then **Trigger OCR on still image**.
   The two demo readings should be 83.2 and 18.4.
2. Choose camera, screen, or Open image. Set the camera/monitor index in Settings.
3. Take a snapshot, then **+ Region**. Click top-left, top-right, bottom-right,
   bottom-left. Choose number/text, unit, confidence threshold and preprocessing.
4. Select **Edit corners on frozen frame** to drag the selected region's handles.
   Clicking a variable selects its region with a thicker border at every zoom level.
5. Add conditions with nested AND/OR groups. Configure consecutive samples and,
   if required, a separate recovery condition for hysteresis.
6. Start monitoring. Events remain local until delivery is enabled.
7. Enter Telegram bot token and chat/topic ID in Settings. Enable desired routes
   and outbound delivery, then press Test send. Routine data additionally needs
   a nonzero interval and the DATA route enabled.

Tokens are saved in Keychain / Windows Credential Locker. Imported profiles and
application restarts always disable outbound delivery until explicitly enabled.
Acknowledge records review; it does not clear an incident. Uncertain delivery
requires checking Telegram before an explicit retry, which may duplicate a message.

This is an assistive monitoring tool. Qualify OCR on the actual fonts, viewing
geometry and lighting before relying on its readings. Perspective correction
cannot restore glare-obscured characters or missing decimal points.

After changing a source or its resolution, existing variables show SOURCE_ERROR.
Verify placement on the new snapshot, then edit the variable or drag its corners
to bind it to that source. Re-select regions if the content moved. This prevents
old camera coordinates from silently becoming readings on another screen.
