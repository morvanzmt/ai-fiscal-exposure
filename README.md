# Employment exposure is not fiscal exposure

**How much of the US federal tax base sits in occupations exposed to AI, and how does that differ from how much of the workforce does?**

![Headline figure](output/figures/fig1_fiscal_exposure.png)

## The question

Every measure of AI exposure is employment-weighted. It asks what share of *workers* sit in exposed occupations. Fiscal capacity is not distributed like headcount: under a progressive income tax, revenue is far more concentrated than employment, and above the Social Security taxable maximum the payroll tax stops accruing altogether.

So the workforce share and the tax-base share should come apart. This measures by how much, using Anthropic's published observed-exposure data joined to CPS ASEC microdata.

## Results

CPS ASEC 2024 and 2025, employed persons with positive wage income. Exposure attached to 94.4% of weighted employment.

**Share of each base, by exposure group**

| | Zero exposure | Middle | Top quartile |
|---|---|---|---|
| Employment | 29.0% | 45.9% | 25.2% |
| Wage income | 20.0% | 51.4% | 28.7% |
| Federal income tax | 15.6% | 54.3% | 30.1% |
| Payroll tax (OASDI) | 21.2% | 50.4% | 28.4% |

**Amplification, each base share divided by the same group's employment share**

| | Zero exposure | Middle | Top quartile |
|---|---|---|---|
| Wage income | 0.69 | 1.12 | 1.14 |
| Federal income tax | **0.54** | **1.18** | **1.19** |
| Payroll tax (OASDI) | 0.73 | 1.10 | 1.13 |

Three things follow.

**1. The tax base is markedly more exposed than the workforce.** 71.0% of workers are in occupations with any observed AI exposure, and they pay 84.4% of federal income tax. Per worker, someone in an exposed occupation pays **2.2 times** the federal income tax of someone in an unexposed one, against a wage gap of 1.65 times. Progressivity roughly doubles the fiscal footprint of the earnings gap.

**2. It is a threshold, not a gradient.** This is the result I did not expect. Income tax amplification runs 0.54, 1.18, 1.19 across the three groups. Almost the entire effect sits at the boundary between zero exposure and any exposure (+0.65), with essentially nothing across the whole remaining range (+0.01). Ranking occupations by *how* exposed they are adds close to no fiscal information once you know *whether* they are exposed at all. Any fiscal early-warning indicator built on this data should therefore track the size of the zero-exposure group, not the intensity of exposure at the top.

**3. Exposed and unexposed work are financed through different taxes.** For every dollar of income-tax base they generate, zero-exposure workers supply **1.36** dollars of OASDI base; exposed workers supply **0.95**. Unexposed employment is relatively payroll-financed, exposed employment relatively income-tax-financed. Displacement concentrated in exposed occupations therefore lands on general revenue, while the Social Security and Medicare trust funds are comparatively more dependent on the unexposed workforce. That is the reverse of the industrial-robot era, when displacement fell in the middle of the wage distribution.

The direct top-quartile payroll spread is smaller than the mechanism alone would predict: income tax amplification 1.19 against OASDI 1.13, a gap of just +0.07. See below.

## What this is not

A static accounting of the composition of **today's** tax base. Not a forecast, not a displacement estimate. It measures how much of the base sits in the line of fire, not how much will be lost.

- Exposure is measured from **Claude usage**, not all AI usage.
- **Exposure is not displacement.** Anthropic find no systematic unemployment increase among exposed workers so far.
- The theoretical-capability layer is pinned to early-2023 LLM capability.
- **No behavioural response, no reallocation, no general equilibrium.** Displaced workers move to other occupations in reality, and that is exactly the mechanism which rescued the tax base in the robot era. Whether it recurs is the open question, and nothing here settles it.
- Tax is levied on units, not persons; two-earner couples split across exposure groups are approximated.

### Why the payroll spread is probably understated

Two known limitations both push the same way, and both bite hardest exactly where the mechanism lives.

**CPS top-codes wage income.** The Social Security taxable maximum sits near the top 6% of earners, so the compression of OASDI liability is a phenomenon of the upper tail. That tail is precisely what top-coding flattens. The result is conservative by construction.

**The tax function is crude.** Liability is computed from statutory brackets on wage income for a single filer with no dependants, credits, or non-wage income. It preserves progressivity, which is what the amplification result depends on, but it misstates levels and cannot capture how filing status and non-wage income redistribute liability at the top.

Neither is a reason to doubt the direction. Both are reasons to want better data, which is the next step rather than a caveat.

### Sanity checks that passed

- Zero-exposure group is 28.9% of weighted employment, against the roughly 30% Anthropic report.
- Crosswalk covers 93.9% of CPS occupation codes and 94.4% of weighted employment.
- Implied wage gap between top-quartile and zero-exposure groups is +65%, against the roughly +47% Anthropic report. Larger, same direction; the likely cause is that this analysis restricts to employed persons with positive wage income, a narrower universe than theirs.

