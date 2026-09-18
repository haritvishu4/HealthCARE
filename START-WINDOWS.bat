@echo off
cd /d "%~dp0"
py scripts\run.py
if errorlevel 1 pause
