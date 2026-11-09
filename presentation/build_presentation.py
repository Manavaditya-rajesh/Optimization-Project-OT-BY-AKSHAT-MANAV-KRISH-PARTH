"""Build finished slides from saved measurements; no solver or benchmark runs."""
from pathlib import Path
from collections import Counter
from importlib.metadata import version
import json, hashlib, subprocess, tempfile, shutil
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from PIL import Image, ImageOps, ImageDraw
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR

HERE=Path(__file__).resolve().parent
ROOT=HERE.parent
ASSETS=HERE/'assets'
ASSETS.mkdir(exist_ok=True)
NAVY='#142C43'; TEAL='#087F7B'; AMBER='#B9672D'; INK='#23384A'; MUTED='#586B79'; PAPER='#F4F7F8'; PALE='#E4F1F0'; WHITE='#FFFFFF'
FONT='DejaVu Sans'
STEM='college_timetable_optimization'
def load(p): return json.loads((ROOT/p).read_text())
summary=load('results/enhancement_validation/summary.json')
verified=load('results/enhancement_validation/verification.json')
manifest=load('results/enhancement_validation/manifest.json')
precision_path='results/exact_fronts/enhancement_validation/summary.json'
precision=load(precision_path)['summary']
representatives=load('results/enhancement_validation/representatives.json')
rows={(r['size'],r['protocol'],r['method']):r for r in summary['summary']}
def hv(s,p,m): return rows[s,p,m]['hypervolume_mean']
gains=[]; ablation=[]
for s in ['medium','large']:
 for p in ['evaluations','wall_time']:
  gains.append((s,p,100*(hv(s,p,'memetic')/hv(s,p,'greedy')-1)))
  ablation.append((s,p,100*(hv(s,p,'memetic')/hv(s,p,'ablation_local')-1)))
source_files=['results/enhancement_validation/summary.json','results/enhancement_validation/verification.json','results/enhancement_validation/manifest.json','results/enhancement_validation/representatives.json','results/enhancement_validation/small_ideal_certificates.json','results/exact_micro/room/exact_front.json',precision_path]
(HERE/'evidence.json').write_text(json.dumps({'source_sha256':manifest['source_sha256'],'numerical_precision':precision,'primary_gains_percent':gains,'ablation_differences_percent':ablation,'verification':{k:v for k,v in verified.items() if not isinstance(v,dict)},'evidence_sha256':{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in source_files}},indent=2)+'\n')
plt.rcParams.update({'font.family':FONT,'font.size':14,'axes.spines.top':False,'axes.spines.right':False})
labels=[s.title()+' · '+('equal evaluations' if p=='evaluations' else 'equal wall time') for s,p,_ in gains]
for filename,values,mode in [('primary_gains',[v for _,_,v in gains],'gains'),('selection_ablation',[v for _,_,v in ablation],'ablation')]:
 fig,ax=plt.subplots(figsize=(11.4,3.8),constrained_layout=True)
 ax.barh(range(4),values,color=[TEAL if v>=0 else AMBER for v in values],height=.56)
 ax.set_yticks(range(4),labels); ax.invert_yaxis(); ax.grid(axis='x',alpha=.15); ax.set_axisbelow(True)
 ax.set_xlabel('Relative change in mean normalized hypervolume (%)' if mode=='gains' else 'Mean HV change: NSGA-II relative to scalar-local (%)')
 ax.set_xlim((0,10.7) if mode=='gains' else (-.25,.4))
 if mode=='ablation': ax.axvline(0,color=MUTED,lw=1)
 for i,v in enumerate(values): ax.text(v+(.15 if mode=='gains' else .012 if v>=0 else -.012),i,f'{v:+.2f}%',va='center',ha='left' if v>=0 else 'right',fontweight='bold',color=NAVY)
 fig.savefig(ASSETS/(filename+'.png'),dpi=190); plt.close(fig)
front=load('results/exact_micro/room/exact_front.json')['objectives']
fig,ax=plt.subplots(figsize=(7.1,3.7),constrained_layout=True)
ax.scatter([p[0] for p in front],[p[1] for p in front],s=170,color=TEAL,edgecolor=WHITE,linewidth=2,zorder=3)
ax.annotate('Compact day\n(0, 0.25, 0)',(0,.25),xytext=(.12,.25),va='center',color=NAVY)
ax.annotate('Best room fit\n(1, 0, 0)',(1,0),xytext=(.55,.045),color=NAVY)
ax.set(xlabel='Internal gaps',ylabel='Unused room fraction',xlim=(-.1,1.16),ylim=(-.025,.30)); ax.grid(alpha=.18)
fig.savefig(ASSETS/'certified_conflict.png',dpi=190); plt.close(fig)
selected={r['selection']:r for r in representatives if r['instance']=='large_1010' and r['method']=='memetic'}
fig,ax=plt.subplots(figsize=(10.9,3.15),constrained_layout=True)
xs=np.arange(4,16)
for offset,label,color,title in [(-.19,'fewest_gaps',AMBER,'Fewest gaps'),(.19,'balanced_workload',TEAL,'Balanced workload')]:
 counts=Counter(selected[label]['metrics']['faculty_loads'].values())
 ax.bar(xs+offset,[counts[x] for x in xs],width=.37,color=color,label=title)
