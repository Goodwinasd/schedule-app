# Graph Report - .  (2026-07-26)

## Corpus Check
- Corpus is ~21,366 words - fits in a single context window. You may not need a graph.

## Summary
- 103 nodes · 104 edges · 27 communities (4 shown, 23 thin omitted)
- Extraction: 100% EXTRACTED · 0% INFERRED · 0% AMBIGUOUS
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- Community 0
- Community 1
- Community 2
- Community 3
- Community 4
- Community 5
- Community 6
- Community 7
- Community 8
- Community 9
- Community 10
- Community 11
- Community 12
- Community 13
- Community 14
- Community 15
- Community 16
- Community 17
- Community 18
- Community 19
- Community 20
- Community 21
- Community 22
- Community 23
- Community 24
- Community 25
- Community 26

## God Nodes (most connected - your core abstractions)
1. `main` - 51 edges
2. `navigation` - 11 edges
3. `ui` - 11 edges
4. `escapeHtml` - 10 edges
5. `api` - 8 edges
6. `toISODate` - 7 edges
7. `getMonday` - 5 edges
8. `addDays` - 4 edges
9. `getWeekNumber` - 4 edges
10. `getweekslist` - 4 edges

## Surprising Connections (you probably didn't know these)
- `loadhealthtab` --calls--> `escapeHtml`  [EXTRACTED]
  schedule-app/static/js/modules/ui.js → schedule-app/static/js/modules/utils.js
- `loadsettingstab` --calls--> `escapeHtml`  [EXTRACTED]
  schedule-app/static/js/modules/ui.js → schedule-app/static/js/modules/utils.js
- `renderavailtable` --calls--> `toISODate`  [EXTRACTED]
  schedule-app/static/js/modules/ui.js → schedule-app/static/js/modules/utils.js
- `loadhealthtab` --calls--> `api`  [EXTRACTED]
  schedule-app/static/js/modules/ui.js → schedule-app/static/js/modules/api.js
- `loadsettingstab` --calls--> `api`  [EXTRACTED]
  schedule-app/static/js/modules/ui.js → schedule-app/static/js/modules/api.js

## Import Cycles
- None detected.

## Communities (27 total, 23 thin omitted)

### Community 0 - "Community 0"
Cohesion: 0.04
Nodes (48): main, addGroup, addLesson, addRefItem, addSubgroupLesson, addSubject, addWeek, advanceCourses (+40 more)

### Community 1 - "Community 1"
Cohesion: 0.30
Nodes (14): getweekslist, availsetactiveweek, getweekslist, renderavailcarousel, navigation, ui, addDays, formatChipRange (+6 more)

### Community 2 - "Community 2"
Cohesion: 0.20
Nodes (10): init, loadhealthtab, loadsettingstab, loadtrashtab, api, auth, updateUI, closeModals (+2 more)

### Community 3 - "Community 3"
Cohesion: 0.25
Nodes (8): makecard, populatesubjectteacherselect, renderavailtable, renderscheduletable, rendertrashsection, renderwarnings, escapeHtml, shiftLabel

## Knowledge Gaps
- **78 isolated node(s):** `checkAuth`, `login`, `logout`, `updateUI`, `goHome` (+73 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **23 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `main` connect `Community 0` to `Community 2`?**
  _High betweenness centrality (0.509) - this node is a cross-community bridge._
- **Why does `api` connect `Community 2` to `Community 0`, `Community 1`?**
  _High betweenness centrality (0.219) - this node is a cross-community bridge._
- **Why does `navigation` connect `Community 1` to `Community 2`, `Community 3`?**
  _High betweenness centrality (0.132) - this node is a cross-community bridge._
- **What connects `checkAuth`, `login`, `logout` to the rest of the system?**
  _78 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Community 0` be split into smaller, more focused modules?**
  _Cohesion score 0.041666666666666664 - nodes in this community are weakly interconnected._