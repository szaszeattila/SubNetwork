"""Render the revised Markdown report with readable tables and working web links.

Dependencies: reportlab, markdown-it-py. Uses system Noto and DejaVu fonts.
Run with the documented bundled Python runtime or another environment with
those dependencies. Input/output can be overridden for review drafts.
"""
import argparse
import html
from pathlib import Path
import re

from markdown_it import MarkdownIt
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.utils import simpleSplit
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import BaseDocTemplate, Frame, PageTemplate, Paragraph, Spacer, LongTable, TableStyle, HRFlowable, CondPageBreak, KeepTogether

PROJECT=Path(__file__).resolve().parents[3]
for family,stem in [("Body","NotoSerif"),("UI","NotoSans"),("Code","DejaVuSansMono")]:
    fontdir=Path("/usr/share/fonts/truetype/dejavu" if family=="Code" else "/usr/share/fonts/truetype/noto")
    variants={"": "" if family=="Code" else "-Regular", "-Bold":"-Bold", "-Italic":"-Oblique" if family=="Code" else "-Italic", "-BoldItalic":"-BoldOblique" if family=="Code" else "-BoldItalic"}
    for suffix,file_suffix in variants.items():
        pdfmetrics.registerFont(TTFont(family+suffix,str(fontdir/(stem+file_suffix+".ttf"))))
    pdfmetrics.registerFontFamily(family,normal=family,bold=family+"-Bold",italic=family+"-Italic",boldItalic=family+"-BoldItalic")

INK=colors.HexColor("#20303B")
BLUE=colors.HexColor("#245875")
RULE=colors.HexColor("#C9D6DC")
WIDTH=510


def clean(text):
    return text.translate(str.maketrans({"\u2011":"-","\u2010":"-","\u2013":"-","\u2014":" - ","\u00a0":" ","\u202f":" ","✓":"yes","✗":"no","→":"->","−":"-","∩":"intersection","∪":"union","≤":"<=","≥":">="}))


def inline(token,header=False):
    parts=[]
    links=[]
    for child in token.children or []:
        t=child.type
        if t=="text": parts.append(html.escape(clean(child.content)))
        elif t=="code_inline":parts.append('<font name="Code" size="8.2">'+html.escape(clean(child.content))+"</font>")
        elif t=="strong_open":parts.append("<b>")
        elif t=="strong_close":parts.append("</b>")
        elif t=="em_open":parts.append("<i>")
        elif t=="em_close":parts.append("</i>")
        elif t in ("softbreak","hardbreak"):parts.append(" " if t=="softbreak" else "<br/>")
        elif t=="link_open":
            href=child.attrGet("href") or ""
            external=href.startswith(("https://","http://"))
            links.append(external)
            parts.append('<link href="'+html.escape(href,quote=True)+'" color="#245875">' if external else '<font color="#245875">')
        elif t=="link_close":parts.append("</link>" if links.pop() else "</font>")
        elif t=="html_inline":parts.append(html.escape(child.content))
        elif child.content:parts.append(html.escape(clean(child.content)))
    return "".join(parts)


class Report(BaseDocTemplate):
    def __init__(self,path,**kwargs):
        super().__init__(str(path),pagesize=(612,792),leftMargin=51,rightMargin=51,topMargin=48,bottomMargin=46,**kwargs)
        self.addPageTemplates(PageTemplate(id="report",frames=[Frame(51,46,WIDTH,698,leftPadding=0,rightPadding=0,topPadding=0,bottomPadding=0)],onPage=self.footer))
        self.section="Clinical catalogue, measured"
    def footer(self,canvas,doc):
        canvas.saveState()
        canvas.setStrokeColor(RULE);canvas.setLineWidth(.5);canvas.line(51, thirty:=32,561,thirty)
        canvas.setFont("UI",7.4);canvas.setFillColor(BLUE)
        canvas.drawString(51,20,"SubNetwork  |  ChEMBL 37  |  Revised 12 Sep 2026")
        canvas.drawRightString(561,20,str(doc.page))
        canvas.restoreState()
    def afterFlowable(self,flow):
        if isinstance(flow,Paragraph) and getattr(flow,"outline_title",None):
            key="section-"+str(self.seq.nextf("outline"))
            self.canv.bookmarkPage(key)
            self.canv.addOutlineEntry(flow.outline_title,key,level=flow.outline_level,closed=False)


