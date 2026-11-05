@echo off
REM ============================================================================
REM  refrescar_screener.bat - Refresca en Neon los datos del screener desde ESTE PC
REM  (Yahoo bloquea las IP de la nube; desde casa responde).
REM
REM  Uso:  doble clic                -> IBEX 35, estructural + fundamental
REM        refrescar_screener.bat todos            -> todos los indices
REM        refrescar_screener.bat "IBEX 35" fundamental
REM        refrescar_screener.bat "IBEX 35" ambos auto   (sin pausa final, para tareas)
REM
REM  La conexion a Neon se lee de la variable de entorno DATABASE_URL.
REM  NUNCA escribas la cadena de conexion en este archivo: el repositorio es publico.
REM ============================================================================
setlocal
chcp 65001 >nul
cd /d "%~dp0"

set "INDICE=%~1"
if "%INDICE%"=="" set "INDICE=IBEX 35"
set "NIVEL=%~2"
if "%NIVEL%"=="" set "NIVEL=ambos"
set "MODO=%~3"

if not defined DATABASE_URL (
    echo No esta definida la variable DATABASE_URL.
    echo Para no tener que pegarla cada vez, guardala una sola vez con:
    echo     setx DATABASE_URL "postgresql://...cadena de Neon..."
    echo y abre una consola nueva.
    if /i "%MODO%"=="auto" exit /b 3
    set /p "DATABASE_URL=Pega ahora la cadena de conexion de Neon y pulsa Enter: "
)
if not defined DATABASE_URL (
    echo Sin cadena de conexion no se puede continuar.
    if /i not "%MODO%"=="auto" pause
    exit /b 3
)

echo.
echo Refrescando screener: indice=%INDICE%  nivel=%NIVEL%
echo (el registro se guarda tambien en la carpeta logs)
echo.
if /i "%INDICE%"=="todos" (
    python cron_fundamentales.py --nivel %NIVEL% --origen pc --log-dir logs
) else (
    python cron_fundamentales.py --indice "%INDICE%" --nivel %NIVEL% --origen pc --log-dir logs
)
set "RC=%ERRORLEVEL%"
echo.
if "%RC%"=="0" (echo Refresco terminado correctamente.) else (echo Refresco terminado con avisos o errores. Codigo: %RC%. Revisa el registro en logs.)
if /i not "%MODO%"=="auto" pause
exit /b %RC%
