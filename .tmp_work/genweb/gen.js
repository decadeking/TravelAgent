"use strict";
const fs = require("fs");
const path = require("path");
const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
  ImageRun, Header, Footer, AlignmentType, BorderStyle, WidthType,
  VerticalAlign, PageNumber, PageBreak, ShadingType,
} = require("docx");

const C = require("./content.js");

const CJK = "SimSun";      // 黑体用 SimHei，正文宋体 SimSun
const HEI = "SimHei";
const ASCII = "Times New Roman";

// 图片绝对路径
function imgPath(idx) {
  const m = C.IMAGES[idx];
  const base = m.dir === "diag" ? C.IMG_DIR : C.SHOT_DIR;
  return path.join(base, m.file);
}

// 三线表边框
const tb = { style: BorderStyle.SINGLE, size: 12, color: "000000" };
const tn = { style: BorderStyle.SINGLE, size: 4, color: "000000" };
const none = { style: BorderStyle.NONE, size: 0, color: "FFFFFF" };
const threeLine = {
  top: tb, bottom: tb, left: none, right: none,
  insideHorizontal: tn, insideVertical: none,
};

function para(text, opts) {
  return new Paragraph({
    alignment: (opts && opts.align) || AlignmentType.JUSTIFIED,
    indent: (opts && opts.indent !== undefined) ? opts.indent : { firstLine: 480 },
    spacing: (opts && opts.spacing) || { line: 360, lineRule: "auto" },
    children: [new TextRun({
      text,
      font: { ascii: ASCII, hAnsi: ASCII, eastAsia: CJK },
      size: (opts && opts.size) || 24,
      bold: (opts && opts.bold) || false,
    })],
    running: opts && opts.running,
  });
}

function heading(text, level) {
  const sizes = { 1: 32, 2: 28, 3: 24 };
  const fonts = { 1: HEI, 2: HEI, 3: HEI };
  const aligns = { 1: AlignmentType.CENTER, 2: AlignmentType.LEFT, 3: AlignmentType.LEFT };
  return new Paragraph({
    alignment: aligns[level],
    spacing: level === 1 ? { before: 240, after: 240, line: 360, lineRule: "auto" }
                         : { before: 120, after: 120, line: 360, lineRule: "auto" },
    pageBreakBefore: level === 1,
    children: [new TextRun({
      text, bold: true,
      font: { ascii: fonts[level], hAnsi: fonts[level], eastAsia: fonts[level] },
      size: sizes[level],
    })],
  });
}

function imagePara(idx, caption) {
  const m = C.IMAGES[idx];
  const alt = caption.replace(/^图\d+\.\d+\s*/, "");
  return [
    new Paragraph({
      alignment: AlignmentType.CENTER,
      spacing: { before: 120, after: 60, line: 240, lineRule: "auto" },
      children: [new ImageRun({
        type: "png",
        data: fs.readFileSync(imgPath(idx)),
        transformation: { width: m.w, height: m.h },
        altText: { title: caption, description: alt, name: caption },
      })],
    }),
    new Paragraph({
      alignment: AlignmentType.CENTER,
      spacing: { before: 60, after: 120, line: 240, lineRule: "auto" },
      children: [new TextRun({ text: caption, font: { ascii: HEI, hAnsi: HEI, eastAsia: HEI }, size: 21 })],
    }),
  ];
}

