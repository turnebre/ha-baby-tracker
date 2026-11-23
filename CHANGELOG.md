# Changelog

Format based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); semantic versioning (MAJOR.MINOR.PATCH).
While the version is 0.x, minor versions may contain breaking changes.

## [Unreleased]
### Added
- **Growth units** option (imperial lb/in or metric kg/cm) when adding a baby, in **Configure**, and in the panel's **Settings** tab
  (new `baby_tracker.set_growth_unit` action). It controls the Growth tab, the Today summary and the weight/length sensors.
  Defaults to imperial, so existing babies are unchanged; stored data is not affected.
- `log_measurement` also accepts `weight_kg`, `height_cm` and `head_cm` (use either set per measurement), and `list_measurements`
  returns both the metric and imperial fields.
- The weight and length sensors now report kg/cm natively and are shown in the baby's growth unit through the entity registry.
  A unit you picked yourself in the sensor's settings (other than lb/kg and in/cm) is left alone. The sensors also expose the
  exact `weight_kg` / `height_cm` as attributes.
- The `measurement` event now carries both the lb/in and kg/cm fields.
- New `baby_tracker_growth_unit_changed` event (`baby`, `growth_unit`), fired when the growth unit is changed from the panel or
  the `set_growth_unit` action; open panels use it to stay in sync.

## [2.0.0] - English-only fork
### Changed
- The whole codebase is now English: identifiers, comments, SQLite tables and columns, stored values, services (actions),
  entity keys, events, blueprints and docs. The Spanish UI translation was removed.
- Integration domain `bebe` → `baby_tracker`; services are now `baby_tracker.log_feeding`, `baby_tracker.new_bottle`, etc.
  (see `docs/GLOSSARY.md` for every old → new name).
- Database file `bebe.db` → `baby_tracker.db` (additional babies: `baby_tracker_<id>.db`).
- Blueprints live in `blueprints/automation/baby_tracker/` and are English only; notification action ids are `BABY_*`.
- Milestone catalog (`www/milestones.json`) is English only and uses English ids.
- The pediatrician's plan is now a **daily goal (oz/day)** plus the daytime interval, instead of a goal per feeding. The old
  `number.*_goal_per_feeding` entity is removed; **re-enter your daily goal** after updating (default 24 oz).
- New **bedtime / wake-up** settings (`time.*_night_start`, `time.*_night_end`, default 9:00 PM–6:00 AM). No feedings are
  expected overnight: "Expected by now" stays flat until wake-up and reaches the goal at bedtime, the list of upcoming feedings stops
  at bedtime (with a top-up at bedtime when it is at least half an interval away), "Next feeding" (and so the reminder) moves to
  wake-up, and per-feeding amounts are the remaining goal divided by the daytime feedings left. Set both times equal to disable.
- Growth metrics are entered and shown in pounds and inches (panel, `log_measurement` fields `weight_lb`/`height_in`/`head_in`,
  `list_measurements` output, weight/length sensors). The database still stores kg/cm, so existing data is unaffected.
### Added
- "Import data from a previous install" option when adding a baby: copies a legacy `bebe*.db` into the new English schema
  (the original file is never modified).
### Removed
- The **Milestones** tab in the panel. The `mark_milestone`, `unmark_milestone` and `list_milestones` actions and the stored data are unchanged.
- Upgrade code for databases older than the Spanish schema v6 (use the importer instead).

## [1.2.0] - 2026-11-02
### Added
- Milestones tab: first year of life, week by week, with the 59 CDC milestones for 2, 4, 6, 9 and 12 months grouped into
  14 skills. You mark the day they noticed it; there is progress per skill, a timeline and a chart per area.
  Stages, what is normal, ideas and weeks are our own guidance text, not CDC's.
- Actions `mark_milestone`, `unmark_milestone` and `list_milestones`.
- Database schema v6 (`milestones` table), with an automatic backup before migrating.

## [1.1.0] - 2026-10-05
### Added
- Reference for the day in **Today**: two goals, **minimum** and **ideal** (the lower and higher of the pediatrician's goal and the
  weight-based reference; each day is evaluated with the weight current on that day). The bar shows where the baby should be at this
  time (with a one-feeding margin), how much is needed per feeding to reach each goal (never suggesting more than prescribed + 1 oz),
  what is expected in the remaining feedings of the day and which goals were met in the last 7 days.
- Sensor `reference_now` ("Reference at this time"): expected amount according to the minimum; the ideal, the goals, the plan for the
  upcoming feedings and the days met go in attributes. The daily series of `oz_today` includes `goal_minimum`,
  `goal_ideal` and `achievement` per day.
- Charts: the amount-per-day chart shows the minimum and ideal lines (stepped when the weight changes).

## [1.0.0] - 2026-10-01
First public release. Includes everything from 0.4.0 and 0.5.0 (below).
### Fixed
- Two error messages had placeholders inside single quotes (not allowed by Home Assistant validation).

## [0.5.0] - 2026-10-01
### Added
- Breast milk from the stash: "＋ Breast milk" in Today asks which stash bottle to use (soonest to expire first)
  when there is more than one. When logging a breast milk feeding with a new bottle, or when switching a bottle to breast milk, the panel
  asks which stash bottle it came from and deducts it (or "Not from the stash").
- `log_feeding` accepts `stash_id` and `pause_current`; `correct_bottle` accepts `stash_id`.
### Changed
- A feeding's type is always its bottle's type (`type` in `log_feeding` only decides the type of a new bottle);
  changing a bottle's type changes its feedings too.
### Fixed
- A breast milk bottle created by hand did not deduct the stash (the milk stayed there and later counted as wasted).

## [0.4.0] - 2026-10-01
### Added
- Several babies per install: one entry per baby, each with its own database, sensors and settings.
  Actions accept the `baby` field (entry id or name); optional with a single baby.
  The panel shows a selector when there is more than one baby (it remembers the last one chosen on each device).
- Automatic database backup before each schema migration (`<db>.before-vN`).
- Automatically created bottles use the baby's main milk type.
- English: integration (forms, sensors, actions) and the whole panel; the panel follows the Home Assistant user's language.
- Translatable error messages (`exceptions` section in `translations/*.json`).
- Blueprints: button press adds to the bottle; button hold = new bottle; feeding reminder answered from the
  notification; breast milk about to expire; notification buttons (undo, edit, move, answers);
  voice via to-do list + AI (optional). They work with several babies and with oz or ml.
- Action responses include `baby`, `name` and `unit`; the main sensors expose `baby_id`, `name` and `unit`.
### Fixed
- The panel header could hang when switching babies (recursion when updating the age).
### Compatibility
- Existing installs keep using the original database file; their entities, actions and automations do not change.

## [0.3.0] - 2026-09-30
### Added
- Diapers: pee, poop or both; color and consistency for poop with configurable usual values.
- "Today" screen with the last and next feeding highlighted; editing the size of the current bottle.
- Rate metrics (oz/h), distribution by hour of day and diapers by type.
- Paused bottles: give breast milk and continue later with formula.
- Breast milk: pumping, stash (fridge / room temperature) with expiry and warnings.
- "Configure" option: name, date of birth, sex, unit (oz/ml) and usual poop.
- Project name: Baby Tracker.

## [0.2.0] - 2026-09-29
### Added
- Bottle model with incremental feedings (each feeding adds to the current bottle).
- Sidebar panel: Today, Feedings, Measurements, Charts and Settings.
- Daily goal based on the pediatrician's guidance (oz per feeding and interval).

## [0.1.0] - 2026-09-28
### Added
- Initial integration: logging of feedings and measurements in SQLite, KPI sensors.
