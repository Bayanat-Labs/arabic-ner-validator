// User interface of the static page. Validation runs in worker.js (validator.js); nothing is sent
// over the network and nothing is stored.
import { CODES } from "./codes.js";
import { EXAMPLES } from "./examples.js";
import { VERSION, shareReport, csvReport } from "./validator.js";

const MAX_BYTES = 10 * 1024 * 1024;
const MAX_RECORDS = 10000;
const SHOW_RECORDS = 200;

const T = {
  en: {},
  ar: {
    skip: "انتقل إلى النتائج", brand: "بيانات لابز", title: "مدقّق مواضع الكيانات المسمّاة العربية",
    lede: "افحص وسوم الكيانات المسمّاة العربية قبل التدريب: مواضع محسوبة بوحدة خاطئة، ونص تغيّر بعد الوسم (NFC وNFKC وحذف التطويل وفواصل الأسطر وعلامة ترتيب البايتات)، وامتدادات تفصل الحرف عن حركته أو السابقة عن كلمتها، والتداخل والتعشيش، وأخطاء وسوم BIO وBIOES وBILUO.",
    privacy: "يعمل كل شيء داخل هذه الصفحة. لا يُرفع الملف الذي تفتحه ولا النص الذي تلصقه ولا يُخزَّن؛ ويُمحى بإغلاق الصفحة أو بالضغط على «مسح».",
    inputH: "1. المدخلات", examples: "أمثلة", openFile: "افتح ملفًا", pasteLabel: "أو الصق محتوى الملف",
    crlfHint: "مربع النص يحوّل فواصل الأسطر CRLF إلى LF. لفحص فواصل الأسطر أو علامة ترتيب البايتات افتح الملف بدل لصقه.",
    format: "الصيغة", fmtAuto: "اكتشاف من المحتوى", unit: "وحدة المواضع", unitRecord: "كما هي معلنة في كل سجل",
    unitCp: "نقاط الترميز (Python str)", unitU16: "وحدات UTF-16 (JavaScript String)", unitU8: "بايتات UTF-8", unitG: "عناقيد كتابية",
    scheme: "مخطط الوسوم", schemeNone: "غير معلن", nested: "الامتدادات المتداخلة", forbid: "ممنوعة", allow: "مسموحة",
    clitic: "السوابق المتصلة (و ف ب ك ل)", cliticU: "لا تُفحص", cliticI: "داخل الامتداد", cliticE: "خارج الامتداد (وأداة التعريف داخله)",
    labels: "قائمة الوسوم (مفصولة بفواصل، اختيارية)", tagNames: "أسماء الوسوم للوسوم الرقمية (صفوف Hugging Face)",
    unitHint: "لا تُخمَّن وحدة المواضع أبدًا. إن لم تكن متأكدًا فشغّل الفحص مرة: يذكر التقرير الوحدة المطابقة.",
    run: "افحص", clear: "مسح", resultsH: "النتائج", empty: "افتح ملفًا أو الصق الوسوم أو اختر مثالًا، ثم اضغط «افحص».",
    byCode: "النتائج حسب الرمز", code: "الرمز", what: "المعنى", count: "العدد",
    dlJson: "نزّل تقرير JSON", dlShare: "نزّل التقرير القابل للمشاركة (بلا نص)", dlCsv: "نزّل CSV",
    shareHint: "لا يحتفظ التقرير القابل للمشاركة إلا بمعرّفات السجلات والرموز والمواضع والأعداد، مع إصدار المدقّق وبصمة الإعدادات.",
    recsH: "سجلات فيها أخطاء أو تحذيرات", diffH: "الإصلاحات المقترحة (فرق للمراجعة)",
    diffHint: "المواضع فقط، بالوحدة المعلنة. لا تُغيَّر الوسوم ولا النص أبدًا. وتستطيع أداة سطر الأوامر كتابة نسخة مُصلحة بالخيار --apply-suggestions.",
    record: "السجل", span: "الامتداد", oldNew: "القديم ← الجديد", reason: "السبب", confidence: "الثقة",
    howH: "طريقة العمل",
    how1: "تُقرأ المواضع بالوحدة التي تعلنها (نقاط الترميز أو وحدات UTF-16 أو بايتات UTF-8 أو العناقيد الكتابية) وتُطابَق مع النص كما هو مخزّن.",
    how2: "إذا لم يطابق امتداد، يجرّب المدقّق الوحدات الأخرى والتغييرات المعتادة على النص (NFC وNFKC وحذف التطويل أو التشكيل وCRLF وLF وعلامة ترتيب البايتات). فإن جعلت قراءة واحدة فقط الامتداد مطابقًا سمّاها واقترح مواضع جديدة؛ وإن اختلفت عدة قراءات بقي الامتداد خطأً بلا اقتراح.",
    how3: "تُفحص حدود الامتدادات بالنسبة إلى العناقيد الكتابية (الحرف وحركاته) والكلمات والوحدات وسياسة السوابق ومحارف التحكم الاتجاهية وصفرية العرض والمسافات وعلامات الترقيم. ويُفحص التداخل والتعشيش والوسوم وتسلسلها في كل سجل.",
    how4: "تشغّل هذه الصفحة نسخة JavaScript من حزمة Python، وكلتاهما تعطي التقرير نفسه في كل حالات الاختبار.",
    codesH: "الرموز", severity: "الدرجة", code_link: "الشيفرة وحالات الاختبار", data_link: "مجموعة بيانات الحالات", cli_link: "أداة سطر الأوامر",
    licence: "الشيفرة: Apache-2.0. نص الصفحة وحالات الاختبار: CC BY 4.0. الخط: IBM Plex Sans Arabic (SIL OFL 1.1). للتواصل: hello@bayanatlabs.com",
  },
};
const S = {
  en: {
    working: "Checking…", tooBig: "The input is larger than 10 MiB; use the command-line tool for larger files.",
    tooMany: "The input has more than 10,000 records; use the command-line tool for larger files.", nothing: "Nothing to check yet.",
    ok: "No errors or warnings", warn: "Warnings only", bad: "Errors found", records: "records", spans: "spans", valid: "valid spans",
    errors: "errors", warnings: "warnings", notes: "notes", pick: "Pick an example", more: (n) => `${n} more records with findings are in the JSON report.`,
    failed: "The check stopped: ", fileRead: (n, b) => `Loaded ${n} (${b} bytes).`, error: "error", warning: "warning", info: "note", file: "file",
    langBtn: "العربية", conf: { high: "high", medium: "medium", low: "low" },
  },
  ar: {
    working: "جارٍ الفحص…", tooBig: "حجم المدخلات أكبر من 10 ميغابايت؛ استعمل أداة سطر الأوامر للملفات الأكبر.",
    tooMany: "في المدخلات أكثر من 10,000 سجل؛ استعمل أداة سطر الأوامر للملفات الأكبر.", nothing: "لا شيء للفحص بعد.",
    ok: "لا أخطاء ولا تحذيرات", warn: "تحذيرات فقط", bad: "وُجدت أخطاء", records: "سجلات", spans: "امتدادات", valid: "امتدادات سليمة",
    errors: "أخطاء", warnings: "تحذيرات", notes: "ملاحظات", pick: "اختر مثالًا", more: (n) => `في تقرير JSON ‏${n} سجلًا آخر فيها نتائج.`,
    failed: "توقف الفحص: ", fileRead: (n, b) => `حُمّل ${n} (${b} بايت).`, error: "خطأ", warning: "تحذير", info: "ملاحظة", file: "الملف",
    langBtn: "English", conf: { high: "عالية", medium: "متوسطة", low: "منخفضة" },
  },
};

