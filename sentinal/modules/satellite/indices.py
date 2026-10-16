import numpy as np
def _ratio(a,b): return (a-b)/np.maximum(np.abs(a)+np.abs(b),1e-9)
def spectral_indices(bands):
 missing=[k for k in ('red','nir','green','swir1') if k not in bands]
 if missing: raise ValueError('missing bands: '+', '.join(missing))
 r,n,g,s=[np.asarray(bands[k],float) for k in ('red','nir','green','swir1')]
 return {'ndvi':_ratio(n,r),'ndwi':_ratio(g,n),'nbr':_ratio(n,s)}
def classify_land_cover(indices):
 n=np.asarray(indices['ndvi']); w=np.asarray(indices.get('ndwi',0)); b=np.asarray(indices.get('nbr',0)); out=np.full(n.shape,'bare',dtype=object)
 out[n>=.45]='vegetation'; out[(w>=.2)&(n<.45)]='water'; out[(b<.1)&(n>.15)]='burned'; return out
