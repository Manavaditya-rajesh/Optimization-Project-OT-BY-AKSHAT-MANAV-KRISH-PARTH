# Synthetic timetable datasets

All generated college data in this repository are **synthetic**. No student,
teacher, room, or institutional measurements were collected. The generator
models a repeating weekly timetable for disjoint student cohorts. Its default
laboratory sessions involve the whole cohort; split batches, individual student
enrolment overlaps, and institutional teaching qualifications are not inferred.

## Generate and verify

From the repository root after installation:

```bash
python main.py generate --size small --seed 10 --output data/example.json --certificate data/certificates/example.json
python main.py evaluate data/example.json data/certificates/example.json
python main.py solve data/example.json --method enhanced --seed 0 --budget 480 --population 24 --output results/example --figures figures/example
```

`generate_instance(size, seed, config)` returns `(problem, certificate)`. It first
constructs a valid timetable and then samples resource unavailability from
periods that do not destroy that certificate. Qualification sets retain the
certificate teacher and add alternatives. The independent evaluator checks the
certificate before generation returns. Thus algorithm failure on these generated
instances cannot be attributed to an impossible timetable.

The certificate is saved separately and is **never an input to the algorithms**.
It establishes feasibility, not an optimality bound or a competitive baseline.
The generator samples a planted-feasible distribution, which can be easier and
more structured than arbitrary real college instances. A bounded generation
failure under custom parameters is not a proof that those parameters are
infeasible.

## Presets and parameters

| Preset | Events | Groups | Rooms | Faculty |
|---|---:|---:|---:|---:|
| small | 40 | 2 | 5 | 6 |
| medium | 150 | 8 | 12 | 20 |
| large | 400 | 20 | 25 | 50 |

Events count sessions, not occupied periods: a two-period laboratory is one
event. Defaults use five days, eight grid periods per day, and lunch at the
zero-based period index `4`. Group sizes cycle through 24, 36, 48, and 54.
Room capacities cycle through 30, 45, 60, and 90, with at least one sufficient
room of each required kind. Rooms are classified as `classroom` or `lab` and
cannot substitute for another kind. Each group has six theory offerings and two
laboratory offerings. Theory sessions are distributed to reach the target event
count; each offering has at most one theory session per day. Labs last two
periods. Default faculty limits are 20 periods weekly and six daily. The default
unavailability sampling rate is `0.08`, conditional on the certificate.

Pass a JSON overrides file to `generate --config FILE`, or use a scenario's
`generator` object in an experiment configuration. Recognized keys are:

- `groups`, `rooms`, `faculty`, and `target_events`;
- `days`, `periods_per_day`, and `lunch_periods`;
- `theory_offerings_per_group`, `lab_offerings_per_group`, and `lab_duration`;
- `theory_sessions` as an alternative to `target_events`;
- `max_weekly`, `max_daily`, `unavailability_rate`, `eligible_per_offering`, and
  `construction_attempts`.

Unknown keys and the main invalid parameter domains are rejected. `theory_sessions` and
an explicit `target_events` cannot be combined. Changing `groups` without a
target recalculates demand from the offering counts and session defaults. Tight
custom instances may require more construction attempts or resources.

Two optional-configuration limitations remain in the frozen generator. Supply
`theory_sessions` as a positive JSON integer: the legacy implementation accepts
`true` as one session instead of rejecting it. When replaying a configuration
copied from generated metadata, remove the derived `target_events` if
`theory_sessions` is present; the recorded metadata can contain both, whereas
input overrides require one. These cases do not affect the published preset
instances. Preserve the actual input configuration and seed when reproducing.

For example:

```json
{
  "groups": 4,
  "rooms": 8,
  "faculty": 12,
  "theory_sessions": 3,
  "unavailability_rate": 0.15
}
```

## JSON schema and interpretation

Problems use `schema_version: 1` and contain `name`, `days`,
`periods_per_day`, `lunch_periods`, `groups`, `rooms`, `faculty`, `offerings`, and
`metadata`. The metadata records generator version, seed, parameters, and
synthetic sampling assumptions. It contains no witness placements or teachers.

| Entity | Required attributes |
|---|---|
| Group | `id`, positive integer `size` |
| Room | `id`, positive integer `capacity`, `kind`, flat-slot `unavailable` list |
| Faculty | `id`, positive integer `max_weekly`, `max_daily`, flat-slot `unavailable` list |
| Offering | `id`, `groups`, `eligible_faculty`, positive `sessions`, `duration`, `room_kind`, Boolean `distinct_days` |

Event order is derived deterministically from offering order and then session
number. Event IDs are `offering_id:session_number`. An event with several groups
occupies all of those groups and has their summed headcount. The default
generator creates single-cohort events; the model/evaluator also support shared
events in custom JSON instances.

Schedule JSON contains `placements` in event order and `teachers` in offering
order. A placement is `{"start": INTEGER, "room": "ROOM_ID"}`. Time is flattened
as `day_index * periods_per_day + period_index`, with zero-based indices. One
teacher gene per offering applies to all its sessions. Missing/invalid genes
are infeasible. Exported human-readable CSV grids label periods starting at 1.

`validate_problem` checks schema consistency while permitting well-formed
infeasible inputs, such as an event with no eligible teacher or no large-enough
room. `evaluate` checks an actual candidate against all scheduling constraints.
An infeasible candidate is excluded from reported fronts and hypervolume.

## Study artifacts

An experiment named `STUDY` saves instances as `data/STUDY/SIZE_SEED.json` and
certificates under `data/STUDY/certificates/`. Saved run records include a hash
of the corresponding instance. Do not substitute a regenerated or edited
instance when evaluating an archived timetable. The exact conflict examples
created by `prove-tradeoffs` are separate deliberately tiny synthetic models,
not measurements of college-scale data.
