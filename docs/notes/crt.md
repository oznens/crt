# CRT — Candle Range Theory (Timon / ICT University)

Source: `docs/pdfs/846803727-Basic-of-CRT.pdf` (90 pages, Canva deck by @timon_ict).
This file is the working knowledge base the terminal will be built on top of.

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
