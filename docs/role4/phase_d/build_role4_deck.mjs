/** Rebuild the three-slide Role 4 contribution using the bundled Artifact Tool.
 * Set SKILL_DIR, RUNTIME_NODE_MODULES and RUNTIME_PYTHON from dependency discovery.
 * Drafts/previews stay in ignored logs; final output must be a new filename.
 */
import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, '../../..');
const build = path.join(root, 'evaluation/logs/role4/phase_d_build', `deck_${new Date().toISOString().replace(/[^0-9TZ]/g, '')}`);
const finalPath = process.env.PHASE_D_FINAL_PPTX || path.join(here, 'role4_midproject_review.pptx');
const skill = process.env.SKILL_DIR;
const runtime = process.env.RUNTIME_NODE_MODULES;
if (!skill || !runtime || !process.env.RUNTIME_PYTHON) throw new Error('Bundled runtime paths required');
const { Presentation, PresentationFile } = await import(pathToFileURL(path.join(runtime, '@oai/artifact-tool/dist/artifact_tool.mjs')).href);
const { resolvePresentationFont, finalizePresentation } = await import(pathToFileURL(path.join(skill, 'container_tools/artifact_tool_utils.mjs')).href);
const family = resolvePresentationFont();
const evidence = JSON.parse(await fs.readFile(path.join(here, 'evidence_summary.json'), 'utf8'));
if (evidence.test_methods.combined !== 177 || evidence.backend_type !== 'reference' ||
    evidence.cases.length !== 10 || !evidence.cases.every(c => c.expectation_met)) throw new Error('Evidence disagrees with slide claims');
const script = await fs.readFile(path.join(here, 'speaking_script.md'), 'utf8');
const notes = [1, 2, 3].map(i => script.split(`## Slide ${i}:`)[1].split(i === 3 ? '## Evidence anchors' : `## Slide ${i + 1}:`)[0].split('\n').slice(1).join('\n').trim());
const sources = [
  'evaluation/role4/evaluator.py; evaluation/role4/integration/trace_recorder.py; docs/role4/phase_c_verification.json',
  'docs/role4/phase_d/evidence_summary.json; docs/role4/phase_d/rehearsal_record.json; tests/role4/scenarios.json',
  'docs/role4/phase_c_remaining_integration_gaps.md; phase_c_s07_reuse_and_fixture_alignment.md; phase_d/teammate_decisions_unsent.md',
];
const presentation = Presentation.create({ slideSize: { width: 1280, height: 720 } });
const ink = '#142D3B', teal = '#006F72', muted = '#445A66';
function text(slide, value, left, top, width, height, size = 27, color = ink, bold = false) {
  const box = slide.shapes.add({ geometry: 'textbox', position: { left, top, width, height },
                                 fill: 'none', line: { fill: 'none', width: 0 } });
  box.text = value;
  box.text.style = { typeface: family, fontSize: size, color, bold, autoFit: 'none' };
  return box;
}
function slide(title, i) {
  const s = presentation.slides.add();
  s.background.fill = '#FFFFFF';
  text(s, title, 72, 48, 1136, 82, 44, ink, true);
  text(s, 'Reference-backed evaluation', 72, 137, 1136, 42, 26, teal, true);
  s.speakerNotes.textFrame.setText(`${notes[i]}\n\nEvidence: ${sources[i]}\nPrepared 3 October 2026. Scheduled October 5 peer review and October 6 presentation remain pending.`);
  return s;
}
const s1 = slide('Evaluation framework and audit trail', 0);
text(s1, 'Structured checks', 72, 220, 535, 50, 32, ink, true);
text(s1, 'Recorded evidence', 674, 220, 534, 50, 32, ink, true);
const checks = ['Required tools and forbidden actions', 'Claims bound to returned evidence', 'Source, confidence and perspective', 'Belief changes and trace replay'];
const records = ['Question and initial state', 'Public calls and raw tool returns', 'Evidence IDs and before/after beliefs', 'Answer, check results and reasons'];
for (let i = 0; i < 4; i++) {
  text(s1, checks[i], 72, 285 + i * 70, 535, 65);
  text(s1, records[i], 674, 285 + i * 70, 534, 65);
}
text(s1, 'Human prose review remains pending. Automated checks validate structured metadata.', 72, 611, 1136, 73, 24, muted);

const s2 = slide('Five-case results and deliberate faults', 1);
const labels = { S01: 'Missing LiDAR', S02: 'Historical claim used as current', S03: 'Perspectives collapsed',
                 S07: 'Fabricated temperature, movement request', S08: 'User claim replaces blocked sensor' };
const values = [['Scenario', 'Valid', 'Injected fault', 'Detected behavior']];
for (const sid of ['S01', 'S02', 'S03', 'S07', 'S08']) {
  const valid = evidence.cases.find(c => c.scenario_id === sid && c.case === 'valid');
  const fault = evidence.cases.find(c => c.scenario_id === sid && c.case === 'injected_fault');
  values.push([sid, valid.status, `${fault.status} (expected)`, labels[sid]]);
}
const table = s2.tables.add({ rows: 6, columns: 4, left: 72, top: 210, width: 1136, height: 318,
                             columnWidths: [130, 115, 220, 671], values });
