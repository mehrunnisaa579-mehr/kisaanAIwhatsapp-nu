// ── Urdu digit map ──
const urduDigits = ['۰', '۱', '۲', '۳', '۴', '۵', '۶', '۷', '۸', '۹'];

function toUrduDigits(num) {
  return String(num)
    .split('')
    .map((ch) => (ch >= '0' && ch <= '9' ? urduDigits[parseInt(ch)] : ch))
    .join('');
}

// ── Crop → Urdu ──
const cropMap = {
  cotton: 'کپاس',
  kapaas: 'کپاس',
  'کپاس': 'کپاس',
  wheat: 'گندم',
  gandum: 'گندم',
  'گندم': 'گندم',
  mango: 'آم',
  aam: 'آم',
  'آم': 'آم',
  rice: 'چاول',
  chawal: 'چاول',
  'چاول': 'چاول',
  sugarcane: 'گنا',
  ganna: 'گنا',
  'گنا': 'گنا',
  maize: 'مکئی',
  corn: 'مکئی',
  'مکئی': 'مکئی',
  unknown: 'نامعلوم فصل',
};

export function formatCropUrdu(value) {
  if (!value) return 'نامعلوم فصل';
  const key = String(value).toLowerCase().trim();
  return cropMap[key] || value;
}

// ── Disease → Urdu ──
const diseaseMap = {
  'possible cotton leaf curl virus': 'کپاس کے پتوں کے مڑنے کی بیماری کا امکان',
  'cotton leaf curl virus': 'کپاس کے پتوں کے مڑنے کی بیماری',
  'possible yellow rust': 'گندم میں زرد زنگ کا امکان',
  'yellow rust': 'گندم میں زرد زنگ',
  'possible anthracnose': 'آم میں اینتھراکنوز کا امکان',
  anthracnose: 'آم میں اینتھراکنوز',
  'unknown crop issue': 'فصل کا مسئلہ مکمل طور پر واضح نہیں',
  unknown: 'مسئلہ مکمل طور پر واضح نہیں',
};

export function formatDiseaseUrdu(disease, diseaseUrdu) {
  // Always prefer disease_urdu from backend
  if (diseaseUrdu) return diseaseUrdu;
  if (!disease) return 'مسئلہ مکمل طور پر واضح نہیں';
  const key = String(disease).toLowerCase().trim();
  return diseaseMap[key] || disease;
}

// ── Risk → Urdu ──
const riskMap = {
  low: 'کم',
  medium: 'درمیانہ',
  high: 'زیادہ',
  critical: 'بہت زیادہ',
  unknown: 'نامعلوم',
};

export function formatRiskUrdu(value) {
  if (!value) return 'نامعلوم';
  const key = String(value).toLowerCase().trim();
  return riskMap[key] || value;
}

// ── Risk label with emoji (for diagnosis card) ──
export function getRiskLabel(risk) {
  if (!risk) return 'نامعلوم';
  const key = String(risk).toLowerCase().trim();
  const labels = {
    low: '🟢 کم',
    medium: '🟡 درمیانہ',
    high: '🔴 زیادہ',
    critical: '🔴 بہت زیادہ',
  };
  return labels[key] || risk;
}

// ── Confidence → Urdu ──
export function formatConfidence(value) {
  if (value === null || value === undefined) return 'نامعلوم';
  const pct = Math.round(value * 100);
  return toUrduDigits(pct) + '٪';
}

// ── Action chain agent name → Urdu ──
const agentNameMap = {
  inputparser: 'ان پٹ کی جانچ',
  actionplanneragent: 'منصوبہ بندی',
  diagnosisagent: 'تشخیص',
  contextagent: 'سیاق و سباق',
  executionagent: 'عمل درآمد',
  recoveryagent: 'بحالی',
  outcomeagent: 'نتائج',
  weatheragent: 'موسم کی جانچ',
};

export function mapAgentNameUrdu(agentName) {
  if (!agentName) return '';
  const key = String(agentName).toLowerCase().replace(/[\s_-]/g, '').trim();
  return agentNameMap[key] || agentName;
}

// ── Simplified Urdu steps for action chain ──
const actionSteps = [
  'تشخیص مکمل ہوئی',
  'موسم چیک کیا گیا',
  'علاج کا مشورہ تیار ہوا',
  'ماہر کو اطلاع دی گئی',
  '۴۸ گھنٹے بعد دوبارہ جائزہ',
];

export function mapActionStepUrdu(index) {
  return actionSteps[index] || 'مرحلہ مکمل ہوا';
}
