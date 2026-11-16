# Baby Tracker for Home Assistant

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://hacs.xyz/)
[![Validate](https://github.com/turnebre/ha-baby-tracker/actions/workflows/validate.yml/badge.svg)](https://github.com/turnebre/ha-baby-tracker/actions/workflows/validate.yml)

Track your baby's **bottles (formula and breast milk), feedings, diapers, pumping and growth** right inside Home Assistant —
with a dedicated panel, charts, reminders and one-tap logging from a Zigbee button, your phone or your voice assistant.
Everything is stored **locally** in your Home Assistant (SQLite). No cloud, no accounts, no subscriptions.

> ⚠️ **Not medical advice.** Baby Tracker is a logging tool. Goals, limits and hints are general references;
> decisions about your baby's feeding and health belong to your pediatrician.

<p align="center">
  <img src="docs/img/today.png" alt="Today tab" width="78%">
  <img src="docs/img/mobile.png" alt="Today tab on a phone" width="20%">
</p>

## Features

- **Bottles + incremental feedings** — every feeding adds to the current bottle; start a new bottle only when you prepare one.
  Overflow automatically goes to the next bottle. Edit the size of the current bottle for special cases.
- **Breast milk** — log pumping sessions (left/right), keep a **stash** (fridge / room temperature) with expiry;
  choose which stash bottle to use (soonest to expire first) and it is deducted from the stash; pause the formula bottle
  while giving breast milk and resume it later.
- **Diapers** — pee, poop or both; color and consistency for poop with your baby's "usual" preselected.
- **Today at a glance** — last and next feeding (big), current bottle, diapers, rate per hour, and how much the baby
  *should have had by now* against two daily goals: a **minimum** and an **ideal** (the lower and higher of the
  pediatrician's goal and the weight-based reference, which follows the latest weight). Shows how much per feeding is
  left to reach each one, the expected amount at the next feedings, and which goals were met on each of the last 7 days.
- **Charts** by day, week or month: amount per day (formula vs breast milk), feedings, amount per feeding, bottles,
  % finished, wasted formula, pumped milk, diapers, and *when* the baby eats / needs a change.
- **Pediatrician's plan** — a daily goal in oz, the daytime feeding interval and a bedtime/wake-up window. Nothing is expected overnight; the per-feeding amounts, the "expected by now" curve and the reminder follow it.
- **Growth** — weight (lb), length (in) and head circumference (in) history.
- **Milestones** — first year, week by week: CDC milestones grouped into skills, tick them when you notice them and see progress by skill and area. A guide, not a test or a deadline.
- **Several babies** (twins!) — one entry per baby, a selector in the panel.
- **oz or ml** units.
- **Blueprints** for buttons, reminders, milk expiry, notification actions and voice.

## Installation

### HACS (recommended)
1. HACS → ⋮ → **Custom repositories** → `https://github.com/turnebre/ha-baby-tracker` · type **Integration**.
2. Install **Baby Tracker** and restart Home Assistant.
3. Settings → Devices & services → **Add integration** → **Baby Tracker**. Add one entry per baby.

### Manual
Copy `custom_components/baby_tracker` into your `config/custom_components/` folder and restart.

## Configuration

When adding a baby you set the **name, date of birth, usual bottle size and main milk type**.
Later, **Configure** lets you change name, date of birth, sex, **unit (oz/ml)** and the **usual poop color/consistency**.
The **Settings** tab in the panel holds the pediatrician's plan (daily goal, daytime interval, bedtime and wake-up) and milk limits.

> The internal domain is `baby_tracker` (entities and actions use it, e.g. `baby_tracker.log_feeding`).

## The panel

A **Baby Tracker** entry appears in the sidebar (and in the companion app):

| Tab | What you do there |
|---|---|
| **Today** | Last/next feeding, current bottle (*How much did baby drink?*), new bottle, diaper buttons, KPIs |
| **Feedings** | Day view grouped by bottle; edit, delete, move feedings; diapers of the day |
| **Breast milk** | Stash with expiry, save milk, log pumping sessions |
| **Growth** | Weight / length / head circumference and their charts |
| **Milestones** | Week-by-week first year: milestones to tick, what is normal, ideas, progress by skill |
| **Charts** | Day / week / month charts |
| **Settings** | Bottle size, pediatrician's plan, milk limits, hints from the last 7 days |

| Feedings | Breast milk |
|---|---|
| ![Feedings](docs/img/feedings.png) | ![Breast milk](docs/img/milk.png) |
| **Charts** | **Growth** |
| ![Charts](docs/img/charts.png) | ![Growth](docs/img/growth.png) |

<details><summary>Settings</summary>

![Settings](docs/img/settings.png)

</details>

## Blueprints

Import the ones you need (they work with **any** button, phone and language):

| Blueprint | What it does | File |
|---|---|---|
| **Button press adds to the bottle** | Each press adds e.g. 0.5 oz; presses close together = one feeding; one summary notification | `blueprints/automation/baby_tracker/button_tap.yaml` |
| **Button hold starts a new bottle** | Long press → new bottle of the usual size | `blueprints/automation/baby_tracker/button_hold.yaml` |
| **Feeding reminder** | When the next feeding is due and nothing was logged, asks on your phones; answer with the amount and/or real time | `blueprints/automation/baby_tracker/reminder.yaml` |
| **Breast milk about to expire** | Warns before the soonest stash bottle expires: Use now / Move to fridge / Discard | `blueprints/automation/baby_tracker/milk_expiring.yaml` |
| **Notification buttons** | **Required** by the others: Undo, Edit amount, It was a new bottle, reminder answers, stash actions | `blueprints/automation/baby_tracker/actions.yaml` |
| **Voice via to-do list + AI** *(optional)* | For assistants that add items to a list (e.g. Alexa lists): an AI Task entity interprets "drank one ounce" | `blueprints/automation/baby_tracker/voice_list.yaml` |

Reminder answers accept text such as `1.5`, `20:15 1.5`, `40 min ago`, `new 2`
Amounts are in the baby's unit.

## Actions (services)

All actions accept an optional `baby` field (entry id or baby name) — required only with more than one baby.

| Action | Purpose |
|---|---|
| `baby_tracker.log_feeding` | Log a feeding (`oz_taken`, or `oz_leftover: 0` = finished what was left; `new_bottle`, `ended_at`, `type`…) |
| `baby_tracker.correct_feeding` · `baby_tracker.delete_feeding` · `baby_tracker.restore_feeding` | Edit / move (`move: new/previous`), delete, restore a feeding |
| `baby_tracker.new_bottle` · `baby_tracker.close_bottle` · `baby_tracker.resume_bottle` · `baby_tracker.correct_bottle` · `baby_tracker.delete_bottle` | Bottles |
| `baby_tracker.save_milk` · `baby_tracker.use_stash` · `baby_tracker.move_stash` · `baby_tracker.discard_stash` | Breast milk stash |
| `baby_tracker.log_pumping` · `baby_tracker.delete_pumping` | Pumping sessions |
| `baby_tracker.log_diaper` · `baby_tracker.correct_diaper` · `baby_tracker.delete_diaper` | Diapers |
| `baby_tracker.log_measurement` · `baby_tracker.delete_measurement` | Growth measurements |
| `baby_tracker.list_*` | Read data (return a response) |

Every response includes `baby`, `name` and `unit`, handy for your own notifications.

## Sensors

Per baby: last / next feeding, amount today, feedings today, last 24 h, 7-day average, interval, daily goal, goal progress, expected by now,
rate per hour, current bottle remaining / use-by, amount per feeding, feedings per day, bottles today, % finished,
wasted formula, breast milk / formula today, pumped today / average, stash and next expiry, last diaper / pee / poop,
diapers today / per day, time between diapers, weight, length and age. Plus `number` entities for the settings.

## Data & backups

Each baby's data lives in `config/baby_tracker.db` (additional babies: `config/baby_tracker_<id>.db`) and is included in Home Assistant backups.
Removing a baby keeps its file.

## Limitations

- Charts are simple SVG; growth percentiles (WHO curves) are planned.
- Breast milk logged by voice (or by an action without `stash_id`) is not taken from the stash; use the panel for that.
- The REST API shows validation errors as HTTP 500 (a Home Assistant behavior); the panel and automations show the proper message.

## Contributing

This is a private, English-only fork. UI text lives in `custom_components/baby_tracker/translations/en.json` and directly in `www/baby-tracker-panel.js`.

## License

[MIT](LICENSE)
