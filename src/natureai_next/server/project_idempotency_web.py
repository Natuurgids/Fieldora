"""Browser patch for stable Project mutation identities."""

from __future__ import annotations

from urllib.parse import urlsplit

from natureai_next.server.api import ApiResponse

_PROJECT_IDEMPOTENCY_PATCH = bytes(
    r"""

/* WEB-049: one mutation identity per open Project create intent. */
(()=>{
 let projectMutationId="";
 const beginProjectMutation=()=>{projectMutationId=crypto.randomUUID()};
 const clearProjectMutation=()=>{projectMutationId=""};

 if(typeof editRecord==="function"){
  const baseEditRecord=editRecord;
  editRecord=function(kind){
   if(kind==="project")beginProjectMutation();
   return baseEditRecord(kind);
  };
 }
 const portfolioOpen=document.getElementById("portfolio-new-project");
 if(portfolioOpen)portfolioOpen.addEventListener("click",beginProjectMutation);
 const portfolioCancel=document.getElementById("portfolio-project-cancel");
 if(portfolioCancel)portfolioCancel.addEventListener("click",clearProjectMutation);

 const previousApi=api;
 api=async function(path,options={}){
  const method=String(options.method||"GET").toUpperCase();
  if(path==="/api/v1/projects"&&method==="POST"){
   if(!projectMutationId)beginProjectMutation();
   let record;
   try{record=JSON.parse(options.body||"{}")}catch(_error){record=null}
   if(record&&typeof record==="object"){
    record.id=projectMutationId;
    options={...options,body:JSON.stringify(record)};
   }
   try{
    const result=await previousApi(path,options);
    clearProjectMutation();
    return result;
   }catch(error){
    /* Keep the mutation identity after transport/server failure so explicit retry
       converges on the same durable Project instead of allocating another one. */
    throw error;
   }
  }
  return previousApi(path,options);
 };
})();
""",
    "utf-8",
)


class ProjectIdempotencyWebApiMixin:
    """Append the stable-mutation browser contract after established app patches."""

    def dispatch(
        self, method: str, target: str, headers: dict[str, str], body: bytes
    ) -> ApiResponse:
        response = super().dispatch(method, target, headers, body)
        if (
            method != "GET"
            or urlsplit(target).path != "/app.js"
            or response.status != 200
            or _PROJECT_IDEMPOTENCY_PATCH in response.body
        ):
            return response
        return ApiResponse(
            response.status,
            response.body + _PROJECT_IDEMPOTENCY_PATCH,
            response.content_type,
            response.headers,
        )