ax.set(xlabel='Weekly teaching periods per faculty member',ylabel='Faculty count',xticks=xs); ax.legend(frameon=False); ax.grid(axis='y',alpha=.15); ax.set_axisbelow(True)
fig.savefig(ASSETS/'real_workload_tradeoff.png',dpi=190); plt.close(fig)
formulas={
'gaps':r'$f_1=\sum_{g,d}\mathrm{gap}_{g,d}+\frac{1}{2}\sum_{f,d}\mathrm{gap}_{f,d}$',
'room':r'$f_2=\frac{1}{\sum_e\ell_e}\sum_e\ell_e(1-n_e/c_{r(e)})$',
'workload':r'$f_3=\sqrt{\frac{1}{|F|}\sum_f(L_f/H_f-\bar\rho)^2}$',
'binary':r'$z_{e,s,r,f}\in\{0,1\},\quad y_{k,f}\in\{0,1\}$',
'assignment':r'$\sum_{(s,r,f)\in A_e}z_{e,s,r,f}=1,\quad\sum_{f\in F_k}y_{k,f}=1$',
'coupling':r'$\sum_{(s,r):(s,r,f)\in A_e}z_{e,s,r,f}=y_{k(e),f}$'}
for name,formula in formulas.items():
 fig=plt.figure(figsize=(10,1)); fig.text(.01,.5,formula,fontsize=26,color=NAVY,va='center'); fig.savefig(ASSETS/f'formula_{name}.png',dpi=200,bbox_inches='tight',pad_inches=.08,facecolor=WHITE); plt.close(fig)

slides=[]
def S(title,kicker,kind='bullets',notes='',source='',**kwargs):
 slides.append(dict(title=title,kicker=kicker,kind=kind,notes=notes,source=source,**kwargs))
S('Multi-Objective\nCollege Timetable\nOptimization','OPTIMIZATION TECHNIQUES · GROUP PROJECT','title',
 subtitle='Feasible schedules. Explicit trade-offs. Reproducible evidence.',
 stats=[('168','held-out runs'),('3.9–9.0%','primary mean HV gains'),('0','invalid exported schedules')],
 notes='The coordinator assigns every required session to a time block, suitable room and eligible teacher. Feasibility comes first. Headline gains refer only to the declared medium/large synthetic validation cases and both resource protocols. Small regressions and the competitive local-search ablation are retained. This technical presentation does not establish personal authorship, professor approval or eight weeks of individual participation.',source='report/enhancement_report.md; verification.json')
S('A scheduling decision with three interests','01 / PROBLEM AND DECISIONS','cards',
 cards=[('Students','Attend every required session.\nAvoid internal idle gaps.'),('Faculty','No double bookings.\nCompact and balanced teaching.'),('College','Use compatible rooms.\nMatch class sizes to seats.')],
 bullets=['Fixed inputs: demand, duration, cohorts, rooms, eligibility, availability and limits.','Decisions: one start + room per event; one eligible teacher per offering.'],
 banner='All weekly sessions of an offering share the same teacher.',
 notes='An offering is a subject taught to a group in the term; an event is one weekly session. Shared events name every attending disjoint atomic cohort and use their summed headcount. Teacher choice changes whole offering loads, making workload balance a genuine decision. Required demand is fixed, so quality cannot improve by cancelling classes. The week repeats deterministically.',source='problem/README.md; formulation/README.md, Sections 1–2')
S('Hard constraints define a usable timetable','02 / FEASIBILITY','constraints',
 bullets=['Every session exactly once; consistent eligible offering teachers.','No room, faculty or student-group clash in any occupied period.','Sufficient capacity, exact room type and full-block availability.','Daily/weekly teaching limits; distinct teaching days when requested.'],
 banner='A lab is one contiguous block: it cannot cross lunch or a day boundary.',
 notes='A two-period lab reserves both resource cells and consumes two teaching periods. Lunch is unavailable, not a penalty. A single clash keeps a candidate infeasible regardless of attractive objective values. The complete checker returns a violation breakdown; only violation zero permits export. Cohorts must be disjoint: overlapping parent divisions and their batches must not be counted as independent groups. The illustrated row is schematic, not an experimental timetable.',source='formulation/README.md, C1–C8; evaluation.py')
S('Three objectives, all minimized','03 / MATHEMATICAL QUALITY','objectives',
 cards=[('Idle gaps','Internal free teaching periods; mandatory lunch excluded.'),('Room wastage','Duration-weighted unused seat fraction during scheduled use.'),('Workload imbalance','Population SD of teaching load divided by weekly allowance.')],
 banner='Teacher choice makes workload optimizable; changing only times would not.',
 notes='Gaps exclude free time before the first and after the last class. Faculty gaps have weight one-half. Unavailability inside a teaching span still counts as teaching-free time, which may be a meeting in reality. Room wastage is seat fit, not campus room-hour utilization. Workload includes teaching, not research or administration. Every listed faculty member, including zero loads, is included. All sessions move together under one teacher. NSGA-II uses the three objectives directly rather than one fixed weighted sum.',source='formulation/README.md, Section 4')
S('Conflict is demonstrated, not assumed','04 / MULTI-OBJECTIVE RELEVANCE','conflict',image='presentation/assets/certified_conflict.png',
 bullets=['Small room: available at separated periods 0 and 2.','Larger room: available at periods 1 and 3.','Zero wastage forces a gap; zero gap requires extra seats.'],
 banner='64 complete candidate evaluations certify this tiny global front.',
 notes='The example has two one-period offerings, one 20-student group and two eligible teachers. A 20-seat room at separated periods gives (1,0,0); a compact pair using the 40-seat room once gives (0,0.25,0). These points come from exhaustive complete schedules, not a manufactured plotted front. Another exhaustive example shows workload/compactness conflict. This establishes possible conflict in the model, not inevitable conflict for every generated college instance. Some checked small instances have a singleton global ideal.',source='results/exact_micro/room/exact_front.json; formulation Section 5')
