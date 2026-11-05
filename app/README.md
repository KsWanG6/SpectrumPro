# ramanproc v0.4
Independent Raman post-processing library (numpy/scipy/sklearn). Run tests: `python -m pytest tests`

## Validated against reference input/output pairs (tests/test_reference.py)
- smooth savgol (order 2; frame 5 exact; frame 9 matches after the reference's missing /231 normalisation - defect NOT reproduced); edges pass through
- normalize minmax (exact, 2 datasets)
- remove_cosmic_ray: running median, window 7, windows truncated at the ends (exact on 2 spectra)
- integral: natural-spline definite integral clipped to data range (exact, 2 dialog values)
- uniform_x: natural cubic spline on multiples of step, rounded range (exact)
- remove_baseline polynomial (order 2, 20 fits on 0.5 cm-1 natural-spline grid, exact, not floored)
- remove_baseline iterative_clipping (width 50/100, max err ~1e-5, floored at 0)

## Implemented with standard definitions, NOT validated against the reference
smooth moving_average (edge handling unknown), smooth moving_median (assumed same as cosmic-ray median), normalize area, crop, ayb, ay1_by2_c, log_y (base param), [integral now validated],
average, std_curve, standardize (z-score assumed), auto_stacking, add/remove point,
find_raman_peaks, rank_matches (7 distances), SVM train/predict, readers (xy, xyxy, xyy), run_pipeline (records history).

## Not implemented
Instrument/vendor file formats (Horiba, Enwave, Pyrochlore, SPC): need sample files.

## 桌面程式（GUI）
Windows：安裝 Python 3.10+（勾選 Add to PATH），雙擊 `start.bat`（第一次會自動建立環境並安裝套件）。
也可：`pip install -r requirements.txt` 後執行 `python run_gui.py [光譜檔...]`。
想要單一 exe：雙擊 `build_exe.bat`（需網路，產生 dist\SpectrumPro\SpectrumPro.exe）。
操作：檔案→開啟（可多選 txt/csv；4 欄以上視為 XYXY 多光譜）；左側清單勾選顯示、選取作為處理對象（未選取時處理所有勾選者）；
處理選單的各項功能與原軟體相同，可勾「建立新光譜」；Ctrl+Z / Ctrl+Y 復原重做；區間→加入 Strip 可供裁切與積分使用；峰→尋峰並標示。

### 滑鼠工具（工具箱）
Pointer 平移 / Zoom In/Out 框選縮放 / Shift 在圖上垂直拖曳平移光譜 / Multiply 垂直拖曳等比縮放 Y（以起點 Y 值為基準）/
XY Pointer 十字線與座標 / Data Cursor 吸附最近資料點 / Add Text 加文字（可拖動）/ Add Image 加圖片；
Strip：Draw Strip 拖曳畫區間（可多個）、Remove Strips 點區間移除；Peak：Label Peaks 點峰標示位置。
Shift / Multiply 作用在清單中選取的光譜（未選取時為最上層可見光譜），放開後套用，可 Ctrl+Z 復原。

### 工具列快捷（v1.2）
工具列上的 平均 / 裁切 / 平滑 / 去背景 / 均一化：直接點圖示 = 用「上次設定的參數」一鍵套用（第一次使用預設：SG 窗口 5、IterativeClipping 峰寬 100、min-max）；
點圖示右邊的小箭頭 →「設定參數…」可修改並記住。裁切：圖上有區間（Strip）就裁成該範圍；平均：選 2 條以上光譜。處理對象＝清單中選取的光譜（未選取則為勾選顯示者）。

## v1.3 介面（參考 LabSpec 6 的版面配置）
- 藍色主題、上方大圖示工具列（開啟/儲存/圖片/復原/重做＋平均/裁切/去尖峰/平滑/去背景/均一化＋尋峰/區間積分/全範圍）。
- 左側垂直圖示條（由上而下）：X 標線、框選區間（自動算積分）、十字線 XY、放大、移動 Y 軸（Shift）、移動全圖、標文字、標峰值；其下為 Multiply、資料點游標、插入圖片、移除區間。
- 中央分頁：Spectra（標題列顯示目前光譜）、Data（X/Y 數值表）。
- 右側面板：Browser（光譜列表）、Info（資訊與處理歷程）、Processing（可摺疊區塊，參數即時記住，按「套用」）、
  Analysis（Peaks 尋峰表；Bands 彩色 From/To 區間，圖上顯示色帶並計算面積、可複製）、Display（格線/圖例/線寬/背景）。
- 僅借鏡版面與配色，未使用任何 HORIBA 商標或圖示。
- 橡皮擦（去宇宙射線）：左側工具列最後一個主要工具；點尖峰或拖曳框選範圍，只在該範圍做中位數去尖峰。頂端「去尖峰」鈕圖示同為橡皮擦（對整條光譜）。

## v1.6
- 右側面板改為淺色（強制淺色調色盤，不受 Windows 深色模式影響）。
- 上方工具列：移除「去尖峰」，新增「多曲線 / 單曲線」顯示切換；去尖峰只留在左側橡皮擦。
- 手動基線：左側「手動基線」工具加錨點（靠近曲線自動貼齊、可拖曳、點錨點刪除）→ Processing → Baseline →「套用手動基線」；亦可「自動取點」先抓 10 個點再微調。

## LOD / LOQ
Analysis → LOD / LOQ：選光譜 → 載入 → 填濃度、空白打勾 → 計算。響應可選峰高/峰面積（可扣兩端直線基線）；校正曲線可選線性或 log₁₀(濃度)。
報告空白法（kσ_blank/S）、回歸殘差法（3.3·Sy.x/S）、截距法（3.3·SE_intercept/S）；LOQ 用 10σ/S。log 曲線以 mean(blank)+3σ_blank 代回擬合式換算濃度。

## EF（增強因子）
Analysis → EF：選 SERS 光譜 → 「選取 → SERS 組」；選 Raman 參考光譜 → 「選取 → Raman 參考組」；填濃度（或分子數）、雷射功率與積分時間（相同條件留 1）→ 計算。
EF = (I_SERS/X_SERS/P/t) ÷ (I_RS/X_RS/P/t)，重複光譜取平均 ± SD，EF 誤差依相對 SD 傳遞。

## 定量與 LOD（獨立分頁 Quantification）
流程：載入光譜 → 指定角色（空白／標準品／未知樣品／低濃度驗證）、填濃度與曲線編號 → 選特徵（峰高／峰面積／峰比值）→ 選尺度與模型（線性 OLS、加權 1/C、1/C²、對數）→ 選 σ 來源（空白、最低濃度重複、迴歸殘差、截距標準誤、多條檢量線截距變異）與 k → 計算。
輸出：檢量線與殘差圖、斜率／截距±標準誤、R²、Sy.x、未知樣品濃度與 95% 區間、超出校正範圍／<LOD／LOD–LOQ 標記；LOD 記錄表（方法、σ 來源與值、有效重複數、斜率來源、前處理流程、濃度尺度、驗證狀態）。
驗證狀態：預設「僅由公式估算」；加入 ≥3 個低濃度驗證樣品且檢出率達門檻（預設 95%）則標為「已確認」。

## Peak Analysis 峰分析（獨立分頁）
- 尋峰並計算：峰位（拋物線內插）、高度、面積（扣基線）、FWHM、Prominence、S/N；可同時做 Gaussian / Lorentzian / pseudo-Voigt 擬合（峰位、高度、面積±SD、R²）。
- 基線：線性（窗口兩端）／無／水平（窗口最低點）；積分窗 = ±N×FWHM；可用最小 S/N 過濾雜訊峰。
- 峰比值：高度比、面積比、擬合面積比、內標比；A、B 各自峰位／搜尋範圍／基線方式；兩峰使用同一特徵類型；分母下限與失敗處理（標記失敗／以下限取代／報錯）；
  誤差傳遞 σ_R/R = √[(σ_A/A)²+(σ_B/B)²]，重疊峰聯合擬合時加入協方差項。

## v1.7 檢視與品質功能
- **光譜清單（Browser）**：篩選、右鍵選單（重新命名、改色、群組、顯示/隱藏/只顯示選取/只顯示此群組）、排序（名稱/群組/X 起點/最大強度）、品質檢查報告；清單中 ⚠ = 有異常（v2.3 起匯入後**不會**自動檢查，按「品質檢查」才執行，處理後的光譜需重新檢查）。
- **處理前後對照（Display → Compare）**：原始、平滑後、基線估計、最終，可個別開關（記錄 Processing 的平滑/去基線階段）。
- **平均 ± SD 誤差帶**、只顯示平均；**游標處顯示所有光譜 Y 值**（浮動標籤＋狀態列）。
- **座標軸（Display → Axes）**：拉曼位移 / 波長（nm，需雷射波長，僅顯示用）、X 反向、數值範圍、Y 軸單位文字。
- **異常標示**：尖峰（◆）、飽和（■）、缺值（×）、平坦光譜；尋峰擬合失敗以紅字與紅 × 標示。偵測為啟發式（尖峰＝高於兩側鄰點 >8σ 的 1–3 點；飽和＝頂端連續相同最大值），可能有誤報／漏報。
- **峰標示編輯**：「標峰」工具點空白處新增、點既有標示刪除、拖曳標示移動。
- **擬合檢視**：Peak Analysis 雙擊表中一列（或按「擬合檢視」）→ 原始、總擬合、各子峰、基線、殘差，X 軸同步縮放。
- **輸出**：PNG（2000 px）、SVG、PDF；所見即所得（保留目前縮放範圍、座標軸與疊圖，匯出時隱藏十字線）。
  SVG 改用 Qt 內建向量輸出（pyqtgraph 內建 SVG 匯出與新版 Qt 不相容）。

## v1.8 介面（參考 macOS 設計）
- 色彩：蘋果系統中性色（視窗 #f5f5f7、分隔線 #d2d2d7、文字 #1d1d1f／次要 #6e6e73），側欄與選取色沿用專案色票（#ecf7fc / #aad7e3 / #1d7cd4）。
- 視窗：淺色選單列與統一工具列（無實心藍條）、圓角按鈕與輸入框（6 px）、分段式頁籤、可收合區段改為 macOS 檢閱面板風格、細捲軸、置中面板標題。
- 對稱：所有圖示自動置中於同一畫布；工具列按鈕同寬同高；側欄按鈕為正方形且圖示四周留白相等；區段內表單左右縮排一致。`MainWindow.layout_audit()` 與測試 `test_layout_symmetry` 會檢查。
- 工具列的「裁切／平滑／去背景／均一化」：點一下＝以目前參數執行，長按＝開啟參數視窗（右下角小箭頭）。
- 選取狀態採扁平設計：工具按鈕與頁籤為淡藍底＋強調色細框，清單／表格／選單高亮為純強調色底白字，主要按鈕為純色，無漸層。

## v1.9 可靠性
- **寬容匯入**：自動處理標題列／說明文字、UTF-8 BOM 與 Big5(cp950) 編碼、X 遞減或未排序（自動反轉／排序）、重複 X（Y 取平均並合併）、空白或非數字列、欄數不一致的列；多欄檔（x1 y1 x2 y2…）自動拆開。所有修正都列在「匯入報告」並寫入光譜的處理歷程，絕不靜默修改。資料點少於 3 點或沒有數值的檔案會明確報錯。一次匯入可用一次「復原」整批撤銷。
- **原子寫檔**：儲存文字檔與工作階段時先寫暫存檔，成功後才取代原檔；寫到一半失敗不會毀掉舊檔。
- **自動存檔與當機還原**：每 30 秒（有變動時）把所有工作區存到 `%LOCALAPPDATA%\SpectrumPro\recovery.ramansession`；正常關閉時刪除。下次啟動若偵測到殘留，詢問是否還原。
- **工作階段**：檔案 → 儲存／開啟工作階段（所有工作區、顏色、群組、顯示狀態、處理歷程、原始光譜；不含復原記錄與前後對照的中間階段）。格式為 numpy .npz＋JSON，不使用 pickle（開啟他人檔案不會執行程式碼）。
- **錯誤處理**：未預期的錯誤會寫入 `%TEMP%\SpectrumPro_error.log`、先自動存檔、再顯示對話框，而不是靜默消失；底層崩潰記錄在 `.fault` 檔。

## RSD 重現性（獨立分頁）
- 設定特徵峰：峰位 ± 半窗寬（可從 X 標線取得、或自動吸附視窗內最高點），或面積模式的自訂 From–To 區間（可取自圖上 Strip）。
- 四種特徵量：峰高（局部基線扣除，兩端直線基線＋拋物線頂點）、峰高（視窗最大值，用於已去背景的光譜）、區域面積（局部基線扣除）、區域曲線下面積（直接積分，與 Analysis → Bands 相同）。
- 輸出：每條光譜一個特徵值；n、平均、樣本 SD（n−1）、RSD% = 100·s/|平均|、SEM、95% t 信賴區間。可依「群組」分別計算（光譜清單的群組欄位）。
- 長條圖：逐條光譜（虛線＝平均、淡藍帶＝±1 SD、標示 RSD%），或各組平均 ± SD（疊加個別點）；可匯出 PNG／SVG／PDF；表格可複製或存 CSV。
- 注意：n < 3 時 RSD 本身不確定度很大（會標示警告）；平均值接近 0 時 RSD 無意義（顯示 NaN）。特徵量的演算法為通用定義，未與參考軟體比對。

## v2.0 去背景 / 光譜數學 / 平滑與濾波（參考 LabSpec 面板配置）
只參考面板的配置與操作方式；演算法與參數定義為本軟體自行訂定，**未與其他軟體比對**（僅有合成資料測試）。各面板標題右側的「?」有說明。
- **Baseline correction**：Type = Linear/Polynom（Manual／Auto）、Multi polynomial、Lorentzian、Rolling Ball、Rolling Ball Auto、Whittaker 1（AsLS）、Whittaker 2（arPLS）；舊的 IterativeClipping／PolynomialFitting（已與參考軟體比對）仍可選。**Fit** 算出基線並以所選 Color 顯示（不改資料），**Sub** 才扣除；Order／Max points／Noise points 為滑桿＋數值框；Correct noise、Attach to curve（手動錨點吸附曲線）；複製／貼上／刪除基線按鈕。Max points＝把光譜分成幾等份各取一個候選錨點；Noise points＝挑錨點前的移動平均寬度。
- **Spectral Math**：One object（X、Y 運算式，例 `Y/5`）、Two objects（`A-B`，B 以 ▶ 指定並內插到 A 的 X，B 須涵蓋 A）、Combine data（可勾 Adjust overlapping intensities：依重疊區縮放＋平移並線性漸變）。運算式為白名單語法，不執行任意程式。
- **Smoothing & Filtering**：Methods = Polynomial（Savitzky–Golay）、Median、FFT、DeNoise（Wiener）、1st／2nd derivative、Despike、SVD；Mode = Automatic（視窗取「最強峰高度損失 ≤ Factor %」的最大奇數視窗；FFT 以雜訊底截止；SVD 以雜訊門檻選成分）／Manual（Window、Order、Factor 由使用者給定；Manual-Polynomial 時 Factor 反灰）。按「Run」執行。

## v2.1 Peaks 整合進 Processing ＋ 一鍵移除標記
- Processing 分頁新增 **Peaks 峰** 區（參考 LabSpec 的 Peaks 面板）：Level (%)、Window (pnt)、Shape（Gaussian / Lorentzian / GaussLor＝pseudo-Voigt）、Error、Red. χ²；**Find** 尋峰並直接標在 Spectra 圖上、**Fit** 擬合並畫出總和與各峰、**Conv** 把擬合的峰存成新光譜；下方有 Peak table。Level＝最小 prominence（Y 範圍 %）、Window＝峰間最小點數；Error＝殘差 RMS；Red. χ²＝殘差平方和／(雜訊²×自由度)（雜訊由相鄰點差 MAD 估計）。定義為本軟體自行訂定，未與其他軟體比對。
- 不常用的區塊預設摺疊：Options（Iterations、Max shift、Min/Max width、Fit baseline）、Display options（Decimals、Attach to curve、Use data color、Sum／各峰）、Normalization、Data、Peak Ratio。標題列點一下即可展開。
- 沒有做的 LabSpec 項目：Reshape、峰圖（Peak map）、負峰擬合、Auto adjust。
- **移除頁面所有標記**：在 Spectra 圖上按右鍵、在左側工具列按右鍵，或「峰」選單，皆可一次清掉峰位標記、擬合曲線、文字／圖片註記、區間、X 標線、資料游標與手動基線點。

## 字體
介面字體使用內附的 **jf open 粉圓 2.0**（jf-openhuninn，SIL Open Font License 1.1，檔案在 `ramanproc/assets/`）。載入失敗時自動退回系統字體。

## v2.2 圖表格式與匯出比例
Display 分頁新增：
- **Figure 標題與字體**：圖標題文字與大小、X 軸標題文字、軸標題大小、X／Y 刻度字體大小（分開設定）、粗體、軸線粗細、外框（四邊皆畫軸線）。
- **Ticks 刻度線**：X、Y 軸各自（或勾「相同設定」同步）設定 **Major／Minor Ticks 的 Style（Out／In／Both／None）、Length、Color、Thickness**；Auto＝Major 6 px、Minor 為 Major 一半、顏色同軸線、粗細 1。刻度線與格線互相獨立（開著格線仍看得到刻度）。
- **Export 匯出圖片比例**：預設 **6:5（同範例圖）**，另有 4:3、3:2、1:1、16:9、維持視窗比例；PNG／SVG／PDF 都依此比例重新排版，與視窗大小無關。匯出時自動隱藏異常點標記。
- 字體為粉圓，只有一個字重；「粗體」在 Windows 由系統合成，看起來可能不如原生粗體。

## v2.3 校正與修正（程式碼審查後）
- **LOD（殘差法）**：加權模型（1/C、1/C²）改用「最低標準品濃度處的響應標準差」Sy.x·C_low^(p/2)，LOD 不再隨濃度單位改變；報告的 Sy.x 為響應單位。
- **峰面積不確定度**：`sigma_area` 加入基線估計的雜訊（線性基線約低估 3 倍、最低點基線約 4 倍的問題），面積比的 σ_R 同步修正。
- **光譜數學**：`max(Y,0)`、`min(Y,2)` 等兩個以上參數的 min / max 可用。
- **Combine**：巢狀範圍（窄範圍落在寬範圍內）不再覆蓋範圍外的原始資料。
- **匯入**：重複 X 合併時只平均有效值（NaN 不再當成 0）。
- **Display → Frame 外框**：外框獨立設定（顯示、上／右邊、粗細、顏色、是否顯示刻度）；上、右軸不再重複畫格線。
- **Display 分頁**可捲動；展開所有區塊也不會再把視窗撐高。
- **自動堆疊**：可選光譜排序（清單順序、名稱自然排序、群組、X 起點、最大強度）、堆疊方向、間距，並可同時重排光譜清單。
- **游標數值窗**：游標離開 Spectra 圖面、切換分頁或視窗失去焦點（例如截圖）時，數值窗與十字虛線一併隱藏。
- **Bands 區間積分**：新增積分數值欄位，長名稱不再擠掉數值；區間超出光譜範圍時會警告。
- **均一化新增 4 種方法**（Processing → Normalization，或工具列均一化旁的參數視窗）：Max（y/最大值，不扣基線）、Vector (L2)（y/√Σy²）、Peak height 峰高、Peak area 峰面積。後兩者每條光譜除以自己在「峰位±半寬」（或圖上 Strip）內的峰高／面積，可選先扣區間兩端直線基線，用於內標峰歸一化。
- **品質檢查改為手動**：匯入與重繪不再自動檢查；按「品質檢查」後才標示 ⚠ 與圖上異常點，光譜經過處理後需重新檢查。
- 回歸測試：`python -m pytest tests -q`（37 項，其中 10 項在修正前會失敗）。
- **雙 X 標線**（左側工具列，X 標線旁）：按住拖曳一次拉出兩條線，或點兩下各放一條；之後點一下移動較近的那條，兩條也可直接拖動。狀態列顯示 X₁、X₂、ΔX 與各光譜的 Y₁、Y₂、ΔY、兩線間面積；Edit 選單「清除雙 X 標線」。
- **更名為 SpectrumPro**：視窗標題、工作列圖示、關於對話框（說明 → 關於 SpectrumPro，含作者 Kuan-Syun Wang 與圖標）、錯誤記錄與自動存檔資料夾（`%LOCALAPPDATA%\SpectrumPro`）、exe 名稱皆已更新；內部程式套件名稱 `ramanproc` 不變。
- **Browser 清單**：新增「✔ 勾選選取」「☐ 取消勾選選取」按鈕，一鍵對反白（框選）的光譜打勾／取消勾選（可復原）。
- **Browser 群組分支圖**：清單改為樹狀——最上層是群組名（顯示已勾選/總數），分支是光譜；勾選／取消勾選群組＝整組一起勾選／取消；可點 ▸ 摺疊／展開（重新整理後維持摺疊狀態；右鍵可「展開／摺疊全部群組」）；選取群組列＝選取整組。沒有任何群組時維持單純清單。
- **衍生光譜歸屬原群組**：在某群組內做 Average、StdDev、A*Y1±B*Y2+C、Two objects、Combine、Peak Conv 等產生新光譜時，新光譜自動歸入來源群組（來源跨多個群組時取第一個有群組者）。
- **UV-Vis 檔（GENESYS 30 CSV）直接匯入**：辨識檔頭（`Scan/Mode/Lower/Upper/Length` 與 `wavelength(nm), ABS, %T` 欄位名稱），拆成 `<檔名>_ABS`、`<檔名>_%T` 兩條光譜（依 `Mode` 只預設顯示 ABS，%T 預設隱藏、可自行勾選）；X 軸標題自動為 Wavelength (nm)、Y 軸為 Absorbance。同時修正：無檔頭的 3 欄檔（X, Y1, Y2）以往會被誤讀成 (X=Y1, Y=Y2)，現在正確拆成兩條；空白逗號行（`,,`）不再被當成資料列。新增 tests/test_import_uvvis.py（含範例檔）；Y 軸不再自動加 SI 前綴（如 ×0.001）。
- **macOS（Apple Silicon / Intel）**：新增 `packaging/macos/`（build_mac.sh、start_mac.command、spectrumpro.icns、README_macOS.md）與 `.github/workflows/build-macos.yml`；資料夾改放 `~/Library/Application Support/SpectrumPro`；錯誤記錄改用系統暫存資料夾。
