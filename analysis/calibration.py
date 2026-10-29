"""Temporal calibration diagnostics; never deploy an in-sample correction."""
import math


def logit(p):
    p = min(.999999, max(.000001, p))
    return math.log(p/(1-p))


def sigmoid(x):
    return 1/(1+math.exp(-max(-30,min(30,x))))


def temporal_diagnostic(rows):
    rows = [r for r in rows if r.get('outcome') in {'won','lost'}]
    dates = sorted({r['report_date'] for r in rows})
    if len(dates) < 4:
        return {'active':False,'reason':'Se necesitan al menos cuatro fechas cerradas independientes'}
    cutoff = dates[max(1,int(len(dates)*.67))-1]
    train = [r for r in rows if r['report_date']<=cutoff]
    test = [r for r in rows if r['report_date']>cutoff]
    if len(train)<100 or len(test)<40:
        return {'active':False,'train_n':len(train),'test_n':len(test),'train_end':cutoff,
                'reason':'Muestra insuficiente para calibración: mínimos provisionales 100/40'}
    a,b = 0.0,1.0
    for _ in range(2500):
        da=db=0.0
        for r in train:
            x=logit(r['probability']); error=sigmoid(a+b*x)-(r['outcome']=='won')
            da+=error;db+=error*x
        a-=.03*da/len(train);b=max(.01,b-.03*(db/len(train)+.01*(b-1)))
    def losses(adjust):
        ps=[sigmoid(a+b*logit(r['probability'])) if adjust else r['probability'] for r in test]
        ys=[r['outcome']=='won' for r in test]
        return {'brier':sum((p-y)**2 for p,y in zip(ps,ys))/len(ps),
                'log_loss':-sum(math.log(max(1e-9,p if y else 1-p)) for p,y in zip(ps,ys))/len(ps)}
    raw,adjusted=losses(False),losses(True)
    return {'active':False,'train_n':len(train),'test_n':len(test),'train_end':cutoff,
            'test_start':min(r['report_date'] for r in test),'test_end':max(r['report_date'] for r in test),
            'intercept':a,'slope':b,'raw':raw,'candidate':adjusted,
            'improves_holdout':adjusted['brier']<raw['brier'] and adjusted['log_loss']<raw['log_loss'],
            'reason':'Diagnóstico, no corrección activa: validar por familia y versión con snapshots prospectivos; no transferir al modelo v2'}