S('Synthetic data with known feasibility','05 / DATA','table',headers=['Preset','Events','Cohorts','Rooms','Faculty'],rows=[['Small','40','2','5','6'],['Medium','150','8','12','20'],['Large','400','20','25','50']],
 bullets=['Five days × eight periods; fixed lunch; two-period full-cohort labs.','Deterministic seeds; configurable demand, resources and availability.','A separate feasible certificate is generated and checked, then withheld from solvers.'],
 banner='Planted feasibility separates algorithm failure from impossibility—and biases sampling.',
 notes='Events count sessions, not occupied periods. Cohort sizes cycle through 24/36/48/54 and room capacities through 30/45/60/90. The generator samples availability without destroying its planted certificate. This ensures tested generated instances are schedulable but conditions the data on constructive feasibility. All data are synthetic. There is no real-institution or ITC benchmark validation. Generic full-cohort labs and disjoint cohorts are explicit simplifications.',source='data/README.md; generation.py')
S('The final method targets an observed weakness','06 / FROM BASELINE TO ENHANCEMENT','algorithm',
 bullets=['Strong reference: repeated DSatur-style greedy construction + a feasible Pareto archive.','Historical enhanced NSGA-II: more than 90% of raw offspring required repair.','Final method: fully feasible initialization and resource-aware mutation.','Retained: true rank/crowding tournaments and elitist parent–offspring survival.'],
 steps=['24 feasible\nconstructive seeds','Rank/crowding\nparent selection','Feasible mutation +\nfaculty search','Counted full\nvalidation','Elitist P + Q\nsurvival'],
 banner='Mutation-only memetic NSGA-II: destructive crossover is deliberately omitted.',
 notes='Historical whole-offering crossover preserved teacher consistency but destroyed interactions across offerings. Repeated reconstruction recovered feasibility without consistently beating the strong greedy front. The follow-up keeps the original data/model/indicators and greedy policy. It seeds the entire population constructively and changes the variation mechanism. A Pareto archive alone would not justify the NSGA-II label; the algorithm actually retains non-dominated ranks, crowding tournaments and parent–offspring environmental selection. No crossover benefit is claimed.',source='docs/enhancement_study.md; memetic.py; historical benchmark')
S('Domain knowledge, with bounded cost','07 / VARIATION AND INTENSIFICATION','columns',
 left_title='Five resource-aware moves',left=['Move a session to a feasible block','Change to a compatible fitting room','Swap event blocks safely','Reinsert an offering with a new teacher','Exchange cross-qualified offering teachers'],
 right_title='Structured faculty reassignment',right=['Reassign up to 8 whole offerings at fixed times/rooms.','Branch-and-bound capped at 12,000 nodes per call.','Equal allowances: smaller squared loads means smaller true workload SD.','Recheck all three objectives and every hard constraint.'],
 banner='Partial checks and search nodes consume time; full evaluator calls are not equal CPU work.',
 notes='Occupancy and load checks screen proposals, while the common complete evaluator remains the final authority. Faculty reassignment optimizes only a selected bounded subproblem, not the whole timetable. It can worsen faculty gaps while balancing loads. Common weekly allowances make squared-load minimization equivalent to true SD; the special search returns unchanged for unequal allowances. Proposal/no-op/duplicate and node diagnostics are saved. Equal-time experiments are essential because considerable internal work may precede one full evaluation.',source='docs/feasible_variation.md; feasible.py; faculty_search.py')
S('Frozen, held-out validation','08 / STUDY DESIGN','table',
 headers=['Size','Instance seeds','Solver seeds','Full-eval cap','Wall allocation'],rows=[['Small regression','1010','0, 1, 2','720','2.5 s'],['Medium primary','1010 / 1020 / 1030','0, 1, 2','360','6 s'],['Large primary','1010 / 1020 / 1030','0, 1, 2','240','16 s']],
 bullets=['Four methods: greedy, original enhanced NSGA-II, final memetic NSGA-II and scalar-local ablation.','Two separate budget protocols; 168 completed runs. Development seeds 9000+ stay separate.','Unchanged presets, objectives, normalization and HV reference (1.1, 1.1, 1.1).'],
 notes='Seven instances times three solver seeds times four methods times two protocols gives 168 runs. The small case is a regression check, not the primary superiority claim. The twelve-run development pilot used seed 9000; the larger development configuration was not run in full. Source hashes, source snapshot and runtime versions were frozen before validation. No operator rates, instance settings or quality indicators were changed in response to held-out outcomes.',source='experiments/enhancement_validation.json; manifest.json')
