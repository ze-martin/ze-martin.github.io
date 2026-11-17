"""Offline presentation regressions, independent of execution/notification code."""
import csv,json,sys,tempfile,unittest
from copy import deepcopy
from pathlib import Path
from datetime import datetime,timezone
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from services.report_template import render_report
from tools.export_protocol_html import build_rows,write_csv

class TablePublicationTests(unittest.TestCase):
    def test_latest_root_links_and_private_json_exclusion(self):
        from unittest.mock import patch
        from tools import build_pages_site as b
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder);out=p/'outputs';out.mkdir();site=p/'site';site.mkdir()
            stem='protocolo_20261117_full_pc'
            (out/(stem+'.html')).write_text('<a href="'+stem+'_todos_los_mercados.csv">CSV</a><a href="'+stem+'_auditoria.json">JSON</a><a href="protocolo_20261117_manual_pc.html">Manual</a>',encoding='utf-8')
            (out/(stem+'_auditoria.json')).write_text('{"schema":"sporting-report-audit-v1"}',encoding='utf-8')
            (out/'private.json').write_text('{"private":true}',encoding='utf-8')
            with patch.object(b,'OUTPUTS',out),patch.object(b,'SITE',site),patch.object(b,'REPORTS',site/'reports'):b.copy_reports()
            text=(site/'latest.html').read_text(encoding='utf-8')
            for ext in ['_todos_los_mercados.csv','_auditoria.json']:self.assertIn('href="reports/'+stem+ext+'"',text)
            self.assertIn('href="reports/protocolo_20261117_manual_pc.html"',text)
            self.assertFalse((site/'reports/private.json').exists())
    def source(self):
        m={'key':'BTTS:YES','market':'BTTS YES','probability':.72,'odds_api':None,'odds_betano':1.8,'bookmaker_api':'Casa original','betano_captured_at':'2026-11-17T10:00:00+00:00','api_captured_at':'2026-11-17T10:00:00+00:00','api_updated_at':'2026-11-17T09:00:00+00:00','api_quote_observation':{'odds':2.3,'bookmaker':'Casa observada','captured_at':'2026-11-17T10:00:00+00:00','provider_updated_at':'2026-11-17T09:00:00+00:00','validation_error':'Proveedor vencido'}}
        return {'generated_at':'2026-11-17T10:00:00+00:00','date_lima_filter':'2026-11-17','selection_policy':'selection-v3-quality-review-v1','results':[{'match_id':'1','match':'Local vs Visita','kickoff_lima':'2026-11-17T20:00:00-05:00','all_markets':[m],'recommended_pick':None,'alternative_picks':[]}]}
    def test_tabs_closed_audit_and_source_immutable(self):
        d=self.source();before=deepcopy(d)
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'report.html';render_report(d,p,'Prueba',now=datetime(2026,11,17,11,tzinfo=timezone.utc));h=p.read_text(encoding='utf-8')
            self.assertEqual(d,before)
            for name in ['Principales','Alternativas','Todos los mercados','Jugadores','Auditoría']:self.assertIn('>'+name+'</button>',h)
            self.assertIn('<details id="audit-json">',h);self.assertNotIn('<pre>',h[:h.index('id="panel-auditoria"')])
            self.assertIn('header{position:static;',h);self.assertIn('flex:0 0 auto;width:auto;',h)
    def test_csv_keeps_discarded_observation_without_active_price(self):
        rows,_,_=build_rows(self.source())
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'report.csv';write_csv(rows,p)
            with p.open(encoding='utf-8-sig',newline='') as f:r=next(csv.DictReader(f))
            self.assertEqual(r['bookmaker_api'],'Casa observada');self.assertEqual(r['api_precio_observado_historico'],'2.3');self.assertEqual(r['cuota_api'],'')
            self.assertEqual(r['api_update_original_historico'],'2026-11-17T09:00:00+00:00')
    def test_empty_advanced_sample_never_shows_certainty(self):
        d=self.source();d['results'][0]['all_markets'][0].update(key='CORNERS:OVER:0.5',probability=1.)
        d['results'][0]['model_audit']={'advanced_metric_sample_min':{'CORNERS':0}}
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'r.html';render_report(d,p,'Prueba');h=p.read_text(encoding='utf-8');main=h.split('id="panel-auditoria"')[0]
            self.assertIn('Datos insuficientes',main);self.assertNotIn('100,0%',main)
            audit=json.loads(p.with_name('r_auditoria.json').read_text(encoding='utf-8'));self.assertEqual(audit['matches'][0]['markets'][0]['probability'],1.)

if __name__=='__main__':unittest.main()
