"""Defensive deterministic cyber signal scoring."""
from datetime import datetime,timezone
from pathlib import Path
from typing import Any,Mapping
import yaml
DEFAULT=Path(__file__).parents[2]/'config/thresholds.yaml'
def _num(v): return float(v) if isinstance(v,(int,float)) and not isinstance(v,bool) else None
def _label(s): return 'critical' if s>=80 else 'high' if s>=60 else 'medium' if s>=30 else 'low'
class CyberAnalyzer:
 def __init__(self,thresholds_path=None,trusted_scanners=None):
  try:
   with open(thresholds_path or DEFAULT) as f:self.thresholds=(yaml.safe_load(f) or {}).get('cyber',{})
  except Exception:self.thresholds={}
  self.trusted_scanners=trusted_scanners or set()
 def analyze(self,data=None,*,signal_id='cyber'):
  d=data if isinstance(data,Mapping) else {}; reasons=[]; evidence=[]; vals=[]
  def threshold(name,value):
   n=_num(value);t=self.thresholds.get(name,{})
   if n is None or not isinstance(t,Mapping):return
   level=100 if n>=t.get('critical',1e99) else 75 if n>=t.get('high',1e99) else 45 if n>=t.get('warn',1e99) else 0
   if level:vals.append(level);reasons.append({'code':name,'detail':f'{n:g} exceeds configured threshold'});evidence.append({'type':'cyber','ref':name,'detail':str(n)})
  threshold('failed_logins_10m',d.get('failed_logins_10m',d.get('failed_logins')));threshold('distinct_source_ips_10m',d.get('distinct_source_ips_10m',d.get('source_ips', d.get('distinct_source_ips'))))
  for key in ('port_scans','odd_traffic','malware','malware_flag'):
   if d.get(key):vals.append(90);reasons.append({'code':key,'detail':f'{key} indicator detected'});evidence.append({'type':'cyber','ref':key})
  if isinstance(d.get('packets_per_second'), (int, float)) and d['packets_per_second'] >= 100:
   vals.append(70); reasons.append({'code':'odd_traffic','detail':'packet rate exceeds the synthetic baseline'}); evidence.append({'type':'cyber','ref':'packets_per_second'})
  scanner=d.get('scanner',d.get('scanner_id'))
  if scanner and str(scanner) not in self.trusted_scanners:vals.append(55);reasons.append({'code':'untrusted_scanner','detail':'scanner is not allow-listed'});evidence.append({'type':'cyber','ref':'scanner'})
  score=sum(vals)/len(vals) if vals else 0; imp=_num(d.get('asset_importance',d.get('importance')))
  if imp is not None:score=min(100,score*(.5+max(0,min(100,imp))/200))
  if not reasons:reasons=[{'code':'no_indicators','detail':'no configured cyber indicators detected'}]
  return {'module':'cyber','signal_id':signal_id,'score':round(score,2),'label':_label(score),'reasons':reasons,'evidence':evidence,'confidence':min(1,.5+.1*len(vals)),'timestamp':datetime.now(timezone.utc).isoformat()}
def analyze_cyber(data=None,**kwargs):return CyberAnalyzer(kwargs.pop('thresholds_path',None),kwargs.pop('trusted_scanners',None)).analyze(data,**kwargs)
