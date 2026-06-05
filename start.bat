@echo off
cd /d "%~dp0"

:: 获取 PySide6 插件目录并设置 QT_PLUGIN_PATH
for /f "delims=" %%i in ('python -c "import PySide6, os; print(os.path.join(os.path.dirname(PySide6.__file__), 'Qt', 'plugins'))"') do set "QT_PLUGIN_PATH=%%i"

:: 启动应用
python -m app.main