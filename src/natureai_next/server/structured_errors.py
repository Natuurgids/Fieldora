"""Stable, safe browser-facing API error envelopes."""

from __future__ import annotations

import json
from uuid import uuid4

from natureai_next.server.api import ApiResponse

_SAFE_MESSAGES = {
    400: "The request is invalid. Check the entered values and try again.",
    401: "Your session is not authorized. Sign in again and retry.",
    403: "You are not authorized to perform this action.",
    404: "The requested record is not available in your access scope.",
    409: "The request conflicts with the current server state.",
    413: "The request is too large for this endpoint.",
    416: "The requested byte range is not available.",
    429: "Too many requests were made. Try again shortly.",
}


def _safe_message(status: int) -> str:
    if status in _SAFE_MESSAGES:
        return _SAFE_MESSAGES[status]
    if 400 <= status < 500:
        return "The request could not be completed. Check the request and try again."
    return "The server could not complete the request. Retry or contact an administrator."


def _correlation_id() -> str:
    return str(uuid4())


def structured_error_response(response: ApiResponse) -> ApiResponse:
    """Add a stable error contract without removing legacy response fields."""
    if response.status < 400:
        return response
    try:
        payload = json.loads(response.body)
    except (TypeError, ValueError, json.JSONDecodeError):
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    code = str(payload.get("code") or payload.get("error") or "request_failed").strip()
    if not code:
        code = "request_failed"
    correlation_id = _correlation_id()
    normalized = dict(payload)
    normalized["code"] = code
    normalized["message"] = _safe_message(response.status)
    normalized["correlation_id"] = correlation_id
    headers = tuple(
        (name, value)
        for name, value in response.headers
        if name.casefold() != "x-correlation-id"
    ) + (("X-Correlation-ID", correlation_id),)
    return ApiResponse.json(response.status, normalized).__class__(
        response.status,
        ApiResponse.json(response.status, normalized).body,
        "application/json; charset=utf-8",
        headers,
    )


_STRUCTURED_ERROR_WEB_PATCH = bytes(
    r"""

/* WEB-051: preserve structured server errors and distinguish transport failures. */
(()=>{
 if(window.__fieldoraStructuredErrors)return;
 window.__fieldoraStructuredErrors=true;
 const baseStructuredApi=api;
 function fieldoraError(kind,code,message,correlationId,status,payload){
  const error=new Error(message||code||"Request failed");
  error.kind=kind;error.code=code||"request_failed";error.correlationId=correlationId||"";
  error.status=status||0;error.payload=payload||{};
  return error;
 }
 api=async function(path,options={}){
  try{return await baseStructuredApi(path,options)}
  catch(error){
   if(error&&error.payload&&error.code)return Promise.reject(error);
   if(error instanceof TypeError)return Promise.reject(fieldoraError("transport","network_error","The server could not be reached. Check the connection and try again.","",0,{}));
   return Promise.reject(error);
  }
 };
 const originalFetch=window.fetch.bind(window);
 window.fetch=async function(input,init){
  const response=await originalFetch(input,init);
  if(response.ok)return response;
  const clone=response.clone();let payload={};
  try{payload=await clone.json()}catch(_error){}
  const code=String(payload.code||payload.error||"request_failed");
  const correlationId=String(payload.correlation_id||response.headers.get("X-Correlation-ID")||"");
  const message=String(payload.message||`Request failed (${response.status})`);
  const kind=response.status===401||response.status===403?"auth":response.status===409?"conflict":response.status===400||response.status===413||response.status===416||response.status===422?"validation":"server";
  throw fieldoraError(kind,code,message,correlationId,response.status,payload);
 };
 window.fieldoraErrorSummary=function(error){
  const suffix=error?.correlationId?` · reference ${error.correlationId}`:"";
  return `${error?.message||"Request failed"}${suffix}`;
 };
})();
""",
    "utf-8",
)


class StructuredErrorApiMixin:
    """Normalize API errors and add the browser error-classification adapter."""

    def dispatch(
        self, method: str, target: str, headers: dict[str, str], body: bytes
    ) -> ApiResponse:
        response = super().dispatch(method, target, headers, body)
        if target.split("?", 1)[0] == "/app.js" and response.status == 200:
            if _STRUCTURED_ERROR_WEB_PATCH not in response.body:
                return ApiResponse(
                    response.status,
                    response.body + _STRUCTURED_ERROR_WEB_PATCH,
                    response.content_type,
                    response.headers,
                )
            return response
        if target.split("?", 1)[0].startswith("/api/"):
            return structured_error_response(response)
        return response
