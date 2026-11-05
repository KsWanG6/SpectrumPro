# SpectrumPro — macOS 打包資料夾

這個資料夾是**可以單獨上傳到 GitHub 的完整 repo 內容**，用 GitHub Actions 在雲端的 Mac 上打包（不需要自己有 Mac）。

```
Mac/
├─ .github/workflows/build-macos.yml   ← GitHub Actions 設定（Apple Silicon arm64 + Intel x86_64 各建一份）
├─ app/                                ← 程式原始碼（含 IR 功能）、測試、打包腳本
│   ├─ ramanproc/  run_gui.py  requirements.txt  tests/
│   └─ packaging/macos/  build_mac.sh  spectrumpro.icns  start_mac.command  README_macOS.md
├─ .gitattributes   .gitignore
└─ README.md
```

## 步驟
1. 在 GitHub 建一個新的 repo。
2. 把 **這個資料夾裡面的東西**（不是 `Mac` 資料夾本身）放到 repo 根目錄，也就是 `.github/` 與 `app/` 要在最上層：
   ```bash
   cd Mac
   git init && git add -A && git commit -m "SpectrumPro macOS build"
   git branch -M main
   git remote add origin https://github.com/<你的帳號>/<repo>.git
   git push -u origin main
   ```
3. GitHub → **Actions** → *Build SpectrumPro (macOS)* → **Run workflow**（或推送 `v1.0` 之類的 tag 自動觸發）。
4. 約 10 分鐘後，在該次執行頁面下方 **Artifacts** 下載：
   - `SpectrumPro-macos-arm64`（M1/M2/M3/M4 Mac）
   - `SpectrumPro-macos-x86_64`（Intel Mac）

## 使用者端
解壓後把 `SpectrumPro.app` 拖進「應用程式」。因為沒有 Apple 開發者付費簽章，第一次要對 App 按右鍵 →「打開」→ 再按「打開」，
或在終端機執行 `xattr -dr com.apple.quarantine /Applications/SpectrumPro.app`。

## 說明
- Workflow 會先跑 `app/tests`（全部通過才會打包），再執行 `app/packaging/macos/build_mac.sh`（PyInstaller + ad-hoc codesign）。
- 這個資料夾是 `app/` 的**複本**：之後改了原始碼，請重新複製一次 `app/`，不然 Mac 版會是舊的。
