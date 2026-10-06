#!/usr/bin/env python3
"""
oa_pdf_fetcher.py
依 PubMed 檢索式、PMID/DOI 清單或 RIS 檔（例如 Embase 匯出），批次下載「合法開放取用」的全文 PDF。

全文來源（依序嘗試）：
  1. Europe PMC：PMC 收錄的 OA 全文
  2. Unpaywall：出版社 OA 版、作者自存稿、機構典藏

抓不到的文章會寫進 not_found_dois.txt，可整份貼進 Zotero「依識別碼新增項目」，
再在學校網路或 VPN 下用 Zotero 的「尋找可用的 PDF」補抓。

需求：Python 3.8+，requests（pip install requests）

用法：
  python oa_pdf_fetcher.py --email you@example.com --query "statin*[tiab] AND frail*[tiab]"
  python oa_pdf_fetcher.py --email you@example.com --ids ids.txt
  python oa_pdf_fetcher.py --email you@example.com --ris embase_export.ris

email 與 NCBI API key 也可以用環境變數 OA_FETCHER_EMAIL、NCBI_API_KEY 設定，就不必每次輸入。

選項：
  --out      PDF 輸出資料夾（預設 ./pdfs）
  --api-key   NCBI API key（建議，PubMed 速率從每秒 3 次提高到 10 次）
  --max       最多處理幾篇（預設全部；PubMed 單次檢索上限 10,000 筆）
  --delay     兩次下載之間的間隔秒數（預設 1.0）

ids.txt 每行一個識別碼，可混用 PMID（純數字）、DOI（10.xxxx/...）、PMCID（PMC123456）。
"""
import argparse
import csv
import os
import re
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

try:
    import requests
except ImportError:
    sys.exit("缺少 requests 套件，請先執行：pip install requests")

EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
EPMC_SEARCH = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
EPMC_PDF = "https://europepmc.org/backend/ptpmcrender.fcgi"
UNPAYWALL = "https://api.unpaywall.org/v2/"

DOI_RE = re.compile(r"10\.\d{4,9}/[^\s\"<>]+", re.I)


# ---------------------------------------------------------------- HTTP 工具
class Client:
    def __init__(self, email, api_key=None):
        self.email = email
        self.api_key = api_key
        self.s = requests.Session()
        self.s.headers["User-Agent"] = f"oa_pdf_fetcher/1.0 (mailto:{email})"
        self.ncbi_gap = 0.11 if api_key else 0.34
        self._last_ncbi = 0.0

    def _request(self, method, url, retries=3, **kw):
        kw.setdefault("timeout", 60)
        for attempt in range(retries):
            try:
                r = self.s.request(method, url, **kw)
                if r.status_code in (429, 500, 502, 503, 504) and attempt < retries - 1:
                    time.sleep(3 * (attempt + 1))
                    continue
                return r
            except requests.RequestException:
                if attempt == retries - 1:
                    raise
                time.sleep(3 * (attempt + 1))

    def ncbi(self, endpoint, params):
        wait = self.ncbi_gap - (time.time() - self._last_ncbi)
        if wait > 0:
            time.sleep(wait)
        data = dict(params, tool="oa_pdf_fetcher", email=self.email)
        if self.api_key:
            data["api_key"] = self.api_key
        r = self._request("POST", f"{EUTILS}/{endpoint}", data=data)
        self._last_ncbi = time.time()
        r.raise_for_status()
        return r

    def get(self, url, **kw):
        return self._request("GET", url, **kw)


# ---------------------------------------------------------------- 取得書目
def esearch(client, query, max_n=None):
    r = client.ncbi("esearch.fcgi", {"db": "pubmed", "term": query,
                                     "retmax": 10000, "retmode": "json"})
    res = r.json()["esearchresult"]
    count = int(res["count"])
    ids = res["idlist"]
    print(f"PubMed 檢索結果：{count} 筆")
    if count > 10000:
        print("  注意：超過 10,000 筆，只會處理前 10,000 筆。建議用年份等條件拆成幾次檢索。")
    return ids[:max_n] if max_n else ids


