@echo off
setlocal

rem build_release.bat
rem 用 Visual Studio 2022 的开发者命令提示符（cmd 方式）执行 CMake 配置、构建、安装。
rem 与 build_release.ps1 效果相同；直接双击或在 cmd 中运行即可。
rem 脚本结束时会明确提示成功或失败，并 pause 停留供查看结果。

rem 1. 用 vswhere 自动定位 VS 2022（兼容 Community / Professional / Enterprise）
set "VSWHERE=%ProgramFiles(x86)%\Microsoft Visual Studio\Installer\vswhere.exe"
if not exist "%VSWHERE%" (
    echo [ERROR] 未找到 vswhere.exe，请确认已安装 Visual Studio 2022。
    echo [结果] 失败。
    pause
    exit /b 1
)
for /f "usebackq delims=" %%i in (`"%VSWHERE%" -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath`) do set "VSINSTALL=%%i"
if not defined VSINSTALL (
    echo [ERROR] 未找到安装 C++ 工具的 Visual Studio 2022。
    echo [结果] 失败。
    pause
    exit /b 1
)
echo 使用 Visual Studio: %VSINSTALL%

rem 2. 进入 VS 2022 开发者环境
call "%VSINSTALL%\Common7\Tools\VsDevCmd.bat" -arch=x64 >nul
if errorlevel 1 (
    echo [ERROR] 进入 VS 2022 开发者环境失败。
    echo [结果] 失败。
    pause
    exit /b 1
)

rem 3. 切换到工程根目录（本脚本位于 Script 子目录下）
cd /d "%~dp0.."
echo 当前目录: %CD%

rem 4. 依次执行三条 cmake 指令
echo.
echo [1/3] cmake -S . -B cmake-build-release -G "Visual Studio 17 2022" -A x64 -DCMAKE_BUILD_TYPE=Release -DENABLE_CGNS_MODULE=OFF -DENABLE_QT_MODULE=OFF
cmake -S . -B cmake-build-release -G "Visual Studio 17 2022" -A x64 -DCMAKE_BUILD_TYPE=Release -DENABLE_CGNS_MODULE=OFF -DENABLE_QT_MODULE=OFF
if errorlevel 1 goto :failed

echo.
echo [2/3] cmake --build cmake-build-release --config Release -- /p:TrackFileAccess=false
cmake --build cmake-build-release --config Release -- /p:TrackFileAccess=false
if errorlevel 1 goto :failed

echo.
echo [3/3] cmake --install cmake-build-release --config Release
cmake --install cmake-build-release --config Release
if errorlevel 1 goto :failed

echo.
echo [结果] 成功：配置、构建、安装全部完成。
pause
exit /b 0

:failed
set "ERR=%errorlevel%"
echo.
echo [结果] 失败：cmake 返回错误码 %ERR%，请查看上方日志。
pause
exit /b %ERR%
