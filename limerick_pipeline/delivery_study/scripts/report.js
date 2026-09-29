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
const F = JSON.parse(fs.readFileSync('facts.json', 'utf8'));

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
  p(`This study tracks ${F.permitted} permitted residential schemes in County Limerick, totalling ${F.units_permitted} units, from planning application to completion. It joins the national planning applications register, building control commencement notices and CIS project records at scheme level, and classifies each scheme as public (local authority, approved housing body or Land Development Agency) or private. The aim is to show how quickly permitted housing gets built, where it stalls, and which permissions are close to expiry.`),
  p([b('Getting permission is not the main delay. '), r(`The median time from application to permission is about ${F.approval_months} months. It is about ${F.nofi_weeks} weeks where no further information is requested and there is no appeal, ${F.fi_med} years with a further information request, and ${F.appeal_med} years on appeal. Further information was requested on ${F.fi_share} of private and LRD applications.`)]),
  p([b('Starting on site takes longer. '), r(`${F.st2} of permitted schemes had started within two years of permission and ${F.st5} within five years. For schemes that have started, the median gap between permission and start is ${F.g2s_med} years.`)]),
  p([b(`Completed schemes took a median of ${F.e2e_med} years from application to completion `), r(`(interquartile range ${F.e2e_lq} to ${F.e2e_uq} years, ${F.n_complete} schemes). Median build-out rates run from ${F.dpa_small} dwellings per annum on schemes of 1–9 units to ${F.dpa_large} on schemes of 100+ units, though the larger bands rest on very few completed schemes.`)]),
  p([b('Public schemes are quicker through planning but slower to start. '), r(`Public schemes (${F.pub_n} schemes, ${F.pub_units} units, ${F.pub_share} of units) have a median approval period of ${F.pub_appr} years against ${F.pri_appr} for private schemes. After permission, ${F.pub_st2} of public schemes had started within two years against ${F.pri_st2} of private schemes. Over the longer run the gap narrows: on permissions at least two years old, ${F.pub_coh_pct} of public units and ${F.pri_coh_pct} of private units have started.`)]),
  p([b(`${F.u_ns} permitted units have not started. `), r(`Most sit on recent permissions: ${F.exp_more} units have more than three years left to run. The near-term risk is ${F.exp_risk} units: ${F.exp_past} already past expiry and ${F.exp_2yr} expiring within two years.`)]),
  p([b(`Limerick city holds ${F.city_share} of permitted units. `), r(`Within the nine city neighbourhoods, ${F.nb_top1} (${F.nb_top1_u} units), ${F.nb_top2} (${F.nb_top2_u}) and ${F.nb_top3} (${F.nb_top3_u}) carry the most permitted housing. The City Centre stands out: only ${F.nb_cc} of units on older permissions have started, against ${F.nb_ct} in Castletroy/Annacotty.`)]),
  p([b('Official completions data is incomplete. '), r(`Completion certificates exist for ${F.ccc_n} of the ${F.n_complete} completed schemes, but they account for only ${F.ccc_units} of their ${F.cis_units} units.`)]),
];

const intro = [
  h1('1. Purpose and scope'),
  p('The Council asked how quickly residential permissions in Limerick are turning into homes, what holds them back, and where. The study measures three stages for every scheme: the time from lodging an application to receiving permission, the time from permission to starting on site, and the time from starting to completion, together with the annual rate at which completed schemes delivered homes.'),
  p('Most schemes in Limerick are small, so results are reported in five size bands: 1–9, 10–24, 25–49, 50–99 and 100+ units. Results are also split by public and private delivery, by Local Electoral Area and, for the city, by the nine neighbourhoods the Council uses for planning.'),
  p('The sample is the set of residential schemes tracked by CIS in County Limerick with permissions from 2018 onward, newer applications from the latest CIS export, and Part 8 council schemes from the planning register that CIS does not hold. Where several applications relate to one site, each distinct scheme is counted once. Extensions of duration, superseded applications and minor amendments are not counted as separate schemes. Refused and withdrawn applications are excluded from the scheme count but reported as indicators of delay.'),
  p('The study does not cover one-off rural houses, schemes neither CIS nor the Part 8 register records, or pre-application and zoning stages.'),
];