def parse_pubmed_xml(xml_text):
    recs = []
    root = ET.fromstring(xml_text)
    for art in root.findall(".//PubmedArticle"):
        rec = {"pmid": "", "pmcid": "", "doi": "", "author": "", "year": "", "title": ""}
        rec["pmid"] = (art.findtext("MedlineCitation/PMID") or "").strip()
        a = art.find("MedlineCitation/Article")
        if a is not None:
            t = a.find("ArticleTitle")
            rec["title"] = "".join(t.itertext()).strip() if t is not None else ""
            first = a.find("AuthorList/Author")
            if first is not None:
                rec["author"] = (first.findtext("LastName") or first.findtext("CollectiveName") or "").strip()
            pd = a.find("Journal/JournalIssue/PubDate")
            if pd is not None:
                y = pd.findtext("Year") or pd.findtext("MedlineDate") or ""
                m = re.search(r"\d{4}", y)
                rec["year"] = m.group(0) if m else ""
            for el in a.findall("ELocationID"):
                if el.get("EIdType") == "doi" and el.text:
                    rec["doi"] = el.text.strip()
        for aid in art.findall("PubmedData/ArticleIdList/ArticleId"):
            typ, val = aid.get("IdType"), (aid.text or "").strip()
            if typ == "doi" and val:
                rec["doi"] = val
            elif typ == "pmc" and val:
                rec["pmcid"] = val
        recs.append(rec)
    return recs


def efetch_records(client, pmids):
    recs = []
    for i in range(0, len(pmids), 200):
        batch = pmids[i:i + 200]
        r = client.ncbi("efetch.fcgi", {"db": "pubmed", "id": ",".join(batch), "retmode": "xml"})
        recs.extend(parse_pubmed_xml(r.text))
        print(f"  已取得書目 {min(i + 200, len(pmids))}/{len(pmids)}")
    return recs


def epmc_lookup(client, query):
    """用 Europe PMC 補 PMCID 與書目（給 DOI 或 PMCID 輸入用）。"""
    try:
        r = client.get(EPMC_SEARCH, params={"query": query, "format": "json",
                                            "resultType": "lite", "pageSize": 1})
        hits = r.json().get("resultList", {}).get("result", []) if r.ok else []
    except (requests.RequestException, ValueError):
        hits = []
    time.sleep(0.2)
    if not hits:
        return None
    h = hits[0]
    author = (h.get("authorString") or "").split(",")[0].strip()
    author = author.split(" ")[0] if author else ""
    return {"pmid": h.get("pmid", ""), "pmcid": h.get("pmcid", ""), "doi": h.get("doi", ""),
            "author": author, "year": h.get("pubYear", ""), "title": h.get("title", "")}


def parse_ris(path):
    text = Path(path).read_text(encoding="utf-8-sig", errors="replace")
    recs, cur = [], {}
    tag_re = re.compile(r"^([A-Z][A-Z0-9])  -\s?(.*)$")
    for line in text.splitlines():
        m = tag_re.match(line.strip("\ufeff"))
        if not m:
            continue
        tag, val = m.group(1), m.group(2).strip()
        if tag == "ER":
            if cur:
                recs.append(cur)
            cur = {}
            continue
        cur.setdefault(tag, []).append(val)
    if cur:
        recs.append(cur)

    out = []
    for r in recs:
        doi = ""
        for tag in ("DO", "UR", "L2", "M3"):
            for v in r.get(tag, []):
                m = DOI_RE.search(v)
                if m:
                    doi = m.group(0).rstrip(".,;")
                    break
            if doi:
                break
        au = (r.get("AU") or r.get("A1") or [""])[0]
        yr = ""
        for tag in ("PY", "Y1", "DA"):
            m = re.search(r"\d{4}", " ".join(r.get(tag, [])))
            if m:
                yr = m.group(0)
                break
        out.append({"pmid": "", "pmcid": "", "doi": doi,
                    "author": au.split(",")[0].strip(), "year": yr,
                    "title": (r.get("TI") or r.get("T1") or [""])[0]})
    return out


