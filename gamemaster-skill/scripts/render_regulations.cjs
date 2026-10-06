// Internal Word backend. Python validates and resolves the style profile first.
const fs = require('node:fs');
const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell, WidthType,
  Footer, Header, PageNumber, AlignmentType, ShadingType, TableLayoutType,
  BorderStyle, TabStopType, LineRuleType, Tab, PageOrientation
} = require('docx');
const [input, output] = process.argv.slice(2);
const d = JSON.parse(fs.readFileSync(input, 'utf8'));
if (!d._word_style) throw new Error('Use render_regulations.py to validate the document and style profile.');
if (fs.existsSync(output)) throw new Error('Output exists; use a new version filename.');
const s = d._word_style;
const mm = value => Math.round(value * 1440 / 25.4);
const pt = value => Math.round(value * 20);
const halfPt = value => Math.round(value * 2);
const page = s.page;
const total = mm(page.width_mm) - mm(page.margins_mm.left) - mm(page.margins_mm.right);
const font = heading => ({ascii:s.fonts.latin, hAnsi:s.fonts.latin, cs:s.fonts.latin,
                         eastAsia: heading ? s.fonts.heading_cjk : s.fonts.cjk});
const styleIds = {body:'Normal', lead:'RegLead', issuer:'RegIssuer', date:'RegDate', note:'RegNote'};
function paragraph(text, style='Normal', options={}) {
  return new Paragraph({style, children:[new TextRun({text})], ...options});
}
function textParagraphs(text, style='Normal', options={}) {
  // A source newline creates a real Word paragraph, never a newline in w:t.
  return text.split('\n').map(part=>paragraph(part, style, options));
}
function measureLabel(text) {
  // For hanging indent only; authored labels remain literal text, never padded spaces.
  return [...text].reduce((n,c)=>n+(/[\u0000-\u00ff]/.test(c) ? 0.55 : 1), 0) + 0.4;
}
function table(block) {
  const n = block.headers.length;
  let widths;
  if (block.column_widths_mm) {
    widths = block.column_widths_mm.map(mm);
    // Correct rounding only when explicitly full-width.
    const requested = block.column_widths_mm.reduce((a,b)=>a+b,0);
    const bodyMm = page.width_mm-page.margins_mm.left-page.margins_mm.right;
    if (Math.abs(requested-bodyMm)<0.01) widths[n-1] += total-widths.reduce((a,b)=>a+b,0);
  } else {
    widths = Array(n).fill(Math.floor(total/n));
    widths[n-1] += total-widths.reduce((a,b)=>a+b,0);
  }
  const border = {style:BorderStyle.SINGLE,size:4,color:s.table.border_color};
  return new Table({width:{size:widths.reduce((a,b)=>a+b,0),type:WidthType.DXA},
    columnWidths:widths, layout:TableLayoutType.FIXED, alignment:AlignmentType.CENTER,
    borders:{top:border,bottom:border,left:border,right:border,insideHorizontal:border,insideVertical:border},
    rows:[block.headers,...block.rows].map((row,i)=>new TableRow({
      tableHeader:i===0,
      cantSplit:i===0 || !(block.allow_row_split ?? s.table.allow_row_split),
      children:row.map((cell,j)=>new TableCell({
        width:{size:widths[j],type:WidthType.DXA},
        margins:{top:mm(s.table.padding_mm),bottom:mm(s.table.padding_mm),left:mm(s.table.padding_mm),right:mm(s.table.padding_mm)},
        shading:i===0 ? {fill:s.table.header_fill,type:ShadingType.CLEAR}:undefined,
        children:textParagraphs(cell, i===0 ? 'RegTableHeader':'RegTable')
      }))
    }))});
}
function blocks(items) {
  const result=[];
  for (const b of items) {
    if (b.type==='paragraph') result.push(...textParagraphs(b.text,styleIds[b.style||'body']));
    else if (b.type==='heading') result.push(paragraph(b.text,'Heading'+b.level));
    else if (b.type==='clause') {
      const hang = pt(s.sizes_pt.body*measureLabel(b.label));
      const left = pt((b.level-1)*s.paragraph.clause_level_indent_chars*s.sizes_pt.body)+hang;
      result.push(new Paragraph({style:'RegClause',indent:{left,hanging:hang},
        tabStops:[{type:TabStopType.LEFT,position:left}],
        children:[new TextRun({text:b.label}),new TextRun({children:[new Tab()]}),new TextRun({text:b.text})]}));
    } else if (b.type==='table') {
      if (b.caption) result.push(paragraph(b.caption,'RegCaption'));
      result.push(table(b),paragraph('', 'RegTableGap'));
    } else if (b.type==='page_break') result.push(paragraph('', 'RegBreak', {pageBreakBefore:true}));
    else if (b.type==='appendix') {
      result.push(paragraph(b.title,'RegAppendix',{pageBreakBefore:true}));
      result.push(...blocks(b.blocks));
    } else throw new Error('Unsupported block '+b.type);
  }
  return result;
}
const children=[paragraph(d.title,'Title')];
if(d.subtitle) children.push(paragraph(d.subtitle,'Subtitle'));
children.push(paragraph(d.status==='draft' ? '草案｜待确认内容不可作为正式发布依据':(d.document_label||'竞赛规程'),'RegLabel'));
for (const section of d.sections) {
  children.push(paragraph(section.heading,'Heading'+(section.level||1)));
  children.push(...blocks(section.blocks));
}
const normalSpacing={line:Math.round(240*s.paragraph.line_multiple),lineRule:LineRuleType.AUTO,
                     after:pt(s.paragraph.space_after_pt),before:0};
