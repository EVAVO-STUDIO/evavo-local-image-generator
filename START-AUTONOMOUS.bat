@echo off
REM EVAVO Quick Start - Windows Batch File
REM Single command to start complete autonomous system

setlocal enabledelayedexpansion

echo.
echo ======================================================================
echo   EVAVO AUTONOMOUS IMAGE GENERATION
echo ======================================================================
echo.

REM Change to repository directory
cd /d "C:\Gitrepos\evavo-local-image-generator"

if errorlevel 1 (
    echo ERROR: Repository not found at C:\Gitrepos\evavo-local-image-generator
    pause
    exit /b 1
)

REM Run PowerShell automation
echo Starting complete automation system...
echo.

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "& '.\MASTER-AUTOMATION-CONTROLLER.ps1' -Mode Full"

if errorlevel 1 (
    echo.
    echo AUTOMATION FAILED - Check logs at: C:\Gitrepos\evavo-logs\
    pause
    exit /b 1
)

echo.
echo ======================================================================
echo   GENERATION COMPLETE
echo ======================================================================
echo.
echo Images saved to: C:\Gitrepos\evavo-generations\
echo Logs saved to: C:\Gitrepos\evavo-logs\
echo.
pause
