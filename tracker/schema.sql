-- Fitness tracker schema. Its own database: fitness, public schema.

-- One row per day. Garmin fills this. Manual edits are kept.
create table if not exists daily (
  date            date primary key,
  weight_kg       numeric(4,1),
  steps           integer,
  sleep_mins      integer,
  resting_hr      integer,
  alcohol_units   numeric(3,1),
  notes           text
);

-- The exercise catalogue for the 12-week programme.
create table if not exists exercise (
  id            serial primary key,
  name          text unique not null,
  session_label text not null,          -- 'A', 'B', 'BOTH', 'MINI'
  category      text not null,          -- warmup, physio, strength, core, golf
  target_sets   integer,
  target_reps   text,
  ref_kg        numeric(5,1),           -- 100% reference load. Null means bodyweight.
  from_week     integer default 1,
  sort_order    integer
);

-- One gym gym_session.
create table if not exists gym_session (
  id        serial primary key,
  date      date not null,
  label     text not null,              -- 'A' or 'B'
  week_no   integer,
  notes     text
);

-- One row per set. This is the progression record.
create table if not exists set_log (
  id          serial primary key,
  session_id  integer not null references gym_session(id) on delete cascade,
  exercise_id integer not null references exercise(id),
  set_no      integer not null,
  reps        integer,
  kg          numeric(5,1),
  rpe         integer,
  unique (session_id, exercise_id, set_no)
);

-- Sunday check-in.
create table if not exists weekly (
  week_no       integer primary key,
  start_date    date,
  weight_kg     numeric(4,1),
  sleep_quality integer,                -- 1 to 5
  alcohol_units numeric(3,1),
  sessions_done integer,
  notes         text
);

-- The plan itself: weekly weight target and load percentage.
create table if not exists plan (
  week_no          integer primary key,
  block            text,
  start_date       date,
  target_weight_kg numeric(4,1),
  load_pct         integer,
  sets_per_lift    integer,
  focus            text
);

create index if not exists idx_setlog_session on set_log(session_id);
create index if not exists idx_session_date   on gym_session(date);