S('Fair budgets and verified cutoff evidence','09 / ACCOUNTING AND VERIFICATION','metrics',stats=[('201','pre-freeze tests passed'),('168 / 168','declared runs verified'),('3,295','raw feasible schedules'),('9','late evaluations excluded')],
 bullets=['Charge initialization, duplicates, repair and rejected full local proposals.','Time preprocessing, partial checks, native bookkeeping and common observation.','Reset constructor caches; run methods sequentially in rotated order.','Only complete objective results available by the deadline receive quality credit.'],
 banner='All raw schedules are feasible. Exact rational filtering retains 3,242 front points.',
 notes='Verification uses the common checker outside search and reconstructs every cutoff front. It is independent from search execution, not a claim that two independently authored validators exist. Timestamps mark full objective evaluation completion, before observer archive bookkeeping; bookkeeping still consumes measured time. Nine late completed calls were charged but excluded from quality. Bounded atomic work can overrun; actual runtime and overshoot are recorded. No background optimizer continues after a reported run. The count 3,295 is raw feasible schedules; mandatory exact rational postprocessing retains 3,242 non-dominated front points, removing 53 falsely retained floating-point ties. This does not change feasibility or timings.',source='verification.json; exact_fronts summary; tests_before_validation.txt')
S('The final method improves the primary comparisons','10 / MEASURED RESULTS','chart',image='presentation/assets/primary_gains.png',
 bullets=['9 paired wins out of 9 in each medium/large condition.','Equal-evaluation mean runtime: 2.93 s vs 20.22 s (medium); 8.04 s vs 51.67 s (large).','Observed synthetic gains, not universal superiority or global Pareto optimality.'],
 notes='The four relative mean-HV gains over unchanged repeated greedy are medium +4.74% equal-evaluation and +7.26% equal-time; large +3.88% and +8.97%. Hypervolume is unitless and may exceed one because the reference point is 1.1 on each normalized axis. Relative HV gains are not percentages of a known global optimum. These repeated improvements meet the professor’s primary comparison requirement on the declared medium/large conditions. They do not imply every timetable or objective improved.',source='summary.json; report/enhancement_report.md')
small_rows=[]
for p in ['evaluations','wall_time']:
 g,m=hv('small',p,'greedy'),hv('small',p,'memetic')
 small_rows.append(['Equal evaluations' if p=='evaluations' else 'Equal wall time',f'{g:.6f}',f'{m:.6f}',f'{100*(m/g-1):+.2f}%'])
S('Keep contrary evidence and the ablation','11 / HONEST INTERPRETATION','ablation',image='presentation/assets/selection_ablation.png',headers=['Small regression','Greedy HV','Memetic HV','Change'],rows=small_rows,
 banner='Scalar-local search is competitive; NSGA-II selection has no consistent demonstrated advantage.',
 notes='Small equal-evaluation mean HV decreased 0.48%; equal-time mean HV increased only 0.05%. Every run remains visible. The ablation shares constructive initialization and proposal family, replacing the NSGA-II selection/survival bundle with uniformly chosen fixed-positive-scalar local trajectories. The NSGA-II mean is higher for medium evaluations and large time, but lower for medium time and large evaluations. Later candidate streams diverge. This tests a policy bundle, not one isolated causal component. Credit the feasible variation/intensification design rather than assuming the NSGA-II name explains the gain.',source='summary.json: memetic_vs_ablation_local; enhancement_report.md')
S('Convergence follows real candidate discoveries','12 / ANYTIME EVIDENCE','chart',image='figures/enhancement_validation/large_anytime.png',
 bullets=['Quality and evaluation-count curves use real completion timestamps.','Shading: descriptive one-SD variability across solver runs, not independent-instance confidence intervals.','Three independent primary instances per size: minimum two-sided instance sign-test p = 0.25.'],
 notes='These plots come from saved raw histories, not average-time interpolation. Nine solver-run pairs are clustered within three college instances. Generalization uses independent instances, so even three consistent instance-mean wins have a minimum two-sided sign-test p-value of 0.25. No broad statistical superiority, operational real-college effectiveness or multiplicity-adjusted significance is claimed. Earlier objective points are never invented to improve a cutoff curve.',source='figures/enhancement_validation/large_anytime.png; instance-level comparisons')
for method,title,stats in [('greedy','A complete baseline timetable: balanced workload',[('3.0','global weighted gaps'),('0.192972','unused-seat fraction'),('0.050249','relative-load SD'),('6–11','faculty weekly load range')]),('memetic','The matched final timetable improves this choice',[('2.0','global weighted gaps'),('0.191165','unused-seat fraction'),('0.022913','relative-load SD'),('8–9','faculty weekly load range')])]:
 S(title,'13 / MATCHED MEDIUM 1010 EXAMPLE' if method=='greedy' else '14 / MATCHED MEDIUM 1010 EXAMPLE','timetable',image=f'figures/enhancement_validation/timetables/medium_1010_{method}_balanced_workload.png',stats=stats,
 caption=('Repeated greedy' if method=='greedy' else 'Final memetic method')+' · instance 1010 · seed 0 · 6-second protocol · same SD / gaps / room preference.',
 notes='The image shows one cohort’s grid, while the metrics describe the complete feasible college timetable. All displayed values are attained together, not separate objective minima. Selection is minimum workload SD, then gaps, then room wastage, identically for both methods. Greedy has zero student gaps and six faculty gaps; memetic has zero student gaps and four faculty gaps. In this matched example the final selected schedule improves all three objectives and narrows faculty loads from 6–11 to 8–9. This is an illustration, not proof every memetic timetable dominates every greedy alternative. The medium workload bound certifies this one objective only.',source=f'representatives.json: medium_1010 / {method} / balanced_workload')