const method = [
  h1('2. Data and method'),
  h2('2.1 Sources'),
  table([
    ['Stage', 'Source', 'Coverage in this study'],
    ['Application, further information, appeal, decision, grant, expiry', 'National Planning Applications dataset (Department of Housing, Local Government and Heritage), Limerick records from 2017; An Coimisiún Pleanála case records for SHD', 'CIS applications matched by planning reference; Part 8 schemes matched by file number or location'],
    ['Start on site', 'Building control commencement notices (National Building Control Office open data, 2014 onward)', `${F.g2s_n} schemes with a measured start`],
    ['Completion', 'CIS project updates (dated), CIS finish dates; Department of Housing social housing construction status report for matched public schemes', `${F.n_complete} completed schemes`],
    ['Public / private', 'Grantee named in CIS records, CIS promoter, building control flags for local authority and approved housing body projects, Part 8 file numbers, Department of Housing social housing construction status report (Q1 2026)', 'All schemes'],
    ['Location', 'Scheme coordinates; Local Electoral Areas 2019 (Tailte Éireann); city neighbourhoods defined by the Council from 42 Electoral Divisions', 'All schemes'],
  ], [2400, 4400, CONTENT_W - 6800]),
  spacer(),
  h2('2.2 Definitions'),
  bullet([b('Approval period: '), r('application received to final grant. Where a decision was appealed, the appeal decision date is used. For Part 8 schemes, the register decision date.')]),
  bullet([b('Permission to start: '), r('final grant to the earliest commencement date on a building control commencement notice for that permission, including notices citing its extension of duration or appeal reference.')]),
  bullet([b('Build period: '), r('start on site to the date CIS first records the scheme as complete. Build-out rate is units divided by build period (floored at six months).')]),
  bullet([b('Status: '), r('Complete; Under construction (commencement notice, or CIS records the scheme on site); Not started with permission live; Not started and past expiry. Expiry is the register expiry date, updated where a granted extension of duration applies. Part 8 approvals have no register expiry.')]),
  bullet([b('Public: '), r('schemes promoted by Limerick City and County Council (including Part 8), approved housing bodies or the Land Development Agency. Turnkey schemes bought by a public body are classed as public where the Department of Housing’s social housing construction status report (Q1 2026) could be matched to the scheme with confidence; other turnkeys remain classed as private.')]),
  h2('2.3 Part 8 coverage'),
  p(`Limerick files Part 8 schemes in the planning register as “yy/8nnn”. CIS records many Part 8s under its own project numbers rather than the council file number, so these were matched to the register by location, date and unit count. The study includes ${F.p8_total} Part 8 schemes. ${F.p8_added} residential Part 8s in the register (${F.p8_added_units} units) were not held by CIS and have been added. Their start dates come from building control; their completion is not tracked, so those that have started are counted as under construction. Two further 2017 Part 8s have no recorded decision or commencement and are excluded: ${T.p8_undecided.map(x => `${x[0]} (${x[1]} units)`).join(' and ')}. Part 8 schemes before 2017 are not in the register.`),
  h2('2.4 Social housing construction report'),
  p(`The Department of Housing’s quarterly status report lists social housing construction and turnkey projects by name, units, funding programme and stage, without planning references or coordinates. It was matched to the study schemes on name, address and unit count. ${F.sh_n} schemes (${F.sh_units} units) matched with confidence and consistent dates; these supply public ownership (including ${F.sh_turnkey} turnkey purchases), and completion dates for ${F.sh_completed} schemes that CIS had not recorded as complete. Buy and Renew, remedial works and rows that could not be matched with confidence were not used.`),
  h2('2.5 Limitations'),
  bullet('Sample sizes in the 50–99 and 100+ bands are small, particularly for completed schemes. Treat those medians as indicative.'),
  bullet('Durations from permission to start are measured only for schemes that have started. The cumulative start shares in Section 3 cover all permissions and are the fairer measure of how many permissions get built.'),
  bullet('CIS records reasons for delay only occasionally, so barriers are mostly inferred from the planning and building control record rather than stated by developers.'),
  bullet('Completion certificates under-record units (see Appendix A), so completions rely on CIS.'),
];