def records_from_ids(client, path):
    pmids, recs = [], []
    for raw in Path(path).read_text(encoding="utf-8-sig").splitlines():
        s = raw.strip()
        if not s:
            continue
        if s.isdigit():
            pmids.append(s)
        elif re.fullmatch(r"PMC\d+", s, re.I):
            rec = epmc_lookup(client, f"PMCID:{s.upper()}") or \
                {"pmid": "", "pmcid": s.upper(), "doi": "", "author": "", "year": "", "title": ""}
            recs.append(rec)
        else:
            m = DOI_RE.search(s)
            if m:
                recs.append({"pmid": "", "pmcid": "", "doi": m.group(0), "author": "",
                             "year": "", "title": ""})
            else:
                print(f"  無法辨識，略過：{s}")
    if pmids:
        recs = efetch_records(client, pmids) + recs
    return recs


def enrich_with_epmc(client, recs):
    """沒有 PMCID 但有 DOI 的，用 Europe PMC 查查看有沒有 PMC 全文。"""
    todo = [r for r in recs if r["doi"] and not r["pmcid"]]
    for i, r in enumerate(todo, 1):
        hit = epmc_lookup(client, f'DOI:"{r["doi"]}"')
        if hit:
            for k, v in hit.items():
                if v and not r.get(k):
                    r[k] = v
        if i % 50 == 0:
            print(f"  Europe PMC 比對 {i}/{len(todo)}")


# ---------------------------------------------------------------- 下載
def safe_name(rec):
    ident = rec["pmid"] or rec["pmcid"] or rec["doi"] or "unknown"
    base = f'{rec["author"] or "NA"}_{rec["year"] or "NA"}_{ident}'
    base = re.sub(r'[\\/:*?"<>|\s]+', "_", base)
    return base[:150] + ".pdf"


def fetch_pdf(client, url, params=None):
    try:
        r = client.get(url, params=params, timeout=90, allow_redirects=True, retries=2)
    except requests.RequestException:
        return None
    if r is not None and r.ok and b"%PDF" in r.content[:1024]:
        return r.content
    return None


def unpaywall_urls(client, doi):
    try:
        r = client.get(UNPAYWALL + doi, params={"email": client.email}, retries=2)
        if not r.ok:
            return []
        data = r.json()
    except (requests.RequestException, ValueError):
        return []
    urls = []
    locs = [data.get("best_oa_location")] + (data.get("oa_locations") or [])
    for loc in locs:
        if loc and loc.get("url_for_pdf") and loc["url_for_pdf"] not in urls:
            urls.append(loc["url_for_pdf"])
    return urls


def download_all(client, recs, outdir, delay):
    outdir.mkdir(parents=True, exist_ok=True)
    n = len(recs)
    for i, rec in enumerate(recs, 1):
        fname = safe_name(rec)
        path = outdir / fname
        rec["file"], rec["source"] = "", ""
        if path.exists():
            rec["status"], rec["file"] = "already_exists", fname
            print(f"[{i}/{n}] 已存在  {fname}")
            continue

        content = None
        if rec["pmcid"]:
            content = fetch_pdf(client, EPMC_PDF, {"accid": rec["pmcid"], "blobtype": "pdf"})
            if content:
                rec["source"] = "Europe PMC"
        if not content and rec["doi"]:
            for url in unpaywall_urls(client, rec["doi"]):
                content = fetch_pdf(client, url)
                if content:
                    rec["source"] = "Unpaywall"
                    break
                time.sleep(0.5)

        if content:
            path.write_bytes(content)
            rec["status"], rec["file"] = "downloaded", fname
            print(f"[{i}/{n}] 下載成功（{rec['source']}）  {fname}")
        else:
            rec["status"] = "no_oa_pdf"
            print(f"[{i}/{n}] 無 OA 全文  {rec['doi'] or rec['pmid']}")
        time.sleep(delay)


