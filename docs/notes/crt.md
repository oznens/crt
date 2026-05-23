# CRT — Candle Range Theory

Working knowledge base the terminal is built on. Two source documents so far:

- `docs/pdfs/846803727-Basic-of-CRT.pdf` — Timon / ICT University (Canva deck, 90 pages). The mechanical framework: AMD, 5 subtypes, DOL ladder. Covered in Part 1.
- `docs/pdfs/942591252-CRT-SECRETS-SERIES.pdf` — RomeoTPT (founder) + TradesbyVee (author), 85-page LaTeX compilation of the 9-episode CRT Secrets series. Adds Model #1, Kiss of Death, SMT, key-level prerequisites, the 4-step trade recipe. Covered in Part 2.

The two sources are complementary: Timon defines the **mechanics** of the pattern; Romeotpt / TradesbyVee define the **context** required for the pattern to be tradable.

---

## 0. Core idea

- **Every candle is a Range.** All candles are ranges. Ranges are "angels" — algorithmic anchor points.
- **CRT = a reversal model** built around the anatomy of a 3-candle structure that wraps PO3 (AMD) with Turtle Soup at an HTF POI.
- **Time > Price.** Highs, lows, swing points and MSS are *predetermined* by the algorithm before the candle prints. Submit to time.

> "ICT is the key to the charts. Turtle Soup is the key to ICT."

---

## 1. Candle anatomy — PO3 / AMD

Every HTF candle is one of two opening types:

- **OHLC** — Open, High, Low, Close (bearish-style opening: pushes up first, then down)
- **OLHC** — Open, Low, High, Close (bullish-style opening: pushes down first, then up)

Mapped onto AMD (Power of Three):

| Phase | Letter | Role |
|------|--------|------|
| Accumulation | **A** | Range candle |
| Manipulation | **M** | Turtle Soup / purge candle |
| Distribution | **D** | Expansion candle |

**Internal quartile view (p-07):** a single HTF candle, when zoomed to its constituent LTF candles, divides into 4 quarters:

- **Q1 + Q2** → Accumulation (price ranges sideways)
- **Q3** → Manipulation (sharp dip/spike against the eventual direction, hunting liquidity)
- **Q4** → Distribution + Closure (the real expansion, then a brief closing range)

This is the fractal that maps onto the HTF→LTF alignment table below — the same AMD plays out at every nested timeframe.

---

## 2. Time-frame alignment (HTF candle → LTF execution frame)

This is the table the terminal must internalize for "where to look for the PO3 inside an HTF candle":

| HTF candle | LTF execution (PO3) |
|------------|---------------------|
| Monthly    | H4  |
| Weekly     | H1  |
| Daily      | M15 |
| 4-Hour     | M5  |

---

## 3. HTF candle high-probability windows

### Monthly
- Low/High of the month → usually forms in **Week 1 or Week 2**.
- High/Low of the month → usually capped in **Week 3 or Week 4**.

### Weekly
- 2 high-probability trades per week.
- Low/High of the week → usually **Mon–Wed**.
- High/Low of the week → usually capped **Thu–Fri**.

### Daily
- A daily candle = 6× 4H candles.
- 2 high-probability sessions per day → ~10 per week.
- The 6 H4 candles per day open at: **1, 5, 9 (AM)** and **1, 5, 9 (PM)** — visualized on p-18 as a 6-cell strip split into AM and PM halves.
- Anchor candles: **01:00 AM** and **09:00 AM** (server/broker time per chart; usually NY).
- The Monthly chart on p-13 also explicitly marks the candle wick low as forming around W1 boundary (turtle soup) with the body running from Open → close near the high (a bullish OLHC structure visualized over 4 weeks W1..W4).

---

## 4. BIAS building (5 elements)

1. **Order Flow / Market Structure**
   - Bullish OF: HH + HL, lows swept/rejected, bullish PD arrays respected, bearish PD arrays inverse/fail.
   - Bearish OF: LH + LL, highs swept/rejected, bearish PD arrays respected, bullish PD arrays fail.
   - Range/Sideway: HH and LL inside a bound range.
2. **IPDA — Interbank Price Delivery Algorithm**
   - Cycles: **Consolidation → Expansion → Retracement / Reversal**.
   - From Consolidation, next phase is ALWAYS Expansion.
   - From Expansion, price can go to Retracement, Reversal, or Consolidation.
   - From Consolidation, price CANNOT go directly to Retracement or Reversal.
   - IPDA pursues two goals simultaneously: **Liquidity** (resting) + **Imbalance** (HTF). One stone, two mangoes.
