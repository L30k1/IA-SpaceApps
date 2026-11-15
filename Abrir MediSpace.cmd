@echo off
setlocal
pushd "%~dp0" || exit /b 1
python "%~dp0Abrir MediSpace.pyw"
if errorlevel 1 pause
popd