def write_reports(recs, outdir):
    cols = ["status", "source", "file", "pmid", "pmcid", "doi", "author", "year", "title"]
    log = outdir / "download_log.csv"
    with open(log, "w", newline="", encoding="utf-8-sig") as f:   # utf-8-sig：Excel 開啟不會亂碼
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(recs)

    missing = [r for r in recs if r.get("status") == "no_oa_pdf"]
    with open(outdir / "not_found_dois.txt", "w", encoding="utf-8") as f:
        for r in missing:
            if r["doi"]:
                f.write(r["doi"] + "\n")
    no_doi = [r for r in missing if not r["doi"]]

    ok = sum(r.get("status") in ("downloaded", "already_exists") for r in recs)
    print("\n========== 完成 ==========")
    print(f"總筆數：{len(recs)}　取得全文：{ok}　未取得：{len(missing)}")
    print(f"紀錄檔：{log}")
    print(f"未取得的 DOI 清單：{outdir / 'not_found_dois.txt'}（可貼進 Zotero 補抓）")
    if no_doi:
        print(f"另有 {len(no_doi)} 篇沒有 DOI，請看紀錄檔手動處理。")


# ---------------------------------------------------------------- 主程式
def main():
    try:
        sys.stdout.reconfigure(errors="replace")
    except AttributeError:
        pass
    ap = argparse.ArgumentParser(description="批次下載開放取用的全文 PDF")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--query", help="PubMed 檢索式")
    src.add_argument("--ids", help="識別碼清單檔（PMID / DOI / PMCID，每行一個）")
    src.add_argument("--ris", help="RIS 檔（例如 Embase、Scopus 匯出）")
    ap.add_argument("--email", default=os.environ.get("OA_FETCHER_EMAIL"),
                    help="你的 email（NCBI 與 Unpaywall 要求提供；預設讀環境變數 OA_FETCHER_EMAIL）")
    ap.add_argument("--api-key", default=os.environ.get("NCBI_API_KEY"),
                    help="NCBI API key（選填；預設讀環境變數 NCBI_API_KEY）")
    ap.add_argument("--out", default="pdfs", help="輸出資料夾（預設 ./pdfs）")
    ap.add_argument("--max", type=int, help="最多處理幾篇")
    ap.add_argument("--delay", type=float, default=1.0, help="下載間隔秒數（預設 1.0）")
    args = ap.parse_args()
    if not args.email:
        ap.error("需要 email：請加 --email，或設定環境變數 OA_FETCHER_EMAIL")

    client = Client(args.email, args.api_key)
    outdir = Path(args.out)

    if args.query:
        pmids = esearch(client, args.query, args.max)
        recs = efetch_records(client, pmids)
    elif args.ids:
        recs = records_from_ids(client, args.ids)
    else:
        recs = parse_ris(args.ris)
        print(f"RIS 讀入 {len(recs)} 筆")

    # 去重（DOI 優先，其次 PMID）
    seen, uniq = set(), []
    for r in recs:
        key = (r["doi"] or "").lower() or r["pmid"] or r["pmcid"] or r["title"].lower()
        if key and key in seen:
            continue
        seen.add(key)
        uniq.append(r)
    recs = uniq[:args.max] if args.max else uniq

    print("以 Europe PMC 比對 PMC 全文...")
    enrich_with_epmc(client, recs)

    print(f"開始下載，共 {len(recs)} 篇\n")
    download_all(client, recs, outdir, args.delay)
    write_reports(recs, outdir)


if __name__ == "__main__":
    try:
        main()
    except requests.RequestException as e:
        sys.exit(f"\n連線失敗：{e}\n請確認網路連線，或稍後再試（NCBI 偶爾會暫時無回應）。")
    except KeyboardInterrupt:
        sys.exit("\n已中斷。已下載的 PDF 會保留，重新執行時會自動略過。")