const s3 = [
  h1('3. How long does it take to get started?'),
  figTitle('Figure 1. Median time from application to completion, by scheme size'),
  img('charts/c1_timeline.png', 16),
  caption('Medians of each stage calculated separately; the total is indicative, not the median of end-to-end times. Source: national planning register, NBCO commencement notices, CIS.'),
  p(`Across all sizes, permission takes a median of about ${F.approval_months} months from lodgement, and it barely varies with scheme size. The bigger variation is in what happens after permission.`),
  table(T.timeline, split(5, 2000)),
  caption('Median years, with number of schemes measured in brackets. Build rate is the median of completed schemes.'),
  h2('3.1 The planning path'),
  p(`Further information requests and appeals account for most of the variation in approval times. Where the Council asked for further information, the median rose from ${F.nofi_med} to ${F.fi_med} years. Appealed decisions took a median of ${F.appeal_med} years. Further information was requested on ${F.fi_share} of the applications in this group.`),
  table(T.path, split(5, 3800)),
  caption('Standard and LRD applications in the council planning register. SHD and Part 8 excluded.'),
  h2('3.2 From permission to start on site'),
  figTitle('Figure 2. Share of permitted schemes started, by time since permission'),
  img('charts/c2_started_over_time.png', 14.5),
  caption('Each point covers only permissions old enough to have reached that time.'),
  p(`About a quarter of schemes start within a year of permission and ${F.st2} within two years. By five years, ${F.st5} have started. Schemes of 25–99 units have the highest start rate by five years (${F.st5_mid}); schemes of 1–24 units reach ${F.st5_small}. The 100+ band has too few older permissions to measure beyond four years.`),
  table(T.started, split(6, 2000)),
  caption('% of schemes started (number of permissions old enough to be measured).'),
];

const s4 = [
  h1('4. Public and private delivery'),
  p(`Public schemes account for ${F.pub_n} of the ${F.schemes} schemes and ${F.pub_units} units (${F.pub_share}). Most are local authority schemes (${F.la_n} schemes, ${F.la_u} units), followed by approved housing bodies (${F.ahb_n} schemes, ${F.ahb_u} units). The Land Development Agency has one scheme in the sample: the former Limerick Gasworks site on Dock Road (25/60780, 285 units), granted in February 2026 and at tender stage.`),
  table(T.sector_timeline, [1000, 1050, 900, 1550, 1650, 1650, CONTENT_W - 7800]),
  caption('Median years (number of schemes measured).'),
  spacer(),
  p(`Public schemes get through planning faster, mainly because Part 8 approvals are not subject to further information requests or appeal. They are slower to start: ${F.pub_st2} had started within two years of approval, against ${F.pri_st2} of private schemes. In our experience, public schemes usually go to tender and seek funding approval after planning, which adds time before a contractor is on site.`),
  figTitle('Figure 3. Share of permitted schemes started, public and private'),
  img('charts/c10_started_by_sector.png', 14),
  caption('Each point covers only permissions old enough to have reached that time.'),
  table(T.started_sector, split(6, 2000)),
  caption('% of schemes started (number of permissions old enough to be measured).'),
  spacer(),
  p(`Measured by units rather than schemes, public delivery holds up: on permissions at least two years old, ${F.pub_coh_pct} of public units have started against ${F.pri_coh_pct} of private units. The difference reflects a larger number of small public schemes that have not started alongside larger public schemes that have.`),
  table(T.owner, split(6, 2800)),
  caption('Permissions at least two years old.'),
];

const s5 = [
  h1('5. How quickly do schemes build out?'),
  p(`${F.n_complete} schemes in the sample have been completed. The median build period was ${F.build_med} years. Build-out rates rise with scheme size: larger schemes run more units in parallel.`),
  figTitle('Figure 4. Median build-out rate of completed schemes, by size'),
  img('charts/c8_build_rates.png', 14),
  caption('Dwellings per annum = units ÷ build period. Source: NBCO commencement notices, CIS completion updates.'),
  table(T.build, split(5, 2400)),
  spacer(),
  p('Few large schemes have completed in Limerick since 2018, which limits what can be said about build-out on the 100+ unit permissions now in the pipeline.'),
  h2('5.1 Delivery over time'),
  figTitle('Figure 5. Units granted, started and completed per year (study sample)'),
  img('charts/c3_annual_flows.png', 16),
  caption('2026 runs to September. Completions count schemes CIS records as fully complete; completed phases on sites still under construction are not included. Source: planning register, NBCO, CIS.'),
  p(`Permissions have run ahead of starts in most years. In the first nine months of 2026, ${F.granted_2026} units were granted, including several large LRD schemes in Castletroy, Mungret, Singland and Dock Road. Starts peaked in ${F.start_peak_year} at ${F.start_peak} units. Completions are low relative to starts because most recently started schemes are still under construction.`),
];

