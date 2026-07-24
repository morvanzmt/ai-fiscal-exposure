# Data

No data is committed to this repository. Everything under `data/` is
gitignored. This file is the provenance record: it says exactly what to fetch,
from where, under what licence, and how to place it.

Run `python scripts/00_inspect_schemas.py` after fetching, and pin the resulting
column names in `config/config.yaml`.

---

## 1. AI exposure — Anthropic Economic Index

Occupation-level *observed exposure*: the share of an occupation's time-weighted
tasks that are both theoretically feasible for an LLM and observed in
work-related Claude usage, with automated use weighted above augmentative use.

- Dataset: <https://huggingface.co/datasets/Anthropic/EconomicIndex>
- Release: `labor_market_impacts/`
- Paper: <https://www.anthropic.com/research/labor-market-impacts>
- Appendix (formal definition): <https://cdn.sanity.io/files/4zrzovbb/website/e5f77fc0e77c0185110b5e4b909602791ae76eae.pdf>
- Licence: data CC-BY, code MIT

```bash
python scripts/01_fetch.py --aei
# or manually
huggingface-cli download Anthropic/EconomicIndex --repo-type dataset \
  --include "labor_market_impacts/*" --local-dir data/raw/aei
```

Place under `data/raw/aei/`.

**Secondary measure for robustness.** Eloundou et al. (2023) task-level β
scores, useful because Anthropic report that β alone shows no correlation with
BLS projected employment growth while observed exposure does.
- <https://arxiv.org/abs/2303.10130>
- <https://github.com/openai/GPTs-are-GPTs>

---

## 2. Earnings and employment — CPS ASEC

### Route A: IPUMS CPS (preferred)

IPUMS does not offer a direct download link. You define an *extract* (which
samples, which variables), submit it, wait for their servers to build it, and
then download the result. Two ways to do that.

#### A1. Scripted, via the IPUMS API (recommended)

Puts the extract definition under version control, and avoids the web UI's
fixed-width default.

```bash
# once
pip install ipumspy
# register at https://cps.ipums.org/cps/  (free)
# create a key at https://account.ipums.org/api_keys
export IPUMS_API_KEY="your key here"

# submit, wait, download in one go
python scripts/01b_ipums_extract.py --submit --wait --download

# or split across sessions
python scripts/01b_ipums_extract.py --submit      # queues it, saves the id
python scripts/01b_ipums_extract.py --status
python scripts/01b_ipums_extract.py --download    # later
```

The samples and variables live in `scripts/01b_ipums_extract.py`; edit there
rather than in a browser.

#### A2. Manual, via the web interface

1. Register and log in at <https://cps.ipums.org/cps/>.
2. **Select Samples.** Click *Select Samples*, untick everything, then tick
   `ASEC 2024` and `ASEC 2025`. Submit sample selections.
3. **Select Variables.** Use the search box to add each variable below to the
   cart. Some sit under harmonised groupings, so search by name rather than
   browsing the tree.
4. **View Cart**, then *Create Data Extract*.
5. **Change the data format to CSV.** The default is fixed-width `.dat`, which
   requires the codebook to parse and is the single most common way this step
   goes wrong. Click *Change* next to Data Format and pick `.csv`.
6. Leave the structure as **rectangular (person)**.
7. Submit. You get an email when it is built, usually within minutes to hours.
8. Download the `.csv.gz` into `data/raw/cps/`. No need to decompress; the
   loader reads gzipped CSV directly.

#### Variables to request

| Purpose | Variables |
|---|---|
| Weights | `ASECWT` |
| Occupation | `OCC`, `OCC2010`, `OCC1990` (request all three; match to the crosswalk target) |
| Industry | `IND` |
| Earnings | `INCWAGE`, `INCBUS`, `INCFARM` |
| Demographics | `AGE`, `SEX`, `EDUC`, `RACE`, `STATEFIP` |
| Labour force | `EMPSTAT`, `CLASSWKR`, `UHRSWORKLY`, `WKSWORK1` |
| For TAXSIM later | `MARST`, `NCHILD`, `INCTOT`, `INCINT`, `INCDIVID`, `INCRENT`, `INCSS`, `INCRETIR` |

