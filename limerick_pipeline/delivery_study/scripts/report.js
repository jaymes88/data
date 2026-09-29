const fs = require('fs');
const {
  Document, Packer, Paragraph, TextRun, ImageRun, Table, TableRow, TableCell, WidthType, ShadingType,
  AlignmentType, HeadingLevel, BorderStyle, Footer, PageNumber, LevelFormat, PageBreak, Header,
} = require('docx');

const T = JSON.parse(fs.readFileSync('report_tables.json', 'utf8'));
const FONT = 'Arial';
const NAVY = '1F3A5F';
const PAGE_W = 11906, MARGIN = 1247; // A4, ~2.2cm margins
const CONTENT_W = PAGE_W - 2 * MARGIN;

const p = (text, opts = {}) => new Paragraph({
  spacing: { after: 120, line: 290 }, ...opts,
  children: (Array.isArray(text) ? text : [text]).map(t => typeof t === 'string' ? new TextRun({ text: t, font: FONT, size: 21 }) : t),
});
const b = (t) => new TextRun({ text: t, font: FONT, size: 21, bold: true });
const r = (t) => new TextRun({ text: t, font: FONT, size: 21 });
const h1 = (t) => new Paragraph({ heading: HeadingLevel.HEADING_1, spacing: { before: 280, after: 140 }, children: [new TextRun({ text: t, font: FONT })] });
const h2 = (t) => new Paragraph({ heading: HeadingLevel.HEADING_2, spacing: { before: 200, after: 100 }, children: [new TextRun({ text: t, font: FONT })] });
const bullet = (parts) => new Paragraph({ numbering: { reference: 'bul', level: 0 }, spacing: { after: 80, line: 280 },
  children: (Array.isArray(parts) ? parts : [parts]).map(t => typeof t === 'string' ? r(t) : t) });
const caption = (t) => new Paragraph({ spacing: { before: 60, after: 200 }, children: [new TextRun({ text: t, font: FONT, size: 17, italics: true, color: '52514E' })] });
const figTitle = (t) => new Paragraph({ spacing: { before: 160, after: 60 }, keepNext: true, children: [new TextRun({ text: t, font: FONT, size: 20, bold: true, color: NAVY })] });

function img(file, widthCm) {
  const buf = fs.readFileSync(file);
  const w = buf.readUInt32BE(16), hgt = buf.readUInt32BE(20);
  const wpx = widthCm / 2.54 * 96;
  return new Paragraph({ keepNext: true, children: [new ImageRun({ type: 'png', data: buf, transformation: { width: wpx, height: wpx * hgt / w },
    altText: { title: file, description: file, name: file } })] });
}

function table(rows, widths, opts = {}) {
  const total = widths.reduce((a, x) => a + x, 0);
  const border = { style: BorderStyle.SINGLE, size: 4, color: 'D0CFCA' };
  const borders = { top: border, bottom: border, left: border, right: border };
  return new Table({
    width: { size: total, type: WidthType.DXA }, columnWidths: widths,
    rows: rows.map((row, i) => new TableRow({
      tableHeader: i === 0, cantSplit: true,
      children: row.map((cell, j) => new TableCell({
        width: { size: widths[j], type: WidthType.DXA }, borders,
        shading: i === 0 ? { type: ShadingType.CLEAR, fill: NAVY, color: 'auto' } : (opts.boldLast && i === rows.length - 1 ? { type: ShadingType.CLEAR, fill: 'EEF2F7', color: 'auto' } : undefined),
        margins: { top: 50, bottom: 50, left: opts.small ? 50 : 90, right: opts.small ? 50 : 90 },
        children: [new Paragraph({ alignment: j === 0 ? AlignmentType.LEFT : AlignmentType.RIGHT, keepNext: i < rows.length - 1,
          children: [new TextRun({ text: (String(cell).replace(/^ABPREF/, 'ABP-') || '–'), font: FONT, size: opts.small ? 15 : 17, bold: i === 0 || (opts.boldLast && i === rows.length - 1), color: i === 0 ? 'FFFFFF' : '0B0B0B' })] })],
      })),
    })),
  });
}
const spacer = () => new Paragraph({ spacing: { after: 80 }, children: [] });
const split = (n, first) => { const rest = (CONTENT_W - first) / (n - 1); return [first, ...Array(n - 1).fill(Math.floor(rest))]; };