const s6 = [
  h1('6. Barriers to delivery'),
  p(`CIS rarely records why a scheme has not progressed. ${F.onhold} schemes carry notes such as “on hold” or “no movement”, one was quashed following a legal challenge, and two sites were reported for sale. The planning and building control record gives a fuller picture of where delivery slows.`),
  table(T.barriers, split(3, 6400)),
  caption('Counts overlap: a scheme can appear under several indicators.'),
  spacer(),
  h2('6.1 Which permissions are least likely to start?'),
  p(`The tables below cover permissions granted at least two years before September 2026 (${F.coh_n} schemes, ${F.coh_units} units), so every scheme has had time to start. ${F.coh_pct} of those units have started.`),
  table(T.route, split(6, 2600)),
  caption('Permissions at least two years old.'),
  spacer(),
  p(`Standard planning applications and Part 8 schemes start at similar rates by units (${F.std_pct} and ${F.p8_pct}). Two of the six SHD permissions have started, accounting for ${F.shd_pct} of their ${F.shd_units} units. Among the four not started, the largest are Raheen (384 units, CIS: commencement expected), Clonmacken Gardens (165 units) and Annacotty (137 units, now past expiry).`),
  table(T.type, split(6, 2600)),
  caption('Permissions at least two years old. Type from bedroom mix or development description.'),
  spacer(),
  p('Houses and apartments start at similar rates by units. Student accommodation stands out: one of five older student permissions has started. The largest student permissions in the sample, including Punches Cross and the 196-unit Castletroy scheme granted in 2025, have not started.'),
];

const s7 = [
  h1('7. Expiring permissions'),
  figTitle('Figure 6. Units not started, by time to expiry'),
  img('charts/c5_expiry_profile.png', 14.5),
  caption('Expiry from the planning register, updated for granted extensions of duration. Part 8 schemes have no register expiry. Source: planning register, NBCO, CIS.'),
  p(`Of the ${F.u_ns} permitted units not started, ${F.exp_more} have more than three years left on their permission. The near-term pipeline at risk is smaller: ${F.exp_past} units are already past expiry, ${F.exp_12} expire within 12 months and ${F.exp_24} within 12 to 24 months.`),
  table(T.expiry, [1900, 1000, ...Array(7).fill(Math.floor((CONTENT_W - 2900) / 7))], { small: true }),
  caption('Units not started, by LEA and expiry window.'),
  spacer(),
  h2('7.1 Watchlist: schemes of 10+ units past or near expiry'),
  p('These schemes have not started according to building control and CIS records and are past expiry or within two years of it. Each should be checked against the planning file and building control before the Council acts on it, since a start may have been notified under a different reference.'),
  table(T.watch, [3100, 1250, 1900, 900, 700, CONTENT_W - 7850]),
  caption('Scheme names are CIS project headings. Area is the city neighbourhood where applicable, otherwise the LEA.'),
];

const s8 = [
  h1('8. Location'),
  h2('8.1 County'),
  figTitle('Figure 7. Status of permitted units by Local Electoral Area'),
  img('charts/c4_status_by_lea.png', 16),
  caption('All permitted schemes in the sample. Source: planning register, NBCO, CIS; LEA boundaries Tailte Éireann (2019).'),
  p(`Among older permissions, Limerick City East has the highest start rate (${F.lea_east} of units), followed by City West (${F.lea_west}) and City North (${F.lea_north}). The county LEAs have smaller volumes and lower start rates: ${F.ar_started} of ${F.ar_units} units in Adare-Rathkeale and ${F.nw_started} of ${F.nw_units} in Newcastle West. Of the unstarted units in City East, ${F.ce_recent_share} are on permissions granted since January 2025.`),
  table(T.lea, split(6, 2600)),
  caption('Permissions at least two years old.'),
  figTitle('Figure 8. Permitted schemes by status, County Limerick'),
  img('charts/c6_map_county.png', 16),
  h2('8.2 Limerick city neighbourhoods'),
  p(`The nine city neighbourhoods hold ${F.city_units} permitted units across ${F.city_schemes} schemes, ${F.city_share} of the county total. The boundaries follow the Council’s grouping of 42 Electoral Divisions; King’s Island (coded 1a) is shown separately from the rest of the City Centre. Mungret, Patrickswell and the county towns fall outside the nine neighbourhoods and are reported as outside.`),
  figTitle('Figure 9. Status of permitted units by city neighbourhood'),
  img('charts/c9_status_by_nbhd.png', 16),
  caption('All permitted schemes. Neighbourhood boundaries: Limerick City and County Council (42 Electoral Divisions).'),
  table(T.nbhd_status, [2300, 800, 950, 1150, 1150, 950, 1000, CONTENT_W - 8300], { small: true }),
  caption('Units with permission by status. Public share = units on local authority, AHB and LDA schemes.'),
  spacer(),
  p(`${F.nb_top1} carries the largest volume, mostly large private permissions: ${F.ct_ns} of its units have not yet started, almost all on permissions granted in 2025 and 2026. Dooradoyle is similar: ${F.dd_ns} units not started, most on 2025–26 permissions. In Caherdavin, by contrast, the unstarted units are on older permissions.`),
  p(`The City Centre is different. Apart from King’s Island (one older scheme, not started), it has the lowest start rate in the city on older permissions: ${F.nb_cc} of ${F.nb_cc_u} units. ${F.cc_ns} of its ${F.cc_total} permitted units have not started. Its public share (${F.cc_pub_share}) is driven by the LDA’s 285-unit Dock Road scheme. The other unstarted schemes are mostly small private apartment and mixed-use schemes, a median of 13 units, several of them conversions of existing buildings.`),
  table(T.nbhd_impl, split(6, 2800)),
  caption('Permissions at least two years old. Small counts in some neighbourhoods make percentages volatile.'),
  figTitle('Figure 10. Permitted schemes by status, Limerick city neighbourhoods'),
  img('charts/c7_map_city.png', 16),
  caption('Circle area proportional to units.'),
];

