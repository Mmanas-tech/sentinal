from fastapi import APIRouter
router=APIRouter()
@router.post('/satellite/change')
def change(payload:dict): return {'status':'accepted','placeholder':True,'request':payload}
@router.get('/satellite/query')
def query(): return {'items':[],'page':1,'limit':50,'total':0,'placeholder':True}
@router.post('/satellite/query')
def query_post(payload:dict): return {'status':'accepted','placeholder':True,'request':payload}