// ---------------- content ----------------
const title = [
  new Paragraph({ spacing: { before: 2600, after: 200 }, children: [new TextRun({ text: 'Residential Delivery in County Limerick', font: FONT, size: 52, bold: true, color: NAVY })] }),
  new Paragraph({ spacing: { after: 400 }, children: [new TextRun({ text: 'From planning application to completion, 2018–2026', font: FONT, size: 30, color: '52514E' })] }),
  new Paragraph({ spacing: { after: 120 }, border: { top: { style: BorderStyle.SINGLE, size: 8, color: NAVY, space: 12 } }, children: [new TextRun({ text: 'Draft for discussion with Limerick City and County Council', font: FONT, size: 22 })] }),
  new Paragraph({ spacing: { after: 120 }, children: [new TextRun({ text: 'September 2026', font: FONT, size: 22 })] }),
  new Paragraph({ spacing: { after: 120 }, children: [new TextRun({ text: '[Consultancy name]', font: FONT, size: 22, color: '52514E' })] }),
  new Paragraph({ children: [new PageBreak()] }),
];

const summary = [
  h1('Summary'),
  p('This study tracks 237 permitted residential schemes in County Limerick, totalling 10,442 units, from planning application to completion. It joins three sources at scheme level: the national planning applications register, building control commencement notices, and CIS project records. The aim is to give the Council an evidence base on how quickly permitted housing gets built, where it stalls, and which permissions are close to expiry.'),
  p([b('Getting permission is not the main delay. '), r('The median time from application to permission is about seven months (0.6 years). It is about 12 weeks (0.2 years) where no further information is requested and there is no appeal. A further information request takes the median to 0.6 years, and an appeal to 1.2 years.')]),
  p([b('Starting on site takes longer. '), r('For schemes that have started, the median gap between permission and start on site is 1.4 years. Across all permissions, 46% of schemes had started within two years of permission and 71% within five years.')]),
  p([b('Completed schemes took a median of 3.9 years from application to completion '), r('(interquartile range 2.6 to 5.1 years, 44 schemes). Build periods averaged 1.8 years. Median build-out rates rise with scheme size, from 4 dwellings per annum on schemes of 1–9 units to 50 on schemes of 100+ units, though the larger bands rest on very few completed schemes.')]),
  p([b('5,755 permitted units have not started. '), r('Most sit on recent permissions: 4,092 units have more than three years left to run, mainly large schemes in Limerick City East and West granted in 2025 and 2026. The near-term risk is smaller but real: 388 units are already past their expiry date and a further 567 expire within two years.')]),
  p([b('Delivery varies by location. '), r('Among permissions at least two years old, 90% of units in Limerick City East have started, compared with 47% in Newcastle West and 19% in Adare-Rathkeale.')]),
  p([b('Strategic housing developments have been slow to start. '), r('Two of the six SHD schemes permitted by An Bord Pleanála have started, accounting for 44% of the 1,287 units. Part 8 council schemes in the sample also show low start rates, though some of these are at tender stage.')]),
  p([b('Official completions data is incomplete. '), r('Completion certificates exist for 41 of the 44 schemes CIS records as complete, but they account for only 328 of the 1,226 units CIS reports. In our view, completions monitoring should not rely on completion certificate unit counts without checking them against site records.')]),
];

const intro = [
  h1('1. Purpose and scope'),
  p('The Council asked how quickly residential permissions in Limerick are turning into homes, what holds them back, and where. The approach follows the structure of Lichfields’ Start to Finish research (third edition, March 2024), which measures the planning approval period, the time from permission to first completion, and annual build-out rates for large sites in England and Wales. Limerick has few schemes of the size Lichfields study, so this study uses smaller size bands (1–9, 10–24, 25–49, 50–99 and 100+ units) and covers schemes of all sizes.'),
  p('The sample is the set of residential schemes tracked by CIS in County Limerick with permissions from 2018 onward, plus newer applications from the latest CIS export. Where several applications relate to one site, the study counts each distinct scheme once. Extensions of duration, superseded applications and minor amendments are not counted as separate schemes. Refused and withdrawn applications are excluded from the scheme count but reported as indicators of delay.'),
  p('It does not cover one-off rural houses, schemes CIS does not track, or pre-application and zoning stages, which cannot be measured from the available records.'),
];

