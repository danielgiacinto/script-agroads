@echo off
echo Instalando PyInstaller si no esta instalado...
python -m pip install pyinstaller --quiet

echo.
echo Generando ejecutable...
python -m PyInstaller agroads_bot.spec --noconfirm

echo.
echo Instalando Chromium para Playwright...
cd dist\AgroadsBot
set PLAYWRIGHT_BROWSERS_PATH=%CD%\browsers
python -m playwright install chromium
cd ..\..

echo.
echo Listo. La carpeta dist\AgroadsBot contiene AgroadsBot.exe
echo Coloca en esa carpeta: .env, datos.xlsx y la carpeta fotos\
pause