const s9 = [
  h1('9. Implications for the Council'),
  p('The points below are our professional view, drawing on the findings above.'),
  bullet([b('Focus engagement on the near-expiry list. '), r(`About ${F.exp_risk} units are past expiry or will expire within two years without starting. Contacting the owners of the larger schemes on the watchlist would establish which are likely to proceed, which need an extension, and which are unlikely to be built.`)]),
  bullet([b('Track the 2025–26 permissions early. '), r(`About ${F.ns_recent} unstarted units sit on permissions less than two years old, mostly large schemes in Castletroy/Annacotty, Dooradoyle, the City Centre and Mungret. Roughly half of permissions start within two years, so a 12-month check on each is worthwhile.`)]),
  bullet([b('Shorten the post-approval stage for public schemes. '), r('Public schemes clear planning quickly but take longer to reach site. Running tender preparation and funding approval alongside the Part 8 process, where possible, would narrow the gap.')]),
  bullet([b('Look at the City Centre separately. '), r('Its start rate is among the lowest in the city, and most of its unstarted schemes are small apartment schemes and conversions. The barriers there, such as construction cost on constrained or older buildings, are likely to differ from the suburban pipeline.')]),
  bullet([b('Reduce further information requests where possible. '), r('They roughly triple the median approval time for private schemes. Better pre-application engagement on the issues that trigger them is likely to shorten the planning stage more than any other change within the Council’s control.')]),
  bullet([b('Fix the completions record. '), r('Completion certificates under-record units by a wide margin in this sample. Checking unit counts on certificates, or recording completions at site level each quarter, would give the Council reliable delivery figures.')]),
  bullet([b('Ask why schemes stall. '), r('A short survey of permission holders with unstarted schemes of 10+ units would turn the inferred barriers in Section 6 into stated ones: viability, finance, infrastructure or sale.')]),
  bullet([b('Repeat annually. '), r('The method uses public data and can be refreshed each year.')]),
];

const appendix = [
  h1('Appendix A. Data coverage'),
  table(T.sources, [6400, CONTENT_W - 6400]),
  spacer(),
  p(`Completion certificates are the only official site-level record of completions. For the ${F.n_complete} completed schemes, certificates exist for ${F.ccc_n} but record ${F.ccc_units} units against ${F.cis_units}. This could reflect how units are entered on certificates, phased certificates not yet lodged, or schemes certified under a different reference.`),
  h1('Appendix B. Start rate by scheme size'),
  table(T.size, split(6, 2600)),
  caption('Permissions at least two years old.'),
  h1('Appendix C. Companion data'),
  p('The accompanying workbook (Limerick_Delivery_Study_Data.xlsx) contains the scheme-level dataset, every table in this report and the full expiry watchlist. Status tables in the workbook update from the scheme sheet.'),
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
      children: [...summary, ...intro, ...method, ...s3, ...s4, ...s5, ...s6, ...s7, ...s8, ...s9, ...appendix],
    },
  ],
});
Packer.toBuffer(doc).then(buf => { fs.writeFileSync('Limerick_Residential_Delivery_Study.docx', buf); console.log('ok'); });
