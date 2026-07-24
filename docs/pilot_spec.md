# Fiscal Exposure Pilot: Implementation Spec

**Purpose.** Produce one figure and ~600 words in a day, publishable to GitHub, to attach to the Anthropic Fellows application (Economics & Policy, deadline 26 July 2026, 11:59pm PT).

**Working title.** *Employment exposure is not fiscal exposure: AI exposure and the composition of the US federal tax base.*

---

## 1. The claim, scoped precisely

**What the pilot shows.** Existing AI exposure measures are employment-weighted. Fiscal capacity is not. This computes, for the current US tax base, how much of it sits in occupations that are already highly AI-exposed, and shows that the answer differs sharply depending on whether you weight by headcount, by wages, by income tax paid, or by payroll tax paid.

**What it explicitly does not claim.** It is not a forecast. It is not a displacement estimate. It is a static accounting of the composition of today's tax base by exposure, i.e. how much of the base sits in the line of fire. Saying this plainly in the abstract is what makes it defensible in 24 hours rather than reckless.

**The three-way divergence is the finding.** Prediction, from Anthropic's own reported worker characteristics (top-quartile exposed workers earn ~47% more, are far more educated):

| Weighting | Expected share held by top exposure quartile | Why |
|---|---|---|
| Employment | baseline (~25% by construction) | definitional |
| Wage income | above baseline | exposed workers earn more |
| Federal income tax | well above baseline | progressive schedule compounds the earnings gap |
| OASDI payroll tax | **compressed toward or below baseline** | taxable maximum caps the base above ~top 6% of earners |

If that pattern holds, the one-sentence result is: *AI exposure is concentrated in the part of the workforce that funds general revenue, not the part that funds social insurance.* That is a different fiscal risk profile from the robot era, where displacement was concentrated mid-distribution, and it is a direct, testable qualification of the Hötte et al. (2024) "the effect fades" result.

---

## 2. Data sources

### 2.1 AI exposure (the treatment variable)

**Anthropic Economic Index, `labor_market_impacts` release** — occupation-level observed exposure, CC-BY.

- Dataset root: https://huggingface.co/datasets/Anthropic/EconomicIndex
- Folder: https://huggingface.co/datasets/Anthropic/EconomicIndex/tree/main/labor_market_impacts
- Paper: https://www.anthropic.com/research/labor-market-impacts
- Appendix (formal definition of observed exposure): https://cdn.sanity.io/files/4zrzovbb/website/e5f77fc0e77c0185110b5e4b909602791ae76eae.pdf

```bash
pip install huggingface_hub
huggingface-cli download Anthropic/EconomicIndex --repo-type dataset \
  --include "labor_market_impacts/*" --local-dir data/raw/aei
```

First job in the implementation pass: inspect the schema. We need the occupation identifier (expected O\*NET-SOC 8-digit, e.g. `15-1251.00`) and the coverage/exposure score. Also check whether they ship the task-level file, which we'd want for the robustness check on how exposure aggregates.

**Secondary comparison measure.** Eloundou et al. (2023) β scores, task-level. Useful as a robustness contrast, because Anthropic report that β alone shows *no* correlation with BLS projected growth while observed exposure does. Running the fiscal computation under both is a cheap, honest robustness check.
- arXiv: https://arxiv.org/abs/2303.10130
- Data: https://github.com/openai/GPTs-are-GPTs

### 2.2 Earnings and employment (the weighting variable)

**CPS ASEC.** Two routes; pick based on latency.