function tablePara(title, tdef) {
  const rows = tdef.rows;
  const cols = tdef.head.length;
  const colW = Math.floor(9026 / cols);
  const cellOpts = {
    borders: threeLine,
    width: { size: colW, type: WidthType.DXA },
    margins: { top: 80, bottom: 80, left: 100, right: 100 },
    verticalAlign: VerticalAlign.CENTER,
  };
  const mkCell = (txt, head) => new TableCell({
    ...cellOpts,
    shading: head ? { fill: "FFFFFF", type: ShadingType.CLEAR } : undefined,
    children: [new Paragraph({
      alignment: AlignmentType.CENTER,
      spacing: { line: 240, lineRule: "auto" },
      children: [new TextRun({
        text: txt,
        font: { ascii: ASCII, hAnsi: ASCII, eastAsia: CJK },
        size: 21,
        bold: head || false,
      })],
    })],
  });
  const hrow = new TableRow({
    cantSplit: true,
    tableHeader: true,
    children: tdef.head.map((h) => mkCell(h, true)),
  });
  const bodyRows = rows.map((r) => new TableRow({
    cantSplit: true,
    children: r.map((c) => mkCell(String(c), false)),
  }));
  return [
    new Paragraph({
      alignment: AlignmentType.CENTER,
      spacing: { before: 120, after: 60, line: 240, lineRule: "auto" },
      children: [new TextRun({ text: title, font: { ascii: HEI, hAnsi: HEI, eastAsia: HEI }, size: 21 })],
    }),
    new Table({
      width: { size: 9026, type: WidthType.DXA },
      columnWidths: tdef.head.map(() => colW),
      rows: [hrow].concat(bodyRows),
    }),
    new Paragraph({ children: [] }),
  ];
}

function codePara(lines) {
  return lines.map((ln) => new Paragraph({
    spacing: { line: 240, lineRule: "auto" },
    indent: { left: 300 },
    children: [new TextRun({
      text: ln,
      font: { ascii: "Consolas", hAnsi: "Consolas", eastAsia: "SimSun" },
      size: 20,
    })],
  }));
}

// 构建封面
function coverPara(text, opts) {
  const o = opts || {};
  return new Paragraph({
    alignment: o.align || AlignmentType.CENTER,
    spacing: { before: o.before || 0, after: o.after || 0, line: 360, lineRule: "auto" },
    children: [new TextRun({
      text, bold: !!o.bold,
      font: { ascii: ASCII, hAnsi: ASCII, eastAsia: o.hei ? HEI : CJK },
      size: o.size || 28,
    })],
  });
}

// 目录结构（章节列表，不含自动域页码）
const TOC_ITEMS = [
  "第1章 绪论", "1.1 系统开发背景", "1.2 国内外研究现状", "1.3 系统的研究意义", "1.4 系统研究的主要内容",
  "第2章 系统分析", "2.1 系统功能分析", "2.2 系统非功能性分析",
  "第3章 系统设计", "3.1 系统功能模块设计", "3.2 系统数据库设计",
  "第4章 系统实现", "4.1 系统主界面", "4.2 用户功能实现", "4.3 管理员后台功能实现",
  "第5章 系统测试", "5.1 测试的目的", "5.2 测试的内容", "5.3 测试结论",
  "结论", "参考文献", "致谢",
];

function tocPara(txt, lvl) {
  const indent = lvl === 2 ? { left: 480 } : lvl === 3 ? { left: 960 } : undefined;
  return new Paragraph({
    alignment: AlignmentType.LEFT,
    spacing: { line: 360, lineRule: "auto" },
    indent,
    children: [new TextRun({
      text: txt, font: { ascii: ASCII, hAnsi: ASCII, eastAsia: CJK }, size: 24,
    })],
  });
}

let lastWasImg = false;
const children = [];

// 封面
children.push(coverPara("湖南软件职业技术大学", { size: 36, hei: true, after: 240 }));
children.push(coverPara("本科毕业设计（论文）", { size: 32, hei: true, after: 720 }));
children.push(new Paragraph({ children: [new PageBreak()] }));
children.push(coverPara("毕 业 设 计", { size: 40, hei: true, before: 480, after: 480 }));
children.push(coverPara(C.TITLE, { size: 30, hei: true, after: 480 }));
[
  ["学　　院", C.COVER.college],
  ["专　　业", C.COVER.major],
  ["班　　级", C.COVER.className],
  ["学生姓名", C.COVER.name],
  ["学　　号", C.COVER.studentNo],
  ["指导教师", C.COVER.teacher],
  ["完成日期", C.COVER.date],
].forEach(([k, v], i) => {
  children.push(coverPara(k + "　　" + v, { size: 28, hei: true, before: i === 0 ? 720 : 180, align: AlignmentType.LEFT }));
});
children.push(new Paragraph({ children: [new PageBreak()] }));

