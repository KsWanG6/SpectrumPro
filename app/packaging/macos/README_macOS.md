# SpectrumPro on macOS（Apple Silicon 與 Intel）

PyInstaller 不能在 Windows / Linux 上產生 Mac 程式，且 scipy 沒有 universal2 套件，
所以做法是**各建一份**：Apple Silicon 用 arm64 版、Intel 用 x86_64 版。

## 方法 A：在 Mac 上自己建（約 5–10 分鐘）
```
cd app
bash packaging/macos/build_mac.sh
```
產生 `dist/SpectrumPro.app` 與 `dist/SpectrumPro-macos-<arch>.zip`。
- Apple Silicon Mac 建出 arm64 版；Intel Mac 建出 x86_64 版。
- 想在 Apple Silicon 上建 Intel 版：先裝 Rosetta，`arch -x86_64 /usr/local/bin/python3 ...`（需要 x86_64 版 Python），再執行同一支腳本。

## 方法 B：GitHub Actions（不用 Mac，兩種晶片一次建好）
把整個專案推到 GitHub（`app/` 與 `.github/` 放在 repo 根目錄），Actions → Build SpectrumPro (macOS) → Run workflow，
完成後在 Artifacts 下載 `SpectrumPro-macos-arm64` 與 `SpectrumPro-macos-x86_64`。

## 給別人用
壓縮檔解壓後把 `SpectrumPro.app` 拖進「應用程式」。因為沒有 Apple 開發者簽章，第一次要：
- 對 App 按右鍵 →「打開」→ 再按「打開」；或在終端機執行
  `xattr -dr com.apple.quarantine /Applications/SpectrumPro.app`
- 不想打包也可：安裝 Python 3.10–3.12 後雙擊 `packaging/macos/start_mac.command`。

資料與自動存檔位置：`~/Library/Application Support/SpectrumPro/`
