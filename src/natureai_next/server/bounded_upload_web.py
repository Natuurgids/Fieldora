"""Bounded-memory hashing and chunk upload wiring for the managed browser."""

from __future__ import annotations

from urllib.parse import urlsplit

from natureai_next.server.api import ApiResponse

_BOUNDED_UPLOAD_HELPER = bytes(
    r'''

/* WEB-052: hash and upload large browser files without whole-file JS buffers. */
(()=>{
 if(window.__fieldoraBoundedUploads)return;
 window.__fieldoraBoundedUploads=true;
 const K=new Uint32Array([
  0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,
  0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,
  0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,
  0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,
  0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,
  0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,
  0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,
  0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2
 ]);
 const rotr=(v,n)=>(v>>>n)|(v<<(32-n));
 function compress(h,data,offset,w){
  for(let i=0;i<16;i++){const j=offset+i*4;w[i]=((data[j]<<24)|(data[j+1]<<16)|(data[j+2]<<8)|data[j+3])>>>0;}
  for(let i=16;i<64;i++){
   const x=w[i-15],y=w[i-2],s0=rotr(x,7)^rotr(x,18)^(x>>>3),s1=rotr(y,17)^rotr(y,19)^(y>>>10);
   w[i]=(w[i-16]+s0+w[i-7]+s1)>>>0;
  }
  let a=h[0],b=h[1],c=h[2],d=h[3],e=h[4],f=h[5],g=h[6],hh=h[7];
  for(let i=0;i<64;i++){
   const s1=rotr(e,6)^rotr(e,11)^rotr(e,25),ch=(e&f)^(~e&g),t1=(hh+s1+ch+K[i]+w[i])>>>0;
   const s0=rotr(a,2)^rotr(a,13)^rotr(a,22),maj=(a&b)^(a&c)^(b&c),t2=(s0+maj)>>>0;
   hh=g;g=f;f=e;e=(d+t1)>>>0;d=c;c=b;b=a;a=(t1+t2)>>>0;
  }
  h[0]=(h[0]+a)>>>0;h[1]=(h[1]+b)>>>0;h[2]=(h[2]+c)>>>0;h[3]=(h[3]+d)>>>0;
  h[4]=(h[4]+e)>>>0;h[5]=(h[5]+f)>>>0;h[6]=(h[6]+g)>>>0;h[7]=(h[7]+hh)>>>0;
 }
 window.fieldoraBoundedSha256=async function(file,chunkSize=4*1024*1024){
  const h=new Uint32Array([0x6a09e667,0xbb67ae85,0x3c6ef372,0xa54ff53a,0x510e527f,0x9b05688c,0x1f83d9ab,0x5be0cd19]);
  const w=new Uint32Array(64),tail=new Uint8Array(64);let tailLen=0,total=0;
  for(let start=0;start<file.size;start+=chunkSize){
   const end=Math.min(file.size,start+chunkSize),data=new Uint8Array(await file.slice(start,end).arrayBuffer());total+=data.length;let p=0;
   if(tailLen){const take=Math.min(64-tailLen,data.length);tail.set(data.subarray(0,take),tailLen);tailLen+=take;p+=take;if(tailLen===64){compress(h,tail,0,w);tailLen=0;}}
   for(;p+64<=data.length;p+=64)compress(h,data,p,w);
   if(p<data.length){tail.set(data.subarray(p),0);tailLen=data.length-p;}
  }
  tail[tailLen++]=0x80;
  if(tailLen>56){tail.fill(0,tailLen);compress(h,tail,0,w);tailLen=0;}
  tail.fill(0,tailLen,56);const high=Math.floor(total/0x20000000)>>>0,low=(total*8)>>>0;
  tail[56]=high>>>24;tail[57]=high>>>16;tail[58]=high>>>8;tail[59]=high;tail[60]=low>>>24;tail[61]=low>>>16;tail[62]=low>>>8;tail[63]=low;
  compress(h,tail,0,w);return [...h].map(v=>v.toString(16).padStart(8,"0")).join("");
 };
})();
''',
    "utf-8",
)

_FULL_BUFFER_HASH = (
    'const bytes=await file.arrayBuffer(),hash=[...new Uint8Array(await crypto.subtle.digest("SHA-256",bytes))]'
    '.map(x=>x.toString(16).padStart(2,"0")).join("")'
)
_BOUNDED_HASH = 'const hash=await window.fieldoraBoundedSha256(file)'
_DIGEST_FILE = ''' async function digestFile(file){
  const bytes=await file.arrayBuffer();
  const digest=await crypto.subtle.digest("SHA-256",bytes);
  return {bytes,hash:[...new Uint8Array(digest)].map(x=>x.toString(16).padStart(2,"0")).join("")};
 }'''
_BOUNDED_DIGEST_FILE = ''' async function digestFile(file){
  return {hash:await window.fieldoraBoundedSha256(file)};
 }'''


def patch_bounded_upload_response(target: str, response: ApiResponse) -> ApiResponse:
    if urlsplit(target).path != "/app.js" or response.status != 200:
        return response
    text = response.body.decode("utf-8")
    text = text.replace(_FULL_BUFFER_HASH, _BOUNDED_HASH)
    text = text.replace(_DIGEST_FILE, _BOUNDED_DIGEST_FILE)
    text = text.replace("const {bytes,hash}=await digestFile(file);", "const {hash}=await digestFile(file);")
    text = text.replace(
        'file.webkitRelativePath||file.name,{bytes,hash}=await digestFile(file);',
        'file.webkitRelativePath||file.name,{hash}=await digestFile(file);',
    )
    text = text.replace("body:bytes.slice(start,end)", "body:file.slice(start,end)")
    body = text.encode("utf-8")
    if _BOUNDED_UPLOAD_HELPER not in body:
        body += _BOUNDED_UPLOAD_HELPER
    return ApiResponse(response.status, body, response.content_type, response.headers)


class BoundedUploadWebApiMixin:
    """Apply bounded-memory hashing after all managed browser patches are composed."""

    def dispatch(
        self, method: str, target: str, headers: dict[str, str], body: bytes
    ) -> ApiResponse:
        response = super().dispatch(method, target, headers, body)
        return patch_bounded_upload_response(target, response)
