---
name: oa-pdf-fetcher
description: Batch-download legally open-access full-text PDFs of biomedical articles to the user's computer, from a PubMed search string, a list of PMIDs/DOIs/PMCIDs, or an RIS export (Embase, Scopus, Web of Science). Sources are Europe PMC and Unpaywall; articles without an OA copy are listed for follow-up in Zotero. Use this skill whenever the user wants to download, fetch, collect or retrieve full texts or PDFs of papers in bulk, gather PDFs for a systematic review, scoping review or meta-analysis, or turn a PubMed/Embase result set into a folder of PDFs, even if they don't say "open access". Also triggers on Chinese requests such as 下載文獻全文, 批次下載 PDF, 抓全文, 自動下載論文.
---

# OA PDF Fetcher

Downloads open-access (OA) full-text PDFs in bulk and produces a log of what was and wasn't found.

The bundled script is `scripts/oa_pdf_fetcher.py`, relative to this skill's base directory (shown when the skill loads). Run it with an absolute path built from that directory; there is no need to copy it elsewhere.

## Scope: open access only

The script gets PDFs from two places:
1. **Europe PMC**, for articles with a PMC full text.
2. **Unpaywall**, for publisher OA versions, author manuscripts and repository copies.

Paywalled articles are not downloaded, even if the user's institution subscribes. Publisher licences (Elsevier, Wiley, Springer and others) forbid automated bulk downloading, and detection can get a whole university's IP range blocked. So if a user asks to extend the script to scrape publisher sites, log in through a library proxy, or use Sci-Hub-style mirrors, explain this and point them to the Zotero step below instead. That route uses their legitimate access at a human pace and is what librarians recommend for systematic reviews.

## Workflow

### 1. Work out the input

- **A topic or research question, no search string yet**: draft a PubMed query (MeSH terms plus [tiab] synonyms, combined with AND/OR). Show it to the user and get a yes before running, because the query decides the whole result set.
- **A PubMed search string or search-results URL**: use the string as is. From a URL, take the `term=` parameter and URL-decode it.
- **PMIDs, DOIs or PMCIDs** (pasted, or in a file): write them one per line to a text file and use `--ids`.
- **An RIS file** (Embase, Scopus, Web of Science, EndNote or Zotero export): use `--ris`. Embase cannot be searched through an API without a separate Elsevier licence, so an RIS export is the only way to bring Embase records in.

### 2. Check prerequisites

- **Email.** NCBI and Unpaywall require a contact email.
  - The script reads it from the `OA_FETCHER_EMAIL` environment variable, or from `--email`.
  - If neither is set, ask the user for it once. Then suggest they set it permanently, so future runs need nothing:
    - Windows: `setx OA_FETCHER_EMAIL "name@example.com"` (takes effect in new terminals)
    - macOS/Linux: add `export OA_FETCHER_EMAIL=...` to the shell profile
- **NCBI API key** (optional). It is read from `NCBI_API_KEY` or `--api-key`, and raises the PubMed rate limit from 3 to 10 requests per second. Mention it for large searches only.
- **Python.** The script needs Python 3.8+ and `requests`.
  - If `import requests` fails, run `pip install requests`. Use `python -m pip` or `py -m pip` on Windows if `pip` isn't on PATH.
  - On Windows the interpreter is usually `python` or `py`, not `python3`.

### 3. Run

```
python <skill-dir>/scripts/oa_pdf_fetcher.py --query "<search string>" --out <folder>
python <skill-dir>/scripts/oa_pdf_fetcher.py --ids ids.txt --out <folder>
python <skill-dir>/scripts/oa_pdf_fetcher.py --ris export.ris --out <folder>
```

Options:
- `--out`: the output folder. Default is `./pdfs`. Use a meaningful name in the user's project folder, e.g. `pdfs_statin_frailty`.
- `--max N`: process at most N articles.
- `--delay S`: seconds between downloads. Default 1.0; keep it at least that to stay polite to the servers.

Practical points:
- **Large result sets.** Each article takes a few seconds, so 500 articles can take half an hour or more.
  - When a PubMed query returns more than about 300 records, tell the user the count and expected time before downloading everything. Offer a `--max 10` trial first if this is their first run.
  - Run long jobs in the background and check progress, instead of blocking.
- **Over 10,000 PubMed results.** PubMed returns at most 10,000 IDs per search. Split the query by publication year (e.g. `AND 2015:2020[dp]`) and run it in parts, using the same `--out` folder.
- **Resuming.** Re-running with the same `--out` skips PDFs already downloaded, so an interrupted run can simply be restarted.

### 4. Report back

The script prints a summary and writes two files to the output folder:
- `download_log.csv`: one row per article, with status (`downloaded`, `already_exists`, `no_oa_pdf`), source, filename, PMID, PMCID, DOI, first author, year and title. It is UTF-8 with BOM, so it opens cleanly in Excel.
- `not_found_dois.txt`: DOIs of articles with no OA PDF.

Tell the user, briefly:
- how many PDFs were downloaded, out of how many articles
- where the folder is
- what to do with the remainder

A typical OA hit rate is 30–60%, depending on field and publication years. Saying so helps them read the result.

For the remainder, suggest the Zotero route:
1. In Zotero, click the magic-wand button ("Add Item(s) by Identifier") and paste the contents of `not_found_dois.txt`.
2. While on the university network or VPN (with the library's proxy configured in Zotero if needed), select all the new items, right-click, and choose **Find Available PDF**.

Articles with no DOI are marked in the log and have to be handled by hand.

## Troubleshooting

- **Connection or proxy errors to `eutils.ncbi.nlm.nih.gov`.** Usually the network itself, e.g. a firewall or a sandbox without internet. NCBI also has occasional short outages. Wait and retry; don't hammer it.
- **Many `no_oa_pdf` results for articles that look open access.** Some OA hosts block non-browser downloads. Leave these for the Zotero step. Don't spoof browser headers to get around the block.
- **A query that returns 0 results.** Check the syntax in the PubMed web interface first. A common cause is unbalanced quotes or a field tag typo.
