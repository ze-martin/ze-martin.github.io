"""Standalone presentation regressions; no policy/model, DB or network dependency."""
from copy import deepcopy
from datetime import datetime,timezone
from pathlib import Path
import json,sys,tempfile,unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from services.report_template import render_report
from tools.restyle_historical_report import restyle

def snapshot():
    m={'key':'BTTS:YES','probability':.72,'odds_api':1.5,'bookmaker_api':'Casa original','api_captured_at':'2026-11-17T04:00:00+00:00','api_updated_at':'2026-11-17T03:00:00+00:00','selection_quote_source':'API','selection_odds':1.5,'selection_bookmaker':'Casa original','selection_quote_captured_at':'2026-11-17T04:00:00+00:00','selection_role':'Principal'}
    return {'generated_at':'2026-11-17T04:00:00+00:00','date_lima_filter':'2026-11-17','results':[{'match_id':1,'match':'Local vs Visita','kickoff_lima':'2026-11-17T14:00:00-05:00','all_markets':[m],'recommended_pick':deepcopy(m),'alternative_picks':[]}]}

class PresentationOnlyTests(unittest.TestCase):
    def test_export_preserves_every_source_field_and_original_role(self):
        d=snapshot();before=deepcopy(d)
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'report.html';render_report(d,p,'Histórico',now=datetime(2026,11,17,4,5,tzinfo=timezone.utc))
            h=p.read_text(encoding='utf-8');a=json.loads(p.with_name('report_auditoria.json').read_text(encoding='utf-8'))
            self.assertEqual(d,before);self.assertEqual(a['historical_selections'][0]['principal_key'],'BTTS:YES')
            self.assertIn('Principal al corte',h);self.assertIn('Casa original',h)
            manual=h.split('id="panel-manual"')[1].split('id="panel-t60"')[0]
            self.assertIn('Sin apuesta',manual);self.assertNotIn('selection principal',manual)
    def test_closed_audit_compact_tabs_and_static_header(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'report.html';render_report(snapshot(),p,'Histórico');h=p.read_text(encoding='utf-8')
            self.assertIn('<details id="audit-json">',h);self.assertIn('download>Descargar JSON',h)
            self.assertNotIn('<pre>',h[:h.index('id="panel-auditoria"')])
            self.assertIn('header{position:static;',h);self.assertIn('flex:0 0 auto;width:auto;',h)
    def test_restyle_creates_backup_and_checks_original_values(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder);s=p/'source.json';s.write_text(json.dumps(snapshot()),encoding='utf-8');out=p/'report.html';out.write_text('HTML anterior',encoding='utf-8')
            r=restyle(s,out,p/'backup');self.assertTrue(r['data_and_selections_unchanged']);self.assertEqual((p/'backup/report.html').read_text(encoding='utf-8'),'HTML anterior')
    def test_no_policy_or_model_import_in_template(self):
        s=Path('services/report_template.py').read_text(encoding='utf-8')
        self.assertNotIn('from analysis.',s);self.assertNotIn('apply_policy(',s)

if __name__=='__main__':unittest.main()
