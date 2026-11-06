# ClimaGuard AI — QA checklist

Checked: 2026-11-01 (screen checks repeated the same day) · Build: backend `weather-index-v2` engine, web app at `web/` · Tester: Claude Code with DARWIN S

Every acceptance criterion from `documents/ClimaGuard_AI_Epics_and_User_Stories.docx` and the PRD (§3 Must-Haves, §4 metrics, §5 non-functional requirements), each marked with its result and the evidence behind it.

**Result key**
- **Pass:** the criterion is met as written.
- **Pass\*:** met, with a documented change from the original wording (see the design doc's revisions).
- **Partial:** met in part; the gap is stated.
- **Fail:** not met.
- **Not built:** the feature doesn't exist yet.
- **Not checked:** built, but not yet verified.

**Kinds of evidence**
- **Test:** an automated test in `backend/tests/`. Run them all with `cd backend && python -m pytest -q`; 62 pass on 2026-11-01.
- **Browser:** checked by hand in the running app.
- **Real data:** checked against your PostgreSQL data through the API.

## Summary

| | Pass | Pass\* | Partial | Fail | Not built | Not checked |
|---|---|---|---|---|---|---|
| Backlog criteria (43) | 32 | 7 | 2 | 0 | 2 | 0 |
| PRD Must-Have criteria (14) | 12 | 2 | 0 | 0 | 0 | 0 |
| PRD metrics and NFRs (14) | 8 | 3 | 0 | 2 | 0 | 1 |

**Open items, most important first:**
1. **PRD model metrics.** On the 2025-26 season the outlook warned 3 of 8 outbreak months in advance, against 0 of 8 for "same month last year". But the median warning was 1.7 weeks (the target is 2 or more), and 97% of warned months had no outbreak reported. The cause is that the only free case data is sparse outbreak reports; meeting the PRD target needs monthly case counts (Indiastat or IHIP).
2. **E4-S4 is not built** (marking a block visited and showing coverage).
3. **Not yet done:** the "stranger runs it from the README in under 5 minutes" test on a fresh machine.
4. **Found and fixed during the screen checks:** the admin Users screen scrolled sideways at 360 px (599 px wide); fixed.
5. **Found, not fixed:** map labels overlap around Chennai; the 8.6 MB boundaries file is slow on mobile data.

---

## E1 — Platform, data and access

### E1-S1 Admin creates an officer account

| # | Criterion | Result | Evidence |
|---|---|---|---|
| 1 | Admin enters name, official email and district; the account appears in the user list as Deputy Director with that district | Pass | Test `test_full_chain_admin_officer_nurse`; Browser: created a Krishnagiri Deputy Director, shown as "Deputy Director · Krishnagiri · not signed in yet" |
| 2 | An existing email shows "An account with this email already exists" and nothing is created | Pass | Test `test_full_chain_admin_officer_nurse` (case-insensitive duplicate refused with that exact message) |
| 3 | A one-time temporary password is shown once and never stored in plain text | Pass | Tests `test_full_chain_admin_officer_nurse`, `test_password_hash_roundtrip_and_never_plain`; Browser: shown once in a panel, gone after dismissal |

### E1-S2 Officer creates a field staff ID and assigns blocks

| # | Criterion | Result | Evidence |
|---|---|---|---|
| 1 | Signed in as the Krishnagiri officer, the block picker lists only Krishnagiri's blocks | Pass | Test `test_full_chain_admin_officer_nurse`; Browser: picker showed exactly Denkanikottai, Hosur, Krishnagiri, Pochampalli, Uthangarai |
| 2 | Name, mobile and at least one block saves a staff ID, listed with its blocks | Pass\* | Browser: "Staff ID 3 created", listed with Hosur. *Change:* blocks are Census 2011 sub-districts (taluks), since no free block boundaries exist |
| 3 | An already registered mobile shows an error and nothing is created | Pass | Tests `test_full_chain_admin_officer_nurse`, `test_invalid_staff_is_refused`; Real data: "This mobile number is already registered." (409) |

### E1-S3 Sign in and land on the role's home screen

| # | Criterion | Result | Evidence |
|---|---|---|---|
| 1 | Admin lands on user management, Deputy Director on the risk map, nurse on "My blocks" | Pass | Test `test_full_chain_admin_officer_nurse`; Browser: all three roles signed in and landed correctly (the officer's own district opens automatically) |
| 2 | First sign-in with the temporary password forces a new password before continuing | Pass | Test `test_full_chain_admin_officer_nurse` (every endpoint returns 403 until it's changed); Browser: "Set your password" screen with no tabs, for all three roles |
| 3 | A wrong password shows an error and no data | Pass | Tests `test_wrong_password_gives_error_and_no_data`, `test_lockout_after_repeated_failures`; Browser: "Wrong sign-in or password.", password field cleared |
| 4 | Signed out, opening any page by its URL leads to the sign-in screen | Pass | Test `test_signed_out_gets_nothing` (every data endpoint returns 401); Browser: signed out, only the sign-in form shows. The web app has a single URL, so every path shows sign-in |

### E1-S4 System computes district dengue risk levels

| # | Criterion | Result | Evidence |
|---|---|---|---|
| 1 | With cached weather and case files and no network, all 38 districts get a probability and level for 7 and 14 days | Pass\* | Real data, 2026-11-01: scoring ran with the internet blocked and scored 38 districts × 2 horizons (run 60). *Change:* the live engine is a weather suitability index, so the "probability" is a percentile score; fetching the daily forecast itself needs the network |
| 2 | Levels follow the PRD thresholds (Low < 25%, Moderate 25–50%, High 50–75%, Very high > 75%) | Partial | Test `test_levels_follow_prd_thresholds` passes for the ML model. The live index uses percentile levels instead (Low < 50th, Moderate 50–80th, High 80–95th, Very high ≥ 95th), because PRD thresholds on a percentile would put 80% of weeks at High or above (design doc, Revision 2) |
| 3 | The backtest reports detection rate, lead time and Brier score beside "same month last year" | Pass\* | Model backtest (`cli train`) reports all three plus the baseline; Test `test_detection_and_lead_time`. For the live index, `models/index_feedback.json` reports detection and lead time against the baseline; Brier doesn't apply to a percentile score |

## E2 — Risk outlook map

### E2-S1 View the district risk map

| # | Criterion | Result | Evidence |
|---|---|---|---|
| 1 | All 38 districts show a colour and a text label | Pass | Browser: 38 districts drawn, level labels on the map (desktop), plus the "All 38 districts" list with text badges; on phones the labels are off by default and the list or a tap shows them |
| 2 | "Risk estimate, not a diagnosis" is visible without scrolling | Pass | Browser: banner under the header on every screen, desktop and 375 px |
| 3 | Clicking a district opens its detail view | Pass | Browser: clicking Krishnagiri opened the panel with level, score and reasons |

### E2-S2 Switch between 7-day and 14-day outlooks

| # | Criterion | Result | Evidence |
|---|---|---|---|
| 1 | Choosing 14 days updates every district within 3 seconds | Pass | Browser: 0.57 s to redraw all 38 districts |
| 2 | The title states which outlook is shown | Pass | Browser: "Dengue outlook, next 14 days" |

### E2-S3 See the needs-attention list

| # | Criterion | Result | Evidence |
|---|---|---|---|
| 1 | Only High and Very high districts, sorted highest first | Pass | Test `test_train_backtest_live_and_alerts` (sorted, High+ only); Browser |
| 2 | List and map show the same districts and levels | Pass | Both come from the same `/api/risk` response; Browser |
| 3 | With no district at High or above, it says "No districts need attention this week" | Pass | Browser, 2026-11-01: with the risk replies made to report every district as Low (no real run has had zero High districts), the list showed exactly that text and the map labels all read Low |

## E3 — District explanation

### E3-S1 See a district's top three drivers

| # | Criterion | Result | Evidence |
|---|---|---|---|
| 1 | Level, probability and exactly three drivers, ordered by contribution | Pass\* | Tests `test_cards_are_three_plain_ordered_and_distinct`, `test_train_backtest_live_and_alerts`; Browser. *Change:* "probability" is the index score out of 100 |
| 2 | When forecast data changes and the pipeline reruns, the drivers update | Pass | Tests `test_cards_compare_with_the_usual_for_the_month` and the what-if checks (changed humidity gives a different first card) |

### E3-S2 Read drivers as plain-language cards

| # | Criterion | Result | Evidence |
|---|---|---|---|
| 1 | Each card names the factor, raises or lowers, and the time lag | Pass | Browser, e.g. "Rainfall · 3–8 weeks ago — More rain than usual 3–8 weeks ago → more breeding sites now ▲ raises risk" |
| 2 | No raw feature name or code is shown | Pass | Test `test_cards_are_three_plain_ordered_and_distinct` |
| 3 | Every model feature has a plain-language sentence | Pass | Tests `test_every_feature_has_a_sentence`, `test_weights_sum_to_one_and_have_sentences` |

## E4 — Field priority and alerts

### E4-S1 View the block priority list

| # | Criterion | Result | Evidence |
|---|---|---|---|
| 1 | A High or Very high district ranks its blocks by district risk × vulnerability, each with at least one action | Pass\* | Test `test_every_unit_gets_an_action`; Real data: all 25 High+ district outlooks have a ranked list with at least one action per unit. *Change:* covers all districts, not just the five spotlight ones; units are taluks |
| 2 | A district below High shows no list | Pass | Real data: no list below High; Browser: "No priority list: Cuddalore is Low, below High." |
| 3 | Each row shows the factors behind its rank (density, children and older adults, past hotspots) | Partial | Browser: density, % children 0–6 and past outbreaks are shown. **Older adults are missing**: Census age bands are published only per district, so they can't rank taluks within one |

### E4-S2 Alert rule fires and the message appears in the outbox

| # | Criterion | Result | Evidence |
|---|---|---|---|
| 1 | High on two runs in a row, or a two-level jump, creates one alert per nurse on its priority blocks | Pass\* | Tests `test_alert_two_high_runs_fires`, `test_alert_two_level_jump_fires`, `test_train_backtest_live_and_alerts` (one message per nurse, also when both outlooks alert); Real data: 1 message to the test nurse. *Change:* alerts once per High streak, not every day the district stays High; one run per day |
| 2 | High on only one run creates no alert | Pass | Tests `test_alert_single_high_run_does_not_fire`, `test_alert_fires_once_per_high_streak` |
| 3 | The outbox shows recipient, time and message, at most 160 characters, naming the block and first action | Pass | Tests `test_sms_fits_names_block_and_first_action`; DB check constraint; Browser: Alerts tab showed the recipient, time and the message (114/160) |
| 4 | No message contains personal or patient data | Pass | Tests `test_sms_carries_no_personal_data`, `test_train_backtest_live_and_alerts` |

### E4-S3 Field worker sees "My blocks" with age-specific advice

| # | Criterion | Result | Evidence |
|---|---|---|---|
| 1 | Only my blocks, highest priority first, latest alert on top | Pass | Test `test_full_chain_admin_officer_nurse`; Browser (375 px): latest alert card on top, Hosur ranked first |
| 2 | Each block shows what to check, and advice for children 0–12, adults 13–64 and older adults 65+ | Pass | Browser: actions plus "What to tell each household" with all three groups. The text is a draft for health-official review |
| 3 | No assigned block at High or above shows "No priority visits this week" | Pass | Real data: a nurse on a Cuddalore (Low) block got an empty list and that text |

### E4-S4 Mark a block visited; officer sees coverage

| # | Criterion | Result | Evidence |
|---|---|---|---|
| 1 | Marking a block visited with the number of breeding sites shows it as visited with today's date | Not built | A Could-have; next on the backlog |
| 2 | The Deputy Director sees "X of Y priority blocks visited" and sites found per block | Not built | |

## E5 — Planning aids

### E5-S1 Test a wetter or drier forecast

| # | Criterion | Result | Evidence |
|---|---|---|---|
| 1 | Moving a rainfall or humidity slider (−50% to +50%) shows the new level and drivers beside the current ones within 3 seconds | Pass | Browser: humidity −50% changed Krishnagiri from Very high to Moderate in 0.55 s, with new cards; Test `test_train_backtest_live_and_alerts` (limits enforced) |
| 2 | A changed slider labels the screen "Scenario, not forecast" | Pass | Browser; Test (`label` field) |
| 3 | Reset returns the sliders to the forecast values | Pass | Browser: slider back to 0, result equal to the forecast |

### E5-S2 Compare predicted risk with reported cases

| # | Criterion | Result | Evidence |
|---|---|---|---|
| 1 | For the held-out season, each month shows the predicted value next to whether it was above normal | Pass\* | Test `test_feedback_flags_lead_time_and_shared_records`; Browser: 12 months per district with level badge, score, "warned in advance" and "outbreak reported"; outbreak months highlighted (Sivaganga: Sept 2025 missed, Nov 2025 warned 1.7 weeks ahead); newer districts show their parent's record. *Change:* the highest index outlook next to "outbreak reported" (IDSP), not probability and case counts |
| 2 | The panel shows detection rate and lead time and names the season | Pass | Browser: "Season 2025-26, replayed"; 3 of 8 warned (38%), "same month last year" 0%, median 1.7 weeks, 97% of warned months without an outbreak |

---

## PRD §3 Must-Have criteria

| Feature | Criterion | Result | Evidence |
|---|---|---|---|
| M1 | All 38 districts show a level, colour and text label | Pass | See E2-S1 #1 |
| M1 | 7/14 switch updates every district within 3 s | Pass | 0.57 s (E2-S2) |
| M1 | Needs-attention list matches the map, sorted by probability | Pass | E2-S3 |
| M1 | Clicking a district opens its detail view | Pass | E2-S1 #3 |
| M1 | Disclaimer visible on the map screen | Pass | E2-S1 #2 |
| M2 | Exactly three driver cards, ordered by contribution | Pass | E3-S1 |
| M2 | Each card names the factor, direction and time lag | Pass | E3-S2 |
| M2 | No raw feature name or code | Pass | E3-S2 |
| M2 | Drivers change when the forecast data changes | Pass | E3-S1 #2 |
| M3 | Every High or Very high spotlight district shows a ranked block list with at least one action per block | Pass\* | All High+ districts, taluks (E4-S1) |
| M3 | Below High: no list, no alert | Pass | E4-S1 #2, E4-S2 #2 |
| M3 | Alert only on two consecutive High runs or a two-level jump | Pass\* | Plus once per streak (E4-S2 #1) |
| M3 | Each message ≤ 160 characters, names the block and first action | Pass | E4-S2 #3 |
| M3 | No personal or patient data in messages | Pass | E4-S2 #4 |

## PRD §4 metrics

| Metric | Target | Result | Evidence |
|---|---|---|---|
| Detection rate on held-out season | Above "same month last year" | Pass | 2025-26: 3 of 8 (38%) vs 0 of 8 (index replay against IDSP outbreaks) |
| Lead time | ≥ 2 weeks for at least half of above-normal months | Fail | Median 1.7 weeks among the 3 warned months. The longest possible lead for a 14-day outlook is 2 weeks |
| Brier score | Below baseline | Fail | ML model on IDSP outbreak labels: AUC 0.54, 0 of 8 detected; it's switched off. Brier doesn't apply to the live index |
| False-alarm rate | Reported | Pass | Reported: 86 of 89 warned district-months (97%) had no outbreak reported |
| Districts with a level and three drivers | 38 of 38 | Pass | Real data, run 60 |
| High spotlight districts with priority list and outbox message | All | Pass\* | E4-S1, E4-S2 |
| Map load and 7/14 toggle on a laptop | Under 3 s | Pass | Map drawn 1.64 s after page load (dev server, local); toggle 0.57 s. On mobile data the 8.6 MB boundaries file would take far longer; simplifying it is on the to-do list |
| Stranger runs the repo from the README | Under 5 minutes | Not checked | Not tested on a fresh machine |

## PRD §5 non-functional requirements

| ID | Requirement | Result | Evidence |
|---|---|---|---|
| NF1 | Runs fully offline from cached data | Pass\* | Scoring runs with no network (E1-S4 #1). *Change:* it's now a live product that fetches the forecast daily; if that fails, the last run is served and the app warns when it's over a day old |
| NF2 | No personal or patient data collected, stored or shown | Pass\* | No patient data anywhere. Staff accounts store a name, an email or mobile, and a scrypt password hash; mobiles are shown masked (••••••0009). *Change:* staff contact details are needed to sign in and route alerts |
| NF3 | "Risk estimate, not a diagnosis" on every screen | Pass | Browser: banner on sign-in, outlook, staff, users, alerts, trust and My blocks |
| NF4 | Works in a laptop browser and at phone width (360 px) | Pass | Browser at exactly 360 px: all 10 screens (sign-in; admin Users, Outlook, Alerts, Trust; officer Outlook incl. what-if, Staff, Alerts, Trust; nurse My blocks) have no sideways page scroll. **Fixed during QA:** the Users screen was 599 px wide; the user table now scrolls inside its card |
| NF5 | Risk shown by colour and text, never colour alone | Pass | Browser, greyscale view of the outlook: every district label, badge and legend entry is readable by its text, and the four levels also run light to dark. Separate issue: around Chennai, small districts' map labels overlap; hover, tap or the "All districts" list still shows them |
| NF6 | Every screen and endpoint maps to a story ID | Pass | Story IDs in code comments on every API endpoint and web component, and in the README tables |