const method = [
  h1('2. Data and method'),
  h2('2.1 Sources'),
  table([
    ['Stage', 'Source', 'Coverage in this study'],
    ['Application received, further information, appeal, decision, grant, expiry', 'National Planning Applications dataset (Department of Housing, Local Government and Heritage), Limerick records from 2017; An Coimisiún Pleanála case records for SHD', '237 of 281 CIS applications matched by reference; 6 SHD cases'],
    ['Start on site', 'Building control commencement notices (National Building Control Office open data, 2014 onward)', '120 schemes dated from a commencement notice; 10 from CIS start dates'],
    ['Completion', 'CIS project updates (dated), CIS finish dates', '44 completed schemes'],
    ['Location', 'Scheme coordinates; Local Electoral Areas 2019 (Tailte Éireann)', 'All schemes'],
  ], [2600, 4200, CONTENT_W - 6800]),
  spacer(),
  h2('2.2 Definitions'),
  bullet([b('Approval period: '), r('application received to final grant. Where a decision was appealed, the appeal decision date is used.')]),
  bullet([b('Permission to start: '), r('final grant to the earliest commencement date on a building control commencement notice for that permission (including notices citing its extension of duration or appeal reference).')]),
  bullet([b('Build period: '), r('start on site to the date CIS first records the scheme as complete. Build-out rate is units divided by build period (floored at six months).')]),
  bullet([b('Status: '), r('Complete; Under construction (commencement notice, or CIS records the scheme on site); Not started with permission live; Not started and past expiry. Expiry is the register expiry date, updated where a granted extension of duration applies.')]),
  h2('2.3 Limitations'),
  bullet('Sample sizes in the 50–99 and 100+ bands are small, particularly for completed schemes (four and three respectively). Treat those medians as indicative.'),
  bullet('Durations from permission to start are measured only for schemes that have started. The cumulative start shares in Section 3 cover all permissions and are the fairer measure of how many permissions get built.'),
  bullet('Part 8 schemes are not in the planning register. Their dates come from CIS and they have no register expiry date.'),
  bullet('CIS records reasons for delay only occasionally, so barriers are mostly inferred from the planning and building control record rather than stated by developers.'),
  bullet('Completion certificates under-record units (see Appendix A), so completions rely on CIS.'),
];

const s3 = [
  h1('3. How long does it take to get started?'),
  figTitle('Figure 1. Median time from application to completion, by scheme size'),
  img('charts/c1_timeline.png', 16),
  caption('Medians of each stage calculated separately; the total is indicative, not the median of end-to-end times. Source: national planning register, NBCO commencement notices, CIS.'),
  p('Across all sizes, permission takes a median of about seven months from lodgement. The approval period barely changes with scheme size: the 50–99 band is slightly slower at 0.7 years, and the 100+ band sits at 0.5 years. The bigger variation is in what happens after permission.'),
  table(T.timeline, split(5, 2000)),
  caption('Median years, with number of schemes measured in brackets. Build rate is the median of completed schemes.'),
  h2('3.1 The planning path'),
  p('Further information requests and appeals account for most of the variation in approval times. Where the Council asked for further information, the median rose from 0.2 to 0.6 years. Appealed decisions took a median of 1.2 years. Around 70% of schemes in the council register had a further information request.'),
  table(T.path, split(5, 3800)),
  caption('Applications in the council planning register (standard and LRD routes). SHD and Part 8 excluded.'),
  p('For comparison, Lichfields report a median planning approval period of 1.5 years for 50–99 dwelling sites in England and Wales (Table 3.1 of their report). The Limerick median for 50–99 unit schemes is 0.7 years. The measures are close but not identical: Lichfields measure to the first detailed permission on a site, which often follows an outline permission.'),
  h2('3.2 From permission to start on site'),
  figTitle('Figure 2. Share of permitted schemes started, by time since permission'),
  img('charts/c2_started_over_time.png', 14.5),
  caption('Each point covers only permissions old enough to have reached that time. Number of schemes shown in the table below.'),
  p('About a quarter of schemes start within a year of permission and just under half within two years. By five years, 71% have started. Schemes of 25–99 units have the highest start rate by five years (84%). Schemes of 1–24 units reach 66%. The 100+ band has too few older permissions to measure beyond four years.'),
  table(T.started, split(6, 2000)),
  caption('% of schemes started (number of permissions old enough to be measured).'),
];

const s4 = [
  h1('4. How quickly do schemes build out?'),
  p('Forty-four schemes in the sample have been completed. The median build period was 1.8 years. Build-out rates rise with scheme size, which is expected: larger schemes run more units in parallel.'),
  figTitle('Figure 3. Median build-out rate of completed schemes, by size'),
  img('charts/c8_build_rates.png', 14),
  caption('Dwellings per annum = units ÷ build period. Source: NBCO commencement notices, CIS completion updates.'),
  table(T.build, split(5, 2400)),
  spacer(),
  p('Mixed schemes of houses and apartments had the highest median rate (34 dpa), but that group is only six schemes and includes several of the largest completed sites. Few large schemes have completed in Limerick since 2018, which limits what can be said about build-out on the 100+ unit permissions now in the pipeline.'),
  h2('4.1 Delivery over time'),
  figTitle('Figure 4. Units granted, started and completed per year (study sample)'),
  img('charts/c3_annual_flows.png', 16),
  caption('2026 runs to September. Completions count schemes CIS records as fully complete; completed phases on sites still under construction are not included. Source: planning register, NBCO, CIS.'),
  p('Permissions have run ahead of starts in most years, and 2026 stands out: 2,795 units were granted in the first nine months, including several large LRD schemes in Castletroy, Mungret, Singland and Dock Road. Starts peaked in 2024 at 1,082 units. Completions in the sample are low relative to starts because most recently started schemes are still under construction.'),
];

