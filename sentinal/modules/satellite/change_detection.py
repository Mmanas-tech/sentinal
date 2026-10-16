import numpy as np
def difference_mask(before, after, threshold=0.15):
 a,b=np.asarray(before,float),np.asarray(after,float)
 if a.shape!=b.shape: raise ValueError("resolution mismatch: before and after arrays must have the same shape (resample first)")
 return np.abs(b-a)/np.maximum(np.abs(a),1e-9)>=threshold
def analyze_change(before,after,*,threshold=0.15,cloud_cover=0.0,aoi=None):
 a,b=np.asarray(before,float),np.asarray(after,float)
 if a.shape!=b.shape:return {"status":"refused","reason":"resolution mismatch","message":"Before/after resolution differs; resampling is required before comparison."}
 if a.ndim<2:return {"status":"refused","reason":"invalid raster"}
 if aoi is not None:
  y0,x0,y1,x1=map(int,aoi)
  if y0<0 or x0<0 or y1>a.shape[-2] or x1>a.shape[-1] or y0>=y1 or x0>=x1:return {"status":"refused","reason":"AOI out of bounds"}
  a,b=a[...,y0:y1,x0:x1]
 d=np.abs(b-a)/np.maximum(np.abs(a),1e-9); valid=np.isfinite(d); mask=(d>=threshold)&valid
 bounded=np.minimum(d, 1.0)
 cloud=float(cloud_cover)
 warnings=[]
 if cloud > 0.40:
  warnings.append("cloud cover exceeds 40%; confidence reduced")
 return {"status":"ok","difference_mask":mask,"percent_change":float(np.nanmean(bounded)*100) if valid.any() else 0.0,"changed_fraction":float(mask.sum()/valid.sum()) if valid.any() else 0.0,"cloud_cover":cloud,"confidence":max(0.,min(1.,1.-cloud)),"warnings":warnings}