const $ = (id) => document.getElementById(id);
const params = new URLSearchParams(location.search);
let lang = params.get("lang") === "ar" ? "ar" : "en";
let bytes = null;          // the exact input bytes (file or example) until the text box is edited
let source = "";
let report = null;
let worker = null;

function el(tag, attrs = {}, ...kids) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") e.className = v; else if (k === "text") e.textContent = v; else e.setAttribute(k, v);
  }
  for (const k of kids) if (k !== null && k !== undefined) e.append(k);
  return e;
}

const EN = {};
function applyLang() {
  document.documentElement.lang = lang;
  document.documentElement.dir = lang === "ar" ? "rtl" : "ltr";
  for (const n of document.querySelectorAll("[data-i18n]")) {
    const k = n.getAttribute("data-i18n");
    if (!(k in EN)) EN[k] = n.textContent;
    n.textContent = lang === "ar" && T.ar[k] ? T.ar[k] : EN[k];
  }
  const b = $("lang-toggle");
  b.textContent = S[lang].langBtn;
  b.lang = lang === "ar" ? "en" : "ar";
  b.dir = lang === "ar" ? "ltr" : "rtl";
  $("ar-note").hidden = lang !== "ar";
  document.title = (lang === "ar" ? T.ar.title : EN.title || "Arabic NER Offset Validator") + " – " + (lang === "ar" ? "بيانات لابز" : "Bayanat Labs");
  fillExamples();
  fillCodes();
  if (report) render();
}

