# Graded TPMS Lattice Designer

**Live:** https://graded-tpms-designer.hpang05.workers.dev

A single-page browser tool for designing graded TPMS lattices (gyroid, Schwarz P, Diamond) in a given part shape and load case. It checks each design with a quick voxel FE in the browser and exports a closed mesh (3MF or STL) for 3D printing. Nothing needs to be installed: open the HTML file in Chrome, Edge, Firefox or Safari (WebGL2 is needed for the 3D view).

## Files
| File | What it is |
|---|---|
| `gyroid_designer.html` | The page source (no `<html>`/`<head>` wrapper). |
| `index.html` | The same page as a full document, written by `make_local.py`. The website serves it; you can also double-click it to run locally. |
| `fe_core.js` | The FE solver: voxel bricks with incompatible modes, matrix-free PCG with a geometric-multigrid preconditioner (Jacobi as a fallback). It runs in a Web Worker in the page and in node for validation. |
| `mg_test.js` | Node check of the multigrid preconditioner against plain Jacobi on synthetic beams. |
| `fe_validate.js` | Node script that runs `fe_core.js` on a voxel mesh exported from our Abaqus pipeline (`*_solid.npy`). |
| `preload_fe.json` | FE results solved in advance: K, mass, energy deviation, energy map, displacement and energy fields (2 mm grid), plus the FE-redesign histories. |
| `make_local.py` | Copies `fe_core.js` and `preload_fe.json` into the page, then writes `index.html`. Run it after any edit, then commit; every push to `main` redeploys the site. |

## What the page does
- **Part:** box/beam, cube, cylinder and cone (both lying along x), sphere, torus.
- **Lattice:** network or sheet, with optional skin and solid pads. The total solid fraction is held by one global level shift.
- **Density:** a formula ρ(x, y, z, r, u, v, w, d, s) mapped to the level set through an exact volume-fraction table per TPMS type.
- **Cells:**
  - a size formula with stretch per axis;
  - fmin/fmax driven by the beam-theory stress;
  - the 7-number M2 "nodes" field with a Nelder–Mead search.
  - The phase-Jacobian rules (cell range, det ≥ 0.3, aspect cap) are checked.
- **Load cases:** 3-point, 4-point, cantilever, with positions you choose.
- **Quick FE:** PLA E = 2900 MPa, ν = 0.36, rigid-roller contact, K = reaction / 0.1 mm.
  - It shows the energy-per-gram map, its deviation, the deformed shape (scaled) and the FE energy as colour.
- **FE redesign:** the energy-per-gram loop ρ ← clamp(ρ (w/w̄)^η, ρmin, ρmax) on 28 × 12 x–z boxes, with an optional holes step.
  - The grid total is held every step, so ρmax is the real local cap. Holes are made only while the open boxes can still carry the mass under the cap.
  - Check the "Local ρ" readout: it is the solid fraction after the global mass shift, and it must stay at or below the cap.
- **Export:** 3MF (welded, deflated) or binary STL, plus the design as JSON and all FE numbers as CSV.
  - Loose pieces are removed before meshing (only the largest solid body is kept), and the mesh is checked to be closed.
  - The export also reports the share of the solid in walls thinner than two mesh voxels (a printability hint).
- **Hole edges:**
  - By default a hole blends into its neighbours, so the walls taper.
  - *Sharp hole edges* cuts each hole cleanly instead, with an optional lining wall.
  - Clean cuts cost stiffness because of the truncated-cell boundary effect: 3-point gyroid 272 vs 340 N/mm with tapered holes. The page footnote and the 11-11 journal have the full table.
  - PNG figures: the 3D view at 2× resolution (Side + Ortho gives the paper-style side view), plus the energy map and the density map.
- **View finish:** *Studio* (chrome studio-strip reflections, floor shadow) or *Matte* (flat, for figures).
- **FE checks:** before a run the page counts how much of the material stays in one piece at the chosen voxel size; below 70 % it does not solve and offers 0.5 mm voxels (sheet walls under 1 mm need it).

The equations are listed in the page's **Method** section.

## Accuracy (quick FE)
- **Against Abaqus C3D8I on the identical 0.5 mm voxel mesh (CU beam):** 432.8 vs 415.2 N/mm, +4.2 %.
- **Voxel size:** 1 mm is within about 1 % of 0.5 mm for 7 mm gyroid cells.
- **Where 1 mm misleads:**
  - it reads about 17 % stiff for Schwarz P (thin necks);
  - it reads 4–5 % stiff for redesigned beams with 0.2-density webs;
  - it reads 9–14 % soft for stretched M2 cells.
- Use 0.5 mm before quoting a number.

## Solver speed (one worker, 168 × 16 × 24 beam)
| Voxel | Jacobi PCG | Multigrid PCG |
|---|---|---|
| 1 mm | about 2000 iterations, 25–45 s | about 80 iterations, about 5 s |
| 0.5 mm | about 3500 iterations, 8–14 min | about 60 iterations, about 30 s |

K agrees within 0.03 % on every stored example. On the exact 0.5 mm Abaqus voxel mesh of the CU beam (258k elements) multigrid gives K = 432.8 N/mm in 161 iterations, 56 s; Jacobi gave the same 432.8 in 4022 iterations, 587 s (Abaqus C3D8I: 415.2). Run it with `MG=1 node fe_validate.js CU_R3_it06_p0`.

## Rebuild after editing
```
python make_local.py
```

## Re-run the stored FE results
1. Serve the folder, for example `python -m http.server 8765`, and open `http://localhost:8765/index.html`.
   - Use a normal browser tab or headless Chromium. Some embedded browser panes throttle Web Workers.
2. In the console:
   - `__ggd.precompute([[preset, voxel_mm, iteration?], …], workers)` stores its results in `window.__pre`.
   - `__ggd.precomputeOpt([preset, …], iterations)` stores its results in `window.__opt`.
3. Save the results into `preload_fe.json` (merge them into its `list` and `opt` entries), then run `make_local.py`.

Keep the total number of workers at or below the number of physical cores you want to use.

## Main results stored in the page (0.5 mm FE, local ρ ≤ 0.7)
| Load | uniform 7 mm gyroid | density redesign | + holes | M2 cells + redesign + holes |
|---|---|---|---|---|
| 3-point, 168 × 16 × 24, 40 g | 153.8 | 303.8 (×1.94) | 340.0 (×2.15) | 453.3 (×2.90) |
| 4-point | 217.1 | 426.8 (×1.92) | 467.3 (×2.10) | 644.1 (×2.92) |
| cantilever 120 mm, 28.6 g | 21.0 | 42.4 (×1.99) | 41.6 (×1.98) | 61.4 (×2.93) |

K in N/mm; × is K per gram against the uniform beam of the same load. Open an example directly with `#name`, for example `#optM2`, `#optM2_4`, `#optM2_C`.
