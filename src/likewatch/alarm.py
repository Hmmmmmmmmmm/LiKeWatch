"""Read output volume without changing it; alarm playback stays on the UI thread."""
import sys
import subprocess


def output_volume():
    if sys.platform == 'darwin':
        result = subprocess.run(['/usr/bin/osascript', '-e',
            'get {output volume, output muted} of (get volume settings)'],
            capture_output=True, text=True, timeout=3, check=True)
        volume, muted = result.stdout.strip().split(', ')
        return 0 if muted == 'true' else int(volume)
    if sys.platform == 'win32':
        from pycaw.pycaw import AudioUtilities
        endpoint = AudioUtilities.GetSpeakers().EndpointVolume
        return 0 if endpoint.GetMute() else round(endpoint.GetMasterVolumeLevelScalar()*100)
    raise RuntimeError('Output volume unavailable on this platform')