table.borders.assign({ style: 'solid', fill: '#D9E2E5', width: 1 });
for (let row = 0; row < 6; row++) {
  table.rows[row].height = 53;
  for (let col = 0; col < 4; col++) {
    const cell = table.getCell(row, col);
    cell.fill = row === 0 ? '#142D3B' : '#FFFFFF';
    cell.text.style = { typeface: family, fontSize: 24, bold: row === 0,
                        color: row === 0 ? '#FFFFFF' : col === 1 ? teal : ink };
  }
}
text(s2, '177 available test methods = 167 Role 4 + 10 teammate client', 72, 555, 1136, 40, 25, ink, true);
text(s2, 'Separate control: malformed S07 payload returns CONTRACT ERROR', 72, 604, 1136, 38, 24, muted);
text(s2, 'Fixture passes and fault detection do not measure LLM reliability.', 72, 649, 1136, 38, 24, muted);

const s3 = slide('Integration blockers and next milestones', 2);
text(s3, 'Current limitations', 72, 220, 535, 50, 32, ink, true);
text(s3, 'Planned next steps', 674, 220, 534, 50, 32, ink, true);
const left = ['contracts.models and sensorimotor.stub missing', 'Full discovery: 2 collection errors, exit 1',
              'Complete agent and hosted trials pending', 'Scenario B identity and lighting unspecified'];
const right = ['October 5: peer review planned', 'October 6: presentation planned',
               'Agree owner APIs and exact fixtures', 'Human review, integration, then release gates'];
for (let i = 0; i < 4; i++) {
  text(s3, left[i], 72, 285 + i * 73, 535, 69, 26);
  text(s3, right[i], 674, 285 + i * 73, 534, 69, 26);
}
text(s3, "Prem's real client used fake APIs only. Human and peer reviews remain pending.", 72, 618, 1136, 73, 24, muted);

await fs.mkdir(build, { recursive: true });
const candidate = path.join(build, `${path.basename(finalPath, '.pptx')}_candidate.pptx`);
await (await PresentationFile.exportPptx(presentation)).save(candidate);
for (let i = 0; i < 3; i++) {
  const s = [s1, s2, s3][i];
  const preview = await presentation.export({ slide: s, format: 'png', scale: 1 });
  await fs.writeFile(path.join(build, `slide-${i + 1}.png`), new Uint8Array(await preview.arrayBuffer()));
  await fs.writeFile(path.join(build, `slide-${i + 1}.layout.json`), await (await s.export({ format: 'layout' })).text());
}
const result = await finalizePresentation({ workspaceDir: root, candidatePath: candidate, finalPath,
  explicitTotalSlideCount: 3, requiredNativeTableOwnerSlides: [2], requiredNativeChartOwnerSlides: [],
  pythonExecutable: process.env.RUNTIME_PYTHON,
  integrityValidatorPath: path.join(skill, 'container_tools/inspect_presentation_package_integrity.py'),
  layoutValidatorPath: path.join(skill, 'container_tools/inspect_presentation_layout_geometry.py'),
  layoutArgs: ['--expected-slide-size-emu', '12192000,6858000', '--validate-bullet-geometry', '--validate-heading-fit', '--require-native-table-slide', '2'],
  fontPolicy: { basis: 'design', families: [family] }, verifyArtifactToolImport: true,
  receiptPath: path.join(build, `${path.basename(finalPath)}.validation.json`),
});
const md = ['# Role 4 slide content and speaker notes', '', 'Three editable slides. Prepared 3 October 2026. Human and peer reviews pending.', ''];
const copy = [
  ['Evaluation framework and audit trail', ...checks.map((c, i) => `${c} / ${records[i]}`), 'Human prose review remains pending. Automated checks validate structured metadata.'],
  ['Five-case results and deliberate faults', ...values.slice(1).map(r => r.join(' / ')),
   '177 available test methods = 167 Role 4 + 10 teammate client', 'Separate malformed S07 control: CONTRACT ERROR / malformed_payload', 'No LLM reliability measurement'],
  ['Integration blockers and next milestones', ...left, ...right, "Prem's real client used fake APIs only. Human and peer reviews remain pending."],
];
for (let i = 0; i < 3; i++) {
  md.push(`## Slide ${i + 1}: ${copy[i][0]}`, '', '**Visible scope: Reference-backed evaluation**', '',
          ...copy[i].slice(1).map(v => `- ${v}`), '', '**Speaker notes:**', '', notes[i], '', `Evidence: ${sources[i]}`, '');
}
await fs.writeFile(path.join(here, 'slide_content_and_notes.md'), md.join('\n') + '\n');
console.log(JSON.stringify({ finalPath, font: family, slides: 3, validation: result }));