STYLES={
    "body":ParagraphStyle("Body",fontName="Body",fontSize=10.1,leading=14.1,textColor=INK,spaceAfter=7.5,splitLongWords=True),
    "h1":ParagraphStyle("Title",fontName="UI-Bold",fontSize=23,leading=28,textColor=INK,spaceAfter=14,keepWithNext=True),
    "h2":ParagraphStyle("Section",fontName="UI-Bold",fontSize=15,leading=19,textColor=BLUE,spaceBefore=16,spaceAfter=10,keepWithNext=True),
    "h3":ParagraphStyle("Subsection",fontName="UI-Bold",fontSize=11.2,leading=15,textColor=INK,spaceBefore=10,spaceAfter=7,keepWithNext=False),
    "cell":ParagraphStyle("Cell",fontName="UI",fontSize=8.2,leading=11,textColor=INK,spaceAfter=0,splitLongWords=True),
    "head":ParagraphStyle("Head",fontName="UI-Bold",fontSize=8.1,leading=10.6,textColor=INK,spaceAfter=0,splitLongWords=True),
    "code":ParagraphStyle("CodeBlock",fontName="Code",fontSize=8,leading=11,backColor=colors.HexColor("#F2F5F6"),borderPadding=8,spaceBefore=3,spaceAfter=12,splitLongWords=True),
}


def column_widths(rows):
    n=len(rows[0])
    plain=lambda s:html.unescape(re.sub("<[^>]*>","",s))
    if n==2:
        numeric_second=all(re.fullmatch(r"[\d,.%+ /()-]+",plain(r[1]).strip()) for r in rows[1:])
        return [390,120] if numeric_second else [155,355]
    if n==3:
        if plain(rows[0][0]).strip()=="#":return [26,380,104]
        if "Excluded" in plain(rows[0][0]):return [240,75,195]
        longest=max(len(plain(r[0])) for r in rows)
        return [350,80,80] if longest>45 else [230,140,140]
    if n==4:
        if "Evidence basis" in plain(rows[0][0]):return [265,82,82,81]
        if "Flag"==plain(rows[0][0]):return [118,115,59,218]
    numeric=[]
    for j in range(n):
        vals=[plain(r[j]).strip() for r in rows[1:]]
        numeric.append(bool(vals) and sum(bool(re.fullmatch(r"[\d,.%+× /()—–-]*|✓|✗|yes|no",v)) for v in vals)/len(vals)>.75)
    scores=[]
    for j in range(n):
        maxlen=max(len(plain(r[j])) for r in rows)
        scores.append(1 if numeric[j] else min(5.0,max(1.6,maxlen/35)))
    minima=[54 if numeric[j] else 70 for j in range(n)]
    remaining=WIDTH-sum(minima)
    if remaining<0:return [WIDTH/n]*n
    return [mn+remaining*s/sum(scores) for mn,s in zip(minima,scores)]


