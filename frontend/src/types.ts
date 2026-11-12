// Data shapes shared with the Python backend (api/bridge.py converts them to the optimizer's model).

export type EventType = 'theory' | 'lab' | 'tutorial';
export type RoomType = 'classroom' | 'lab' | 'hall';

export interface Group {
  id: string;
  name: string; // e.g. "SY-Comp Div A"
  strength: number;
}

export interface Faculty {
  id: string;
  name: string;
  maxWeekly: number; // H_f
  maxDaily: number;
  unavailable?: number[]; // blocked slots: day * periods.length + period
}

export interface Room {
  id: string;
  name: string;
  capacity: number;
  type: RoomType;
  kind?: string; // optimizer room kind (exact match with the offering)
  unavailable?: number[];
}

export interface Offering {
  id: string;
  subject: string; // full name
  code: string; // short label shown on blocks
  groupIds: string[];
  type: EventType;
  sessionsPerWeek: number;
  eligibleFaculty: string[];
  duration?: number; // periods per session
  roomKind?: string;
  distinctDays?: boolean;
}

export interface TEvent {
  id: string;
  offeringId: string;
  length: number; // periods
  headcount: number;
}

export interface TimeGrid {
  days: string[];
  periods: string[]; // labels like "9:00 - 10:00"
  lunchPeriod: number; // index into periods
  lunchPeriods?: number[];
}

export interface Instance {
  name: string;
  grid: TimeGrid;
  groups: Group[];
  faculty: Faculty[];
  rooms: Room[];
  offerings: Offering[];
  events: TEvent[];
  metadata?: Record<string, unknown>;
}

export interface Assignment {
  eventId: string;
  day: number;
  period: number; // start period
  roomId: string;
}

export interface Objectives {
  f1: number; // idle gaps
  f2: number; // room wastage (0..1)
  f3: number; // workload imbalance (std of relative load)
}

export interface Solution {
  id: string;
  objectives: Objectives;
  assignments: Assignment[];
  facultyOf: Record<string, string>; // offeringId -> facultyId
  onFront: boolean;
  violation?: number;
  metrics?: Record<string, number>; // practical metrics from the backend
}

export type Scenario = 'demo' | 'small' | 'medium' | 'large' | 'published' | 'custom';

/** Settings of one run of the optimizer. */
export interface RunParams {
  scenario: Scenario;
  instanceSeed: number;
  seed: number;
  budget: number; // full evaluations
  population: number;
  searchSeconds: number | null; // wall-time cap; null = evaluations only
  compareBaseline: boolean; // also run multi-algorithm comparison benchmark
}

export interface MultiConvergencePoint {
  evaluations: number;
  hypervolume: number;
}

export interface MultiConvergence {
  memetic: MultiConvergencePoint[];
  moead?: MultiConvergencePoint[];
  amosa?: MultiConvergencePoint[];
  nsga2?: MultiConvergencePoint[];
  greedy?: MultiConvergencePoint[];
}

export interface AlgorithmBenchmark {
  id: string;
  name: string;
  hv: number;
  runtime: number;
  frontSize: number;
  feasible: boolean;
  color: string;
  marker: 'circle' | 'triangle' | 'diamond' | 'square' | 'rhombus';
}

export interface RunStats {
  method: string;
  baselineMethod: string | null;
  runtime: number;
  evaluations: number;
  budget: number;
  population: number;
  searchSeconds: number | null;
  stopReason: string | null;
  generations: number;
  frontSize: number;
  hypervolume: number;
  baselineHypervolume: number;
  baselineRuntime: number | null;
  baselineEvaluations: number | null;
  baselineFrontSize: number;
  baselineFront: Objectives[];
  memeticFront?: Objectives[];
  moeadFront?: Objectives[];
  amosaFront?: Objectives[];
  nsga2Front?: Objectives[];
  algorithmComparison?: AlgorithmBenchmark[];
  multiConvergence?: MultiConvergence;
  spacing: number;
  baselineFeasible: boolean;
  normalization: number[];
  reference: number[];
  verified: boolean;
  savedTo: string | null;
  convergence: { generation: number; evaluations: number; hypervolume: number; archiveSize: number; feasibleFraction: number }[];
}

export interface RunResult {
  runId?: string;
  params: Record<string, unknown>;
  instance: Instance;
  solutions: Solution[];
  baseline: Solution | null;
  stats: RunStats;
}

export interface RunProgress {
  phase: 'queued' | 'memetic' | 'moead' | 'amosa' | 'nsga2' | 'baseline' | 'export';
  evaluations: number;
  budget: number;
  feasibleEvaluations?: number;
  seconds?: number;
  secondsLimit?: number | null;
}

export interface ScenarioInfo {
  id: Scenario;
  label: string;
  events: number;
  groups: number;
  rooms: number;
  faculty: number;
  budget: number;
  seconds: number;
}

export type ViewKind = 'group' | 'faculty' | 'room';