const cleanIndent={left:0,right:0,firstLine:0,firstLineChars:0};
const styles=[
  {id:'Normal',name:'Normal',run:{font:font(false),size:halfPt(s.sizes_pt.body),color:'000000'},
   paragraph:{alignment:AlignmentType.JUSTIFIED,spacing:normalSpacing,indent:{firstLineChars:Math.round(s.paragraph.first_line_chars*100)},widowControl:true}},
  {id:'Title',name:'Title',basedOn:'Normal',next:'Normal',run:{font:font(true),size:halfPt(s.sizes_pt.title),bold:true},
   paragraph:{alignment:AlignmentType.CENTER,indent:cleanIndent,keepNext:true,keepLines:true,spacing:{before:0,after:pt(12),line:312,lineRule:LineRuleType.AUTO}}},
  {id:'Subtitle',name:'Subtitle',basedOn:'Normal',run:{size:halfPt(s.sizes_pt.subtitle)},
   paragraph:{alignment:AlignmentType.CENTER,indent:cleanIndent,keepNext:true,spacing:{before:0,after:pt(6)}}},
  {id:'RegLabel',name:'规程状态',basedOn:'Subtitle',paragraph:{keepNext:true,spacing:{after:pt(12)}}},
  ...[1,2,3].map(level=>({id:'Heading'+level,name:'Heading '+level,basedOn:'Normal',next:'Normal',quickFormat:true,
    run:{font:font(true),size:halfPt(s.sizes_pt['heading'+level]),bold:true},
    paragraph:{outlineLevel:level-1,alignment:AlignmentType.LEFT,indent:cleanIndent,keepNext:true,keepLines:true,
               spacing:{before:pt(level===1?12:6),after:pt(6),line:312,lineRule:LineRuleType.AUTO}}})),
  {id:'RegClause',name:'悬挂条目',basedOn:'Normal',paragraph:{indent:cleanIndent,widowControl:true}},
  {id:'RegLead',name:'导语',basedOn:'Normal',paragraph:{indent:cleanIndent}},
  {id:'RegIssuer',name:'落款单位',basedOn:'Normal',paragraph:{alignment:AlignmentType.RIGHT,indent:cleanIndent,keepNext:true,keepLines:true,spacing:{before:pt(12),after:0}}},
  {id:'RegDate',name:'落款日期',basedOn:'Normal',paragraph:{alignment:AlignmentType.RIGHT,indent:cleanIndent,keepLines:true,spacing:{after:pt(6)}}},
  {id:'RegNote',name:'注释',basedOn:'Normal',run:{size:halfPt(s.sizes_pt.note)},paragraph:{indent:cleanIndent}},
  {id:'RegTable',name:'表格正文',basedOn:'Normal',run:{size:halfPt(s.sizes_pt.table)},
   paragraph:{alignment:AlignmentType.LEFT,indent:cleanIndent,spacing:{before:0,after:0,line:Math.round(240*s.table.line_multiple),lineRule:LineRuleType.AUTO},keepNext:false}},
  {id:'RegTableHeader',name:'表格表头',basedOn:'RegTable',run:{bold:true},paragraph:{alignment:AlignmentType.CENTER,keepNext:false}},
  {id:'RegCaption',name:'表格标题',basedOn:'RegTable',run:{bold:true},paragraph:{alignment:AlignmentType.CENTER,keepNext:true,spacing:{before:pt(6),after:pt(6)}}},
  {id:'RegTableGap',name:'表后间隔',basedOn:'Normal',run:{size:2},paragraph:{indent:cleanIndent,spacing:{line:20,after:pt(6)}}},
  {id:'RegAppendix',name:'附件标题',basedOn:'Heading1',paragraph:{outlineLevel:0}},
  {id:'RegHeaderFooter',name:'页眉页脚',basedOn:'Normal',run:{size:halfPt(s.sizes_pt.header_footer)},
   paragraph:{alignment:AlignmentType.CENTER,indent:cleanIndent,spacing:{before:0,after:0,line:240,lineRule:LineRuleType.AUTO}}},
  {id:'RegBreak',name:'分页控制',basedOn:'Normal',run:{size:2},paragraph:{indent:cleanIndent,spacing:{before:0,after:0,line:20}}}
];
const section={properties:{page:{size:{width:mm(Math.min(page.width_mm,page.height_mm)),height:mm(Math.max(page.width_mm,page.height_mm)),
  orientation:page.width_mm>page.height_mm ? PageOrientation.LANDSCAPE:PageOrientation.PORTRAIT},
  margin:{...Object.fromEntries(Object.entries(page.margins_mm).map(([k,v])=>[k,mm(v)])),header:mm(page.header_mm),footer:mm(page.footer_mm)}}},children};
if(s.header_text) section.headers={default:new Header({children:[paragraph(s.header_text,'RegHeaderFooter')]})};
if(s.page_numbers) section.footers={default:new Footer({children:[new Paragraph({style:'RegHeaderFooter',children:[
  new TextRun('第 '),new TextRun({children:[PageNumber.CURRENT]}),new TextRun(' 页 / 共 '),
  new TextRun({children:[PageNumber.TOTAL_PAGES]}),new TextRun(' 页')
]})]})};
const doc = new Document({title:d.title,creator:'gamemaster',styles:{default:{document:{run:{font:font(false),size:halfPt(s.sizes_pt.body)}}},paragraphStyles:styles},sections:[section]});
Packer.toBuffer(doc).then(data=>fs.writeFileSync(output,data,{flag:'wx'})).catch(error=>{console.error(error.message);process.exitCode=1;});
