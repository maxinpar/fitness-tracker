-- Seed the 12-week programme. Safe to re-run.

truncate plan;
insert into plan (week_no, block, start_date, target_weight_kg, load_pct, sets_per_lift, focus) values
 (1,'Ramp',   '2026-09-14', 77.5,  70, 2, 'Re-acclimatise. Expect no soreness.'),
 (2,'Ramp',   '2026-09-21', 77.0,  75, 2, 'Add reps, not load.'),
 (3,'Ramp',   '2026-09-28', 76.5,  80, 3, 'The third set returns.'),
 (4,'Build',  '2026-10-05', 76.0,  85, 3, 'Load starts to climb.'),
 (5,'Build',  '2026-10-12', 75.5,  90, 3, 'Add 2.5 kg to one lift.'),
 (6,'Build',  '2026-10-19', 75.0,  95, 3, 'Add 2.5 kg to one lift.'),
 (7,'Build',  '2026-10-26', 74.5, 100, 3, 'Match the June loads.'),
 (8,'Deload', '2026-11-02', 74.2,  60, 2, 'Cut the load. Protect the joints.'),
 (9,'Sharpen','2026-11-09', 73.7, 100, 3, 'Add the Cable Rotational Chop.'),
 (10,'Sharpen','2026-11-16',73.2, 105, 3, 'Beat the June loads.'),
 (11,'Sharpen','2026-11-23',72.6, 105, 3, 'Hold the load. Tighten the diet.'),
 (12,'Sharpen','2026-11-30',72.0, 105, 3, 'Final week. Take photos on 6 Dec.');

-- ref_kg is the 100% load. The app shows ref_kg * load_pct, rounded to 2.5 kg.
insert into exercise (name, session_label, category, target_sets, target_reps, ref_kg, from_week, sort_order) values
 ('500 m Row',                     'BOTH','warmup',  1,'500 m',   null, 1, 1),
 ('Split Kneeling Rocks',          'A',   'physio',  2,'5 each',  null, 1, 2),
 ('Dynamic Wind-Up Drill',         'B',   'physio',  2,'5 each',  null, 1, 2),
 ('Lateral Step-Up',               'A',   'strength',3,'8 each',  20.0, 1, 3),
 ('Single Arm Row',                'A',   'strength',3,'8 each',  27.5, 1, 4),
 ('Goblet Squat',                  'A',   'strength',3,'10',      20.0, 1, 5),
 ('Pallof Press',                  'A',   'core',    3,'12 each', 16.0, 1, 6),
 ('Low Oblique Sit',               'A',   'core',    2,'8 each',  null, 1, 7),
 ('Lateral Lunge',                 'B',   'strength',3,'8 each',  20.0, 1, 3),
 ('Cable Chest Press',             'B',   'strength',3,'10',      22.0, 1, 4),
 ('Single Leg Bridge',             'B',   'strength',3,'15 each', null, 1, 5),
 ('Face Pulls',                    'B',   'strength',2,'15',      15.0, 1, 6),
 ('Baby Rocking w/ Groin Squeeze', 'B',   'core',    2,'8 each',  null, 1, 7),
 ('Cable Rotational Chop',         'BOTH','golf',    3,'10 each', 12.0, 9, 8),
 ('Push-ups',                      'MINI','core',    3,'8',       null, 1, 10),
 ('Plank',                         'MINI','core',    3,'25 s',    null, 1, 11),
 ('Chin-ups',                      'MINI','core',    3,'3',       null, 1, 12)
on conflict (name) do nothing;

-- Baseline weight, stated 9 Sep 2026, not yet measured on scales.
insert into daily (date, weight_kg, notes) values
 ('2026-09-09', 78.0, 'Baseline. Estimated, not weighed.')
on conflict (date) do update set weight_kg = excluded.weight_kg, notes = excluded.notes;
