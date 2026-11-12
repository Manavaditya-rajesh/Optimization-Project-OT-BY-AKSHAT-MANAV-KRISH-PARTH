# Automated Live Demo Script for Optimization Techniques Presentation
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host " MULTI-OBJECTIVE COLLEGE TIMETABLE OPTIMIZATION DEMO     " -ForegroundColor Cyan
Write-Host " Benchmark Dataset: ITC-2007 CB-CTT International Benchmark" -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

$python = ".venv\Scripts\python.exe"
$dataset = "data/itc/itc_comp01.json"

# 1. Multi-Algorithm Benchmark Comparison on ITC Dataset
Write-Host "`n[STEP 1] Running 5-Algorithm Comparison on ITC-2007 Benchmark..." -ForegroundColor Yellow
& $python experiments\compare_all_methods.py --instance $dataset --budget 160 --population 16 --seed 0

# 2. Run MOEA/D with Tchebycheff Decomposition
Write-Host "`n[STEP 2] Solving ITC Benchmark with MOEA/D (Tchebycheff)..." -ForegroundColor Yellow
& $python main.py solve $dataset --method moead --budget 240 --population 24 --output results/itc_moead --figures figures/itc_moead

# 3. Independent Constraint Validation
Write-Host "`n[STEP 3] Independently Verifying Hard Constraints & Objectives..." -ForegroundColor Yellow
& $python main.py evaluate $dataset results/itc_moead/timetables/normalized_compromise/schedule.json

# 4. TOPSIS Stakeholder Decision Analysis
Write-Host "`n[STEP 4] Multi-Criteria Decision Analysis (TOPSIS Ranking)..." -ForegroundColor Yellow
& $python main.py mcdm $dataset results/itc_moead/run.json --profile student_first

Write-Host "`n==========================================================" -ForegroundColor Green
Write-Host " DEMO COMPLETE! Results saved to results/itc_moead/        " -ForegroundColor Green
Write-Host "==========================================================" -ForegroundColor Green
