"""Post-hoc citation-format normalization; it does not verify factual support."""
import json,re
from prospective_candidate_review_v2 import validate_vote

def normalize(content,allowed_ids,finish):
 original=validate_vote(content,allowed_ids,finish)
 if original['status']=='valid':return {'status':'valid','vote':original,'normalizedReferences':[]}
 if original.get('reason')!='reason_mentions_unlisted_source':return {'status':'invalid','original':original}
 try:
  text=re.sub(r'^```(?:json)?\s*|\s*```$','',content.strip());obj=json.loads(text);refs=obj['references'];mentioned=set(re.findall(r'comment-\d+',obj['reason']));missing=sorted(mentioned-set(refs))
  if not missing or any(x not in allowed_ids for x in missing):return {'status':'invalid','original':original}
  obj['references']=refs+missing;result=validate_vote(json.dumps(obj,ensure_ascii=False),allowed_ids,finish)
  if result['status']!='valid':return {'status':'invalid','original':original}
  return {'status':'normalized_from_explicit_reason_ids','vote':result,'original':original,'normalizedReferences':missing}
 except Exception:return {'status':'invalid','original':original}