3. **IRL ↔ ERL**
   - **IRL** (Internal Range Liquidity): liquidity inside a dealing range as **imbalance / FVG**.
   - **ERL** (External Range Liquidity): liquidity outside the range as **SSL / BSL**.
   - **IRL → ERL** → seeking liquidity = **continuation**.
   - **ERL → IRL** → filling imbalance = **counter-trend**.
4. **Ranges** (see §5).
5. **DOL — Draw On Liquidity** (see §7).

---

## 5. Range identification

Range = generation of liquidity through accumulation where highs/lows engineer liquidity. Ranges form at PD arrays or near liquidity **at a key time**.

**Steps to mark a valid range candle:**

1. Identify order flow (bullish or bearish).
2. Identify whether price is heading IRL→ERL or ERL→IRL.
3. Mark the recent **"beefy" candle** formed near or at the HTF array.
4. Anticipate the turtle soup at a key time.

**Notes:**
- High-probability range candle forms *after/near a liquidity pool* OR *at an HTF PD array*.
- A range candle is confirmed only by the next candle's manipulation of its high/low.
- Need **price AND time** in agreement.

---

## 6. CRT itself — formation rules

**Where:** at HTF liquidity / HTF PD array, when **both time and price** meet.

**Identification steps:**

1. Mark HTF liquidity or HTF PD array.
2. Mark the range candle formed near/in that POI. Expect candle 2 to manipulate either range high or low.
3. If bullish → expect range LOW to be purged then revert (and vice-versa for bearish).

**Validation rules (hard filters):**

- ✅ 2nd candle (purge) must show a **healthy rejection** from the POI (wick, not body).
- ❌ 2nd candle must **NOT body-close beyond the range candle** (only wick through allowed).

---

## 7. DOL — Draw On Liquidity

Determines directional bias after a purge.

- DOL = the **opposite side** of the manipulation candle (opposite of the side that got purged).
- In a **bullish OF**: after range low gets purged → first target = **50% of range (mid)** (LHF), then **range high** = initial DOL.
- In a **bearish OF**: mirror.

---

## 8. CRT Subtypes — the 5 variants

| # | Name | Notes | Probability / context |
|---|------|-------|-----------------------|
| **1** | **3-Candle CRT (Classic)** | Range → Purge → Revert, all settled in 3 candles. | Baseline. |
| **2** | **2-Candle CRT (Aggressive)** | Candle 2 *purges AND* delivers to the DOL within itself. | Often during **news / dilation before key time**. |
| **3** | **Multi-Candle CRT (LP)** | Same as Classic but expansion takes multiple candles to reach DOL. | **Counter-trend / ERL→IRL**, PM session, low-probability. |
| **4** | **Inside Bar CRT (HP)** | Candle 2 (and possibly more) forms **inside** candle 1's range. Breakout from the engineered inside-bar liquidity = high probability. | High probability. |
| **5** | **3rd-Candle Purge & Revert (Rare)** | 3rd candle manipulates **candle 2's** high/low and distributes to opposite liquidity. Often a 3-drive on LTF. | Rare. **High-impact news / ERL→IRL / low probability** conditions. |

> Practical advice from Timon: don't try to master all five. Pick one model, backtest + forward-test it, master it.

---

## 8b. Subtype visual rules (from PDF illustrations)

Each subtype has a precise geometric fingerprint. Terminology used in the deck: **CRH** = Candle Range High (high of range candle), **CRL** = Candle Range Low.

### Type 1 — 3-Candle CRT (Classic)
```
Bullish:
C1 = bearish range candle (defines CRH and CRL)
C2 = small candle, wick pokes BELOW CRL ("TS"), body stays INSIDE C1's range
C3 = large bullish expansion, body closes ABOVE CRH
```
Mirror for bearish. Everything settles in 3 candles.

### Type 2 — 2-Candle CRT (Aggressive)
```
Bullish:
C1 = range candle (CRH, CRL set)
C2 = single candle that both:
       - has wick BELOW CRL (purges SSL)
       - body closes ABOVE CRH (delivers to DOL)
```
News-driven. Manipulation + distribution in one bar. Often AM dilation candle.

### Type 3 — Multi-Candle CRT
```
C1 = range candle
C2 = purge candle (wicks the engineered side)
C3..Cn = staircase of small candles slowly walking to DOL
```
Counter-trend, PM session, ERL→IRL, low-probability context. Expansion is gradual not explosive.