S('Better balance can cost real idle time','15 / A COMPLETE LARGE-INSTANCE TRADE-OFF','tradeoff',image='presentation/assets/real_workload_tradeoff.png',headers=['Memetic choice','Weighted gaps','Unused seats','Load SD','Student / faculty gaps'],rows=[['Fewest gaps','1.5','0.208333','0.110454','0 / 3'],['Balanced workload','23.5','0.205985','0.036056','8 / 31']],
 banner='The coordinator chooses the compromise; hypervolume is not an administrative utility function.',
 notes='Both are complete feasible schedules from large_1010, solver seed zero and the wall-time protocol. The histogram uses their actual saved faculty load vectors. Balancing teaching loads reduces SD substantially but creates eight student and thirty-one faculty gaps. Seat fit improves slightly. The fixed conservative gap scale makes some practical gap changes weakly visible in HV. Show raw objectives and actual grids before recommending an alternative; a representative is not a unique knee or universally best schedule.',source='representatives.json: large_1010 / memetic / both preference selections')
S('Know which guarantees apply','16 / LIMITS AND NUMERICAL PRECISION','columns',left_title='Established',left=['All 3,295 raw schedules satisfy modeled hard constraints.','Exact rational cleanup retains 3,242 front points.','Tiny fronts and checked small ideal vectors are certified.','Medium schedules attain a workload-only bound.'],right_title='Essential limits',right=['Float SD can create 1-ULP pseudo-ties: exact cleanup is mandatory.','No global medium/large Pareto proof.','NSGA-II selection does not consistently beat scalar-local.','Synthetic data; only three primary instances per size.'],
 banner='Before reporting: python experiments/exact_fronts.py --study enhancement_validation',
 notes='All raw schedules remain feasible. A numerical audit found floating-point workload SD values differing by one ULP for mathematically tied workloads; these pseudo-ties could retain truly dominated points. Exact rational objective comparison removes 53 points from 36 follow-up runs (3,295 raw to 3,242 survivors) and 10 points from 8 historical runs (769 to 759). Maximum absolute hypervolume change is about 3.33e-16; the four printed primary gains and practical conclusions remain unchanged. The mandatory separate postprocessor compares exact rational gaps, room waste and workload variance, avoiding a floating square root. Run python experiments/exact_fronts.py --study enhancement_validation before reporting a front. It preserves frozen search code, raw schedules and measured timings. Exact simultaneous lower-bound attainment still certifies the checked small ideal; medium workload-only attainment does not certify the full front. No global medium/large Pareto guarantee or real-college validation is claimed.',source='docs/numerical_precision.md; results/exact_fronts/enhancement_validation/summary.json')
S('Reproduce and demonstrate the decision','17 / DEMO AND TAKEAWAY','demo',
 code=['python main.py generate --size small --seed 9002 --output work/presentation_demo/instance.json',
 'python main.py solve work/presentation_demo/instance.json --method memetic --seed 0 --budget 120 --population 12 --output work/presentation_demo/run --figures work/presentation_demo/figures',
 'python main.py evaluate work/presentation_demo/instance.json work/presentation_demo/run/timetables/normalized_compromise/schedule.json'],
 bullets=['Display violation = 0, objective values and the exported weekly grid.','Keep live examples separate from frozen measurements.','Next: real coordinator validation, broader instances, and reference/scale sensitivity.'],
 banner='Choose a clash-free timetable by explicit priorities—and keep the evidence behind the choice.',
 notes='Activate the documented Python environment first. The live small example is for transparent execution, not a promise to beat greedy. The three commands are also in presentation/demo.sh and write only to ignored work/presentation_demo. For new comparison studies, run the mandatory exact rational front cleanup before reporting: python experiments/exact_fronts.py --study YOUR_STUDY. A frozen medium saved alternative can be inspected if the live demo is inappropriate. The project now has a valid formulation, strong reference, tested optimization, controlled repeated comparisons, genuine trade-off examples and reproducible artifacts. The favorable claim is deliberately restricted to the declared primary medium/large synthetic conditions.',source='presentation/demo.sh; main.py; report/enhancement_report.md')
S('Backup: binary formulation and teacher consistency','APPENDIX A / FORMULATION','formulation',
 bullets=['Aₑ filters room capacity/type, geometry, lunch and full-block unavailability.','Resource occupancy ≤ 1 for every room, teacher and cohort in every period.','Weekly offering loads and daily occupied periods obey faculty limits.'],
 banner='Discrete constrained feasibility is binary linear; workload SD is nonlinear.',
 notes='z selects a joint event/start/room/faculty option; y selects a teacher per offering. Exactly one event option and one eligible offering teacher are selected. The coupling equation applies to each event and eligible faculty, forcing every session of the offering to share its teacher. This replaces the proposal’s bilinear occupancy product. The compact categorical search representation makes the same decisions. Exact scalar CP-SAT OPTIMAL certifies only the chosen objective; UNKNOWN does not prove infeasibility.',source='formulation/README.md, C1–C8; exact.py')
S('Backup: the small ideal is a valid exact certificate','APPENDIX B / GUARANTEES',
 bullets=['44 teaching periods; 6 faculty; common allowance 20.','Indivisible offering loads: twelve 3-period and four 2-period offerings.','Exact partition relaxation: min squared loads = 328 → variance ≥ 1/450.','Independent bounds: gaps ≥ 0 and unused-seat fraction ≥ 14/55.','A feasible timetable attains every bound: loads [6, 6, 8, 8, 8, 8].'],
 banner='Simultaneous attainment proves a singleton ideal; it does not prove reliable attainment across runs.',
 notes='Each relaxation bound remains valid for the original constrained problem. Equal weekly allowances make the mean normalized load constant. Exact variance is 328/(6×20²) − (44/(6×20))² = 1/450. The certificate checks integer gaps, exact rational room waste and integer squared loads. small_1010 attainment is in memetic evaluation seed one, archive index zero. One successful run does not erase its unfavorable equal-evaluation mean. No such full-front proof is claimed for medium/large instances.',source='small_ideal_certificates.json; experiments/certify_small_ideal.py')