function fillExamples() {
  const sel = $("examples");
  const cur = sel.value;
  sel.textContent = "";
  sel.append(el("option", { value: "", text: S[lang].pick }));
  EXAMPLES.forEach((x, i) => sel.append(el("option", { value: String(i), text: lang === "ar" ? x.title_ar : x.title_en })));
  sel.value = cur;
}

function fillCodes() {
  const tb = $("codes").tBodies[0];
  tb.textContent = "";
  for (const [code, c] of Object.entries(CODES)) {
    tb.append(el("tr", {}, el("td", {}, el("span", { class: "badge b-" + c.severity, text: code })), el("td", { text: S[lang][c.severity] }), el("td", { text: lang === "ar" ? c.title_ar : c.title_en })));
  }
}

function settings() {
  const v = (id) => $(id).value.trim();
  const list = (s) => (s ? s.split(",").map((x) => x.trim()).filter(Boolean) : null);
  return {
    format: v("format") || "auto",
    offset_unit: v("unit") || null,
    scheme: v("scheme") || null,
    nested_policy: v("nested"),
    clitic_policy: v("clitic"),
    label_set: list(v("labels")),
    normalization_declared: null,
    tag_names: list(v("tagnames")),
  };
}

function currentBytes() {
  if (bytes !== null) return bytes;
  const t = $("input").value;
  return t ? new TextEncoder().encode(t) : null;
}

function startWorker() {
  if (worker) worker.terminate();
  worker = new Worker("worker.js", { type: "module" });
  worker.onmessage = (e) => {
    $("run").disabled = false;
    $("busy").textContent = "";
    if (!e.data.ok) { status("bad", S[lang].failed + e.data.error); return; }
    if (e.data.report.input.records > MAX_RECORDS) { report = null; clearResults(); status("bad", S[lang].tooMany); return; }
    report = e.data.report;
    render();
  };
}

function status(kind, text, extra) {
  const box = $("status");
  box.className = "status" + (kind ? " s-" + kind : "");
  box.textContent = "";
  box.append(el("p", { class: "v", text }));
  if (extra) box.append(extra);
}

// Record count before parsing: JSON Lines count non-blank lines, CoNLL counts blank-line separated
// blocks; a JSON array (Label Studio) is counted after parsing.
function preCount(b) {
  const t = new TextDecoder().decode(b);
  const s = t.replace(/^[\ufeff\s]+/, "");
  if (s.startsWith("[")) return 0;
  const lines = t.split("\n");
  if (s.startsWith("{")) return lines.filter((l) => l.trim()).length;
  let n = 0, inBlock = false;
  for (const l of lines) { if (l.trim()) { if (!inBlock) n++; inBlock = true; } else inBlock = false; }
  return n;
}

function run(ev) {
  if (ev) ev.preventDefault();
  const b = currentBytes();
  if (!b || !b.length) { status("", S[lang].nothing); return; }
  if (b.length > MAX_BYTES) { status("bad", S[lang].tooBig); return; }
  if (preCount(b) > MAX_RECORDS) { status("bad", S[lang].tooMany); return; }
  $("run").disabled = true;
  $("busy").textContent = S[lang].working;
  worker.postMessage({ bytes: b.slice(), settings: settings() });
}

function clearResults() {
  for (const id of ["codes-card", "recs-card", "diff-card"]) $(id).hidden = true;
  $("recs").textContent = "";
  $("by-code").tBodies[0].textContent = "";
  $("diff").tBodies[0].textContent = "";
}

