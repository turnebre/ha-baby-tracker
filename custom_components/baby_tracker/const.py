"""Constants for the Baby Tracker integration."""

from datetime import time

DOMAIN = "baby_tracker"
DB_FILENAME = "baby_tracker.db"
# Database file for each baby (one config entry per baby); the first one uses baby_tracker.db
CONF_DB = "db"

CONF_BABY_NAME = "name"
CONF_BIRTH_DATE = "birth_date"
CONF_OZ_DEFAULT = "oz_default"
CONF_TYPE_DEFAULT = "type_default"
CONF_SEX = "sex"
# Expected "normal" poop; preselected and used when not specified (editable in Configure)
CONF_POOP_COLOR = "poop_color_default"
CONF_POOP_CONSISTENCY = "poop_consistency_default"
POOP_COLOR_DEFAULT = "yellow"
POOP_CONSISTENCY_DEFAULT = "pasty"
SEXES = ["boy", "girl", "unspecified"]
PROJECT_NAME = "Baby Tracker"
# Unit used to display and enter amounts (everything is stored in oz internally)
CONF_UNIT = "unit"
UNITS = ["oz", "ml"]
# Unit system used to enter and display growth measurements (the database always stores kg/cm)
CONF_GROWTH_UNIT = "growth_unit"
GROWTH_UNITS = ["imperial", "metric"]
GROWTH_UNIT_DEFAULT = "imperial"

TYPES = ["formula", "breast_milk", "mixed"]
CONFIDENCES = ["exact", "estimated", "inferred"]

ML_PER_OZ = 29.5735
# Growth measurements are stored in kg/cm in the database and shown/entered in lb/in or kg/cm (CONF_GROWTH_UNIT).
LB_PER_KG = 2.20462262
CM_PER_IN = 2.54
# General weight-based reference (informational only): ~150 ml/kg/day, capped at ~32 oz/day.
ML_PER_KG_DAY = 150
OZ_DAY_MAX = 32

# Pediatrician's guidance (adjustable from the UI with number entities)
GOAL_OZ_DAY_DEFAULT = 24.0
# Overnight sleep window: no feedings are expected between bedtime and wake-up (equal times = no night)
NIGHT_START_DEFAULT = time(21, 0)
NIGHT_END_DEFAULT = time(6, 0)
PRESCRIBED_INTERVAL_DEFAULT_H = 3.0
# Time since the first feeding after which preparing another bottle is suggested
BOTTLE_LIMIT_DEFAULT_H = 1.5
# Breast milk (general CDC guidance; adjustable from the UI): since the first feeding and per storage
BREAST_MILK_LIMIT_DEFAULT_H = 2.0
ROOM_EXPIRY_DEFAULT_H = 4.0
FRIDGE_EXPIRY_DEFAULT_DAYS = 4.0
LOCATIONS = ["room", "fridge"]
# A feeding timestamped within this many minutes of "now" is considered live
LIVE_WINDOW_MIN = 5
# A time up to 5 min in the future is tolerated (skewed clocks); anything beyond is rejected.
FUTURE_TOLERANCE_MIN = 5

DIAPER_TYPES = ["pee", "poop", "both"]
POOP_COLORS = ["yellow", "green", "brown", "orange", "black", "red", "white", "not_sure"]
POOP_CONSISTENCIES = ["watery", "seedy", "pasty", "hard", "not_sure"]

EVENT_FEEDING = "baby_tracker_feeding_logged"
EVENT_MEASUREMENT = "baby_tracker_measurement_logged"