### Type 4 — Inside Bar CRT (HP)
```
C1 = LARGE range candle (often a strong displacement bar)
C2..Cn = INSIDE BARS (high < CRH AND low > CRL for each)
One of the inside bars wicks beyond CRH or CRL (false breakout / engineered TS)
Then a strong expansion candle breaks the opposite side of C1
```
Highest probability per the deck. Inside-bar period acts as engineered liquidity nest, breakout fires toward opposite extreme.

### Type 5 — 3rd-Candle Reversal (Rare)
```
C1 = range candle
C2 = forms normally
C3 = manipulates C2's high/low (not C1's), then distributes to opposite liquidity
```
3-drive pattern on LTF. High-impact news traps, ERL→IRL, low probability.

---

## 8c. DOL ladder (from p-64/p-65)

Visual hierarchy of targets after a CRT confirms:

```
Bullish CRT (range low purged):
  ├─ Target 1: 50% of range candle  →  labeled "Low Hanging Fruit" (LHF)
  ├─ Target 2: Range High (CRH)     →  Initial DOL
  └─ Target 3: External BSL above   →  Extended DOL

Bearish CRT (range high purged):
  ├─ Target 1: 50% of range candle  →  LHF
  ├─ Target 2: Range Low (CRL)      →  Initial DOL
  └─ Target 3: External SSL below   →  Extended DOL
```

These are the levels the terminal should auto-project after a CRT detection.

---

## 8d. Validation deltas (visually confirmed)

Additional precise filters lifted from the visual examples:

- **C2 (purge candle) body** must stay inside C1's range. Body close beyond CRH/CRL invalidates the CRT.
- **C2 wick** must clearly extend beyond CRH or CRL (engineered TS). A wick that does not reach the level isn't a CRT — it's a failed setup.
- **C3 (expansion)** must body-close beyond C1's opposite extreme for Type 1 confirmation. If C3 only wicks past, the structure is unconfirmed; could become Type 3 or fail.
- **Inside Bar (Type 4)** detection requires *every* candle from C2 onward to satisfy `candle.high ≤ C1.high AND candle.low ≥ C1.low` until one bar breaks one side.
- **Turtle Soup wick** examples (p-47/p-48) show the wick spike usually exceeds prior swing extreme by a small margin — not a violent break, just a controlled sweep with immediate rejection (heavy wick, small body).

---

## 9. Quartet of "smart money quarters"

Smart money operates on specific quarters:

1. A specific **Monthly** candle of the year.
2. A specific **Weekly** candle of the month.
3. A specific **Daily** candle of the week.
4. A specific **Hourly** candle of the day.

---

## 10. Terminal design implications (for our build)

Things this knowledge base directly maps into the future scanner:

- **Candle aggregation must be multi-timeframe** (M5, M15, H1, H4, D, W, M) and the HTF→LTF alignment table in §2 is hard-coded routing logic.
- **Range candle detector**: needs to flag "beefy" candles (size relative to recent ATR / N-candle median) that print near a tagged HTF PD array or liquidity pool.
- **Purge detector** (candle 2): wick beyond candle-1 range, body close inside candle-1 range, healthy rejection (wick / body ratio threshold).
- **Subtype classifier**: after a confirmed range + purge, watch candles 3..N to label which of the 5 variants occurred.
- **DOL projector**: auto-draw 50% line of the range candle + opposite extreme as DOL.
- **Time gating**: alerts should fire ONLY when the LTF entry frame is aligned with the HTF candle context and price is at an HTF POI (per §2 + §3). Time filters: NY 01:00 / 09:00 anchors, weekly Mon–Wed / Thu–Fri windows, monthly W1–W2 / W3–W4 windows.
- **IPDA state machine**: track Consolidation → Expansion → Retracement/Reversal for each symbol per timeframe; forbid illegal transitions (Consolidation → Retracement/Reversal direct).
- **IRL/ERL tagger**: liquidity (SSL/BSL) on external pivots, imbalance (FVG) on internal — required to label setups as continuation vs counter-trend.

---

# Part 2 — CRT Secrets Series (RomeoTPT + TradesbyVee)

The Secrets compilation reframes CRT as a *layered* system: pattern alone is not enough. A clean three-candle structure that prints in the wrong place at the wrong time should be ignored.

## P2.1 — Model #1 (the single trigger candle)

Model #1 is **one specific candle** (not a zone, not a cluster) that becomes the trigger for the expansion phase of a CRT.