def make_table(rows):
    # The original 11-column seed table is split into two full-width tables
    # sharing Seed, preserving every column while keeping text readable.
    if len(rows[0])>8:
        groups=[[0,1,2,3,4],[0]+list(range(5,len(rows[0])))]
        out=[]
        for g in groups:
            out.extend(make_table([[r[j] for j in g] for r in rows]))
        return out
    widths=column_widths(rows)
    cells=[[Paragraph(c,STYLES["head" if i==0 else "cell"]) for c in row] for i,row in enumerate(rows)]
    t=LongTable(cells,colWidths=widths,repeatRows=1,hAlign="LEFT",splitByRow=1)
    t.setStyle(TableStyle([
        ("BACKGROUND",(0,0),(-1,0),colors.HexColor("#E7EFF3")),
        ("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white,colors.HexColor("#F7F9FA")]),
        ("LINEBELOW",(0,0),(-1,0),.7,RULE),("LINEBELOW",(0,1),(-1,-1),.35,RULE),
        ("VALIGN",(0,0),(-1,-1),"TOP"),("LEFTPADDING",(0,0),(-1,-1),6),
        ("RIGHTPADDING",(0,0),(-1,-1),6),("TOPPADDING",(0,0),(-1,-1),5),
        ("BOTTOMPADDING",(0,0),(-1,-1),5)]))
    _,height=t.wrap(WIDTH,10000)
    return [KeepTogether([t,Spacer(1,11)])] if height<270 else [t,Spacer(1,11)]


def story(md):
    tokens=MarkdownIt("commonmark").enable("table").parse(md)
    flows=[];i=0;list_stack=[];next_heading=None
    while i<len(tokens):
        t=tokens[i]
        if t.type=="heading_open":
            level=int(t.tag[1]);text=inline(tokens[i+1]);p=Paragraph(text,STYLES["h"+str(min(level,3))])
            if level==2:
                flows.append(CondPageBreak(90));p.outline_title=clean(tokens[i+1].content);p.outline_level=0
            elif level==3:flows.append(CondPageBreak(105))
            flows.append(p);i+=3;continue
        if t.type=="paragraph_open":
            content=inline(tokens[i+1])
            if list_stack:
                state=list_stack[-1];prefix=str(state[1])+"." if state[0]=="ordered" else "-"
                if state[2]:prefix=""
                state[2]=True
                style=ParagraphStyle("List",parent=STYLES["body"],leftIndent=13*len(list_stack),firstLineIndent=0,bulletIndent=0)
                flows.append(Paragraph(content,style,bulletText=prefix))
            else:flows.append(Paragraph(content,STYLES["body"]))
            i+=3;continue
        if t.type in ("bullet_list_open","ordered_list_open"):
            list_stack.append(["ordered" if t.type=="ordered_list_open" else "bullet",int(t.attrGet("start") or 1),False])
        elif t.type=="list_item_open":list_stack[-1][2]=False
        elif t.type=="list_item_close":list_stack[-1][1]+=1
        elif t.type in ("bullet_list_close","ordered_list_close"):list_stack.pop()
        elif t.type=="table_open":
            rows=[];row=[];i+=1
            while tokens[i].type!="table_close":
                if tokens[i].type=="tr_open":row=[]
                elif tokens[i].type=="inline":row.append(inline(tokens[i]))
                elif tokens[i].type=="tr_close":rows.append(row)
                i+=1
            flows.extend(make_table(rows))
        elif t.type in ("fence","code_block"):
            content=html.escape(clean(t.content.strip())).replace("\n","<br/>")
            flows.append(Paragraph(content,STYLES["code"]))
        elif t.type=="hr":flows.extend([Spacer(1,6),HRFlowable(width=WIDTH,thickness=.7,color=RULE),Spacer(1,4)])
        i+=1
    return flows


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--input",type=Path,default=PROJECT/"docs/COHORT-REPORT.md")
    p.add_argument("--output",type=Path,default=PROJECT/"docs/COHORT-REPORT.pdf")
    args=p.parse_args();args.output.parent.mkdir(parents=True,exist_ok=True)
    doc=Report(args.output,title="Cohort 1 - clinical catalogue and evidence review",author="SubNetwork",subject="ChEMBL 37 baseline; Zotero annotation follow-up and proposed import policies")
    doc.build(story(args.input.read_text()))
    print(args.output)


if __name__=="__main__":main()
