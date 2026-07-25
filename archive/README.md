# Employment exposure is not fiscal exposure

**How much of the US federal tax base sits in occupations already exposed to AI, and how does that differ from how much of the workforce does?**

> **Status: pipeline complete, running on synthetic fixtures.** Every number and
> figure below is currently generated from `fiscal_exposure.synthetic` and is
> meaningless. Figures produced from fixtures carry a `SYNTHETIC DATA`
> watermark. Real results land once the CPS ASEC extract clears.

![Headline figure](output/figures/fig1_fiscal_exposure.png)

---

## The question

Every measure of AI exposure is employment-weighted. It asks what share of
*workers* are in exposed occupations. Fiscal capacity is not distributed like
headcount: under a progressive income tax, revenue is far more concentrated than
employment, and above the Social Security taxable maximum the payroll tax stops
accruing altogether.

Anthropic's own data says exposure is concentrated at the top of the earnings
distribution: workers in the most exposed occupations earn roughly 47% more than
the unexposed, and are almost four times as likely to hold a graduate degree.
If that is right, then three things follow that nobody has measured:

1. The **wage base** in exposed occupations exceeds their employment share.
2. The **income tax base** exceeds even that, because progressivity compounds
   the earnings gap.
3. The **payroll tax base** does *not*, because the taxable maximum truncates
   liability at precisely the earnings levels where exposure concentrates.

The spread between (2) and (3) is the finding. It implies AI exposure threatens
the revenue that funds general government rather than the revenue that funds
social insurance, which is the opposite of the robot era, when displacement was
concentrated in the middle of the wage distribution.

## Results

<!-- FILL: replace with real numbers once the CPS extract lands -->

| Base | Share held by top exposure quartile | Amplification vs employment |
|---|---|---|
| Employment | `X.X%` | 1.00 |
| Wage income | `X.X%` | `X.XX` |
| Federal income tax | `X.X%` | `X.XX` |
| Payroll tax (OASDI) | `X.X%` | `X.XX` |

## What this is not

This is a static accounting of the **composition of today's tax base**, not a
forecast and not a displacement estimate. It measures how much of the base sits
in the line of fire, not how much will be lost. Specifically:

- Exposure is measured from **Claude usage**, not all AI usage.
- **Exposure is not displacement.** Anthropic find no systematic increase in
  unemployment for highly exposed workers to date, with only tentative evidence
  of slowed hiring among workers aged 22 to 25.
- The theoretical-capability layer is pinned to **early-2023** LLM capability.
- CPS occupation is self-reported; wage income is top-coded, which biases the
  headline **downward**.
- **No behavioural response, no reallocation, no general equilibrium.**
  Displaced workers move to other occupations in reality, and that is precisely
  the mechanism which rescued the tax base in the robot era. Whether it recurs
  is the open question, not something this exercise settles.
- Tax is levied on units, not persons; a two-earner couple split across exposure
  groups is approximated. A single-earner-household variant is reported.

The opposing case deserves stating plainly: ITIF argue the erosion concern is
overstated, because labour's share would have to fall dramatically and
persistently, and because displaced workers historically transition rather than
disappear. Nothing here refutes that. What it does is change *which* revenue
stream is at risk, which matters for the argument either way.

## Why it matters

The Budget Lab at Yale's AI tax microsimulation names one missing input: "the
missing piece is an occupation-level exposure imputation onto the tax-unit
file", absent because the IRS Public Use File carries no occupation. Anthropic's
policy framework says new revenue sources will be needed if income shifts from
labour to capital, names universal basic income and AI sovereign wealth funds as
candidate mechanisms, and states it is investing in the research required to
evaluate them. Every one of those mechanisms assumes a state that can still
raise revenue. This measures whether the assumption holds, and where it fails
first.

## Quickstart

```bash
git clone https://github.com/morvanzmt/ai-fiscal-exposure
cd ai-fiscal-exposure
uv venv && source .venv/bin/activate
uv pip install -e ".[dev,notebook,fetch]"

# Run end to end on synthetic fixtures, no downloads needed
python scripts/01_fetch.py --synthetic
python scripts/02_build_dataset.py --config config/config.synthetic.yaml
pytest
```

For real data, see [`data/README.md`](data/README.md), then:

```bash
python scripts/01_fetch.py --aei
python scripts/00_inspect_schemas.py --dir data/raw --full   # pin the schema
cp config/config.example.yaml config/config.yaml             # fill FILL_ME fields
python scripts/02_build_dataset.py --config config/config.yaml
```

Walkthrough: [`notebooks/walkthrough.ipynb`](notebooks/walkthrough.ipynb).

## Reproducibility

Every pipeline step appends to `output/manifest.json`: the files read and
written with SHA-256 digests, the parameters in force, the git revision, and
diagnostic metrics such as crosswalk coverage. Any figure traces back to the
exact inputs that produced it. Paths, column names and analysis parameters live
in `config/`, never in code.

Two tests exist because they catch errors that eyeballing a figure would not:
tied exposure scores must not be split across bins (roughly 30% of workers sit
at exactly zero exposure), and OASDI liability must flatten above the taxable
maximum, which is the entire mechanism behind the payroll result.

## Next

- Statistical match of occupation onto the IRS PUF, so the exposure scenario can
  slot into a full tax microsimulation rather than a CPS approximation.
- Extension across OECD tax mixes. The same exposure shock has different fiscal
  consequences depending on whether a country finances social protection through
  payroll contributions or through VAT. This also bounds the sovereign wealth
  fund proposals, which are only available to countries that host the firms.
- Decomposition of amplification into progressivity, the payroll cap, and the
  occupational earnings gradient.

## Sources

Massenkoff and McCrory (2026), *Labor market impacts of AI: A new measure and
early evidence* · Anthropic Economic Index, `labor_market_impacts` release
(CC-BY) · CPS ASEC via IPUMS · Eckhardt and Goldschlag (2025) crosswalk, EIG ·
Korinek and Lockwood (2025), *Preserving Fiscal Stability in the Age of
Transformative AI* · Hötte et al. (2024), *Oxford Economic Papers* · Acemoglu
and Restrepo (2020), *JPE* · Eloundou et al. (2023) · The Budget Lab at Yale
(2026) · Windfall Trust, *Mapping Tax Risks From Labour-Displacing AI* · ITIF
(2026). Full links in [`data/README.md`](data/README.md).

## Licence

MIT (code). Input data remains under its original licence; the Anthropic
Economic Index is CC-BY.
