# Install LiKeWatch 0.1

## Windows 10/11 x64
Download `LiKeWatch-0.1-Windows-x64-portable.exe` and launch it from a writable
folder. No Python, Tesseract, administrator install, or separate OCR download is
needed. The single executable extracts its runtime to a temporary folder at
launch. Profiles/history live in your local application-data directory.

The executable is not Authenticode-signed. Windows may show an unknown-publisher
prompt. Check the release source and SHA-256 before choosing to run it.

## macOS 15 or newer, Apple Silicon
Open `LiKeWatch-0.1-macOS-arm64.dmg`, drag LiKeWatch to Applications, then launch.
This release is locally ad-hoc signed, not Apple Developer ID signed or notarized.
If macOS blocks it, use System Settings → Privacy & Security → Open Anyway for
the downloaded application you have verified. Do not disable Gatekeeper globally.

Camera access and screen recording need OS permission. Enable LiKeWatch under
Privacy & Security → Camera and Screen & System Audio Recording as applicable,
then quit/reopen it. The app does not request camera/screen access in demo mode.

## First run
1. Choose **Snapshot** in Demo mode. The two demo readings should be 83.2 and 18.4.
2. Choose camera, screen, or Open image. Set the camera/monitor index in Settings.
3. Take a snapshot, then **+ Region**. Click top-left, top-right, bottom-right,
   bottom-left. Choose number/text, unit, confidence threshold and preprocessing.
4. Select **Edit corners on frozen frame** to drag the selected region's handles.
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
