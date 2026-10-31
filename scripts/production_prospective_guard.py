"""Constrain a patch to one pure known return expression before local testing."""
import re

def accepts(replacement):
 match = re.fullmatch(r'function\s+customOmitClone\s*\(value\)\s*\{\s*return\s+([A-Za-z0-9_\s?!:()|&=]+);\s*\}', replacement)
 if not match:
  return False
 identifiers = set(re.findall(r'[A-Za-z_]\w*', match.group(1)))
 return identifiers <= {'isPlainObject', 'isArray', 'undefined', 'value'}
