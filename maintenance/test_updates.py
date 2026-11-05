import unittest,json,tempfile
from pathlib import Path
from update_core import preview,read_input,pub
class Tests(unittest.TestCase):
 def setUp(self):
  self.base=[{'id':'CN123456789A','applicationNumber':'CN202010000001.1'}];self.empty={'events':[]}
 def row(self,**kw):return dict(kind='patent',company='chcnav',publicationId='CN123456789B',applicationNumber='CN202010000001.1',title='隔离测试',applicants='测试',sourceUrl='https://example.org/evidence',**kw)
 def test_versions(self):
  for x in ['US20240012345A1','EP1234567B1','WO2024123456A1','CN123456789S']:self.assertEqual(pub(x),x)
  with self.assertRaises(ValueError):pub('CN123456789')
 def test_dedupe(self):
  r=preview([self.row(),self.row()],self.base,self.empty,{'other'},set());self.assertEqual([x['decision'] for x in r],['新增','已存在'])
 def test_conflict(self):
  r=self.row();r.update(publicationId='CN123456789A',applicationNumber='CN202099999999.1');self.assertEqual(preview([r],self.base,self.empty,set(),set())[0]['decision'],'冲突')
 def test_privacy_empty(self):
  r=self.row();r.update(title='',internalNote='私有');o=preview([r],self.base,self.empty,set(),set())[0];self.assertEqual(o['decision'],'缺失信息')
 def test_status(self):
  r={'kind':'status','publicationId':'CN123456789A','statusRaw':'授权','normalizedStatus':'granted','sourceUrl':'https://example.org/record','verification':'official','asOf':'2026-11-05'}
  self.assertEqual(preview([r],self.base,self.empty,set(),set())[0]['decision'],'冲突')
  r['evidenceUrl']='https://example.org/evidence';self.assertEqual(preview([r],self.base,self.empty,set(),set())[0]['decision'],'更新')
 def test_xlsx_physical_rows(self):
  import zipfile
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'test.xlsx'
   with zipfile.ZipFile(p,'w') as z:z.writestr('xl/worksheets/sheet1.xml','<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><dimension ref="A1"/><sheetData><row><c r="A1" t="inlineStr"><is><t>公开号</t></is></c></row><row><c r="A2" t="inlineStr"><is><t>CN123456789A</t></is></c></row></sheetData></worksheet>')
   self.assertEqual(read_input(p)[0]['publicationId'],'CN123456789A')
 def test_pdf_content(self):
  from unittest.mock import patch
  import find_pdfs
  def fetch(u):return b'User-agent: *\nAllow: /' if u.endswith('robots.txt') else b'<meta name="citation_pdf_url" content="https://patents.google.com/a.pdf">' if '/patent/' in u else b'<html>wrong</html>'
  with patch.object(find_pdfs,'get',fetch):self.assertEqual(find_pdfs.check('CN123456789A','https://patents.google.com/patent/CN123456789A')['pdfStatus'],'链接失效')
 def test_pdf_wrong_version(self):
  from unittest.mock import patch
  import find_pdfs
  def fetch(u):return b'User-agent: *\nAllow: /' if u.endswith('robots.txt') else b'<meta name="citation_pdf_url" content="https://patents.google.com/a.pdf">' if '/patent/' in u else b'%PDF-test-only'
  with patch.object(find_pdfs,'get',fetch),patch.object(find_pdfs.subprocess,'check_output',return_value=b'CN123456789B citation CN123456789A'):
   self.assertEqual(find_pdfs.check('CN123456789A','https://patents.google.com/patent/CN123456789A')['pdfStatus'],'找到候选，待核验')
if __name__=='__main__':unittest.main()
