// quick check of the multigrid preconditioner against plain Jacobi on synthetic voxel beams (node mg_test.js)
const { feSolve } = require('./fe_core.js');
function beam(nx, ny, nz, holes) {
  const occ = new Uint8Array(nx * ny * nz);
  for (let k = 0; k < nz; k++) for (let j = 0; j < ny; j++) for (let i = 0; i < nx; i++) {
    let on = 1;
    if (holes) { const x = i + 0.5, y = j + 0.5, z = k + 0.5; on = (Math.sin(x * 0.9) * Math.cos(y * 0.9) + Math.sin(y * 0.9) * Math.cos(z * 0.9) + Math.sin(z * 0.9) * Math.cos(x * 0.9)) > 0 ? 1 : 0; }
    occ[i + nx * (j + ny * k)] = on;
  }
  return occ;
}
for (const [name, nx, ny, nz, holes] of [['solid 84x8x12', 84, 8, 12, false], ['gyroid-like 168x16x24', 168, 16, 24, true]]) {
  const hx = nx / 2, hz = nz / 2;
  const base = { nx, ny, nz, ax: 1, ay: 1, az: 1, x0: -hx, y0: -ny / 2, z0: -hz, E: 2900, nu: 0.36, delta: 0.1,
    loads: [0], sups: [-0.857 * hx, 0.857 * hx], fixX: null, strip: 1, tol: 1e-5, maxit: 40000 };
  for (const mg of [false, true]) {
    const t0 = Date.now(), r = feSolve({ ...base, occ: beam(nx, ny, nz, holes), mg });
    console.log(name.padEnd(24), mg ? 'MG    ' : 'Jacobi', 'K', r.K.toFixed(4), 'iters', r.iters, 'sec', ((Date.now() - t0) / 1000).toFixed(1), 'mg used', r.mg);
  }
}
