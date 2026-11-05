# SpectrumPro

Raman / SERS（以及 UV-Vis）光譜後處理與定量分析桌面軟體。作者：Kuan-Syun Wang

- 原始碼：`app/`（Python 3.10–3.12，PySide6 + pyqtgraph）
- 執行：`cd app && pip install -r requirements.txt && python run_gui.py`
- 測試：`cd app && python -m pytest tests -q`
- Windows 打包：`app\build_exe.bat`
- macOS 打包（Apple Silicon / Intel）：見 `app/packaging/macos/README_macOS.md`，或在 GitHub 的 Actions 執行 *Build SpectrumPro (macOS)*

詳細功能與修正記錄見 `app/README.md`。