const s5 = [
  h1('5. Barriers to delivery'),
  p('CIS rarely records why a scheme has not progressed. Ten schemes carry notes such as “on hold” or “no movement”, one was quashed following a legal challenge, and two sites were reported for sale. The planning and building control record gives a fuller picture of where delivery slows.'),
  table(T.barriers, split(3, 6400)),
  caption('Counts overlap: a scheme can appear under several indicators.'),
  spacer(),
  h2('5.1 Which permissions are least likely to start?'),
  p('The tables below cover permissions granted at least two years before September 2026 (176 schemes, 6,409 units), so every scheme has had time to start. 69% of those units have started.'),
  table(T.route, split(6, 2600)),
  caption('Permissions at least two years old.'),
  spacer(),
  p('Standard planning applications perform best, with 76% of units started. Two of the six SHD permissions have started. Among the four not started, the largest are Raheen (384 units, CIS: commencement expected), Clonmacken Gardens (165 units) and Annacotty (137 units, now past expiry). Part 8 schemes show low start rates in this data, but several are at tender or contract award stage, and CIS start dates for council schemes may lag actual progress.'),
  table(T.type, split(6, 2600)),
  caption('Permissions at least two years old. Type from bedroom mix or development description.'),
  spacer(),
  p('Houses and apartments start at similar rates by units. Student accommodation stands out: one of five older student permissions has started. The largest student permissions in the sample, including Punches Cross and the 196-unit Castletroy scheme granted in 2025, have not started.'),
];

const s6 = [
  h1('6. Expiring permissions'),
  figTitle('Figure 5. Units not started, by time to expiry'),
  img('charts/c5_expiry_profile.png', 14.5),
  caption('Expiry from the planning register, updated for granted extensions of duration. Part 8 schemes have no register expiry. Source: planning register, NBCO, CIS.'),
  p('Of the 5,755 permitted units not started, 4,092 have more than three years left on their permission. The near-term pipeline at risk is smaller: 388 units are already past expiry, 360 expire within 12 months and 207 within 12 to 24 months.'),
  table(T.expiry, [1900, 1000, ...Array(7).fill(Math.floor((CONTENT_W - 2900) / 7))], { small: true }),
  caption('Units not started, by LEA and expiry window.'),
  spacer(),
  h2('6.1 Watchlist: schemes of 10+ units past or near expiry'),
  p('These schemes have not started according to building control and CIS records and are past expiry or within two years of it. Before the Council relies on this list it should check each one against the planning file and building control, since a start may have been notified under a different reference.'),
  table(T.watch, [3000, 1250, 1900, 700, 1150, CONTENT_W - 8000]),
  caption('Scheme names are CIS project headings. “Tender” and “Contract awarded” are CIS stages, mainly for council and AHB schemes.'),
];

const s7 = [
  h1('7. Location'),
  figTitle('Figure 6. Status of permitted units by Local Electoral Area'),
  img('charts/c4_status_by_lea.png', 16),
  caption('All permitted schemes in the sample. Source: planning register, NBCO, CIS; LEA boundaries Tailte Éireann (2019).'),
  p('The three city LEAs hold 87% of permitted units. Limerick City East has the most units under permission (3,807) and, among older permissions, the highest start rate. Most of its unstarted units are on large permissions granted in 2025 and 2026 around Castletroy and Singland. Limerick City West has the largest volume under construction (1,502 units), concentrated in Mungret and Patrickswell.'),
  table(T.lea, split(6, 2600)),
  caption('Permissions at least two years old.'),
  spacer(),
  p('The county LEAs have smaller volumes and lower start rates. In Adare-Rathkeale, 31 of 165 units on older permissions have started. In Newcastle West, 206 of 436. The median time from permission to start is also longer in Adare-Rathkeale (2.1 years) and Cappamore-Kilmallock (1.8 years) than in the city (1.4 to 1.5 years).'),
  figTitle('Figure 7. Permitted schemes by status, County Limerick'),
  img('charts/c6_map_county.png', 16),
  figTitle('Figure 8. Permitted schemes by status, Limerick city and suburbs'),
  img('charts/c7_map_city.png', 16),
  caption('Circle area proportional to units.'),
];

