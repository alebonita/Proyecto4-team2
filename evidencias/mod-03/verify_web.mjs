// MOD-3 — carga la variante INT8 con el RUNTIME WEB (onnxruntime-web, backend WASM)
// y comprueba que da la misma clase que el modelo original en las 5 imágenes de MOD-2.
//
//   npm install            (instala onnxruntime-web con la versión de package.json)
//   node verify_web.mjs
//
// Usa las entradas que preparó ../mod-02/export_onnx.py (../mod-02/inputs/*.bin: el mismo tensor que recibe
// el original, ya preprocesado), así que compara el MODELO convertido, no el resize.
// Escribe resultados_web.json y termina con código 1 si alguna clase no coincide.

import { createHash } from "node:crypto";
import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import * as ort from "onnxruntime-web";

const HERE = dirname(fileURLToPath(import.meta.url));
const MODEL = join(HERE, "model", "dog-cat-resnet18-1.0.0-int8.onnx");
const MODEL_S3 =
  "s3://mlops-p4-equipo-452857281704/models/dog-cat-resnet18/1.0.0/onnx/dog-cat-resnet18-1.0.0-int8.onnx";
if (!existsSync(MODEL)) {
  console.error(
    "No está model/dog-cat-resnet18-1.0.0-int8.onnx (no se guarda en git).\n" +
      "Genéralo con `python quantize_int8.py` o bájalo del bucket del equipo:\n\n" +
      `  aws s3 cp ${MODEL_S3} model/ --region us-east-2 --profile <tu-perfil>\n`,
  );
  process.exit(1);
}
const expected = JSON.parse(readFileSync(join(HERE, "..", "mod-02", "inputs", "expected.json"), "utf8"));
const ortVersion = JSON.parse(
  readFileSync(join(HERE, "node_modules", "onnxruntime-web", "package.json"), "utf8"),
).version;

const sha256 = (buf) => createHash("sha256").update(buf).digest("hex");
const softmax = (xs) => {
  const m = Math.max(...xs);
  const e = xs.map((x) => Math.exp(x - m));
  const s = e.reduce((a, b) => a + b, 0);
  return e.map((x) => x / s);
};

ort.env.wasm.numThreads = 1; // determinista y sin workers en Node
const modelBytes = readFileSync(MODEL);
const session = await ort.InferenceSession.create(modelBytes, { executionProviders: ["wasm"] });

console.log(`onnxruntime-web ${ortVersion} (backend wasm), Node ${process.version}`);
console.log(`modelo: model/dog-cat-resnet18-1.0.0-int8.onnx  SHA-256 ${sha256(modelBytes)}`);
console.log(`entrada: ${session.inputNames.join(",")}  salida: ${session.outputNames.join(",")}\n`);

const results = [];
for (const sample of expected.samples) {
  const raw = readFileSync(join(HERE, "..", "mod-02", "inputs", `${sample.crop_id}.bin`));
  const data = new Float32Array(raw.buffer, raw.byteOffset, raw.byteLength / 4);
  const input = new ort.Tensor("float32", data, expected.input_shape);
  const out = await session.run({ [expected.input_name]: input });
  const logits = Array.from(out[expected.output_name].data);
  const probs = softmax(logits);
  const webClass = expected.classes[logits.indexOf(Math.max(...logits))];
  const maxDiffLogits = Math.max(...logits.map((v, i) => Math.abs(v - sample.original_logits[i])));
  const match = webClass === sample.original_class;
  results.push({
    crop_id: sample.crop_id,
    caso: sample.why,
    clase_real: sample.true_class,
    clase_original: sample.original_class,
    clase_web: webClass,
    coincide: match,
    prob_original: sample.original_probs,
    prob_web: Object.fromEntries(expected.classes.map((c, i) => [c, probs[i]])),
    max_abs_diff_logits: maxDiffLogits,
  });
  console.log(
    `${match ? "OK " : "NO "} ${sample.crop_id.padEnd(14)} real=${sample.true_class.padEnd(3)} ` +
      `original=${sample.original_class.padEnd(3)} web=${webClass.padEnd(3)} ` +
      `p_web(${webClass})=${probs[expected.classes.indexOf(webClass)].toFixed(6)}  Δlogits=${maxDiffLogits.toExponential(2)}`,
  );
}

const ok = results.every((r) => r.coincide);
writeFileSync(
  join(HERE, "resultados_web.json"),
  `${JSON.stringify(
    {
      runtime: `onnxruntime-web ${ortVersion} (wasm)`,
      node: process.version,
      modelo: "model/dog-cat-resnet18-1.0.0-int8.onnx",
      modelo_sha256: sha256(modelBytes),
      coinciden: `${results.filter((r) => r.coincide).length}/${results.length}`,
      resultados: results,
    },
    null,
    2,
  )}\n`,
);
console.log(`\n${ok ? "OK" : "FALLA"}: ${results.filter((r) => r.coincide).length}/${results.length} con la misma clase que el original -> resultados_web.json`);
process.exit(ok ? 0 : 1);