S('Backup: references and viva checkpoints','APPENDIX C / SOURCES',
 bullets=['Deb et al. (2002), NSGA-II. IEEE TEC. DOI: 10.1109/4235.996017.','Brélaz (1979), New Methods to Color the Vertices of a Graph. DOI: 10.1145/359094.359101.','Schaerf (1999), A Survey of Automated Timetabling. Artificial Intelligence Review.','Zitzler et al. (2003), Performance Assessment of Multiobjective Optimizers. IEEE TEC.','Google OR-Tools CP-SAT documentation; professor assignment and supplied proposal.'],
 banner='Rebuild: python presentation/build_presentation.py · Evidence values/hashes: presentation/evidence.json',
 notes='Full references and exact roles are in literature/README.md. Every member should explain why teacher choice changes workload, why labs reserve all periods, constraint domination among infeasible candidates, why equal evaluation counts are not equal computation, what makes the final algorithm an NSGA-II variant, the scopes of exact guarantees, and why workload balance can hurt students. The mandatory front-cleanup command is python experiments/exact_fronts.py --study enhancement_validation. It leaves frozen search/timing records unchanged and writes exact rational reporting fronts separately. The presentation builder reads saved artifacts only and runs no optimizer. The source hash of measured validation is '+manifest['source_sha256']+'.',source='literature/README.md; docs/reference_review.md; manifest.json')

# Common editable PowerPoint layout helpers.
def rgb(c): return RGBColor.from_string(c[1:])
def rect(sl,x,y,w,h,color):
 sh=sl.shapes.add_shape(MSO_SHAPE.RECTANGLE,Inches(x),Inches(y),Inches(w),Inches(h)); sh.fill.solid(); sh.fill.fore_color.rgb=rgb(color); sh.line.fill.background(); return sh
def text(sl,value,x,y,w,h,size=20,color=INK,bold=False,align=PP_ALIGN.LEFT):
 box=sl.shapes.add_textbox(Inches(x),Inches(y),Inches(w),Inches(h)); tf=box.text_frame; tf.word_wrap=True
 tf.margin_left=tf.margin_right=tf.margin_top=tf.margin_bottom=0
 for i,line in enumerate(value.split('\n') if isinstance(value,str) else value):
  p=tf.paragraphs[0] if i==0 else tf.add_paragraph(); p.text=line; p.font.name=FONT; p.font.size=Pt(size); p.font.color.rgb=rgb(color); p.font.bold=bold; p.alignment=align; p.space_after=Pt(9)
 return box
def bullets(sl,values,x=.8,y=1.75,w=11.75,h=4.4,size=20): return text(sl,['•  '+v for v in values],x,y,w,h,size)
def picture(sl,path,x,y,w,h):
 p=ROOT/path; im=Image.open(p); ratio=min(w/im.width,h/im.height); iw,ih=im.width*ratio,im.height*ratio
 sl.shapes.add_picture(str(p),Inches(x+(w-iw)/2),Inches(y+(h-ih)/2),width=Inches(iw),height=Inches(ih))
def banner(sl,t): rect(sl,.60,6.40,12.12,.48,NAVY); text(sl,t,.78,6.50,11.8,.30,13,WHITE,True)
def table(sl,headers,data,y=1.72,rh=.53,font=16):
 sh=sl.shapes.add_table(len(data)+1,len(headers),Inches(.65),Inches(y),Inches(12.05),Inches(rh*(len(data)+1)))
 for i,row in enumerate([headers]+data):
  for j,v in enumerate(row):
   c=sh.table.cell(i,j); c.fill.solid(); c.fill.fore_color.rgb=rgb(NAVY if i==0 else WHITE if i%2 else '#EAF0F2'); c.margin_left=Inches(.1); c.margin_right=Inches(.08); c.vertical_anchor=MSO_ANCHOR.MIDDLE; c.text=str(v)
   for p in c.text_frame.paragraphs: p.font.name=FONT; p.font.size=Pt(font); p.font.bold=i==0; p.font.color.rgb=rgb(WHITE if i==0 else INK); p.alignment=PP_ALIGN.LEFT if j==0 else PP_ALIGN.CENTER
 return sh
def metrics(sl,stats,y=1.7,height=1.25,size=30):
 width=(12.05-.2*(len(stats)-1))/len(stats)
 for i,(number,label) in enumerate(stats):
  x=.65+i*(width+.2); rect(sl,x,y,width,height,PALE); text(sl,number,x+.14,y+.13,width-.28,.5,size,TEAL,True); text(sl,label,x+.14,y+.74,width-.28,.39,12,NAVY)

