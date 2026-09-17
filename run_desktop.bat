@echo off
title OmniDub AI - Desktop Studio
echo =========================================================================
echo             Starting OmniDub AI Desktop Studio (Electron + React)
echo =========================================================================
cd /d "%~dp0frontend"
npm run electron:dev
pause
