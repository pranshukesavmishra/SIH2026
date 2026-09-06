# SIH 2026 — problem statement selection analysis

Which of the 226 Smart India Hackathon 2026 problem statements to enter, scored against
four filters: five editions of winner patterns, a defence/space mandate, provable
end-to-end buildability, and how hard each statement works to repel the field.

**Full write-up:** the dossier in `sih2026-dossier.html` (open it in a browser).

## Recommendation

| | PS | Organisation | Statement |
|---|---|---|---|
| **Primary** | `SIH26169` | ISRO | AI-based virtual camera tracking for coarse alignment of mobile FSOC terminals |
| Highest ceiling | `SIH26168` | ISRO | AI/ML intelligent dead reckoning for GNSS-denied navigation |
| Maximum DRDO credential | `SIH26055` | DRDO | Smart scan strategy for electronic warfare |
| Hedges | `SIH26159`, `SIH26147` | NTRO | Cryptographic posture assessment from PCAP; `.IQ`/`.wav` signal parameter extraction |

`SIH26169` is recommended over the higher-scoring `SIH26168` because it is the only
statement in the cluster where complete specification coverage is *guaranteed* — you
author the scene, the beacon, the camera, the disturbances and the metrics, so there is
no external dataset, API or hardware that can leave a gap. `SIH26168` asks for
lane-level accuracy through a GNSS blackout, which is a performance target no amount of
preparation can promise.

## Why statement choice dominates

SIH has one winner *per problem statement*, not one national winner. The funnel is:
internal hackathon → SPOC nominates up to 30 teams → idea submission (capped at 500 per
statement) → roughly 5–8 teams per statement reach the Grand Finale. So

    P(shortlist) ≈ 6 / (submissions on your PS)

A statement drawing 400 submissions gives ~1.5%; one drawing 25 gives ~24%. Statement
choice is worth roughly 16×; execution quality is worth roughly 3.6×.

## The crowd-repellence index

`score_problem_statements.py` scores each statement's title and full description for two
opposing vocabularies — one that attracts volume (`portal`, `dashboard`, `chatbot`,
`mobile app`) and one that repels it (`SAR`, `interleaving`, `ephemeris`, `IPsec`,
`dead reckoning`, `electronic warfare`) — combined with acronym density and description
length.

The distinction matters because the low-submission-count strategy is widely known and the
counter is public on the portal. Statements that are merely *unnoticed* get swarmed in the
final week. Statements that are low-count because of a *skill barrier* stay low.

## Reproducing

Both upstream snapshots are public repositories and are fetched rather than vendored:

```sh
mkdir -p analysis/data
git clone --depth 1 https://github.com/NoBugNinja/Smart-India-Hackathon-SIH-2026-Problem-Statements /tmp/ps-desc
git clone --depth 1 https://github.com/Sourav112-droid/sih-2026-problem-statements /tmp/ps-theme
cp /tmp/ps-desc/data/sih2026_ps_*.json analysis/data/sih2026_descriptions.json
cp /tmp/ps-theme/data/sih-2026.json     analysis/data/sih2026_themes.json

python3 analysis/score_problem_statements.py          # defence/space cluster only
python3 analysis/score_problem_statements.py --all    # all 226
```

## Caveats

- **Crowding here is modelled, not measured.** Both snapshots were taken on 21–22 August
  2026, when every statement still read `0/500`. Check live counts on sih.gov.in around
  10–14 September and confirm the picks are genuinely light before locking in.
- Difficulty levels are community-derived estimates from the upstream repository, not
  official SIH ratings.
- The scraped `theme` column in the descriptions snapshot is misaligned against its own
  rows (all 226 disagree with the second source); themes come from the second source.
- The idea submission deadline reads **20 September 2026** on the portal snapshot while
  some secondary write-ups say 30 September. Confirm with your SPOC.
