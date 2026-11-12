# -*- coding: utf-8 -*-
"""docx OOXML 操作辅助函数"""
import copy
from lxml import etree

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
V = "urn:schemas-microsoft-com:vml"
W10 = "urn:schemas-microsoft-com:office:word"
XML = "http://www.w3.org/XML/1998/namespace"


def q(t, ns=W):
    return "{%s}%s" % (ns, t)


def is_red(run):
    rp = run.find(q("rPr"))
    if rp is None:
        return False
    c = rp.find(q("color"))
    return c is not None and (c.get(q("val")) or "").upper() == "FF0000"


def clean_red(root):
    """删掉红色模板文字；含 br/tab 的红 run 只去色，表格内红 run 只去色"""
    for r in list(root.iter(q("r"))):
        rp = r.find(q("rPr"))
        if rp is None:
            continue
        c = rp.find(q("color"))
        if c is None or (c.get(q("val")) or "").upper() != "FF0000":
            continue
        has_br = r.find(q("br")) is not None
        has_tab = r.find(q("tab")) is not None
        in_tbl = any(a.tag == q("tbl") for a in r.iterancestors())
        if in_tbl:
            for cc in rp.findall(q("color")):
                rp.remove(cc)
        elif has_br or has_tab:
            for cc in rp.findall(q("color")):
                rp.remove(cc)
            for t in r.findall(q("t")):
                r.remove(t)
        else:
            r.getparent().remove(r)
    for rp in root.iter(q("rPr")):
        for cc in rp.findall(q("color")):
            if (cc.get(q("val")) or "").upper() == "FF0000":
                rp.remove(cc)
    for ppr in root.iter(q("pPr")):
        for cc in ppr.findall(q("color")):
            if (cc.get(q("val")) or "").upper() == "FF0000":
                ppr.remove(cc)


def text_runs(p):
    return [r for r in p if r.tag == q("r") and r.find(q("t")) is not None]


def set_text(run, text):
    ts = run.findall(q("t"))
    if not ts:
        ts = [etree.SubElement(run, q("t"))]
    for t in ts[1:]:
        run.remove(t)
    ts[0].text = text
    ts[0].set("{%s}space" % XML, "preserve")


def set_para(p, text, keep_br=True):
    trs = text_runs(p)
    target = trs[-1] if trs else None
    for r in [c for c in p if c.tag == q("r")]:
        if r is target:
            continue
        if keep_br and (r.find(q("br")) is not None or r.find(q("tab")) is not None
                        or r.find(q("pict")) is not None):
            continue
        p.remove(r)
    if target is None:
        target = etree.SubElement(p, q("r"))
        ppr = p.find(q("pPr"))
        if ppr is not None and ppr.find(q("rPr")) is not None:
            target.append(copy.deepcopy(ppr.find(q("rPr"))))
        etree.SubElement(target, q("t"))
    set_text(target, text)


def set_two(p, first, second):
    trs = text_runs(p)
    if not trs:
        return
    for r in trs[1:-1]:
        p.remove(r)
    if first is not None:
        set_text(trs[0], first)
    if len(trs) > 1:
        set_text(trs[-1], second)


PPR_ORDER = ["pStyle", "keepNext", "keepLines", "pageBreakBefore", "framePr", "widowControl",
             "numPr", "suppressLineNumbers", "pBdr", "shd", "tabs", "suppressAutoHyphens",
             "kinsoku", "wordWrap", "overflowPunct", "topLinePunct", "autoSpaceDE",
             "autoSpaceDN", "bidi", "adjustRightInd", "snapToGrid", "spacing", "ind",
             "contextualSpacing", "mirrorIndents", "suppressOverlap", "jc", "textDirection",
             "textAlignment", "textboxTightWrap", "outlineLvl", "divId", "cnfStyle", "rPr",
             "sectPr", "pPrChange"]


