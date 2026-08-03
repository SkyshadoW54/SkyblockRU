@echo off
setlocal
rem %~dp0 ends with a backslash, so cd /d "%~dp0" breaks quote parsing.
rem pushd handles it, and gradlew is called by full path anyway.
pushd "%~dp0" || (echo Cannot enter script folder & pause & exit /b 1)

rem Target mods folder. MultiMC instance first, official launcher as fallback.
rem Change this line if the instance is renamed or moved.
set "MODS=C:\MultiMC\instances\26.2\.minecraft\mods"
if not exist "%MODS%" set "MODS=%APPDATA%\.minecraft\mods"

rem WARNING: with Stonecutter there is one build per game version, and they
rem live in versions\<version>\build\libs. Install the one this instance runs.
rem Build ONLY that target: plain "gradlew build" would build every version,
rem including 1.21.x, turning seconds into minutes.
set "TARGET=26.2"
set "LIBS=%~dp0versions\%TARGET%\build\libs"

echo [1/2] Building mod for %TARGET%...
call "%~dp0gradlew.bat" ":%TARGET%:build" --console=plain
if errorlevel 1 goto buildfail

if not exist "%MODS%" mkdir "%MODS%"

rem WARNING: a running game HOLDS the jar, and "copy" fails without saying so.
rem This cost a whole evening: every Java fix looked like it did not work,
rem while the real reason was that the file never reached the instance.
rem The build kept printing DONE, so nothing pointed at copying at all.
rem
rem ASK THE FILE, NOT THE PROCESS LIST.
rem
rem History of this check, because both earlier forms were wrong in a way
rem that looked right:
rem   1. by image name - java.exe and javaw.exe. The Gradle daemon is java.exe
rem      too, so right after a build the script refused to copy while the game
rem      was closed.
rem   2. by command line - any process carrying "minecraft" or "MultiMC".
rem      That still asks the wrong question. It blocked copying while the
rem      player was inside ANOTHER instance (26.1.1) whose jar we never touch,
rem      and the fix for a 26.2 crash could not be installed at all.
rem
rem The question was never "is a game running". It is "is THIS jar locked",
rem and the file itself answers it exactly - no guessing from command lines,
rem no assumption about which launcher started the game. MultiMC does not even
rem put the instance path into the command line (verified: only "natives" is
rem there), so the process list cannot answer it in the first place.
rem
rem Opening for WRITE with no sharing is the same thing "copy" will do a moment
rem later, so a pass here means the copy can land. The size check below stays
rem as the second line: copy can still report success while doing nothing.
set "LOCKED=0"
for /f %%R in ('powershell -NoProfile -Command "$bad=0; foreach ($f in @(Get-ChildItem -LiteralPath '%MODS%' -Filter 'skyblockru-*.jar' -ErrorAction SilentlyContinue)) { try { $s=[IO.File]::Open($f.FullName,'Open','Write','None'); $s.Close() } catch { $bad=1 } }; $bad"') do set "LOCKED=%%R"
if "%LOCKED%"=="1" goto gamerunning

:docopy
echo [2/2] Copying to %MODS%

rem WARNING: copy the NEWEST jar only, and wipe old ones first.
rem The mask "skyblockru-*.jar" used to copy EVERY build. After a test build
rem for another game version the instance held two jars with the same mod id
rem (26.1.2 and 26.2) - Fabric may refuse to load or pick the wrong one.
rem The player found it, not us: nothing in the build ever complained.
del /Q "%MODS%\skyblockru-*.jar" >nul 2>&1
set "JAR="
for /f "delims=" %%F in ('dir /b /o-d "%LIBS%\skyblockru-*.jar" 2^>nul') do if not defined JAR set "JAR=%%F"
if not defined JAR goto copyfail
copy /Y "%LIBS%\%JAR%" "%MODS%\" >nul
if errorlevel 1 goto copyfail

rem Verify the copy actually landed: compare sizes, not the exit code.
rem "copy" can report success while Windows keeps the old file locked.
rem The name is taken from the jar we just copied - a hard-coded version
rem would silently skip the check as soon as the version changes.
for %%F in ("%LIBS%\%JAR%") do set "SRCSIZE=%%~zF"
for %%F in ("%MODS%\%JAR%") do set "DSTSIZE=%%~zF"
if not "%SRCSIZE%"=="%DSTSIZE%" goto sizemismatch

echo.
echo ==== DONE ====
echo Mod installed to %MODS%
echo Fabric API for 26.2 must be in the same folder.
echo The MultiMC instance must have Fabric installed (Version tab).
echo.
popd
pause
exit /b 0

:buildfail
echo.
echo BUILD FAILED - see build_log.txt
popd
pause
exit /b 1

:copyfail
echo.
echo COPY FAILED - close Minecraft and try again
popd
pause
exit /b 1

:gamerunning
echo.
echo ==== THE JAR IN THE INSTANCE IS LOCKED ====
echo Something holds it open, so copying would fail SILENTLY:
echo the old mod stays in the instance and every fix looks like it did nothing.
echo.
echo Almost always this is the game running from THIS instance. Close Minecraft
echo completely - leaving the server is not enough - and run this again.
popd
pause
exit /b 1

:sizemismatch
echo.
echo ==== COPY DID NOT LAND ====
echo Source is %SRCSIZE% bytes, the file in the instance is %DSTSIZE%.
echo The old jar is still there - most likely Minecraft is holding it.
echo Close the game completely and run this again.
popd
pause
exit /b 1
