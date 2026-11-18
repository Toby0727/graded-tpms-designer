// fe_core.js — quick linear-elastic voxel FE for the Graded Gyroid Designer (also runs in node for validation).
// Same model as WIP\11-1\fe\build_linear_inp.py (our Abaqus linear check):
//   brick elements = voxels, C3D8I-type (8 nodes + 9 incompatible bubble modes, condensed out), PLA E = 2900 MPa, nu = 0.36;
//   load: within +-strip of each load x, the top node of each x-y column that lies within one voxel of the highest one
//   (a rigid roller; on a flat face = the top-face nodes) gets u_z = -delta; supports: the same with the lowest nodes, u_z = 0, the first support also u_x = 0, one node per support u_y = 0 (cantilever: all nodes at the fixed
//   end face fully fixed); K = |sum of reaction z on the load nodes| / delta. Only the largest face-connected piece is kept.
// Solver: matrix-free preconditioned conjugate gradients, element-by-element with one shared element matrix. Preconditioner:
//   Jacobi, or (P.mg) a geometric multigrid V-cycle on rediscretised 2x/4x/8x coarse bricks (about 5x faster at 1 mm, 20x at 0.5 mm).
'use strict';

function feKe(ax, ay, az, E, nu) {
  // D (engineering shear strains: xx, yy, zz, xy, yz, zx)
  const lam = E * nu / ((1 + nu) * (1 - 2 * nu)), mu = E / (2 * (1 + nu));
  const D = [[lam + 2 * mu, lam, lam, 0, 0, 0], [lam, lam + 2 * mu, lam, 0, 0, 0], [lam, lam, lam + 2 * mu, 0, 0, 0],
             [0, 0, 0, mu, 0, 0], [0, 0, 0, 0, mu, 0], [0, 0, 0, 0, 0, mu]];
  const S = [[-1, -1, -1], [1, -1, -1], [1, 1, -1], [-1, 1, -1], [-1, -1, 1], [1, -1, 1], [1, 1, 1], [-1, 1, 1]];
  const g = 1 / Math.sqrt(3), jx = ax / 2, jy = ay / 2, jz = az / 2, detJ = jx * jy * jz;
  const Kuu = new Float64Array(576), Kua = new Float64Array(24 * 9), Kaa = new Float64Array(81);
  const strainB = (dx, dy, dz) => [[dx, 0, 0], [0, dy, 0], [0, 0, dz], [dy, dx, 0], [0, dz, dy], [dz, 0, dx]]; // 6x3 for one node / mode
  for (const xi of [-g, g]) for (const et of [-g, g]) for (const ze of [-g, g]) {
    const Bu = [], Ba = [];
    for (let a = 0; a < 8; a++) {
      const [sx, sy, sz] = S[a];
      const dx = sx * (1 + sy * et) * (1 + sz * ze) / 8 / jx, dy = sy * (1 + sx * xi) * (1 + sz * ze) / 8 / jy, dz = sz * (1 + sx * xi) * (1 + sy * et) / 8 / jz;
      Bu.push(strainB(dx, dy, dz));
    }
    // incompatible modes: G1 = 1 - xi^2, G2 = 1 - eta^2, G3 = 1 - zeta^2, one per displacement component (9 dof)
    const dG = [[-2 * xi / jx, 0, 0], [0, -2 * et / jy, 0], [0, 0, -2 * ze / jz]];
    for (let m = 0; m < 3; m++) Ba.push(strainB(dG[m][0], dG[m][1], dG[m][2]));
    const col = (B, n, c) => { const v = new Array(6); for (let r = 0; r < 6; r++) v[r] = B[n][r][c]; return v; };
    const DB = v => D.map(row => row.reduce((s, d, k) => s + d * v[k], 0));
    const U = [], A = [];
    for (let a = 0; a < 8; a++) for (let c = 0; c < 3; c++) U.push(col(Bu, a, c));
    for (let m = 0; m < 3; m++) for (let c = 0; c < 3; c++) A.push(col(Ba, m, c));
    const DU = U.map(DB), DA = A.map(DB);
    const dot = (p, q) => p[0] * q[0] + p[1] * q[1] + p[2] * q[2] + p[3] * q[3] + p[4] * q[4] + p[5] * q[5];
    for (let i = 0; i < 24; i++) { for (let j = 0; j < 24; j++) Kuu[i * 24 + j] += dot(U[i], DU[j]) * detJ; for (let j = 0; j < 9; j++) Kua[i * 9 + j] += dot(U[i], DA[j]) * detJ; }
    for (let i = 0; i < 9; i++) for (let j = 0; j < 9; j++) Kaa[i * 9 + j] += dot(A[i], DA[j]) * detJ;
  }
  // Ke = Kuu - Kua Kaa^-1 Kau  (Kaa is symmetric positive definite: Gauss-Jordan inverse)
  const n = 9, M = Array.from({ length: n }, (_, i) => { const r = new Float64Array(2 * n); for (let j = 0; j < n; j++) r[j] = Kaa[i * n + j]; r[n + i] = 1; return r; });
  for (let c = 0; c < n; c++) {
    let p = c; for (let r = c + 1; r < n; r++) if (Math.abs(M[r][c]) > Math.abs(M[p][c])) p = r;
    [M[c], M[p]] = [M[p], M[c]];
    const d = M[c][c]; for (let j = 0; j < 2 * n; j++) M[c][j] /= d;
    for (let r = 0; r < n; r++) if (r !== c) { const f = M[r][c]; if (f) for (let j = 0; j < 2 * n; j++) M[r][j] -= f * M[c][j]; }
  }
  const Ke = new Float64Array(576);
  for (let i = 0; i < 24; i++) for (let j = 0; j < 24; j++) {
    let s = 0; for (let a = 0; a < 9; a++) { let t = 0; for (let b = 0; b < 9; b++) t += M[a][n + b] * Kua[j * 9 + b]; s += Kua[i * 9 + a] * t; }
    Ke[i * 24 + j] = Kuu[i * 24 + j] - s;
  }
  return Ke;
}