const s8 = [
  h1('8. Implications for the Council'),
  p('The points below are our professional view, drawing on the findings above.'),
  bullet([b('Focus engagement on the near-expiry list. '), r('Around 950 units are past expiry or will expire within two years without starting. Contacting the owners of the larger schemes on the watchlist would establish which are likely to proceed, which need an extension, and which are unlikely to be built.')]),
  bullet([b('Track the 2025–26 permissions early. '), r('About 3,700 unstarted units sit on permissions less than two years old, mostly large LRD schemes in the city. Their progress will largely decide delivery in 2027 to 2030. The data suggests roughly half of permissions start within two years, so a 12-month check on each is worthwhile.')]),
  bullet([b('Reduce further information requests where possible. '), r('They roughly triple the median approval time. Better pre-application engagement on the issues that trigger them is likely to shorten the planning stage more than any other change within the Council’s control.')]),
  bullet([b('Fix the completions record. '), r('Completion certificates under-record units by a wide margin in this sample. The Council cannot monitor delivery against targets without reliable completions data. Checking unit counts on certificates, or recording completions at site level each quarter, would close the gap.')]),
  bullet([b('Ask why schemes stall. '), r('The records rarely say why a permitted scheme has not started. A short survey of permission holders with unstarted schemes of 10+ units would turn the inferred barriers in Section 5 into stated ones: viability, finance, infrastructure or sale.')]),
  bullet([b('Repeat annually. '), r('The method uses public data and can be refreshed each year. A consistent annual series would show whether time from permission to start is improving.')]),
];

const appendix = [
  h1('Appendix A. Data coverage'),
  table(T.sources, [6400, CONTENT_W - 6400]),
  spacer(),
  p('Completion certificates are the only official site-level record of completions. For the 44 schemes CIS records as complete, certificates exist for 41 but record 328 units against 1,226. This could reflect how units are entered on certificates, phased certificates not yet lodged, or schemes certified under a different reference. We have not been able to resolve which.'),
  h1('Appendix B. Start rate by scheme size'),
  table(T.size, split(6, 2600)),
  caption('Permissions at least two years old.'),
  h1('Appendix C. Companion data'),
  p('The accompanying workbook (Limerick_Delivery_Study_Data.xlsx) contains the scheme-level dataset, every table in this report, and the full expiry watchlist. Status tables in the workbook update from the scheme sheet.'),
];

const doc = new Document({
  creator: '[Consultancy name]', title: 'Residential Delivery in County Limerick',
  styles: {
    default: { document: { run: { font: FONT, size: 21 } } },
    paragraphStyles: [
      { id: 'Heading1', name: 'Heading 1', basedOn: 'Normal', next: 'Normal', quickFormat: true, run: { size: 30, bold: true, color: NAVY, font: FONT }, paragraph: { outlineLevel: 0, keepNext: true } },
      { id: 'Heading2', name: 'Heading 2', basedOn: 'Normal', next: 'Normal', quickFormat: true, run: { size: 24, bold: true, color: NAVY, font: FONT }, paragraph: { outlineLevel: 1, keepNext: true } },
    ],
  },
  numbering: { config: [{ reference: 'bul', levels: [{ level: 0, format: LevelFormat.BULLET, text: '•', alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 400, hanging: 260 } } } }] }] },
  sections: [
    { properties: { page: { size: { width: PAGE_W, height: 16838 }, margin: { top: 1300, bottom: 1300, left: MARGIN, right: MARGIN } } }, children: title },
    {
      properties: { page: { size: { width: PAGE_W, height: 16838 }, margin: { top: 1300, bottom: 1300, left: MARGIN, right: MARGIN }, pageNumbers: { start: 1 } } },
      headers: { default: new Header({ children: [new Paragraph({ alignment: AlignmentType.RIGHT, children: [new TextRun({ text: 'Residential Delivery in County Limerick – Draft', font: FONT, size: 16, color: '8A8984' })] })] }) },
      footers: { default: new Footer({ children: [new Paragraph({ alignment: AlignmentType.CENTER, children: [new TextRun({ children: [PageNumber.CURRENT], font: FONT, size: 16, color: '8A8984' })] })] }) },
      children: [...summary, ...intro, ...method, ...s3, ...s4, ...s5, ...s6, ...s7, ...s8, ...appendix],
    },
  ],
});
Packer.toBuffer(doc).then(buf => { fs.writeFileSync('Limerick_Residential_Delivery_Study.docx', buf); console.log('ok'); });