*Route A, IPUMS CPS (preferred, cleaner harmonised occupation codes).*
- https://cps.ipums.org/cps/
- Free registration required. **Submit the extract before doing anything else** — processing can take from minutes to a couple of hours, and it is the blocking dependency for the whole day.
- Variables: `YEAR`, `ASECWT`, `AGE`, `SEX`, `EDUC`, `EMPSTAT`, `CLASSWKR`, `OCC`, `OCC2010`, `OCC1990`, `IND`, `INCWAGE`, `INCBUS`, `INCFARM`, `UHRSWORKLY`, `WKSWORK1`, `STATEFIP`, `MARST`, `NCHILD`, `AGI`-relevant income components if going to TAXSIM (`INCTOT`, `INCINT`, `INCDIVID`, `INCRENT`, `INCSS`, `INCRETIR`).
- Sample: ASEC 2024 and 2025 (use 2025 if available; pool if sample size is tight at fine occupation detail).
- Python client: `ipumspy` (https://github.com/ipums/ipumspy). R: `ipumsr`.

*Route B, Census direct (no queue, immediate).*
- https://www.census.gov/data/datasets/time-series/demo/cps/cps-asec.html
- Fixed-width public use microdata + data dictionary. More parsing work, zero waiting. Good fallback if IPUMS stalls.

**Note on top-coding.** CPS top-codes and swaps high incomes. This will *understate* the concentration of income and tax in high-earning occupations, which biases the headline result toward zero. State this: a conservative bias is a feature in a first pass, and it motivates the PUF-based extension.

### 2.3 The crosswalk (the actual hard part)

O\*NET-SOC 8-digit → SOC → CPS occupation codes. Do not build this yourself.

**Use the same crosswalk Anthropic used.** Massenkoff and McCrory state they matched O\*NET-SOC to `occ1990` codes in the CPS using the crosswalk from Eckhardt and Goldschlag (2025), Economic Innovation Group:
- https://eig.org/ai-and-jobs-the-final-word/

Using their crosswalk means your occupation mapping is identical to theirs, so any divergence in results is attributable to the fiscal layer, not to plumbing. That is worth saying explicitly in the writeup.

Backups if the EIG file is awkward:
- O\*NET taxonomy and SOC crosswalks: https://www.onetcenter.org/taxonomy.html and https://www.onetcenter.org/crosswalks.html
- BLS SOC crosswalks: https://www.bls.gov/soc/2018/crosswalks.htm
- IPUMS occupation crosswalk documentation: https://cps.ipums.org/cps/occ_transition.shtml

**Aggregation rule.** O\*NET-SOC is finer than CPS occupation. When several O\*NET codes map to one CPS code, aggregate the exposure score weighted by O\*NET-SOC employment (from BLS OES, https://www.bls.gov/oes/tables.htm) rather than taking a simple mean. Record the choice and show the simple-mean version as a robustness row.

### 2.4 Tax liability (the outcome variable)

*Minimum viable (do this first).* Skip the calculator entirely for v0 and compute wage-income shares only. This alone gives a publishable figure and a real number.

*The version worth having.* Actual federal liability per CPS record.

**NBER TAXSIM 35** — free, fast, well-trodden with CPS ASEC.
- https://taxsim.nber.org/
- R wrapper: `usincometaxes` (https://www.shanejorr.com/usincometaxes/)
- Python/Stata interfaces: https://taxsim.nber.org/taxsim35/
- Returns federal income tax liability and FICA separately, which is exactly the split we need.

**Policy Simulation Library Tax-Calculator** — open source, ships a public CPS-derived microdata file.
- https://github.com/PSLmodels/Tax-Calculator
- Docs: https://taxcalc.pslmodels.org/
- Relevant because Budget Lab's stated blocker is that the IRS PUF carries no occupation. CPS does. Starting from CPS sidesteps the imputation problem entirely for a first pass, at the cost of top-income accuracy. That trade is the methodological point of the pilot, and it points directly at what four months would buy: doing the imputation properly onto the PUF.

**Payroll cap parameters.** Social Security taxable maximum, contribution and benefit base by year:
- https://www.ssa.gov/oact/cola/cbb.html (verify the current year figure; the 2025 base was $176,100)
- Roughly the top 6% of covered earners sit above it. That is the mechanism behind the compression prediction, so get the number right and cite it.

---

## 3. Computation

Let $o$ index occupations, $i$ index CPS persons with ASEC weight $w_i$, occupation $o(i)$, wage income $y_i$, and exposure $e_{o(i)}$.

**Step 1. Quartiles.** Rank occupations by $e_o$ and cut into quartiles *weighted by employment*, so each quartile holds ~25% of workers, not ~25% of occupations. Also construct Anthropic's own grouping (the ~30% zero-exposure group vs the top quartile) so the numbers are directly comparable to their Figure 5.

**Step 2. Shares.** For quartile $q$:

$$S^{\text{emp}}_q = \frac{\sum_{i \in q} w_i}{\sum_i w_i}, \qquad S^{\text{wage}}_q = \frac{\sum_{i \in q} w_i y_i}{\sum_i w_i y_i}$$

$$S^{\text{IIT}}_q = \frac{\sum_{i \in q} w_i \, T^{\text{IIT}}_i}{\sum_i w_i T^{\text{IIT}}_i}, \qquad S^{\text{OASDI}}_q = \frac{\sum_{i \in q} w_i \, T^{\text{OASDI}}_i}{\sum_i w_i T^{\text{OASDI}}_i}$$

**Step 3. Amplification factors.** $A^{X}_q = S^{X}_q / S^{\text{emp}}_q$ for $X \in \{\text{wage}, \text{IIT}, \text{OASDI}\}$.

The headline number is $A^{\text{IIT}}_{Q4}$: how many times more of the income tax base sits in the top exposure quartile than its employment share would suggest. The counterpart, $A^{\text{OASDI}}_{Q4}$, should be markedly lower. **The gap between those two numbers is the paper.**

**Step 4. Tax-unit allocation caveat.** Tax is levied on units, not persons. For v0, assign each person's individual liability by their own occupation. For joint filers with two earners in different exposure quartiles this is an approximation. Handle it by (a) reporting a single-earner-household-only variant as a robustness check, and (b) naming it as a limitation. Do not try to solve it in a day.

---

## 4. The figure

**Panel A (the money shot).** Four bars, top exposure quartile only: share of employment, share of wage income, share of federal income tax, share of OASDI payroll tax. Horizontal reference line at the employment share. Reads in five seconds.

**Panel B (the gradient).** Same four series across all four quartiles, grouped bars or a slope chart. Shows the divergence is monotone, not an artefact of the cutoff.

**Optional Panel C.** Cumulative curve: occupations ranked by exposure on the x-axis, cumulative share of employment vs cumulative share of income tax as two lines. The area between them is the amplification, visually.

Vary the treatment cutoff from the median to the 95th percentile and show the headline number is stable, mirroring what Anthropic do in their appendix.

---

## 5. Honesty section (do not skip; this is being graded)

The posting explicitly asks for people "skilled at writing up and communicating your results, even when they're null or unexpected." A short, unflinching limitations section is worth more than a bigger headline number.

- Exposure is measured from **Claude usage**, not all AI usage. Anthropic say this themselves.
- Exposure is **not displacement**. Anthropic find no systematic unemployment increase in exposed occupations to date. This is a measure of what is at stake, not what is happening.
- The Eloundou et al. capability layer is pinned to **early-2023** LLM capability.
- CPS occupation is **self-reported** and measured with error; income is **top-coded**, biasing the result downward.
- Static accounting: **no behavioural response, no reallocation, no general equilibrium.** Displaced workers in reality move to other occupations; that is precisely the mechanism Hötte et al. find rescued the robot-era tax base, and the whole question is whether it recurs.
- Quartile cutoffs are a choice; results are shown across cutoffs.

Also cite the opposing view directly and fairly: ITIF (May 2026) argue the tax-base erosion concern is overstated because labor's share would have to fall dramatically and persistently, and displaced workers historically transition rather than disappear. Engaging that head-on is a credibility signal, and it is exactly what your KOF letter already does with Hötte.

---

## 6. Repository

```
ai-fiscal-exposure/
├── README.md              # the 600 words, figure embedded at top
├── environment / pyproject.toml   # pinned (uv), consistent with how you already work
├── data/
│   ├── raw/               # gitignored; download script instead
│   └── README.md          # exact provenance + retrieval instructions per source
├── src/
│   ├── 01_fetch.py        # AEI download, crosswalk fetch
│   ├── 02_crosswalk.py    # O*NET-SOC -> CPS occ, with employment weighting
│   ├── 03_merge.py        # exposure onto CPS ASEC persons
│   ├── 04_tax.py          # TAXSIM / Tax-Calculator call
│   └── 05_figures.py
├── notebooks/
│   └── walkthrough.ipynb  # narrative version, runs end to end
├── output/
│   └── figures/
└── tests/                 # at minimum: crosswalk coverage, weight totals vs published CPS
```

Two tests worth writing even under time pressure, because they are the ones that catch real errors: (1) crosswalk coverage — what fraction of CPS employment successfully receives an exposure score, reported in the README; (2) weighted employment and aggregate wage totals reconciled against published BLS/Census aggregates.

This structure is also self-serving in the right way: version control, pinned environments, test coverage and traceable provenance are exactly the practices you describe in your CV, so the repo demonstrates the claim rather than asserting it.

---

## 7. Day plan

| Time | Task | Note |
|---|---|---|
| 0:00 | **Submit IPUMS extract** | Blocking dependency. Do this first, before reading anything. |
| 0:15 | Download AEI `labor_market_impacts`, inspect schema | |
| 0:45 | Fetch EIG crosswalk, inspect | |
| 1:30 | Build crosswalk mapping, report coverage % | The most likely place to lose time |
| 2:30 | Merge exposure onto CPS, compute employment + wage shares | **v0 result exists here.** Stop and look at the number. |
| 3:30 | TAXSIM run, IIT and OASDI shares | If it fights back, ship v0 |
| 4:30 | Figures | |
| 5:30 | Write README (600 words) | |
| 6:30 | Tests, cleanup, push | |

**Hard rule: if TAXSIM is not working by hour four, ship the wage-share version.** A clean figure with employment vs wage income already makes the point and is honest about the rest being next. A broken repo at midnight is worse than a modest one at 6pm.

---

## 8. Literature, with links

**The gap you are filling**
- Anthropic, *Economic Policy Framework*, June 2026 — states that a labor-to-capital shift means the tax system captures a shrinking share of a growing economy, names UBI / sovereign wealth funds / equity-sharing as candidate mechanisms, and says they are investing in the research required to evaluate them. https://www.anthropic.com/economic-futures
- The Budget Lab at Yale, *Methodology: How potential AI futures interact with the current tax system*, 20 July 2026 — the named missing piece is "an occupation-level exposure imputation onto the tax-unit file." https://budgetlab.yale.edu/research/methodology-how-potential-ai-futures-interact-current-tax-system
- The Budget Lab at Yale, *How potential AI futures would play out in the current tax system*, July 2026. https://budgetlab.yale.edu/research/how-potential-ai-futures-would-play-out-current-tax-system

**The measure**
- Massenkoff, M. and McCrory, P. (2026), *Labor market impacts of AI: A new measure and early evidence*. https://www.anthropic.com/research/labor-market-impacts
- Anthropic Economic Index, *Learning curves* (5th report, March 2026). https://www.anthropic.com/research/economic-index-march-2026-report
- Handa, K. et al. (2025), *Which Economic Tasks are Performed with AI?* arXiv:2503.04761. https://arxiv.org/abs/2503.04761
- Eloundou, T., Manning, S., Mishkin, P., Rock, D. (2023), *GPTs are GPTs*. arXiv:2303.10130

**Public finance under AI (the theory you are giving empirics to)**
- Korinek, A. and Lockwood, L., *Preserving Fiscal Stability in the Age of Transformative AI*, Digitalist Papers Vol. 2, Dec 2025. https://www.digitalistpapers.com/vol2/korineklockwood
- Korinek, A. and Lockwood, L., *Public Finance in the Age of AI: A Primer*, NBER volume, Nov 2025 (NBER #34873).
- Korinek, A. and Lockwood, L., *The Future of Tax Policy: A Public Finance Framework for the Age of AI*, Brookings, Jan 2026.
- Both authors' listings: https://leemlockwood.com/research.html
- Windfall Trust, *Mapping Tax Risks From Labour-Displacing AI* — estimates for an "average OECD country"; lists tax base composition and AI exposure as unquantified sources of cross-country variation (this is your extension). https://windfalltrust.org/publications/mapping-tax-risks-from-labour-displacing-ai

**The automation-era benchmark you are testing against**
- Hötte, K. et al. (2024), Oxford Economic Papers — robot adoption matched to OECD tax records; revenue depressed early in diffusion, effect fades as new jobs appear. *(Verify exact citation details before publishing.)*
- Acemoglu, D. and Restrepo, P. (2020), *Robots and Jobs: Evidence from US Labor Markets*, JPE 128(6).
- Acemoglu, D., Autor, D., Hazell, J., Restrepo, P. (2022), *Artificial intelligence and jobs: Evidence from online vacancies*, JOLE 40(S1).
- Graetz, G. and Michaels, G. (2018), *Robots at Work*, REStat 100(5).

**Current labour-market evidence**
- Brynjolfsson, E., Chandar, B., Chen, R. (2025), *Canaries in the Coal Mine*.
- Gimbel, M., Kinder, M., Kendall, J., Lee, M. (2025), *Evaluating the Impact of AI on the Labor Market*, Budget Lab.
- Hampole, M., Papanikolaou, D., Schmidt, L., Seegmiller, B. (2025), NBER.

**The opposing view (cite it)**
- ITIF (14 May 2026), *AI Is Not Going to Reduce Labor's Share of Income or Destroy the Tax Base*. https://itif.org/publications/2026/05/14/ai-not-going-reduce-labors-share-of-income-or-destroy-tax-base/

**Method / plumbing**
- Eckhardt, S. and Goldschlag, N. (2025), *AI and Jobs: The Final Word (Until the Next One)*, EIG — the O\*NET-to-CPS crosswalk. https://eig.org/ai-and-jobs-the-final-word/
- Saez, E. and Zucman, G. (2020), JEP 34(4) — labor/capital split of pass-through income, for the extension.
- Feenberg, D. and Coutts, E., NBER TAXSIM. https://taxsim.nber.org/

---

## 9. The paragraph this buys you

Once the number exists, the "research areas you're excited about" answer stops being a proposal and becomes a report:

> *Every AI exposure measure is employment-weighted; fiscal capacity is not. Using Anthropic's published observed-exposure data against CPS ASEC, I find the top exposure quartile holds [X]% of US employment but [Y]% of the federal income tax base and only [Z]% of the OASDI payroll base. Exposure is concentrated in the revenue that funds general government, not the revenue that funds social insurance, which is the opposite of the robot era. That has a direct bearing on the Tier 3 question in Anthropic's policy framework, and on the Budget Lab's stated need for an occupation-level exposure imputation onto the tax-unit file. Four months would let me do that imputation properly against the PUF, and extend it across OECD tax mixes, where the sovereign-wealth-fund answer is unavailable to countries that do not host the firms.*

Fill in three numbers, and that is the strongest paragraph in the application.
