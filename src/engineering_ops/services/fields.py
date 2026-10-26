from __future__ import annotations
<<<<<<< HEAD

from typing import Any

from engineering_ops.adapters.jira import JiraClient


class ResolutionError(ValueError):
    pass


def resolve_field(client: JiraClient, field_name: str) -> dict[str, Any]:
    matches = [f for f in client.fields() if f.get("name", "").casefold() == field_name.casefold()]
    if not matches:
        raise ResolutionError(f"Field not found: {field_name}")
    if len(matches) > 1:
        raise ResolutionError(f"Ambiguous field name {field_name}; {len(matches)} fields matched")
    return matches[0]


def resolve_value_for_issue(client: JiraClient, issue_key: str, field_id: str, display_value: Any) -> Any:
    meta = client.editmeta(issue_key).get("fields", {})
    info = meta.get(field_id)
    if not info:
        raise ResolutionError(f"Field is not editable for {issue_key}")
    allowed = info.get("allowedValues") or []
    if allowed:
        matches = [
            value
            for value in allowed
            if str(value.get("value") or value.get("name")).casefold() == str(display_value).casefold()
        ]
        if len(matches) != 1:
            raise ResolutionError(f"Value {display_value!r} did not resolve uniquely for {issue_key}")
        chosen = matches[0]
        if "id" in chosen:
            return {"id": str(chosen["id"])}
        if "accountId" in chosen:
            return {"accountId": chosen["accountId"]}
        return {"value": chosen.get("value") or chosen.get("name")}
=======
from typing import Any
from engineering_ops.adapters.jira import JiraClient

class ResolutionError(ValueError): pass

def resolve_field(client:JiraClient, field_name:str)->dict[str,Any]:
    matches=[f for f in client.fields() if f.get('name','').casefold()==field_name.casefold()]
    if not matches:
        raise ResolutionError(f'Field not found: {field_name}')
    if len(matches)>1:
        raise ResolutionError(f'Ambiguous field name {field_name}: {[m.get("id") for m in matches]}')
    return matches[0]

def resolve_value_for_issue(client:JiraClient, issue_key:str, field_id:str, display_value:Any)->Any:
    meta=client.editmeta(issue_key).get('fields',{})
    info=meta.get(field_id)
    if not info:
        raise ResolutionError(f'{field_id} is not editable for {issue_key}')
    allowed=info.get('allowedValues') or []
    if allowed:
        matches=[v for v in allowed if str(v.get('value') or v.get('name')).casefold()==str(display_value).casefold()]
        if len(matches)!=1:
            raise ResolutionError(f'Value {display_value!r} did not resolve uniquely for {issue_key}')
        chosen=matches[0]
        if 'id' in chosen: return {'id':str(chosen['id'])}
        if 'accountId' in chosen: return {'accountId':chosen['accountId']}
        return {'value':chosen.get('value') or chosen.get('name')}
>>>>>>> 6e6588a (Initial Engineering Operations Platform baseline)
    return display_value
