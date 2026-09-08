# PyInstaller build: native wheels supply the OCR libraries on each platform.
from pathlib import Path
import sys
from PyInstaller.utils.hooks import collect_all, collect_submodules

root = Path(SPECPATH)
tess_data,tess_bins,tess_hidden=collect_all('tesserocr')
cy_data,cy_bins,cy_hidden=collect_all('cysignals')
a=Analysis([str(root/'scripts/launch.py')],pathex=[str(root/'src')],
    binaries=tess_bins+cy_bins,
    datas=tess_data+cy_data+[(str(root/'assets'),'assets'),(str(root/'build/licenses'),'licenses/dependencies'),(str(root/'vendor/scoresight/LICENSE'),'licenses/scoresight'),(str(root/'THIRD_PARTY_NOTICES.md'),'.')],
    hiddenimports=tess_hidden+cy_hidden+collect_submodules('keyring.backends'),
    excludes=['PySide6.QtWebEngineCore','PySide6.QtWebEngineWidgets','PySide6.QtQml','PySide6.QtQuick','matplotlib','pandas','pytest'],
    noarchive=False)
pyz=PYZ(a.pure)
if sys.platform == 'darwin':
    exe=EXE(pyz,a.scripts,[],exclude_binaries=True,name='LiKeWatch',console=False,
        argv_emulation=False, codesign_identity=None,
        entitlements_file=str(root/'assets/entitlements.plist'))
    coll=COLLECT(exe,a.binaries,a.datas,strip=False,upx=False,name='LiKeWatch')
    app=BUNDLE(coll,name='LiKeWatch.app',bundle_identifier='com.likewatch.desktop',
        info_plist={'CFBundleShortVersionString':'0.1.0','CFBundleVersion':'1',
            'NSCameraUsageDescription':'LiKeWatch reads selected regions from your camera to monitor values.',
            'NSScreenCaptureUsageDescription':'LiKeWatch reads selected regions from your screen to monitor values.',
            'NSHighResolutionCapable':True,'LSMinimumSystemVersion':'15.0'})
else:
    exe=EXE(pyz,a.scripts,a.binaries,a.datas,[],name='LiKeWatch',console=False,strip=False,upx=False)
