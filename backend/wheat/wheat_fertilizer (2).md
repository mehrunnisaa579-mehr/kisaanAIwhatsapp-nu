<!--
Primary source policy:
- Built from user-uploaded wheat source files only.
- Where uploaded files do not provide a detail, the file marks it as a gap instead of guessing.
- Local Punjab/South Punjab figures, dosages, timings and thresholds are taken only from the uploaded AARI/Ziratnama/Punjab notes.
-->

# Wheat Fertilizer — Punjab / South Punjab

## Executive Summary

The uploaded files do **not** provide a complete Punjab wheat fertilizer dose schedule for nitrogen, phosphorus, potassium, sulfur, or micronutrients. Therefore, this file keeps fertilizer guidance conservative and only includes fertilizer-related facts that are directly supported by the uploaded material.

The main confirmed fertilizer point is: **excess nitrogen increases aphid risk** by producing soft sap-rich canopy growth.

---

## Confirmed Fertilizer-Related Facts From Uploaded Sources

| Topic | Locally supported note |
|---|---|
| Nitrogen overuse | High nitrogen fertilizer over-application can trigger heavy aphid attack. |
| Irrigation link | Moisture shortage at key growth stages reduces tillering, spike count, flowering success, and grain weight. |
| Field leveling | Laser land leveling can reduce water requirement by 20%–25% and improve uniformity. |

---

## Practical Fertilizer Rules for FarmAI Logic

### 1. Do not recommend blind high nitrogen

If farmer reports aphids, sticky leaves, black sooty mold, or very lush soft crop growth, FarmAI should avoid recommending more nitrogen without soil/crop diagnosis.

### 2. Link fertilizer advice with irrigation stage

Fertilizer response depends on water availability. Missing critical irrigation windows can reduce the benefit of fertilizer.

Key irrigation stages from the uploaded files:

| Stage | Timing after sowing | Why it matters |
|---|---:|---|
| Crown root initiation / tillering | 20–25 days | Permanent impact on spike count |
| Jointing / booting | 55–60 days | Stem elongation and lodging prevention |
| Heading / flowering | 80–85 days | Grain count per ear |
| Milk / soft dough | 100–105 days | Grain size and weight |

---

## What Not To Do

Do not add exact Punjab fertilizer bags-per-acre or kg-per-acre values unless a verified local official source is attached. Fertilizer recommendations vary by soil test, variety, irrigation status, sowing time, and local field conditions.

---

## Suggested FarmAI Response Behavior

When a farmer asks “kitni khaad daalun?” and no soil test is available, answer like this:

> Fertilizer dose cannot be safely fixed without soil condition, sowing date, irrigation status, and crop stage. Avoid excessive nitrogen because it can increase aphid attack. For exact dose, use soil-test-based recommendation or verified Punjab Agriculture/AARI fertilizer schedule.

---

## Data Gaps

Missing from uploaded files:

- Exact nitrogen dose for Punjab wheat.
- Exact phosphorus dose.
- Exact potassium dose.
- Urea/DAP/SOP bag schedule.
- Zinc/boron/micronutrient recommendations.
- Soil-test interpretation table.

These gaps should be filled only with verified Punjab/Pakistan official fertilizer sources.

---

## Sources Used

1. User-uploaded `wheat_aari_diseases.txt` — aphid risk linked to excess nitrogen.
2. User-uploaded `wheat_ziratnama_irrigation.txt` — irrigation-stage and laser-leveling logic.