// 摘要
children.push(coverPara("摘　要", { size: 32, hei: true, after: 240 }));
children.push(para(C.ABS));
children.push(para("关键词：" + C.ABS_KEY, { bold: false, spacing: { line: 360, lineRule: "auto" } }));
children.push(new Paragraph({ children: [new PageBreak()] }));

// Abstract
children.push(coverPara("Abstract", { size: 32, hei: true, after: 240 }));
children.push(para(C.ABSTRACT, { align: AlignmentType.JUSTIFIED }));
children.push(para("Keywords: " + C.ABSTRACT_KEY));
children.push(new Paragraph({ children: [new PageBreak()] }));

// 目录
children.push(coverPara("目　录", { size: 32, hei: true, after: 240 }));
TOC_ITEMS.forEach((t) => {
  if (/^第\d+章/.test(t)) children.push(tocPara(t, 1));
  else if (/^\d+\.\d+\.\d+/.test(t)) children.push(tocPara(t, 3));
  else if (/^\d+\.\d+/.test(t)) children.push(tocPara(t, 2));
  else children.push(tocPara(t, 1));
});
children.push(new Paragraph({ children: [new PageBreak()] }));

// 正文按 SECTIONS 组装，并把表5.1 内容表替换为 TEST5_1_TABLE
const secChildren = [];
C.SECTIONS.forEach((s) => {
  if (s.level !== undefined && s.text) {
    secChildren.push(heading(s.text, s.level));
  } else if (s.image) {
    secChildren.push(...imagePara(s.image, s.caption));
  } else if (s.tableTitle) {
    const tdef = s.tableTitle.startsWith("表5") ? C.TEST5_1_TABLE : s.table;
    secChildren.push(...tablePara(s.tableTitle, tdef));
  } else if (s.code) {
    secChildren.push(...codePara(s.code));
  } else if (s.paras) {
    s.paras.forEach((p) => secChildren.push(para(p)));
  }
});

// 去掉首章标题之前的 leading（heading level1 自带 pageBreakBefore）
children.push(...secChildren);

const doc = new Document({
  creator: "成晓宇",
  title: C.TITLE,
  styles: {
    default: {
      document: {
        run: { font: { ascii: ASCII, hAnsi: ASCII, eastAsia: CJK }, size: 24 },
      },
    },
  },
  sections: [{
    properties: {
      page: {
        size: { width: 12240, height: 15840 }, // US Letter
        margin: { top: 1440, right: 1440, bottom: 1440, left: 1440 },
      },
    },
    headers: {
      default: new Header({
        children: [new Paragraph({
          alignment: AlignmentType.CENTER,
          children: [new TextRun({
            text: C.TITLE, font: { ascii: ASCII, hAnsi: ASCII, eastAsia: CJK }, size: 18,
          })],
        })],
      }),
    },
    footers: {
      default: new Footer({
        children: [new Paragraph({
          alignment: AlignmentType.CENTER,
          children: [
            new TextRun({ children: [PageNumber.CURRENT], font: { ascii: ASCII, hAnsi: ASCII, eastAsia: CJK }, size: 18 }),
          ],
        })],
      }),
    },
    children,
  }],
});

Packer.toBuffer(doc).then((buf) => {
  fs.writeFileSync(path.join(__dirname, "..", "out_docxjs.docx"), buf);
  console.log("GEN OK -> out_docxjs.docx");
}).catch((e) => {
  console.error("GEN FAIL", e);
  process.exit(1);
});
