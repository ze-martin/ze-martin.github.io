import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from analysis.policy import apply_policy,compatible_keys
from analysis.model import PoissonModel,TeamStats
from analysis.settlement import grade,profit
from analysis.calibration import temporal_diagnostic
from db.performance_store import PerformanceStore
from services.player_markets import match_player,deduplicate_quotes
from tools.export_protocol_html import build_rows,build_combo_rows
from tools.generate_protocol_probabilities import build_market_rows


def sample_data(ev=.1, sample=12, odds=1.5):
    market={'key':'TOTALS:OVER_1_5','market':'TOTALS OVER.1.5','probability':.8,'odds_api':odds,
            'ev_api':ev,'recommendation_score':100,'market_priority':10,'bookmaker_api':'Test'}
    return {'generated_at':'2090-01-01T00:00:00+00:00','model_version':'test-v2','results':[
        {'match_id':'1','match':'A vs B','kickoff_lima':'2100-01-01T12:00:00-05:00',
         'date_lima':'2100-01-01','time_lima':'12:00','league':'Test','pre_match_eligible':True,
         'recommended_pick':market.copy(),'all_markets':[market],
         'model_audit':{'team_inputs':{side:{'matches':sample} for side in ['home','away']}}}]}


class SelectionTests(unittest.TestCase):
    def test_negative_ev_is_never_principal(self):
        d=apply_policy(sample_data(ev=-.01))
        self.assertIsNone(d['results'][0]['recommended_pick'])
        self.assertEqual(build_rows(d)[1][0]['pick'],'Sin apuesta')

    def test_small_sample_is_not_high_confidence(self):
        d=apply_policy(sample_data(sample=1))
        self.assertIsNone(d['results'][0]['recommended_pick'])
        self.assertIn('Muestra insuficiente',str(d['results'][0]['all_markets'][0]['selection_reasons']))

    def test_betano_can_qualify_without_api_and_retains_attribution(self):
        d=sample_data(odds=None)
        m=d['results'][0]['all_markets'][0];m['ev_api']=None;m['odds_betano']=1.5;m['ev_betano']=.2
        r=apply_policy(d)['results'][0]
        self.assertEqual(r['recommended_pick']['selection_role'],'Principal')
        self.assertIsNone(r['recommended_pick']['odds_api'])
        self.assertEqual(r['recommended_pick']['selection_bookmaker'],'Betano')
        self.assertNotEqual(r['recommended_pick']['recommendation_tier'],'Seguro')

    def test_no_forced_combo_or_nested_btts(self):
        self.assertFalse(compatible_keys(['BTTS:YES','TOTALS:OVER_1_5']))
        self.assertFalse(compatible_keys(['1X2:HOME','DOUBLE_CHANCE:1X']))
        self.assertEqual(build_combo_rows([]),[])
        d=apply_policy(sample_data())
        self.assertEqual(build_combo_rows(build_rows(d)[0]),[])

    def test_no_alternative_counted_as_principal(self):
        d=sample_data();m=d['results'][0]['all_markets'][0].copy();m['key']='BTTS:YES';d['results'][0]['all_markets'].append(m)
        r=apply_policy(d)['results'][0]
        self.assertEqual(sum(m['selection_role']=='Principal' for m in r['all_markets']),1)

    def test_started_fixture_is_excluded_even_with_stale_ns(self):
        d=sample_data();d['results'][0]['kickoff_lima']='2000-01-01T12:00:00-05:00'
        self.assertIsNone(apply_policy(d)['results'][0]['recommended_pick'])


