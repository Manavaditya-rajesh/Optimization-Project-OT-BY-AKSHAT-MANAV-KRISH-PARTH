import type { Instance, Offering, TEvent } from '../types';

// Demo department used when the Python server is not running (offline demo data): 2 divisions, 5 rooms, 10 faculty.

// Same department as the backend's demo (api/bridge.py demo_problem): own professor first, then a qualified backup.
const subjects: { code: string; subject: string; type: 'theory' | 'lab'; sessions: number; faculty: string[] }[] = [
  { code: 'OT', subject: 'Optimization Techniques', type: 'theory', sessions: 3, faculty: ['f1', 'f5'] },
  { code: 'PC', subject: 'Parallel Computing', type: 'theory', sessions: 3, faculty: ['f2', 'f3'] },
  { code: 'PC LAB', subject: 'Parallel Computing Lab', type: 'lab', sessions: 1, faculty: ['f3', 'f2'] },
  { code: 'ML LAB', subject: 'Machine Learning Lab', type: 'lab', sessions: 1, faculty: ['f4', 'f5'] },
  { code: 'ML', subject: 'Machine Learning', type: 'theory', sessions: 3, faculty: ['f5', 'f4'] },
  { code: 'SE', subject: 'Software Engineering', type: 'theory', sessions: 3, faculty: ['f6', 'f8'] },
  { code: 'CN', subject: 'Computer Networking', type: 'theory', sessions: 3, faculty: ['f7', 'f9'] },
  { code: 'HCI', subject: 'Human-Computer Interaction', type: 'theory', sessions: 2, faculty: ['f8', 'f6'] },
  { code: 'OS', subject: 'Operating Systems', type: 'theory', sessions: 3, faculty: ['f9', 'f7'] },
  { code: 'PHY', subject: 'Physics', type: 'theory', sessions: 2, faculty: ['f10'] },
];

const groups = [
  { id: 'gA', name: 'SY-Comp Div A', strength: 58 },
  { id: 'gB', name: 'SY-Comp Div B', strength: 52 },
];

const offerings: Offering[] = [];
const events: TEvent[] = [];

for (const g of groups) {
  for (const s of subjects) {
    const id = `${g.id}-${s.code.replace(/\s/g, '')}`;
    offerings.push({
      id,
      subject: s.subject,
      code: s.code,
      groupIds: [g.id],
      type: s.type,
      sessionsPerWeek: s.sessions,
      eligibleFaculty: s.faculty,
    });
    for (let i = 0; i < s.sessions; i++) {
      events.push({ id: `${id}-${i + 1}`, offeringId: id, length: s.type === 'lab' ? 2 : 1, headcount: g.strength });
    }
  }
}

export const mockInstance: Instance = {
  name: 'SY Computer Engineering — Semester III',
  grid: {
    days: ['Mon', 'Tue', 'Wed', 'Thu', 'Fri'],
    periods: ['9:00 - 10:00', '10:00 - 11:00', '11:00 - 12:00', '12:00 - 1:00', '1:00 - 2:00', '2:00 - 3:00', '3:00 - 4:00', '4:00 - 5:00'],
    lunchPeriod: 4,
  },
  groups,
  faculty: [
    { id: 'f1', name: 'Prof. Kulal', maxWeekly: 12, maxDaily: 3 },
    { id: 'f2', name: 'Prof. Sase', maxWeekly: 10, maxDaily: 3 },
    { id: 'f3', name: 'Prof. Pratik', maxWeekly: 6, maxDaily: 3 },
    { id: 'f4', name: 'Prof. Anushka', maxWeekly: 6, maxDaily: 3 },
    { id: 'f5', name: 'Prof. Shrawne', maxWeekly: 12, maxDaily: 3 },
    { id: 'f6', name: 'Prof. Shirole', maxWeekly: 10, maxDaily: 3 },
    { id: 'f7', name: 'Prof. Chandane', maxWeekly: 8, maxDaily: 3 },
    { id: 'f8', name: 'Prof. Khedkar', maxWeekly: 8, maxDaily: 3 },
    { id: 'f9', name: 'Prof. Kolte', maxWeekly: 10, maxDaily: 3 },
    { id: 'f10', name: 'Prof. Wavhal', maxWeekly: 6, maxDaily: 2 },
  ],
  rooms: [
    { id: 'r1', name: 'CR-101', capacity: 60, type: 'classroom' },
    { id: 'r2', name: 'CR-102', capacity: 72, type: 'classroom' },
    { id: 'r3', name: 'LH-201', capacity: 120, type: 'classroom' },
    { id: 'r4', name: 'Lab A-301', capacity: 64, type: 'lab' },
    { id: 'r5', name: 'Lab B-302', capacity: 70, type: 'lab' },
  ],
  offerings,
  events,
};