IPUMS always adds its own preselected identifiers (`YEAR`, `SERIAL`, `MONTH`,
`CPSID`, `ASECFLAG`, `PERNUM`, `CPSIDP`, `ASECWTH`) on top of these.

**Use `ASECWT`, not `WTFINL`.** `WTFINL` is the basic monthly weight; `ASECWT`
is the person-level supplement weight and is the correct one for ASEC analysis.
Getting this wrong silently changes every share in the results.

Clients: [`ipumspy`](https://github.com/ipums/ipumspy) (Python),
[`ipumsr`](https://tech.popdata.org/ipumsr/) (R).

### Route B: Census Bureau direct (no queue)

<https://www.census.gov/data/datasets/time-series/demo/cps/cps-asec.html>

Fixed-width public use microdata plus data dictionary. More parsing, zero
waiting. Use if IPUMS stalls.

### Two caveats that belong in any writeup

- Occupation is **self-reported** and measured with error.
- Wage income is **top-coded**, which understates concentration at the top and
  therefore biases the headline amplification *toward zero*. The result is
  conservative, and this is the main reason to want the IRS PUF instead.

---

## 3. Crosswalk — O\*NET-SOC to CPS occupation

Use the Eckhardt and Goldschlag (2025) crosswalk from the Economic Innovation
Group, which is the same one Massenkoff and McCrory used to match O\*NET-SOC to
`occ1990` codes in the CPS. Holding the occupation mapping identical to theirs
means any divergence in results is attributable to the fiscal layer rather than
to plumbing.

- <https://eig.org/ai-and-jobs-the-final-word/>

Place under `data/raw/crosswalk/`.

Fallbacks:
- O\*NET taxonomy and crosswalks: <https://www.onetcenter.org/crosswalks.html>
- BLS SOC crosswalks: <https://www.bls.gov/soc/2018/crosswalks.htm>
- IPUMS occupation transitions: <https://cps.ipums.org/cps/occ_transition.shtml>

**Aggregation.** O\*NET-SOC is finer than CPS occupation, so the mapping is
many-to-one. Exposure is aggregated as an employment-weighted mean using BLS OES
employment (<https://www.bls.gov/oes/tables.htm>), with the unweighted mean
retained as a robustness variant. A simple mean would weight a tiny occupation
equally with a huge one, biasing exposure for exactly the large categories that
carry most of the tax base.

---

## 4. Tax parameters

- Social Security contribution and benefit base: <https://www.ssa.gov/oact/cola/cbb.html>
- Statutory brackets and standard deduction: the relevant IRS Revenue Procedure

The values shipped in `config/*.yaml` are **placeholders**. Replace them with
cited values and record the citation in `tax.source` before any published run.

### Tax calculators

- **NBER TAXSIM 35** — <https://taxsim.nber.org/taxsim35/>. Returns federal
  income tax and FICA separately, which is precisely the split this analysis
  needs. R wrapper: [`usincometaxes`](https://www.shanejorr.com/usincometaxes/).
- **PSL Tax-Calculator** — <https://github.com/PSLmodels/Tax-Calculator>. Open
  source, ships a public CPS-derived microdata file.

---

## Why CPS rather than the IRS PUF

The Budget Lab at Yale's AI tax microsimulation names its own missing input: an
occupation-level exposure imputation onto the tax-unit file, absent because the
IRS Public Use File carries no occupation. CPS does carry occupation, so
starting there sidesteps the imputation entirely at the cost of top-income
accuracy. That trade is the methodological point of this pilot, and it defines
the obvious next step: doing the statistical match onto the PUF properly.

- <https://budgetlab.yale.edu/research/methodology-how-potential-ai-futures-interact-current-tax-system>