prs=Presentation(); prs.slide_width=Inches(13.333333); prs.slide_height=Inches(7.5); prs.core_properties.author=''; prs.core_properties.title='Multi-Objective College Timetable Optimization'
md=['---','marp: true','paginate: true','size: 16:9','---','']; notes=['# Complete presenter notes','','Main talk: slides 1–18. Backups: slides 19–21. Suggested duration: 15–18 minutes plus demo.','']
for index,s in enumerate(slides,1):
 sl=prs.slides.add_slide(prs.slide_layouts[6]); sl.background.fill.solid(); sl.background.fill.fore_color.rgb=rgb(PAPER); rect(sl,0,0,.15,7.5,TEAL)
 text(sl,s['kicker'],.62,.30,12,.28,10,TEAL,True)
 if s['kind']!='title': text(sl,s['title'],.62,.80,12.05,.78,28,NAVY,True)
 text(sl,'OPTIMIZATION TECHNIQUES · SYNTHETIC STUDY',.62,7.18,10,.16,7.5,MUTED); text(sl,f'{index:02d} / {len(slides):02d}',11.8,7.12,.91,.24,9,MUTED,align=PP_ALIGN.RIGHT)
 kind=s['kind']
 if kind=='title':
  rect(sl,.15,0,13.19,7.5,NAVY); rect(sl,.65,.58,1.05,.06,'#8ED2CD'); text(sl,s['kicker'],.65,.95,12,.3,12,'#8ED2CD',True); text(sl,s['title'],.65,1.55,12,2.5,39,WHITE,True); text(sl,s['subtitle'],.68,4.4,12,.6,21,'#D3E3E9')
  for i,(number,label) in enumerate(s['stats']): text(sl,number,.68+i*4.12,5.65,3.8,.64,33,WHITE,True); text(sl,label,.68+i*4.12,6.42,3.8,.3,13,'#C1D5DF')
 elif kind=='cards':
  for i,(heading,body) in enumerate(s['cards']):
   x=.65+i*4.12; rect(sl,x,1.77,3.88,2.45,WHITE); rect(sl,x,1.77,3.88,.07,TEAL); text(sl,heading,x+.2,2.10,3.48,.48,23,TEAL,True); text(sl,body,x+.2,2.85,3.48,1.1,18)
  bullets(sl,s['bullets'],y=4.7,h=1.3,size=19)
 elif kind=='constraints':
  bullets(sl,s['bullets'],y=1.72,h=2.65,size=20)
  for p in range(8):
   x=.87+p*1.48; rect(sl,x,4.75,1.33,.75,'#DDE2E5' if p==4 else PALE if p in (1,2) else WHITE); text(sl,'LUNCH' if p==4 else 'LAB' if p in (1,2) else '—',x+.04,4.93,1.25,.33,17,MUTED if p==4 else TEAL,p in (1,2),PP_ALIGN.CENTER); text(sl,f'Period {p+1}',x,5.62,1.33,.27,11,MUTED,align=PP_ALIGN.CENTER)
 elif kind=='objectives':
  for i,((heading,body),formula) in enumerate(zip(s['cards'],['gaps','room','workload'])):
   x=.65+i*4.12; rect(sl,x,1.78,3.88,3.85,WHITE); text(sl,f'f{i+1}  {heading}',x+.18,2.07,3.50,.66,21,TEAL,True); picture(sl,f'presentation/assets/formula_{formula}.png',x+.10,2.95,3.68,1.0); text(sl,body,x+.18,4.30,3.50,1.0,18)
 elif kind=='conflict': picture(sl,s['image'],.75,1.76,7.15,4.25); bullets(sl,s['bullets'],8.1,2.0,4.45,3.4,19)
 elif kind=='table': table(sl,s['headers'],s['rows'],rh=.58,font=15.5); bullets(sl,s['bullets'],y=4.35,h=1.7,size=17.5)
 elif kind=='algorithm':
  for i,step in enumerate(s['steps']):
   x=.65+i*2.47; rect(sl,x,1.82,2.2,1.3,WHITE); text(sl,step,x+.1,2.0,2.0,.98,16.7,TEAL,True,PP_ALIGN.CENTER)
   if i<4: text(sl,'›',x+2.22,2.10,.25,.6,30,AMBER,True)
  bullets(sl,s['bullets'],y=3.7,h=2.3,size=18.5)
 elif kind=='columns':
  for x,title,body in [(.65,s['left_title'],s['left']),(6.87,s['right_title'],s['right'])]:
   rect(sl,x,1.77,5.82,4.2,WHITE); text(sl,title,x+.2,2.05,5.42,.6,21,TEAL,True); bullets(sl,body,x+.2,2.83,5.4,3.0,17.0)
 elif kind=='metrics': metrics(sl,s['stats']); bullets(sl,s['bullets'],y=3.45,h=2.5,size=18.8)
 elif kind=='chart': picture(sl,s['image'],.7,1.62,11.95,3.83); bullets(sl,s['bullets'],y=5.55,h=1.1,size=15.5)
 elif kind=='ablation': table(sl,s['headers'],s['rows'],y=1.67,rh=.44,font=15); picture(sl,s['image'],.85,3.13,11.65,2.76)
 elif kind=='timetable': picture(sl,s['image'],.65,1.68,12.05,3.78); metrics(sl,s['stats'],y=5.59,height=.93,size=24); text(sl,s['caption'],.75,6.68,11.85,.23,10,MUTED)
 elif kind=='tradeoff': table(sl,s['headers'],s['rows'],y=1.68,rh=.49,font=15); picture(sl,s['image'],.86,3.43,11.65,2.53)
 elif kind=='demo':
  rect(sl,.65,1.75,12.05,2.6,NAVY); box=text(sl,'\n\n'.join(s['code']),.86,1.99,11.6,2.15,12,'#D6EEE9')
  for p in box.text_frame.paragraphs: p.font.name='DejaVu Sans Mono'; p.space_after=Pt(5)
  bullets(sl,s['bullets'],y=4.78,h=1.3,size=18)
 elif kind=='formulation':
  for f,y in [('binary',1.75),('assignment',2.63),('coupling',3.53)]: rect(sl,.75,y-.03,11.8,.8,WHITE); picture(sl,f'presentation/assets/formula_{f}.png',.95,y,11.3,.72)
  bullets(sl,s['bullets'],y=4.72,h=1.2,size=17)
 else: bullets(sl,s.get('bullets',[]),size=21 if index<len(slides) else 18.5)
 if 'banner' in s: banner(sl,s['banner'])
 if kind!='title': text(sl,'Evidence: '+s['source'],.65,6.99,12,.16,7.2,MUTED)
 sl.notes_slide.notes_text_frame.text=s['notes']+'\n\nEvidence: '+s['source']
 if index>1: md+=['---','']
 md+=['# '+s['title'].replace('\n',' '),'','<!-- '+s['kicker']+' -->','']
 if 'subtitle' in s: md+=[s['subtitle'],'']
 if 'stats' in s: md+=[' | '.join(f'**{a}** {b}' for a,b in s['stats']),'']
 for heading,body in s.get('cards',[]): md+=['## '+heading,body,'']
 for t,vals in [(s.get('left_title'),s.get('left')),(s.get('right_title'),s.get('right'))]:
  if t: md+=['## '+t]+['- '+v for v in vals]+['']
 if 'headers' in s: md+=['| '+' | '.join(s['headers'])+' |','| '+' | '.join(['---']*len(s['headers']))+' |']+['| '+' | '.join(row)+' |' for row in s['rows']]+['']
 if 'image' in s: md+=['![]('+ (s['image'][13:] if s['image'].startswith('presentation/') else '../'+s['image'])+')','']
 if 'steps' in s: md+=[' → '.join(x.replace('\n',' ') for x in s['steps']),'']
 if kind in ['objectives','formulation']:
  for f in (['gaps','room','workload'] if kind=='objectives' else ['binary','assignment','coupling']): md+=['![](assets/formula_'+f+'.png)','']
 if 'code' in s: md+=['```bash']+s['code']+['```','']
 md+=['- '+v for v in s.get('bullets',[])]+['']
 if 'banner' in s: md+=['**'+s['banner']+'**','']
 md+=['<!-- Speaker notes: '+s['notes']+' -->','','<!-- Evidence: '+s['source']+' -->','']
 notes+=[f"## Slide {index} — "+s['title'].replace('\n',' '),'',s['notes'],'','**Evidence:** '+s['source'],'']