// P: { nx, ny, nz, ax, ay, az, x0, y0, z0, occ: Uint8Array(nx*ny*nz) index i + nx*(j + ny*k),
//      E, nu, delta, loads: [x...], sups: [x...], fixX: number|null, strip, tol, maxit }
function feSolve(P, onProgress) {
  const { nx, ny, nz, ax, ay, az, x0, y0, z0 } = P, occ = P.occ, NV = nx * ny * nz;
  const E = P.E || 2900, nu = P.nu == null ? 0.36 : P.nu, delta = P.delta || 0.1, strip = P.strip == null ? 1.0 : P.strip;
  const tol = P.tol || 1e-6, maxit = P.maxit || 20000;
  // 1. largest face-connected piece
  const lab = new Int32Array(NV).fill(-1), queue = new Int32Array(NV); let best = -1, bestN = 0, nlab = 0, nSolid = 0;
  for (let v = 0; v < NV; v++) {
    if (!occ[v] || lab[v] >= 0) continue;
    let qh = 0, qt = 0; queue[qt++] = v; lab[v] = nlab; let cnt = 0;
    while (qh < qt) {
      const c = queue[qh++]; cnt++;
      const i = c % nx, j = ((c / nx) | 0) % ny, k = (c / (nx * ny)) | 0;
      const nb = [i > 0 ? c - 1 : -1, i < nx - 1 ? c + 1 : -1, j > 0 ? c - nx : -1, j < ny - 1 ? c + nx : -1, k > 0 ? c - nx * ny : -1, k < nz - 1 ? c + nx * ny : -1];
      for (const d of nb) if (d >= 0 && occ[d] && lab[d] < 0) { lab[d] = nlab; queue[qt++] = d; }
    }
    nSolid += cnt; if (cnt > bestN) { bestN = cnt; best = nlab; } nlab++;
  }
  if (best < 0) throw new Error('No solid voxels.');
  // 2. elements and used nodes
  const NX = nx + 1, NY = ny + 1, NN = NX * NY * (nz + 1);
  const nodeId = new Int32Array(NN).fill(-1), ne = bestN, conn = new Int32Array(ne * 8), evox = new Int32Array(ne);
  const off = [[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0], [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1]];
  let nn = 0, e = 0;
  for (let v = 0; v < NV; v++) {
    if (lab[v] !== best) continue;
    const i = v % nx, j = ((v / nx) | 0) % ny, k = (v / (nx * ny)) | 0;
    for (let a = 0; a < 8; a++) {
      const g = (i + off[a][0]) + NX * ((j + off[a][1]) + NY * (k + off[a][2]));
      if (nodeId[g] < 0) nodeId[g] = nn++;
      conn[e * 8 + a] = nodeId[g];
    }
    evox[e++] = v;
  }
  const nxyz = new Float64Array(nn * 3);
  for (let g = 0; g < NN; g++) { const id = nodeId[g]; if (id < 0) continue; const i = g % NX, j = ((g / NX) | 0) % NY, k = (g / (NX * NY)) | 0;
    nxyz[3 * id] = x0 + i * ax; nxyz[3 * id + 1] = y0 + j * ay; nxyz[3 * id + 2] = z0 + k * az; }
  // 3. boundary conditions
  const nd = nn * 3, fixed = new Uint8Array(nd), uP = new Float64Array(nd);
  // contact like a rigid roller: inside the strip take the top (load) or bottom (support) node of every x-y column,
  // and keep the columns whose top lies within one voxel of the highest point the roller meets. On a flat face this is
  // exactly the top / bottom face set of build_linear_inp.py; on an open lattice face the roller rests on the highest struts.
  const xt = strip + 1e-6, colKey = id => Math.round((nxyz[3 * id] - x0) / ax) + NX * Math.round((nxyz[3 * id + 1] - y0) / ay);
  function contact(xc, top) {
    const col = new Map();
    for (let id = 0; id < nn; id++) {
      if (Math.abs(nxyz[3 * id] - xc) > xt) continue;
      const k = colKey(id), z = nxyz[3 * id + 2], c = col.get(k);
      if (c === undefined || (top ? z > nxyz[3 * c + 2] : z < nxyz[3 * c + 2])) col.set(k, id);
    }
    if (!col.size) return [];
    let ext = top ? -1e30 : 1e30; for (const id of col.values()) { const z = nxyz[3 * id + 2]; ext = top ? Math.max(ext, z) : Math.min(ext, z); }
    const out = []; for (const id of col.values()) if (Math.abs(nxyz[3 * id + 2] - ext) <= 1.01 * az) out.push(id);
    return out;
  }
  const loadN = [], supN = P.sups.map(xs => contact(xs, false));
  for (const xl of P.loads) for (const id of contact(xl, true)) loadN.push(id);
  const thin = bestN < 0.9 * nSolid ? ` At ${ax.toFixed(2)} mm voxels the walls break into pieces (the largest keeps ${(100 * bestN / nSolid).toFixed(0)} % of the material); pick a finer FE voxel size or thicker walls.` : '';
  if (!loadN.length) throw new Error('No connected material within ±' + strip.toFixed(1) + ' mm of the load position.' + (thin || ' Move the load onto the part.'));
  for (const id of loadN) { fixed[3 * id + 2] = 1; uP[3 * id + 2] = -delta; }
  if (P.fixX != null) {
    let nfix = 0;
    for (let id = 0; id < nn; id++) if (nxyz[3 * id] <= P.fixX + 1e-6 + 0.01 * ax) { fixed[3 * id] = fixed[3 * id + 1] = fixed[3 * id + 2] = 1; nfix++; }
    if (!nfix) throw new Error('No material at the fixed end.');
  } else {
    supN.forEach((ids, s) => {
      if (!ids.length) throw new Error('No connected material within ±' + strip.toFixed(1) + ' mm of support ' + (s + 1) + '.' + (thin || ' Move the support under the part.'));
      for (const id of ids) { fixed[3 * id + 2] = 1; if (s === 0) fixed[3 * id] = 1; }
      let bi = ids[0], bd = 1e30; for (const id of ids) { const d = Math.abs(nxyz[3 * id + 1]) + Math.abs(nxyz[3 * id] - P.sups[s]); if (d < bd) { bd = d; bi = id; } }
      fixed[3 * bi + 1] = 1;
    });
  }
  // 4. PCG on the free dofs
  const Ke = feKe(ax, ay, az, E, nu);
  const diag = new Float64Array(nd);
  // optional modulus scale per voxel (P.escale, E_voxel / E): two-material parts such as a solid skin around a soft core
  const es = new Float64Array(ne).fill(1); if (P.escale) for (let q = 0; q < ne; q++) es[q] = P.escale[evox[q]];
  for (let q = 0; q < ne; q++) for (let a = 0; a < 8; a++) { const b = conn[q * 8 + a] * 3; for (let c = 0; c < 3; c++) diag[b + c] += es[q] * Ke[(3 * a + c) * 25]; }
  const xe = new Float64Array(24), dofs = new Int32Array(24);
  function matvec(x, y) {
    y.fill(0);
    for (let q = 0; q < ne; q++) {
      const cb = q * 8;
      for (let a = 0; a < 8; a++) { const b = conn[cb + a] * 3; dofs[3 * a] = b; dofs[3 * a + 1] = b + 1; dofs[3 * a + 2] = b + 2; }
      for (let r = 0; r < 24; r++) xe[r] = x[dofs[r]];
      const eq = es[q]; for (let r = 0; r < 24; r++) { let s = 0; const ro = r * 24; for (let c = 0; c < 24; c++) s += Ke[ro + c] * xe[c]; y[dofs[r]] += eq * s; }
    }
  }
  // ---- optional geometric multigrid preconditioner (P.mg) ------------------------------------------------------------
  // Coarse levels by rediscretisation: 2 x 2 x 2 voxel blocks become one brick of twice the size whose stiffness is scaled
  // by the block's solid fraction. Trilinear prolongation P, restriction P^T, damped Jacobi smoothing (same steps before
  // and after, so the V-cycle is symmetric and can precondition CG). It removes the smooth bending error that Jacobi
  // alone removes very slowly.
  let precond = null;
  if (P.mg) {
    const NZ0 = nz + 1, levels = [], W = P.mgW || 0.4, NU = P.mgNu || 1;
    const axisT = F => { const i0 = new Int32Array(F), i1 = new Int32Array(F), w1 = new Float64Array(F);
      for (let n = 0; n < F; n++) { i0[n] = n >> 1; if (n & 1) { i1[n] = (n >> 1) + 1; w1[n] = 0.5; } else { i1[n] = n >> 1; w1[n] = 0; } } return { i0, i1, w1 }; };
    let vx = nx, vy = ny, vz = nz, frac = new Float32Array(nx * ny * nz);
    for (let q = 0; q < ne; q++) frac[evox[q]] = es[q];
    let prevFix = new Uint8Array(NN * 3);
    for (let g = 0; g < NN; g++) { const id = nodeId[g]; if (id < 0) continue; for (let c = 0; c < 3; c++) if (fixed[3 * id + c]) prevFix[3 * g + c] = 1; }
    let prevN = [NX, NY, NZ0], sx = ax, sy = ay, sz = az;
    while (levels.length < (P.mgLevels || 4) && Math.min(vx, vy, vz) > 2) {
      const cx = Math.ceil(vx / 2), cy = Math.ceil(vy / 2), cz = Math.ceil(vz / 2), cf = new Float32Array(cx * cy * cz);
      for (let k = 0; k < vz; k++) for (let j = 0; j < vy; j++) for (let i = 0; i < vx; i++) { const f = frac[i + vx * (j + vy * k)]; if (f) cf[(i >> 1) + cx * ((j >> 1) + cy * (k >> 1))] += f / 8; }
      sx *= 2; sy *= 2; sz *= 2;
      const KeL = feKe(sx, sy, sz, E, nu), CX = cx + 1, CY = cy + 1, CZ = cz + 1, NNc = CX * CY * CZ;
      const el = [], ef = []; for (let e = 0; e < cf.length; e++) if (cf[e] > 0) { el.push(e); ef.push(cf[e]); }
      const cn = new Int32Array(el.length * 8);
      for (let q = 0; q < el.length; q++) { const e = el[q], i = e % cx, j = ((e / cx) | 0) % cy, k = (e / (cx * cy)) | 0;
        for (let a = 0; a < 8; a++) cn[q * 8 + a] = (i + off[a][0]) + CX * ((j + off[a][1]) + CY * (k + off[a][2])); }
      const act = new Uint8Array(NNc); for (let q = 0; q < cn.length; q++) act[cn[q]] = 1;
      const [FX, FY, FZ] = prevN, fixC = new Uint8Array(NNc * 3), tX = axisT(FX), tY = axisT(FY), tZ = axisT(FZ);
      for (let k = 0; k < FZ; k++) for (let j = 0; j < FY; j++) for (let i = 0; i < FX; i++) { const g = i + FX * (j + FY * k);
        for (let c = 0; c < 3; c++) if (prevFix[3 * g + c]) for (const K of [tZ.i0[k], tZ.i1[k]]) for (const J of [tY.i0[j], tY.i1[j]]) for (const I of [tX.i0[i], tX.i1[i]]) fixC[3 * (I + CX * (J + CY * K)) + c] = 1; }
      const dg = new Float64Array(NNc * 3);
      for (let q = 0; q < el.length; q++) for (let a = 0; a < 8; a++) { const b = cn[q * 8 + a] * 3; for (let c = 0; c < 3; c++) dg[b + c] += ef[q] * KeL[(3 * a + c) * 25]; }
      levels.push({ N: [CX, CY, CZ], NN: NNc, Ke: KeL, conn: cn, f: Float64Array.from(ef), act, fix: fixC, diag: dg, fineN: prevN, tX, tY, tZ });
      prevN = [CX, CY, CZ]; prevFix = fixC; frac = cf; vx = cx; vy = cy; vz = cz;
    }
    const xeL = new Float64Array(24);
    const mvL = (L, x, y) => { y.fill(0); const K = L.Ke, cn = L.conn, f = L.f;
      for (let q = 0; q < f.length; q++) { const cb = q * 8;
        for (let a = 0; a < 8; a++) { const b = cn[cb + a] * 3; xeL[3 * a] = x[b]; xeL[3 * a + 1] = x[b + 1]; xeL[3 * a + 2] = x[b + 2]; }
        for (let r = 0; r < 24; r++) { let s = 0; const ro = r * 24; for (let c = 0; c < 24; c++) s += K[ro + c] * xeL[c]; y[cn[cb + ((r / 3) | 0)] * 3 + (r % 3)] += f[q] * s; } } };
    const clampL = (L, v) => { for (let g = 0; g < L.NN; g++) for (let c = 0; c < 3; c++) if (!L.act[g] || L.fix[3 * g + c]) v[3 * g + c] = 0; };
    // transfer between coarse level L and its finer lattice: yf += P xc (prolong), rc = P^T rf (restrict)
    const transfer = (L, src, dst, up) => { const [FX, FY, FZ] = L.fineN, [CX, CY] = L.N, tX = L.tX, tY = L.tY, tZ = L.tZ;
      for (let k = 0; k < FZ; k++) { const k0 = tZ.i0[k], k1 = tZ.i1[k], wk1 = tZ.w1[k], wk0 = 1 - wk1;
        for (let j = 0; j < FY; j++) { const j0 = tY.i0[j], j1 = tY.i1[j], wj1 = tY.w1[j], wj0 = 1 - wj1;
          for (let i = 0; i < FX; i++) { const i0 = tX.i0[i], i1 = tX.i1[i], wi1 = tX.w1[i], wi0 = 1 - wi1, gf = 3 * (i + FX * (j + FY * k));
            if (!up && !src[gf] && !src[gf + 1] && !src[gf + 2]) continue;
            for (let t = 0; t < 8; t++) {
              const I = t & 1 ? i1 : i0, J = t & 2 ? j1 : j0, K = t & 4 ? k1 : k0, w = (t & 1 ? wi1 : wi0) * (t & 2 ? wj1 : wj0) * (t & 4 ? wk1 : wk0);
              if (!w) continue; const gc = 3 * (I + CX * (J + CY * K));
              if (up) { dst[gf] += w * src[gc]; dst[gf + 1] += w * src[gc + 1]; dst[gf + 2] += w * src[gc + 2]; }
              else { dst[gc] += w * src[gf]; dst[gc + 1] += w * src[gf + 1]; dst[gc + 2] += w * src[gf + 2]; } } } } } };
    const vcycle = (l, rhs) => { // l = 1 … levels.length, dense vectors on the level's node lattice
      const L = levels[l - 1], n = L.NN * 3, e = new Float64Array(n), t = new Float64Array(n);
      const smooth = (m, zero) => { for (let s = 0; s < m; s++) { if (zero && s === 0) t.fill(0); else mvL(L, e, t); for (let i = 0; i < n; i++) if (L.diag[i] > 0) e[i] += W * (rhs[i] - t[i]) / L.diag[i]; clampL(L, e); } };   // e starts at 0: the first product is 0
      if (l === levels.length) { smooth(40, true); return e; }
      smooth(NU, true); mvL(L, e, t); for (let i = 0; i < n; i++) t[i] = rhs[i] - t[i]; clampL(L, t);
      const C = levels[l], rc = new Float64Array(C.NN * 3); transfer(C, t, rc, false); clampL(C, rc);
      const ec = vcycle(l + 1, rc), ep = new Float64Array(n); transfer(C, ec, ep, true); for (let i = 0; i < n; i++) e[i] += ep[i]; clampL(L, e);
      smooth(NU); return e;
    };
    if (P.mgTest && levels.length) { // compare R A_h P x with A_c x for a smooth x on level 1
      const L1 = levels[0], xc = new Float64Array(L1.NN * 3); for (let g = 0; g < L1.NN; g++) { const i = g % L1.N[0]; xc[3 * g + 2] = Math.sin(i / L1.N[0] * 3.1416); xc[3 * g] = 0.3 * Math.cos(i / L1.N[0] * 3.1416); }
      const xf = new Float64Array(NN * 3); transfer(L1, xc, xf, true); const xcmp = new Float64Array(nd); for (let g = 0; g < NN; g++) { const id = nodeId[g]; if (id >= 0) for (let c = 0; c < 3; c++) xcmp[3 * id + c] = xf[3 * g + c]; }
      const yf = new Float64Array(nd); matvec(xcmp, yf); const yd = new Float64Array(NN * 3); for (let g = 0; g < NN; g++) { const id = nodeId[g]; if (id >= 0) for (let c = 0; c < 3; c++) yd[3 * g + c] = yf[3 * id + c]; }
      const y1 = new Float64Array(L1.NN * 3); transfer(L1, yd, y1, false); const y2 = new Float64Array(L1.NN * 3); mvL(L1, xc, y2);
      let n1 = 0, n2 = 0, d = 0; for (let i = 0; i < y1.length; i++) { n1 += y1[i] * y1[i]; n2 += y2[i] * y2[i]; d += (y1[i] - y2[i]) ** 2; }
      console.log('mgTest |RAPx|', Math.sqrt(n1).toExponential(3), '|Acx|', Math.sqrt(n2).toExponential(3), 'rel diff', (Math.sqrt(d / n1)).toExponential(3), 'levels', levels.map(L => L.N.join('x')).join(' '));
    }
    if (levels.length) {
      const tf = new Float64Array(nd), rd = new Float64Array(NN * 3), ed = new Float64Array(NN * 3), L1 = levels[0], rc1 = new Float64Array(L1.NN * 3);
      precond = (rIn, e) => {
        e.fill(0);
        const sm = (m, zero) => { for (let s = 0; s < m; s++) { if (zero && s === 0) tf.fill(0); else matvec(e, tf); for (let i = 0; i < nd; i++) if (!fixed[i]) e[i] += W * (rIn[i] - tf[i]) / diag[i]; } };
        sm(NU, true); matvec(e, tf); rd.fill(0);
        for (let g = 0; g < NN; g++) { const id = nodeId[g]; if (id < 0) continue; for (let c = 0; c < 3; c++) if (!fixed[3 * id + c]) rd[3 * g + c] = rIn[3 * id + c] - tf[3 * id + c]; }
        rc1.fill(0); transfer(L1, rd, rc1, false); clampL(L1, rc1);
        const ec = vcycle(1, rc1); ed.fill(0); transfer(L1, ec, ed, true);
        for (let g = 0; g < NN; g++) { const id = nodeId[g]; if (id < 0) continue; for (let c = 0; c < 3; c++) if (!fixed[3 * id + c]) e[3 * id + c] += ed[3 * g + c]; }
        sm(NU);
      };
    }
  }
  const u = uP.slice(), r = new Float64Array(nd), z = new Float64Array(nd), p = new Float64Array(nd), Ap = new Float64Array(nd);
  // the stopping test is relative to the residual of the cold start (u = prescribed values only), so a warm start
  // stops at the same accuracy as a cold one
  matvec(u, r); let r0 = 0; for (let i = 0; i < nd; i++) if (!fixed[i]) r0 += r[i] * r[i]; r0 = Math.sqrt(r0);
  // warm start: a displacement field on the same node lattice (from the previous design in a redesign loop) as the first guess
  if (P.u0 && P.u0.length === NN * 3) { for (let g = 0; g < NN; g++) { const id = nodeId[g]; if (id < 0) continue; for (let c = 0; c < 3; c++) if (!fixed[3 * id + c]) u[3 * id + c] = P.u0[3 * g + c]; } matvec(u, r); }
  for (let i = 0; i < nd; i++) r[i] = fixed[i] ? 0 : -r[i];
  let rz = 0;
  if (precond) precond(r, z); else for (let i = 0; i < nd; i++) z[i] = fixed[i] ? 0 : r[i] / diag[i];
  for (let i = 0; i < nd; i++) { if (fixed[i]) z[i] = 0; p[i] = z[i]; rz += r[i] * z[i]; }
  let it = 0, rel = 1;
  const t0 = Date.now(); let tLast = t0;
  for (it = 1; it <= maxit; it++) {
    matvec(p, Ap);
    let pAp = 0; for (let i = 0; i < nd; i++) { if (fixed[i]) Ap[i] = 0; pAp += p[i] * Ap[i]; }
    const al = rz / pAp; let rr = 0, rzn = 0;
    for (let i = 0; i < nd; i++) { if (fixed[i]) continue; u[i] += al * p[i]; r[i] -= al * Ap[i]; rr += r[i] * r[i]; }
    if (precond) precond(r, z); else for (let i = 0; i < nd; i++) z[i] = fixed[i] ? 0 : r[i] / diag[i];
    for (let i = 0; i < nd; i++) { if (fixed[i]) { z[i] = 0; continue; } rzn += r[i] * z[i]; }
    rel = Math.sqrt(rr) / r0;
    if (rel < tol) break;
    const be = rzn / rz; rz = rzn;
    for (let i = 0; i < nd; i++) p[i] = fixed[i] ? 0 : z[i] + be * p[i];
    if (onProgress && Date.now() - tLast > 250) { tLast = Date.now(); onProgress({ it, rel, sec: (tLast - t0) / 1000 }); }
  }
  // 5. reaction on the load nodes, element energies
  matvec(u, Ap);
  let F = 0; for (const id of loadN) F += Ap[3 * id + 2];
  const energy = new Float32Array(ne); let Utot = 0;
  for (let q = 0; q < ne; q++) {
    for (let a = 0; a < 8; a++) { const b = conn[q * 8 + a] * 3; for (let c = 0; c < 3; c++) xe[3 * a + c] = u[b + c]; }
    let s = 0; for (let rr2 = 0; rr2 < 24; rr2++) { let t = 0; for (let c = 0; c < 24; c++) t += Ke[rr2 * 24 + c] * xe[c]; s += xe[rr2] * t; }
    energy[q] = 0.5 * es[q] * s; Utot += 0.5 * es[q] * s;
  }
  // 5b. optional element-centre stress (sxx, syy, szz, sxy, syz, szx) for the M2 evaluator: B at the centre (incompatible
  //     modes have zero gradient there), sigma = D eps
  let stress = null;
  if (P.wantStress) {
    stress = new Float32Array(ne * 6);
    const lam = E * nu / ((1 + nu) * (1 - 2 * nu)), mu = E / (2 * (1 + nu));
    const SG = [[-1, -1, -1], [1, -1, -1], [1, 1, -1], [-1, 1, -1], [-1, -1, 1], [1, -1, 1], [1, 1, 1], [-1, 1, 1]];
    for (let q = 0; q < ne; q++) {
      let exx = 0, eyy = 0, ezz = 0, gxy = 0, gyz = 0, gzx = 0;
      for (let a = 0; a < 8; a++) { const b = conn[q * 8 + a] * 3, dx = SG[a][0] / (4 * ax), dy = SG[a][1] / (4 * ay), dz = SG[a][2] / (4 * az), ux = u[b], uy = u[b + 1], uz = u[b + 2];
        exx += dx * ux; eyy += dy * uy; ezz += dz * uz; gxy += dy * ux + dx * uy; gyz += dz * uy + dy * uz; gzx += dz * ux + dx * uz; }
      const tr = lam * (exx + eyy + ezz), o = 6 * q, k = es[q];
      stress[o] = k * (tr + 2 * mu * exx); stress[o + 1] = k * (tr + 2 * mu * eyy); stress[o + 2] = k * (tr + 2 * mu * ezz); stress[o + 3] = k * mu * gxy; stress[o + 4] = k * mu * gyz; stress[o + 5] = k * mu * gzx;
    }
  }
  // 6. displacement on the full node lattice (NX x NY x NZ, 3 comps) for the deformed view; empty nodes are filled from
  //    their neighbours a few times so that trilinear sampling near the surface does not pull toward zero
  const NZ = nz + 1, disp = new Float32Array(NN * 3), have = new Uint8Array(NN);
  for (let g = 0; g < NN; g++) { const id = nodeId[g]; if (id < 0) continue; have[g] = 1; disp[3 * g] = u[3 * id]; disp[3 * g + 1] = u[3 * id + 1]; disp[3 * g + 2] = u[3 * id + 2]; }
  for (let pass = 0; pass < 6; pass++) {
    const add = [];
    for (let g = 0; g < NN; g++) {
      if (have[g]) continue;
      const i = g % NX, j = ((g / NX) | 0) % NY, k = (g / (NX * NY)) | 0; let n = 0, sx = 0, sy = 0, sz = 0;
      const nb = [i > 0 ? g - 1 : -1, i < NX - 1 ? g + 1 : -1, j > 0 ? g - NX : -1, j < NY - 1 ? g + NX : -1, k > 0 ? g - NX * NY : -1, k < NZ - 1 ? g + NX * NY : -1];
      for (const d of nb) if (d >= 0 && have[d] === 1) { n++; sx += disp[3 * d]; sy += disp[3 * d + 1]; sz += disp[3 * d + 2]; }
      if (n) add.push(g, sx / n, sy / n, sz / n);
    }
    for (let q = 0; q < add.length; q += 4) { const g = add[q]; disp[3 * g] = add[q + 1]; disp[3 * g + 1] = add[q + 2]; disp[3 * g + 2] = add[q + 3]; have[g] = 2; }
    for (let g = 0; g < NN; g++) if (have[g] === 2) have[g] = 1;
  }
  return { K: Math.abs(F) / delta, F, U: Utot, iters: it, rel, ne, nn, mg: !!precond, dropped: nSolid - bestN, evox, energy, loadNodes: loadN.length, sec: (Date.now() - t0) / 1000,
    disp, dispDims: [NX, NY, NZ], stress };
}

if (typeof module !== 'undefined') module.exports = { feKe, feSolve };
