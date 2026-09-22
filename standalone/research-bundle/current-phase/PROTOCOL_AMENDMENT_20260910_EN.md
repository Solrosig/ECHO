# Full corpus and application coverage amendment

This amendment, requested on 10 September 2026, replaces the earlier 27-clip allocation and limited live tasks. It is a local prospective design record, not an external preregistration. No listener outcome values were inspected to choose this amendment. Current recruitment counts were not re-audited here; the zero-human count in the previous freeze describes its original timestamp only.

## What changes and what stays fixed

The current study identifier is `echo-user-voice-20260910-nine-v5`. Every new listener receives all 45 distinct WAVs once: nine configurations × one neutral plus four emotion presets. The 45 waveform hashes, carrier text, voices, calibration and rating scales are unchanged. Both the website source and standalone package were checked against all 45 hashes and valid nonempty WAV headers. This is a file-integrity check, not a new claim of perceptual validation.

The 16 group links remain usable. Each now includes Happy, Upset, Sad and Calm preset blocks and exactly one neutral block. Group modulo four counterbalances which target is disclosed for the neutral recordings; each target occurs in four groups. The stored seed randomises the full 45-trial order. The primary stimuli remain one fixed English text and one rendition per configuration-condition. Full within-listener coverage does not broaden the population of texts or voices.

Listeners give perceived valence, arousal and naturalness before target disclosure; those answers lock before the fourth, target-match question. There are 180 answers per completed Listening session. Suggest a short break after trials 15 and 30. Budget approximately 20–30 minutes for Listening and verify actual burden during the technical pilot. Increased fatigue and attrition are risks to report, not reasons to fill missing values or select favourable recordings.

## Primary analysis and compatibility

H1 and H2 retain their definitions. For each listener, pair all 36 preset observations with the nine same-engine neutral observations. Recalculate each neutral perception's distance to each of four targets. E_V = |v − v_target| / 2, E_A = |a − a_target| / 2 and E_T = (E_V + E_A) / 2. Improvement is neutral error minus preset error. H1 tests mean participant improvement in E_T > 0; H2 tests mean participant arousal improvement minus valence improvement > 0. Report both dimension changes regardless of H2 direction.

Average the 36 contrasts inside each participant before inference. The four uses of a neutral are dependent; neither 36 comparisons nor 45 ratings represent independent participants. Direct neutral target-match ratings apply only to the target actually disclosed. Do not copy those responses to the other three targets. Naturalness and initial perceived coordinates were measured once per neutral and can be linked to paired contrasts without multiplying the effective sample size.

Keep the resource-based target of 32 eligible completed listeners, exclusions, stopping rule, participant bootstrap, Holm adjustment and fixed-material interpretation from the previous protocol. Recruiting roughly two listeners per group balances neutral target disclosure; assignment is not enforced as a quota by the random homepage allocation. Prefer researcher-assigned group links. Freeze any calendar cutoff before outcome inspection. Report the actual completed sample and dropout at each stage.

`analyse_ratings.py` defaults to the current 45-clip cohort and requires 45 complete, valid rows. It reports other study versions as excluded from that run. For the older cohort, explicitly use `--study-version echo-user-voice-20260907-nine-v4` with a separate output folder; it requires 27 rows and 18 contrasts. Never pool the two designs automatically or count a repeat participant twice. Stored older browser sessions can finish their original 27 trials. The database migration preserves existing records and raises the response-order limit to 45.

The original protocol and its referenced source snapshots are retained under `research-bundle/archive/20260907-nine-v4/`. The original `PROTOCOL_FREEZE.json` remains historical; `PROTOCOL_FREEZE_V2.json` is the amended record. Acoustic evidence stays linked by unchanged WAV hashes. UTMOS/SER outputs are already available for these same 45 recordings and need no rerun merely because allocation changes.

## Test and Explore procedure

These remain unblinded application activities, separate from primary H1/H2. Complete Listening before revealing the named live engines. Follow the numbered Version 2 listener guide and record task, session and turn identifiers on the supplied coverage sheet. The website saves four voice answers per successfully rated message; completion of all live cells is verified by the researcher, not automatically enforced by the UI.

Test uses Kokoro, Chatterbox, StyleTTS2, CosyVoice2 and Parler-TTS. For each, generate the same supplied phrase with all four emotion presets and one neutral baseline: 25 recordings, including 20 emotion cells. The neutral direct-match target is Happy. Its perceived coordinates can be compared descriptively against other targets; its Happy match score cannot be copied. Keep text and voice configuration fixed. The default sequence puts neutral last; this can cause order effects. If rotating the sequence, assign and record it before participation, never after inspecting ratings.

Explore uses Chatterbox, Parler-TTS and Kokoro. Each listener completes 12 fresh conversations: three engines × four targets, one successful reply per cell, using the same opening prompt. Rate the voice before revealing the transcript. Then collect relevance, text-target alignment and text-voice agreement on the external sheet, with 1–5 or Cannot judge. Brief appropriateness, helpfulness and waiting-time questions describe that single exchange. These tasks test first-reply integration; they do not establish sustained conversation quality. Optional longer dialogue follows the required block and is reported separately.

Use the first successful generation in each cell; log failed, cancelled, inaudible and missing tasks. Do not regenerate successful messages to select preferred responses. Rotate engine order by participant when feasible and record the actual order. The same opening prompt does not guarantee the same generated text, so Explore differences cannot be attributed solely to TTS. Preserve generated text, audio hashes, selected target, settings and model versions. Report free-hosting failures as application feasibility evidence, separately from voice ratings.

## Results and thesis reporting

The main evidence cycle is unchanged: verified audio and acoustic measurements → blind Listening → waveform-linked interpretation → bounded conclusions. Present acoustic changes, human target correspondence, and correspondence versus naturalness as the three central figures. The amended design gives each completed listener all four emotions in every configuration, simplifying equally weighted engine-emotion summaries. Uncertainty still comes from listeners and is conditional on fixed stimuli.

Report a participant-flow table separately for the old and new versions, per-engine/emotion coverage, exclusions, receipt failures, and durations. Add a descriptive application section with 20 Test emotion cells plus baselines, 12 Explore cells, their denominators and external text/voice scores. Do not merge live and blind scores into one hypothesis test or present these selected live engines as listener-validated winners before results exist.

Use this amendment and Version 2 listener materials when revising the thesis methods and annex. Earlier Word manuscript and Version 1 protocol/questionnaire files remain historical drafts; their 27-clip and Calm-only task descriptions are superseded by this record. No human Results or Conclusions are fabricated by this amendment.
