@echo off
setlocal DisableDelayedExpansion
"%PREFIX%\python.exe" -I -B "%PREFIX%\manager\post_install.py" "%PREFIX%"
if errorlevel 1 exit /b 1
endlocal