### One honest join caveat

Where a Census occupation category spans several SOC occupations, exposure is averaged **equally** across them. Weighting by BLS OES employment would be better. The hook exists (`crosswalk.weight_col`) and is unused.

## Why it matters

The Budget Lab at Yale's AI tax microsimulation names one missing input: "the missing piece is an occupation-level exposure imputation onto the tax-unit file", absent because the IRS Public Use File carries no occupation. CPS does carry occupation, which is why this pilot starts there, at the cost of the top-tail accuracy discussed above.

Anthropic's economic policy framework states that a shift in national income from labour to capital means the current tax system captures a shrinking share of a growing economy, names universal basic income and AI sovereign wealth funds among candidate responses, and says it is investing in the research required to evaluate them. Every one of those mechanisms assumes a state that can still raise revenue. This measures whether that assumption holds, and which revenue stream fails first.

## Next

- **TAXSIM** for real federal liability, using the household variables already in the extract.
- **Statistical match of occupation onto the IRS PUF**, which removes the top-coding problem and slots directly into the Budget Lab's stated gap.
- **Employment-weighted crosswalk aggregation** using BLS OES.
- **Extension across OECD tax mixes.** The same exposure shock has very different fiscal consequences depending on whether a country finances social protection through payroll contributions or through VAT. This also bounds the sovereign wealth fund proposals, which are only available to countries that host the firms.

## Quickstart

```bash
git clone https://github.com/morvanzmt/ai-fiscal-exposure
cd ai-fiscal-exposure
uv venv && source .venv/bin/activate
uv pip install -e ".[dev,notebook,fetch]"

# End to end on synthetic fixtures, no downloads, no credentials
python scripts/01_fetch.py --synthetic
python scripts/02_build_dataset.py --config config/config.synthetic.yaml
pytest
```

For the real run, see [`data/README.md`](data/README.md):

```bash
export IPUMS_API_KEY="..."
python scripts/01b_ipums_extract.py --submit --wait --download
python scripts/01_fetch.py --aei
python scripts/01c_build_crosswalk.py
cp config/config.real.yaml config/config.yaml
python scripts/02_build_dataset.py --config config/config.yaml
```

Walkthrough: [`notebooks/walkthrough.ipynb`](notebooks/walkthrough.ipynb).

## Reproducibility

Every pipeline step appends to `output/manifest.json`: files read and written with SHA-256 digests, parameters in force, git revision, and diagnostics such as crosswalk coverage. Any figure traces back to the inputs that produced it. Paths, column names and analysis parameters live in `config/`, never in code.

Some of the 29 tests exist because they catch errors that eyeballing a figure would not:

- Tied exposure scores must not be split across bins. 29% of workers sit at exactly zero, and a naive quantile cut would divide them arbitrarily. The binning code warns when this happens, which is why headline numbers use the zero-versus-top contrast rather than raw quartiles.
- OASDI liability must flatten above the taxable maximum, the entire mechanism behind the payroll result.
- IPUMS sentinel values (`99999999` for not-in-universe) must be cleared before arithmetic, or they enter weighted totals as hundred-million-dollar salaries.
- Census occupation codes must keep leading zeros, or `0010` becomes `10` and silently fails to merge.

## Data and method notes

Exposure is the *observed exposure* measure of Massenkoff and McCrory (2026): the share of an occupation's time-weighted tasks that are both theoretically feasible for an LLM and observed in work-related Claude usage, with automated use weighted above augmentative use.

The AEI publishes on 6-digit **SOC 2018** codes; the CPS uses **Census occupation codes**. The join uses the Census Bureau's 2018 occupation code list. Two details matter and are handled in `census_crosswalk.py`: the Census list frequently maps a Census code to a SOC *broad group* (`11-9030`) while exposure is published at the *detailed* level (`11-9031`), which must be expanded hierarchically or roughly a third of codes silently fail to match; and the workbook contains a 2010-to-2018 sheet that will merge cleanly while being on the wrong vintage, so sheets are ranked rather than chosen on volume.

## Sources

Massenkoff and McCrory (2026), *Labor market impacts of AI: A new measure and early evidence* · Anthropic Economic Index, `labor_market_impacts` release (CC-BY) · CPS ASEC via IPUMS · US Census Bureau, 2018 Census Occupation Code List · Korinek and Lockwood (2025), *Preserving Fiscal Stability in the Age of Transformative AI* · Hötte et al. (2024), *Oxford Economic Papers* · Acemoglu and Restrepo (2020), *JPE* · Eloundou et al. (2023) · The Budget Lab at Yale (2026) · Windfall Trust, *Mapping Tax Risks From Labour-Displacing AI* · ITIF (2026). Links in [`data/README.md`](data/README.md).

## Licence

MIT (code). Input data remains under its original licence; the Anthropic Economic Index is CC-BY.
