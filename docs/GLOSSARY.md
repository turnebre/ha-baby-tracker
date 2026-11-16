# Spanish → English glossary

Every Spanish name in the original project and what it became. The legacy importer (`migrate_legacy.py`) is the only file that still contains the old names.

## Core terms

| Spanish | English |
|---|---|
| `bebé / bebe` | `baby` |
| `toma` | `feeding` |
| `biberón` | `bottle` |
| `pañal` | `diaper` |
| `extracción` | `pumping` |
| `medida` | `measurement` |
| `hito` | `milestone` |
| `reserva` | `stash` |
| `materna` | `breast_milk` |
| `mixta` | `mixed` |
| `pipí / popó / ambos` | `pee / poop / both` |
| `exacto / estimado / inferido` | `exact / estimated / inferred` |
| `ambiente / refrigerador` | `room / fridge` |
| `meta` | `goal` |
| `caducidad` | `expiry` |
| `vence / caduca` | `use_by / expires_at` |

## Package, domain, files

| Old | New |
|---|---|
| `bebe (domain)` | `baby_tracker` |
| `bebe.db` | `baby_tracker.db` |
| `custom_components/bebe` | `custom_components/baby_tracker` |
| `www/bebe-panel.js` | `www/baby-tracker-panel.js` |
| `www/bebe-milestones.json` | `www/milestones.json` |
| `blueprints/automation/bebe` | `blueprints/automation/baby_tracker` |

## SQLite tables

| Old | New |
|---|---|
| `tomas` | `feedings` |
| `biberones` | `bottles` |
| `extracciones` | `pumpings` |
| `panales` | `diapers` |
| `medidas` | `measurements` |
| `hitos` | `milestones` |

## Services (actions)

| Old | New |
|---|---|
| `bebe.registrar_toma` | `baby_tracker.log_feeding` |
| `bebe.corregir_toma` | `baby_tracker.correct_feeding` |
| `bebe.borrar_toma` | `baby_tracker.delete_feeding` |
| `bebe.restaurar_toma` | `baby_tracker.restore_feeding` |
| `bebe.nuevo_biberon` | `baby_tracker.new_bottle` |
| `bebe.cerrar_biberon` | `baby_tracker.close_bottle` |
| `bebe.reanudar_biberon` | `baby_tracker.resume_bottle` |
| `bebe.corregir_biberon` | `baby_tracker.correct_bottle` |
| `bebe.borrar_biberon` | `baby_tracker.delete_bottle` |
| `bebe.guardar_leche` | `baby_tracker.save_milk` |
| `bebe.usar_reserva` | `baby_tracker.use_stash` |
| `bebe.mover_reserva` | `baby_tracker.move_stash` |
| `bebe.descartar_reserva` | `baby_tracker.discard_stash` |
| `bebe.registrar_extraccion` | `baby_tracker.log_pumping` |
| `bebe.borrar_extraccion` | `baby_tracker.delete_pumping` |
| `bebe.registrar_panal` | `baby_tracker.log_diaper` |
| `bebe.corregir_panal` | `baby_tracker.correct_diaper` |
| `bebe.borrar_panal` | `baby_tracker.delete_diaper` |
| `bebe.registrar_medida` | `baby_tracker.log_measurement` |
| `bebe.borrar_medida` | `baby_tracker.delete_measurement` |
| `bebe.marcar_hito` | `baby_tracker.mark_milestone` |
| `bebe.desmarcar_hito` | `baby_tracker.unmark_milestone` |
| `bebe.listar_tomas` | `baby_tracker.list_feedings` |
| `bebe.listar_biberones` | `baby_tracker.list_bottles` |
| `bebe.listar_reservas` | `baby_tracker.list_stashes` |
| `bebe.listar_extracciones` | `baby_tracker.list_pumpings` |
| `bebe.listar_panales` | `baby_tracker.list_diapers` |
| `bebe.listar_medidas` | `baby_tracker.list_measurements` |
| `bebe.listar_hitos` | `baby_tracker.list_milestones` |

## Entity keys

| Old | New |
|---|---|
| `ultima_toma` | `last_feeding` |
| `proxima_toma` | `next_feeding` |
| `oz_hoy` | `oz_today` |
| `tomas_hoy` | `feedings_today` |
| `promedio_7d` | `average_7d` |
| `meta_oz_dia` | `goal_oz_day` |
| `avance_meta` | `goal_progress` |
| `referencia_ahora` | `reference_now` |
| `biberon_restante` | `bottle_remaining` |
| `biberon_vence` | `bottle_use_by` |
| `reserva_oz` | `stash_oz` |
| `reserva_caduca` | `stash_expires` |
| `ultimo_panal` | `last_diaper` |
| `panales_hoy` | `diapers_today` |
| `intervalo_indicado` | `prescribed_interval` |
| `limite_biberon` | `bottle_limit` |
| `limite_materna` | `breast_milk_limit` |
| `caducidad_ambiente` | `room_expiry` |
| `caducidad_refri` | `fridge_expiry` |

## Events

| Old | New |
|---|---|
| `bebe_toma_registrada` | `baby_tracker_feeding_logged` |
| `bebe_medida_registrada` | `baby_tracker_measurement_logged` |

## Common fields / columns

| Old | New |
|---|---|
| `bebe` | `baby` |
| `nombre` | `name` |
| `unidad` | `unit` |
| `inicio` | `started_at` |
| `fin` | `ended_at` |
| `oz_tomadas` | `oz_taken` |
| `oz_sobrantes` | `oz_leftover` |
| `oz_izq` | `oz_left` |
| `oz_der` | `oz_right` |
| `tipo` | `type` |
| `confianza` | `confidence` |
| `fuente` | `source` |
| `nota` | `note` |
| `creado` | `created_at` |
| `modificado` | `modified_at` |
| `borrado` | `deleted` |
| `cerrado` | `closed_at` |
| `preparado` | `prepared_at` |
| `hecho` | `made_at` |
| `ubicacion` | `location` |
| `biberon_id` | `bottle_id` |
| `reserva_id` | `stash_id` |
| `pausar_actual` | `pause_current` |
| `nuevo_biberon` | `new_bottle` |
| `registrado_por` | `logged_by` |
| `peso_kg` | `weight_kg` |
| `talla_cm` | `height_cm` |
| `perimetro_cm` | `head_cm` |
| `fecha` | `date` |
| `hito_id` | `milestone_id` |

## Milestone ids

See `MILESTONE_IDS` in `custom_components/baby_tracker/migrate_legacy.py` (old step id → new step id).
