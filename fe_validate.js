// node fe_validate.js <name> [coarsen]  — runs fe_core.js on the exact 0.5 mm voxel set of an Abaqus linear job
// (WIP\11-1\fe\mesh\<name>_h050_solid.npy, packed bits, shape 336 x 32 x 48, x-major) and prints K next to the Abaqus value.
// coarsen = 2: 1.0 mm voxels, a coarse voxel is solid when >= 4 of its 8 fine voxels are (to see the resolution effect).
const fs = require('fs'), { feSolve } = require('./fe_core.js');
const name = process.argv[2], cf = +(process.argv[3] || 1);
const buf = fs.readFileSync(`D:\\syr\\research\\WIP\\11-1\\fe\\mesh\\${name}_h050_solid.npy`);
const hl = buf.readUInt16LE(8), data = buf.subarray(10 + hl);
const SX = 336, SY = 32, SZ = 48, bit = n => (data[n >> 3] >> (7 - (n & 7))) & 1;
const nx = SX / cf, ny = SY / cf, nz = SZ / cf, occ = new Uint8Array(nx * ny * nz);
for (let i = 0; i < nx; i++) for (let j = 0; j < ny; j++) for (let k = 0; k < nz; k++) {
  if (process.env.SAMPLE != null && cf > 1) {   // point sample like the page (one fine voxel per coarse voxel, offset SAMPLE = 0 or 1)
    const o = +process.env.SAMPLE; occ[i + nx * (j + ny * k)] = bit(((i * cf + o) * SY + (j * cf + o)) * SZ + (k * cf + o)); continue;
  }
  let c = 0; for (let a = 0; a < cf; a++) for (let b = 0; b < cf; b++) for (let d = 0; d < cf; d++) c += bit(((i * cf + a) * SY + (j * cf + b)) * SZ + (k * cf + d));
  occ[i + nx * (j + ny * k)] = c * 2 >= cf ** 3 ? 1 : 0;
}
const h = 0.5 * cf;
const r = feSolve({ nx, ny, nz, ax: h, ay: h, az: h, x0: -84, y0: -8, z0: -12, occ, loads: [0], sups: [-72, 72], fixX: null, strip: 1.0, tol: +(process.env.TOL || 1e-6), mg: process.env.MG === '1' },
  p => process.stderr.write(`\r it ${p.it} rel ${p.rel.toExponential(2)} ${p.sec.toFixed(0)} s   `));
let fracFine = 0; for (let n = 0; n < SX * SY * SZ; n++) fracFine += bit(n);
console.log(`\n${name} h=${h} mm: K = ${r.K.toFixed(1)} N/mm, elements ${r.ne}, dropped ${r.dropped}, load nodes ${r.loadNodes}, iters ${r.iters}, rel ${r.rel.toExponential(1)}, ${r.sec.toFixed(0)} s, solid ${(r.ne / (nx * ny * nz)).toFixed(4)} (fine ${(fracFine / (SX * SY * SZ)).toFixed(4)})`);