function render() {
  clearResults();
  const s = report.summary;
  const sev = s.by_severity;
  const kind = sev.error ? "bad" : sev.warning ? "warn" : "ok";
  const st = el("ul", { class: "stats" },
    el("li", {}, el("b", { text: String(s.records) }), " " + S[lang].records),
    el("li", {}, el("b", { text: String(s.spans) }), " " + S[lang].spans),
    el("li", {}, el("b", { text: String(s.valid_spans) }), " " + S[lang].valid),
    el("li", {}, el("b", { text: String(sev.error) }), " " + S[lang].errors),
    el("li", {}, el("b", { text: String(sev.warning) }), " " + S[lang].warnings),
    el("li", {}, el("b", { text: String(sev.info) }), " " + S[lang].notes));
  status(kind, S[lang][kind], st);
  const tb = $("by-code").tBodies[0];
  for (const [code, n] of Object.entries(s.by_code)) {
    const c = CODES[code];
    tb.append(el("tr", {}, el("td", {}, el("span", { class: "badge b-" + c.severity, text: code })), el("td", { text: lang === "ar" ? c.title_ar : c.title_en }), el("td", { class: "num", text: String(n) })));
  }
  $("codes-card").hidden = false;
  const msg = (f) => (lang === "ar" ? f.message_ar : f.message_en);
  const list = $("recs");
  let shown = 0, hidden = 0;
  if (report.file_findings.length) {
    const ul = el("ul");
    for (const f of report.file_findings) ul.append(el("li", {}, el("span", { class: "badge b-" + f.severity, text: f.code }), el("span", { text: msg(f) })));
    list.append(el("li", {}, el("span", { class: "rid", text: S[lang].file }), ul));
  }
  for (const r of report.records) {
    const fs = r.findings.filter((f) => f.severity !== "info");
    if (!fs.length) continue;
    if (shown >= SHOW_RECORDS) { hidden++; continue; }
    shown++;
    const ul = el("ul");
    for (const f of r.findings) {
      const off = f.span_index === null ? "" : `#${f.span_index} [${f.start}, ${f.end})`;
      ul.append(el("li", {}, el("span", { class: "badge b-" + f.severity, text: f.code }), el("span", {}, el("span", { text: msg(f) + " " }), el("span", { class: "off", text: off }))));
    }
    const txt = r.text.length > 400 ? r.text.slice(0, 400) + "…" : r.text;
    list.append(el("li", {}, el("span", { class: "rid ltr", text: r.id + (r.line ? ` (line ${r.line})` : "") }), el("span", { class: "txt", dir: "auto", text: txt }), ul));
  }
  $("recs-more").textContent = hidden ? S[lang].more(hidden) : "";
  $("recs-card").hidden = shown === 0;
  const diff = report.suggested_export ? report.suggested_export.audit_diff : [];
  const dt = $("diff").tBodies[0];
  for (const d of diff) {
    const on = d.old ? `[${d.old.join(", ")}] → [${d.new.join(", ")}] ${d.unit || ""}` : d.action;
    dt.append(el("tr", {}, el("td", { class: "ltr", text: d.record_id === null ? S[lang].file : d.record_id }), el("td", { class: "num", text: d.span_index === null ? "" : String(d.span_index) }),
      el("td", { class: "ltr", text: on }), el("td", {}, el("span", { class: "badge b-" + (CODES[d.reason_code] || { severity: "info" }).severity, text: d.reason_code })), el("td", { text: S[lang].conf[d.confidence] || d.confidence })));
  }
  $("diff-card").hidden = diff.length === 0;
}

function download(name, text, type) {
  const url = URL.createObjectURL(new Blob([text], { type }));
  const a = el("a", { href: url, download: name });
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function init() {
  applyLang();
  startWorker();
  $("ver").textContent = `arabic-ner-validator ${VERSION} (JavaScript port)`;
  $("lang-toggle").addEventListener("click", () => { lang = lang === "ar" ? "en" : "ar"; applyLang(); });
  $("form").addEventListener("submit", run);
  $("input").addEventListener("input", () => { bytes = null; source = "text"; });
  $("examples").addEventListener("change", () => {
    const i = $("examples").value;
    if (i === "") return;
    const x = EXAMPLES[Number(i)];
    bytes = new TextEncoder().encode(x.payload);
    source = "example";
    $("input").value = x.payload;
    $("format").value = x.format;
    $("unit").value = x.options.offset_unit || "";
    $("scheme").value = x.options.scheme || "";
    $("nested").value = x.options.nested_policy || "forbid";
    $("clitic").value = x.options.clitic_policy || "unspecified";
    $("labels").value = (x.options.label_set || []).join(",");
    $("tagnames").value = (x.options.tag_names || []).join(",");
    run();
  });
  $("file").addEventListener("change", async () => {
    const f = $("file").files[0];
    if (!f) return;
    if (f.size > MAX_BYTES) { status("bad", S[lang].tooBig); return; }
    bytes = new Uint8Array(await f.arrayBuffer());
    source = "file";
    $("input").value = new TextDecoder().decode(bytes);
    status("", S[lang].fileRead(f.name, bytes.length));
  });
  $("clear").addEventListener("click", () => {
    bytes = null; report = null; source = "";
    $("input").value = ""; $("file").value = ""; $("examples").value = "";
    clearResults();
    status("", S[lang].nothing);
    startWorker();
  });
  $("dl-json").addEventListener("click", () => report && download("arabic-ner-report.json", JSON.stringify(report, null, 1) + "\n", "application/json"));
  $("dl-share").addEventListener("click", () => report && download("arabic-ner-report-share.json", JSON.stringify(shareReport(report), null, 1) + "\n", "application/json"));
  $("dl-csv").addEventListener("click", () => report && download("arabic-ner-report.csv", csvReport(report), "text/csv"));
}

init();