(HERE/'slides.md').write_text('\n'.join(md)+'\n'); (HERE/'presenter_notes.md').write_text('\n'.join(notes)+'\n')
pptx=HERE/(STEM+'.pptx'); prs.save(pptx)
parsed=Presentation(pptx); assert len(parsed.slides)==len(slides); assert all(sl.notes_slide.notes_text_frame.text.strip() for sl in parsed.slides)
prior_checks=json.loads((HERE/'build_checks.json').read_text()) if (HERE/'build_checks.json').exists() else {}
checks={'pptx_slides':len(slides),'speaker_notes_slides':len(slides),'solver_runs_during_build':0,'exact_front_postprocessing_disclosed':True,'versions':{p:version(p) for p in ['python-pptx','matplotlib','Pillow']}}
with tempfile.TemporaryDirectory(prefix='timetable-slides-') as tmp:
 command=[shutil.which('soffice'),'-env:UserInstallation=file://'+tmp+'/profile','--headless','--convert-to','pdf','--outdir',str(HERE),str(pptx)]
 subprocess.run(command,check=True,capture_output=True,text=True,timeout=180)
 pdf=HERE/(STEM+'.pdf'); assert pdf.exists()
 info=subprocess.run(['pdfinfo',str(pdf)],check=True,capture_output=True,text=True).stdout
 pages=int(next(x.split(':',1)[1] for x in info.splitlines() if x.startswith('Pages:'))); assert pages==len(slides); checks['pdf_pages']=pages
 content=subprocess.run(['pdftotext',str(pdf),'-'],check=True,capture_output=True,text=True).stdout
 for phrase in ['College Timetable','Mutation-only','3,295','3,242','exact_fronts.py','Small regression','APPENDIX C']: assert phrase in content,phrase
 checks['required_pdf_text']='PASS'
 subprocess.run(['pdftoppm','-scale-to','480','-png',str(pdf),tmp+'/slide'],check=True,capture_output=True,timeout=120)
 thumbs=sorted(Path(tmp).glob('slide-*.png')); width,height=480,270; cols=4
 sheet=Image.new('RGB',(cols*492+12,((len(thumbs)+cols-1)//cols)*300+12),'#DCE5E9'); draw=ImageDraw.Draw(sheet)
 for i,p in enumerate(thumbs):
  x,y=12+(i%cols)*492,12+(i//cols)*300; image=ImageOps.contain(Image.open(p).convert('RGB'),(width,height)); sheet.paste(image,(x,y)); draw.text((x+5,y+275),f'{i+1:02d}',fill=INK)
 sheet.save(HERE/'preview.png'); checks['rendered_preview_slides']=len(thumbs)
for key in ['demo_script_syntax','demo_execution']:
 if key in prior_checks: checks[key]=prior_checks[key]
(HERE/'build_checks.json').write_text(json.dumps(checks,indent=2)+'\n')
print(json.dumps(checks,indent=2))
