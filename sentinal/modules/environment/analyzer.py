"""Environmental scoring with optional station/satellite hooks."""
from datetime import datetime,timezone
from pathlib import Path
from typing import Mapping
import yaml
DEFAULT=Path(__file__).parents[2]/'config/thresholds.yaml'
def _label(s):return 'critical' if s>=80 else 'high' if s>=60 else 'medium' if s>=30 else 'low'
class EnvironmentAnalyzer:
 def __init__(self,thresholds_path=None,station_hook=None,satellite_hook=None):
  try:
   with open(thresholds_path or DEFAULT) as f:self.thresholds=(yaml.safe_load(f) or {}).get('environment',{})
  except Exception:self.thresholds={}
  self.station_hook,self.satellite_hook=station_hook,satellite_hook
 def analyze(self,data=None,*,signal_id='environment'):
  d=data if isinstance(data,Mapping) else {};reasons=[];evidence=[];vals=[]
  aliases={'rainfall_24h_mm':('rainfall_24h_mm','rainfall_mm'),'smoke_index':('smoke_index',),'flood_level_m':('flood_level_m','water_level_m'),'wind_speed_mps':('wind_speed_mps',)}
  for key in ('rainfall_24h_mm','smoke_index','flood_level_m','wind_speed_mps'):
   v=next((d.get(alias) for alias in aliases[key] if alias in d),None);t=self.thresholds.get(key,{})
   if isinstance(v,(int,float)) and not isinstance(v,bool) and isinstance(t,Mapping):
    level=100 if v>=t.get('critical',1e99) else 75 if v>=t.get('high',1e99) else 45 if v>=t.get('warn',1e99) else 0
    if level:vals.append(level);reasons.append({'code':key,'detail':f'{v:g} exceeds configured threshold'});evidence.append({'type':'environment','ref':key,'detail':str(v)})
  v=d.get('temperature_c',d.get('temperature'))
  if isinstance(v,(int,float)) and (v>45 or v<-20):vals.append(70);reasons.append({'code':'temperature','detail':'extreme temperature'});evidence.append({'type':'environment','ref':'temperature'})
  for hook,typ in ((self.station_hook,'station'),(self.satellite_hook,'satellite')):
   if hook:
    try:
     out=hook(d);evidence.append({'type':typ,'ref':'comparison','detail':str(out)})
     if isinstance(out,Mapping) and out.get('hazard'):vals.append(float(out.get('score',50)))
    except Exception:pass
  score=max(vals,default=0)
  if not reasons:reasons=[{'code':'no_hazards','detail':'no configured environmental hazards detected'}]
  return {'module':'environment','signal_id':signal_id,'score':round(min(100,score),2),'label':_label(score),'reasons':reasons,'evidence':evidence,'confidence':min(1,.5+.1*len(vals)),'timestamp':datetime.now(timezone.utc).isoformat()}
def analyze_environment(data=None,**kwargs):return EnvironmentAnalyzer(kwargs.pop('thresholds_path',None),kwargs.pop('station_hook',None),kwargs.pop('satellite_hook',None)).analyze(data,**kwargs)