**Bearish Model #1** (sell setup):
1. Find an old high on the chart (engineered BSL).
2. Wait for price to stab into that old high.
3. A **thick up-close candle** (large bullish body) forms inside or just past the level.
4. Enter SHORT the moment the **next candle closes BELOW** that thick up-close candle's low.
5. Stop loss: above the thick up-close candle's high.
6. Target: next lows beneath / external SSL.

**Bullish Model #1** is the exact mirror — old low, thick down-close candle, enter long when next candle closes ABOVE its high.

Strengtheners:
- **FVG confluence** — Model #1 inside or right at an FVG is the highest-probability variant ("Magic Ingredient").
- Wait for the actual close. No early entries.

## P2.2 — Kiss of Death (KOD)

KOD = the **final** turtle soup before price reaches its major target. It is the market's last trap before the big expansion completes.

Three candles:
1. Accumulation — smart money builds.
2. Manipulation — fake breakout to engineer liquidity.
3. Distribution — KOD prints; explosive move follows.

**Bearish KOD**: price pushes above an old high (TS), a big up-close candle forms (looks bullish to retail), then price closes back below the TS point. Target = CRT low.
**Bullish KOD**: mirror — TS below an old low, big down-close candle, then close back above. Target = CRT high.

Entry rule: wait for the KOD candle to close, enter in the OPPOSITE direction, stop loss beyond the turtle soup point.
KOD + FVG = highest conviction trade per the deck.

## P2.3 — The three-candle journey (zoomed view)

Same AMD triad but the Secrets series adds an explicit beginner / advanced split:

| Candle | Phase | Trader role | Beginner advice |
|--------|-------|-------------|-----------------|
| 1 | Accumulation | Watch | Don't trade |
| 2 | Manipulation | Avoid the trap | Don't trade until experienced |
| 3 | Distribution | TRADE | Only this one as a beginner |

**Inside Candle 2 (micro-structure):** Turtle Soup → Model #1 → Breaker → OTE → Kiss of Death. Every CRT contains these elements; the operator's job is just to recognize them.

## P2.4 — Key Levels are the gating prerequisite

> "CRT patterns ONLY work well when they happen at key levels."

Key level definition: a price where price has historically bounced or reversed.

Sources:
- Old highs (engineered BSL).
- Old lows (engineered SSL).
- Sites of prior SMT footprints (where institutions left signatures).

Operating modes (pick one per level, do not mix):
- **Trade TO the level** — fade approaching price into the level.
- **Trade FROM the level** — wait for confirmed bounce off the level.

Watch out for **fake bounces** — the market regularly prints one false bounce before the real one. Wait for confirmation.

## P2.5 — SMT (Smart Money Technique) divergence

Correlated-pair check. Two markets that usually move together; when one prints a new extreme and the other fails to, that's an SMT signal.

| Pattern | Market A | Market B | Signal |
|---------|----------|----------|--------|
| Bearish SMT | new high | fails to make new high | SELL |
| Bullish SMT | new low  | fails to make new low  | BUY |

Standard pairs:
- EURUSD ↔ DXY (inverse correlation)
- BTC ↔ ETH (positive correlation)
- Gold ↔ DXY (inverse)
- Sector leader vs follower (in equities)

Combined with KOD: **SMT + KOD = high conviction**.
Combined with HTF bias: only take bullish SMT when HTF is bullish, only bearish SMT when HTF is bearish.

## P2.6 — Weekly candle rhythm

Slightly refined version of Timon's weekly windows:

| Day | Role |
|-----|------|
| Monday | Open + manipulation often happens |
| Tuesday – Wednesday | Real move develops |
| Thursday – Friday | Distribution + preparation for next week |

## P2.7 — The 4-step recipe (Episode 9)

The full pipeline a trade must pass before execution:

1. **Higher-Timeframe Narrative** — monthly / weekly / daily candle shape, big liquidity pools, FVGs, prior highs/lows. Bias is bullish, bearish, or neutral?
2. **Market Profile and Structure** — mark relevant highs/lows; identify any true market-structure shifts (clean close past a prior structure point).
3. **Stack Confluences** — only trade when multiple line up:
   - CRT (AMD) present
   - FVG at relevant location
   - SMT aligned
   - Model #1 or true MSS
   - Time of day / session (NY anchors, London session)
4. **Define Entry Model (LAST step)** — choose Model #1 entry or MSS entry. Entry is the final confirmation, never the first decision.

## P2.8 — Risk model

