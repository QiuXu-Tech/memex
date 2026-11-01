import importlib.util, pathlib, sys, types
from unittest.mock import MagicMock

root=pathlib.Path('/work')
def module(name):
 m=types.ModuleType(name);sys.modules[name]=m;return m
package=module('neural_lam');package.__path__=[str(root/'neural_lam')]
pl=module('pytorch_lightning');torch=module('torch');fabric=module('lightning_fabric');fabric.__path__=[];fabric_utils=module('lightning_fabric.utilities');fabric_utils.__path__=[];fabric_utils.seed=types.SimpleNamespace(seed_everything=lambda *a,**kw:None)
loguru=module('loguru')
class Logger:
 def warning(self,*a,**kw):pass
 def catch(self,*a,**kw):return lambda fn:fn
loguru.logger=Logger()
torch.serialization=types.SimpleNamespace(add_safe_globals=lambda *a,**kw:None)
torch.cuda=types.SimpleNamespace(is_available=lambda:False)
torch.set_float32_matmul_precision=lambda *a,**kw:None
utils=module('neural_lam.utils');utils.setup_training_logger=lambda **kw:None
conf=module('neural_lam.config')
for name in ('ComputeConfig','DataConfig','DatastoreSelection','LoggingConfig','ManualStateFeatureWeighting','ModelConfig','NeuralLAMConfig','OutputClamping','TrainingConfig','TrainRunConfig','UniformFeatureWeighting'):
 setattr(conf,name,type(name,(),{}))
conf.load_config_and_datastore=lambda **kw:None
datastore_pkg=module('neural_lam.datastore');datastore_pkg.__path__=[]
datastore_base=module('neural_lam.datastore.base');datastore_base.BaseDatastore=type('BaseDatastore',(),{})
gnn=module('neural_lam.gnn_layers');gnn.GNN_TYPES={'test':object}
models=module('neural_lam.models');models.MODELS={'graph_lam':object};models.BaseHiGraphModel=type('BaseHiGraphModel',(),{})
models.DeterministicARForecaster=lambda *a,**kw:object();models.DeterministicForecastingModule=lambda *a,**kw:object()
weather=module('neural_lam.weather_dataset');weather.WeatherDataModule=lambda **kw:object()
pl.callbacks=types.SimpleNamespace(ModelCheckpoint=lambda **kw:object())
class Captured(BaseException):
 def __init__(self,kwargs):self.kwargs=kwargs
class Trainer:
 def __init__(self,**kwargs):raise Captured(kwargs)
pl.Trainer=Trainer
spec=importlib.util.spec_from_file_location('neural_lam.train_model',root/'neural_lam/train_model.py')
m=importlib.util.module_from_spec(spec);sys.modules[spec.name]=m;spec.loader.exec_module(m)
m.dataclasses=types.SimpleNamespace(asdict=lambda obj:{})
m.build_predictor=lambda *a,**kw:types.SimpleNamespace(trainable=True)

def fit_devices(devices,cuda=False):
 torch.cuda.is_available=lambda:cuda
 train=types.SimpleNamespace(ar_steps_train=1,ar_steps_eval=1,train_steps_to_log=[],val_steps_to_log=[],var_leads_metrics_watch={},metrics_watch=[],eval=None,load=None,batch_size=1,num_workers=0,loss='mse',lr=0.01,restore_opt=False,n_example_pred=0,create_gif=False,epochs=1,val_interval=1,num_sanity_val_steps=0)
 data=types.SimpleNamespace(num_past_forcing_steps=0,num_future_forcing_steps=0,num_past_boundary_steps=0,num_future_boundary_steps=0,load_single_member=False,num_workers=0)
 compute=types.SimpleNamespace(seed=1,devices=devices,num_nodes=1,precision='32')
 model=types.SimpleNamespace(model='graph_lam',processor_layers=1,hidden_dim=1)
 logging=types.SimpleNamespace(logger_run_name='trial',runs_root='/tmp')
 store=types.SimpleNamespace(get_vars_names=lambda **kw:['value'])
 try:m.fit(model,train,data,compute,logging,config=object(),datastore=store)
 except Captured as e:return e.kwargs
 raise AssertionError('trainer was not reached')

def positive(raw,cuda,expected):
 r=fit_devices(raw,cuda);assert r['devices']==expected,(r['devices'],expected);assert r['accelerator']==('cuda' if cuda else 'cpu');assert r['strategy']=='auto'
def invalid(raw):
 try:fit_devices(raw,False)
 except ValueError as e:assert '--devices' in str(e),str(e);return
 raise AssertionError(f'{raw!r} should raise a ValueError mentioning --devices')

def help_text():
 s=m.build_parser().format_help().lower();assert 'cpu' in s and ('count' in s or 'process' in s),s

checks={'cpu one process':lambda:positive(['1'],False,1),'cpu auto':lambda:positive(['auto'],False,'auto'),'gpu list remains IDs':lambda:positive(['0','1'],True,[0,1]),'help documents CPU count':help_text,'cpu two processes':lambda:positive(['2'],False,2),'reject cpu zero':lambda:invalid(['0']),'reject cpu negative':lambda:invalid(['-1']),'reject multiple cpu ids':lambda:invalid(['1','2']),'gpu single ID remains list':lambda:positive(['0'],True,[0]),'gpu auto preserved':lambda:positive(['auto'],True,'auto')}
sets={'public':['cpu one process','cpu auto','gpu list remains IDs','help documents CPU count'],'hidden':['cpu two processes','reject cpu zero','reject cpu negative','reject multiple cpu ids','gpu single ID remains list','gpu auto preserved']}
if __name__=='__main__':
 failures=0
 for label in sets[sys.argv[1]]:
  try:checks[label]();print('PASS '+label)
  except Exception as e:failures+=1;print('FAIL '+label+': '+type(e).__name__+': '+str(e)[:400])
 sys.exit(1 if failures else 0)