class SettlementTests(unittest.TestCase):
    def test_draw_no_bet_ev_accounts_for_refund(self):
        rows=build_market_rows({'DRAW_NO_BET:HOME':.6,'1X2:DRAW':.25}, {'markets':{'DRAW_NO_BET:HOME':2.0}})
        dnb=next(r for r in rows if r['key']=='DRAW_NO_BET:HOME')
        self.assertAlmostEqual(dnb['ev'],.15)
    def test_penalty_shootout_does_not_change_90_minute_pick(self):
        f={'fixture':{'status':{'short':'PEN'}},'score':{'fulltime':{'home':1,'away':1},'penalty':{'home':5,'away':4}}}
        self.assertEqual(grade('DOUBLE_CHANCE:12',f),'lost')
        self.assertEqual(grade('DRAW_NO_BET:HOME',f),'void')
        self.assertIsNone(grade('FIRST_HALF_TOTALS:OVER_0_5',f))
        self.assertEqual(profit('void',2.0),0)

    def test_unavailable_result_is_not_a_loss(self):
        self.assertIsNone(grade('BTTS:YES',{'fixture':{'status':{'short':'NS'}}}))
        with self.assertRaises(ValueError):profit('won',1,1)


class LedgerTests(unittest.TestCase):
    def test_snapshot_immutable_and_actual_wager_separate(self):
        with tempfile.TemporaryDirectory() as tmp:
            s=PerformanceStore(Path(tmp)/'audit.sqlite');s.initialize()
            d=apply_policy(sample_data());d['generated_at']='2000-01-01T00:00:00+00:00';sid=s.freeze(d,'2100-01-01')
            self.assertEqual(s.freeze(d,'2100-01-01'),sid)
            self.assertEqual(len(s.rows()),1)
            with s.connect() as c:
                with self.assertRaises(sqlite3.IntegrityError):c.execute("UPDATE prediction_snapshot SET model_version='fake'")
            pick=s.rows()[0];s.settle(pick['id'],'won',{'score':{'home':2,'away':0}})
            self.assertEqual(s.actual_summary()['bets'],0)
            s.record_bet('ticket',pick['id'],'Test',1.5,10,'2020-12-31T12:00:00+00:00')
            self.assertEqual(s.actual_summary()['profit'],5)
            with self.assertRaises(ValueError):s.record_bet('bad',pick['id'],'Test',float('nan'),1,'2099-12-31T00:00:00+00:00')


class ModelAndPlayerTests(unittest.TestCase):
    def test_joint_probabilities_are_coherent(self):
        m=PoissonModel();p=m.match_probabilities(TeamStats('A',10,15,10),TeamStats('B',10,12,13))
        self.assertAlmostEqual(sum(p['1X2:'+s] for s in ['HOME','DRAW','AWAY']),1,places=6)
        self.assertAlmostEqual(p['WIN_BTTS:HOME_YES']+p['WIN_BTTS:HOME_NO'],p['1X2:HOME'],places=6)
        self.assertLessEqual(p['TOTAL_RANGE:2_3'],p['TOTALS:OVER_1_5'])

    def test_player_matching_does_not_guess_ambiguous_name(self):
        self.assertIsNone(match_player('John Smith',[{'id':1,'name':'J. Smith'},{'id':2,'name':'J. Smith'}]))
        self.assertEqual(match_player('Ousmane Dembele',[{'id':1,'name':'O. Dembélé'}])['id'],1)

    def test_duplicate_player_quote_does_not_create_more_options(self):
        options=[{'api_quotes':[{'bookmaker':'A','odds':2},{'bookmaker':'A','odds':2},{'bookmaker':'B','odds':2}]}]
        deduplicate_quotes(options)
        self.assertEqual(len(options[0]['api_quotes']),2)

    def test_temporal_calibration_does_not_train_on_holdout(self):
        rows=[{'report_date':f'2026-01-{day:02}','probability':.8,'outcome':'won' if i%3 else 'lost'} for day in range(1,7) for i in range(30)]
        first=temporal_diagnostic(rows)
        second=temporal_diagnostic([{**r,'outcome':'lost' if r['outcome']=='won' else 'won'} if r['report_date']>first['train_end'] else r for r in rows])
        self.assertLess(first['train_end'],first['test_start'])
        self.assertEqual(first['intercept'],second['intercept'])
        self.assertFalse(first['active'])

    def test_calibration_refuses_tiny_sample(self):
        self.assertFalse(temporal_diagnostic([])['active'])


if __name__=='__main__':unittest.main()
