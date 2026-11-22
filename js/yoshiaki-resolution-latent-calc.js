// Pure size calculation for YoshiakiResolutionLatent's live preview.
// Mirror of modules/yoshiaki_resolution_latent/calc.py -- keep both in sync
// (modules/yoshiaki_resolution_latent/tests/cases.json is shared by both tests).
// No app.registerExtension here: ComfyUI loads every .js in this folder as an
// extension, and this one only exports functions.

export const CUSTOM_LABEL = "カスタム";
export const ORIENT_LANDSCAPE = "横長";
export const ORIENT_PORTRAIT = "縦長";
export const MIN_FIXED_SIDE = 64;
export const DEFAULT_MAX_RESOLUTION = 16384;

const FIXED_RE = /^(\d+)\s*[x×X]\s*(\d+)$/;
const NUM = "(\\d+(?:\\.\\d+)?|\\.\\d+)";
const RATIO_RE = new RegExp(`^${NUM}\\s*:\\s*${NUM}$`);
const DECIMAL_RE = new RegExp(`^${NUM}$`);
const INPUT_EXAMPLES = "入力例: 16:9 / 2.39:1 / 1.85 / 1152x896";

export class CalcError extends Error {}

export function specToken(text) {
	return String(text).trim().split(" ", 1)[0];
}

export function parseSpec(text) {
	const token = specToken(text);
	let m = FIXED_RE.exec(token);
	if (m) {
		const w = parseInt(m[1], 10);
		const h = parseInt(m[2], 10);
		if (w < MIN_FIXED_SIDE || h < MIN_FIXED_SIDE) {
			throw new CalcError(
				`固定解像度 '${token}' の辺が${MIN_FIXED_SIDE}px未満です。比率なら 16:9 のように ':' で書いてください`
			);
		}
		return ["fixed", w, h];
	}
	let rw, rh;
	m = RATIO_RE.exec(token);
	if (m) {
		rw = parseFloat(m[1]);
		rh = parseFloat(m[2]);
	} else {
		m = DECIMAL_RE.exec(token);
		if (!m) throw new CalcError(`比率 '${text}' を解析できません（${INPUT_EXAMPLES}）`);
		rw = parseFloat(m[1]);
		rh = 1.0;
	}
	if (rw <= 0 || rh <= 0) {
		throw new CalcError(`比率 '${text}' は0より大きい値で書いてください（${INPUT_EXAMPLES}）`);
	}
	return ["ratio", rw, rh];
}

export function roundTo(x, m) {
	return Math.floor(x / m + 0.5) * m;
}

export function orient(a, b, orientation) {
	const longSide = Math.max(a, b);
	const shortSide = Math.min(a, b);
	return orientation === ORIENT_PORTRAIT ? [shortSide, longSide] : [longSide, shortSide];
}

function gcd(a, b) {
	while (b) [a, b] = [b, a % b];
	return a;
}

export function requiredMultiple(presetMultiple, downscale, generic) {
	if (generic) return downscale;
	return (presetMultiple / gcd(presetMultiple, downscale)) * downscale;
}

export function fixMultiple(multiple, req) {
	if (multiple % req === 0) return [multiple, null];
	const fixed = Math.ceil(multiple / req) * req;
	return [fixed, `倍数 ${multiple} は必要倍数 ${req} の倍数でないため ${fixed} に切り上げました`];
}

export function compute(text, orientation, megapixels, multiple, req, mpRange = null,
	maxResolution = DEFAULT_MAX_RESOLUTION) {
	const warnings = [];
	const [kind, a, b] = parseSpec(text);
	const [m, warn] = fixMultiple(multiple, req);
	if (warn) warnings.push(warn);

	let width, height;
	if (kind === "ratio") {
		const [rw, rh] = orient(a, b, orientation);
		const scale = Math.sqrt((megapixels * 1024 * 1024) / (rw * rh));
		width = Math.max(m, roundTo(rw * scale, m));
		height = Math.max(m, roundTo(rh * scale, m));
		if (mpRange && !(mpRange[0] <= megapixels && megapixels <= mpRange[1])) {
			warnings.push(`メガピクセル ${megapixels.toFixed(2)} が推奨範囲 ${mpRange[0]}〜${mpRange[1]} の外です`);
		}
	} else {
		const [fw, fh] = orient(a, b, orientation);
		width = Math.max(m, roundTo(fw, m));
		height = Math.max(m, roundTo(fh, m));
		if (width !== fw || height !== fh) {
			warnings.push(`固定解像度 ${fw}x${fh} を倍数 ${m} に合わせて ${width}x${height} にしました`);
		}
		const actual = (width * height) / (1024 * 1024);
		if (mpRange && !(mpRange[0] <= actual && actual <= mpRange[1])) {
			warnings.push(`メガピクセル ${actual.toFixed(2)} が推奨範囲 ${mpRange[0]}〜${mpRange[1]} の外です`);
		}
	}

	if (width > maxResolution || height > maxResolution) {
		throw new CalcError(`${width}x${height} は最大解像度 ${maxResolution} を超えています`);
	}
	return { kind, width, height, mp: (width * height) / (1024 * 1024), multiple: m, warnings };
}