def add_page_break_before(p):
    ppr = p.find(q("pPr"))
    if ppr is None:
        ppr = etree.Element(q("pPr"))
        p.insert(0, ppr)
    for old in ppr.findall(q("pageBreakBefore")):
        ppr.remove(old)
    pos = 0
    for i, ch in enumerate(ppr):
        ln = etree.QName(ch).localname
        if ln in PPR_ORDER and PPR_ORDER.index(ln) < PPR_ORDER.index("pageBreakBefore"):
            pos = i + 1
    el = etree.Element(q("pageBreakBefore"))
    ppr.insert(pos, el)


def set_heading(p, text, page_break=False):
    for r in [c for c in p if c.tag == q("r")]:
        if is_red(r) or r.find(q("br")) is not None:
            p.remove(r)
    trs = [r for r in p if r.tag == q("r") and r.find(q("t")) is not None]
    keep = trs[0] if trs else None
    for r in [c for c in p if c.tag == q("r")]:
        if r is not keep:
            p.remove(r)
    if keep is None:
        keep = etree.SubElement(p, q("r"))
        etree.SubElement(keep, q("t"))
    set_text(keep, text)
    if page_break:
        add_page_break_before(p)


def drop_ind(p):
    ppr = p.find(q("pPr"))
    if ppr is not None:
        for i in ppr.findall(q("ind")):
            ppr.remove(i)


def center(p):
    ppr = p.find(q("pPr"))
    if ppr is None:
        ppr = etree.Element(q("pPr"))
        p.insert(0, ppr)
    for j in ppr.findall(q("jc")):
        ppr.remove(j)
    jc = etree.SubElement(ppr, q("jc"))
    jc.set(q("val"), "center")


IMG_PPR = ('<w:pPr xmlns:w="%s"><w:widowControl/><w:spacing w:line="240" w:lineRule="auto"/>'
           '<w:ind w:firstLine="0" w:firstLineChars="0"/><w:jc w:val="center"/></w:pPr>') % W


def make_img_para(pict_run, wpt, hpt):
    p = etree.Element(q("p"))
    p.append(etree.fromstring(IMG_PPR))
    run = copy.deepcopy(pict_run)
    for sh in run.iter("{%s}shape" % V):
        sh.set("style", "height:%.2fpt;width:%.2fpt;" % (hpt, wpt))
        for tag in ("wrap", "anchorlock"):
            for e in sh.findall("{%s}%s" % (W10, tag)):
                sh.remove(e)
    p.append(run)
    return p


def detach_pict(p):
    """摘出段落里的 pict run 并从原段删除"""
    for r in [c for c in p if c.tag == q("r")]:
        if r.find(q("pict")) is not None:
            p.remove(r)
            return r
    return None


def inline_pict_inplace(p, wpt, hpt):
    for sh in p.iter("{%s}shape" % V):
        sh.set("style", "height:%.2fpt;width:%.2fpt;" % (hpt, wpt))
        for tag in ("wrap", "anchorlock"):
            for e in sh.findall("{%s}%s" % (W10, tag)):
                sh.remove(e)


def set_cell(tc, lines):
    ps = tc.findall(q("p"))
    if not ps:
        p = etree.SubElement(tc, q("p"))
        ps = [p]
    last = ps[-1]
    for i, line in enumerate(lines):
        if i < len(ps):
            set_para(ps[i], line)
        else:
            np_ = copy.deepcopy(last)
            set_para(np_, line)
            last.addnext(np_)
            last = np_
    for p in ps[len(lines):]:
        tc.remove(p)


def fill_table(tbl, rows):
    trs = tbl.findall(q("tr"))
    for tr in trs:
        tbl.remove(tr)
    n = len(rows)
    for i, row in enumerate(rows):
        src = trs[0] if i == 0 else (trs[-1] if i == n - 1 else trs[2])
        tr = copy.deepcopy(src)
        tcs = tr.findall(q("tc"))
        for tc, val in zip(tcs, row):
            set_cell(tc, val if isinstance(val, list) else [val])
        tbl.append(tr)
