-- v2: ramp by exercise count, not load. Time-boxed sessions. A/B only from week 9.

alter table daily add column if not exists water_ml integer;

alter table plan add column if not exists max_from_week integer;  -- which exercises are active
alter table plan add column if not exists split boolean default false;
alter table plan add column if not exists est_minutes integer;

alter table exercise add column if not exists photo text;         -- filename in static/exercises/
alter table exercise add column if not exists default_reps integer;
alter table exercise add column if not exists est_minutes numeric(3,1);

-- Rebuild the plan. Sets and exercise count now ramp together.
truncate plan;
insert into plan (week_no, block, start_date, target_weight_kg, load_pct, sets_per_lift,
                  max_from_week, split, est_minutes, focus) values
 (1, 'Ramp',   '2026-09-14', 77.5,  70, 2, 1, false, 22, 'Five exercises. Two sets. Get the habit back.'),
 (2, 'Ramp',   '2026-09-21', 77.0,  75, 2, 1, false, 22, 'Same five. Add reps, not load.'),
 (3, 'Ramp',   '2026-09-28', 76.5,  80, 2, 1, false, 22, 'Same five. Last easy week.'),
 (4, 'Build',  '2026-10-05', 76.0,  85, 3, 4, false, 35, 'Three new exercises. Three sets.'),
 (5, 'Build',  '2026-10-12', 75.5,  90, 3, 4, false, 35, 'Add 2.5 kg to one lift.'),
 (6, 'Build',  '2026-10-19', 75.0,  95, 3, 4, false, 35, 'Add 2.5 kg to one lift.'),
 (7, 'Build',  '2026-10-26', 74.5, 100, 3, 4, false, 35, 'Match the June loads.'),
 (8, 'Deload', '2026-11-02', 74.2,  60, 2, 1, false, 20, 'Back to the five, light. Protect the joints.'),
 (9, 'Sharpen','2026-11-09', 73.7, 100, 3, 9, true,  30, 'Ten exercises. Split into A and B.'),
 (10,'Sharpen','2026-11-16', 73.2, 105, 3, 9, true,  30, 'Beat the June loads.'),
 (11,'Sharpen','2026-11-23', 72.6, 105, 3, 9, true,  30, 'Hold the load. Tighten the diet.'),
 (12,'Sharpen','2026-11-30', 72.0, 105, 3, 9, true,  30, 'Final week. Photos on 6 Dec.');

-- Rebuild the catalogue: 10 exercises, no more.
delete from set_log;
delete from gym_session;
delete from exercise;

insert into exercise (name, session_label, category, target_sets, target_reps, default_reps,
                      ref_kg, from_week, sort_order, est_minutes, photo) values
 ('500 m Row',                'BOTH','warmup',  1,'500 m',   null, null, 1, 1, 3.0, null),
 ('Goblet Squat',             'A',   'strength',3,'10',        10, 20.0, 1, 3, 4.0, null),
 ('Single Arm Row',           'A',   'strength',3,'8 each',     8, 27.5, 1, 4, 4.0, null),
 ('Cable Chest Press',        'B',   'strength',3,'10',        10, 22.0, 1, 5, 4.0, null),
 ('Pallof Press',             'A',   'core',    3,'12 each',   12, 16.0, 1, 6, 4.0, null),
 ('Split Kneeling Rocks',     'BOTH','physio',  2,'5 each',     5, null, 4, 2, 2.0, null),
 ('DB Romanian Deadlift',     'B',   'strength',3,'10',        10, 20.0, 4, 7, 4.0, null),
 ('Face Pulls',               'B',   'strength',2,'15',        15, 15.0, 4, 8, 3.0, null),
 ('Lateral Lunge',            'A',   'strength',3,'8 each',     8, 20.0, 9, 9, 4.0, null),
 ('Cable Rotational Chop',    'B',   'golf',    3,'10 each',   10, 12.0, 9,10, 4.0, null);