- Stop loss is set **just beyond the turtle soup point**. The rationale: if your stop is the TS itself, it's unlikely to be re-hunted.
- Position size: risk **1–2% of account per trade**. Non-negotiable.
- Exit by **price** (target hit) OR by **time** (session ends, e.g., London close). Both legitimate.
- Take-profit ladder: TP1 at **50%** of the move (the "first slice"), TP2 at the full target (CRT high / low / extended DOL).
- Always have a **Plan B** — the alternate scenario written before the trade fires.

## P2.9 — Why a CRT trade goes wrong

Per Episode 8, there are exactly three failure modes:
1. **SMT Wall** — a correlated market diverged; the setup was blocked by smart money. Always check SMT before trading.
2. **50% Mission Complete** — price reached the LHF and stopped. The CRT did its first job; the trade still printed money. Don't complain.
3. **Wrong Direction** — trading against the trend / HTF bias. Only trade with the bigger-picture direction.

Journaling discipline: **Catch → Miss → Avoid → Repeat**.

## P2.10 — Pre-trade checklist

Before executing, every item must be true:
1. Higher-timeframe bias confirmed.
2. CRT / FVG / SMT aligned.
3. True market-structure shift (if applicable).
4. Entry model confirmed (Model #1 or MSS).
5. Stop and target planned; risk math done (1-2%).
6. Time / session window matches the setup.
7. Plan B (alternate scenario) prepared.

---

## P2.11 — Implications for the terminal (delta from Part 1)

New modules the scanner needs, in priority order:

- **Key-level tracker** — per symbol, maintain a rolling list of swept / unswept old highs and old lows. CRT signals that don't sit on a key level should be down-tiered or dropped.
- **SMT pair monitor** — for each tracked symbol, store a list of correlated symbols (BTC↔ETH by default for crypto). On every new HTF extreme, compare and flag divergences. Signals on a symbol whose pair is diverging the wrong way get blocked or down-tiered.
- **FVG detector** — three-candle gap detector. FVG location is one of the confluences in the 4-step recipe.
- **Model #1 sub-detector** — orthogonal to the 5 subtype detectors. Single-candle trigger detection right after a key-level sweep.
- **KOD detector** — the *final* TS before a target completes; needs awareness of an in-progress CRT and its DOL ladder.
- **Confluence stacker** — produces a numeric confluence score per signal:
  - +X for HTF bias agreement
  - +X for key-level presence
  - +X for FVG alignment
  - +X for SMT confirmation
  - +X for high time-tier
  - the runtime can require a minimum confluence score before opening a paper position
- **Failure tagging** — when a paper position closes at SL, tag the reason via the three Episode-8 buckets so the journal can be analyzed by mode.
- **Risk model refinement** — set stop directly at the TS price (no extra buffer beyond a small slippage cushion). Add explicit time-based exit (close at session end if neither TP nor SL hit).

## Glossary

- **CRT** — Candle Range Theory
- **PO3 / AMD** — Power of Three / Accumulation–Manipulation–Distribution
- **OHLC / OLHC** — Candle opening sequence types
- **IPDA** — Interbank Price Delivery Algorithm
- **POI** — Point of Interest
- **PD array** — Premium/Discount array
- **IRL / ERL** — Internal / External Range Liquidity
- **SSL / BSL** — Sell-Side / Buy-Side Liquidity
- **FVG** — Fair Value Gap (imbalance)
- **MSS** — Market Structure Shift
- **DOL** — Draw On Liquidity
- **LHF** — Low Hanging Fruit (50% of range candle, first target after a confirmed CRT)
- **HTF / LTF** — Higher / Lower Time Frame
- **Turtle Soup** — false breakout / stop-raid on short-term high/low
- **CRH / CRL** — Candle Range High / Candle Range Low (high & low of the range candle)
- **TS** — Turtle Soup (used as a label on charts)
- **OB** — Order Block
- **AMD** — Accumulation / Manipulation / Distribution (same as PO3)
- **Q1–Q4** — Quartile mapping of a single HTF candle: Q1+Q2 = Accumulation, Q3 = Manipulation, Q4 = Distribution/Closure
- **Model #1** — Single trigger candle (thick body) that closes back through a swept old high/low; the "starter pistol" for the expansion
- **KOD** — Kiss of Death, the final TS before a CRT target completes
- **SMT** — Smart Money Technique; correlated-pair divergence
- **OTE** — Optimal Trade Entry (Fibonacci 0.62–0.79 retrace zone in ICT vocabulary)
- **Breaker** — Failed order block that flips polarity after a structure shift
- **Key level** — Price at which historical bounces have occurred; CRT prerequisite
