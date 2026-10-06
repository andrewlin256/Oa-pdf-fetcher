# OA PDF Fetcher

讓 Claude Code 依 PubMed 檢索式、PMID/DOI 清單或 Embase 等資料庫匯出的 RIS 檔，批次下載**開放取用（OA）**的全文 PDF 到你的電腦。

A Claude Code skill that batch-downloads open-access full-text PDFs from a PubMed search, a PMID/DOI list, or an RIS export (Embase, Scopus), using Europe PMC and Unpaywall.

## 功能

- **輸入**：PubMed 檢索式（或 PubMed 搜尋結果網址）、PMID / DOI / PMCID 清單、RIS 檔
- **全文來源**：Europe PMC（PMC 收錄的全文）→ Unpaywall（出版社 OA 版、作者自存稿、機構典藏）
- **輸出**：
  - PDF，檔名格式為 `作者_年份_PMID.pdf`
  - `download_log.csv`：每篇文章的下載狀態
  - `not_found_dois.txt`：沒抓到全文的 DOI 清單
- **可續跑**：中斷後重新執行，已下載的檔案會自動略過

只下載合法開放取用的全文。需要訂閱的期刊請用 Zotero 補抓，見下方「抓不到的文章」。

## 安裝

### 方法一：以 plugin 安裝（推薦，可自動更新）

在 Claude Code 中執行：

```
/plugin marketplace add andrewlin256/oa-pdf-fetcher
/plugin install oa-pdf-fetcher@andrewlin256
```

### 方法二：手動安裝成個人 skill

```bash
git clone https://github.com/andrewlin256/oa-pdf-fetcher.git
```

再把 `skills/oa-pdf-fetcher` 資料夾複製到：

- **Windows**：`%USERPROFILE%\.claude\skills\`
- **macOS / Linux**：`~/.claude/skills/`

### 前置需求

- Python 3.8 以上，以及 `requests` 套件：`pip install requests`
- 設定 email。NCBI 與 Unpaywall 都要求提供，設定一次就好：
  - Windows：`setx OA_FETCHER_EMAIL "你的email"`，設定後要開新的終端機才會生效
  - macOS / Linux：在 shell 設定檔加入 `export OA_FETCHER_EMAIL="你的email"`
- 選填：[NCBI API key](https://www.ncbi.nlm.nih.gov/account/settings/)。設定 `NCBI_API_KEY` 後，PubMed 速率上限從每秒 3 次提高到 10 次。

## 使用方式

裝好後直接用自然語言跟 Claude Code 說，例如：

- 「幫我下載這個 PubMed 檢索式的全文：`statin*[tiab] AND frail*[tiab] AND aged[mh]`」
- 「這是 Embase 匯出的 embase.ris，把能抓的 OA 全文都下載到 pdfs 資料夾」
- 「幫我抓這幾篇的 PDF：34567890, 10.1001/jama.2020.1234」

也可以不透過 Claude，直接執行腳本：

```bash
python skills/oa-pdf-fetcher/scripts/oa_pdf_fetcher.py --query "statin*[tiab] AND frail*[tiab]" --out pdfs
python skills/oa-pdf-fetcher/scripts/oa_pdf_fetcher.py --ris embase.ris --out pdfs
python skills/oa-pdf-fetcher/scripts/oa_pdf_fetcher.py --ids ids.txt --out pdfs
```

| 選項 | 說明 |
|---|---|
| `--out` | 輸出資料夾，預設 `./pdfs` |
| `--max N` | 最多處理 N 篇，第一次可以先用 `--max 5` 測試 |
| `--delay S` | 兩次下載之間的間隔秒數，預設 1.0 |
| `--email` / `--api-key` | 不想用環境變數時，可以直接在指令中指定 |

PubMed 單次檢索最多回傳 10,000 筆。結果超過時，請用年份拆成幾次檢索，例如加上 `AND 2015:2020[dp]`。

## 抓不到的文章

OA 全文的取得率通常約三到六成，視領域與發表年份而定。其餘文章可以這樣補抓：

1. 在 Zotero 點魔術棒圖示（Add Item by Identifier），把 `not_found_dois.txt` 的內容整份貼上。
2. 在學校網路或 VPN 下全選新匯入的項目，按右鍵選 **Find Available PDF**。

這樣是用你的合法權限、以正常速度下載，不會違反出版社的授權條款。

## 授權

MIT License
