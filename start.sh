#!/bin/bash
cd "$(dirname "$0")"
export QT_PLUGIN_PATH="$(python -c 'import PySide6; import os; print(os.path.join(os.path.dirname(PySide6.__file__), "Qt", "plugins"))')"
export DYLD_FRAMEWORK_PATH="$(python -c 'import PySide6; import os; print(os.path.join(os.path.dirname(PySide6.__file__), "Qt", "lib"))')"
python -m app.main
