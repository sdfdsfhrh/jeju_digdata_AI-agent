"""Leaflet 로컬 정적 자산/타일 전달. 서비스 키·요청 URL은 로그에 남기지 않는다."""
import base64,secrets,threading,hashlib,socket,json
from collections import deque
import requests
from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlsplit
import streamlit as st
from agent import config
ROOT=Path(__file__).resolve().parent
DIAGNOSTICS=deque(maxlen=100)  # 공개 타일 좌표와 성패만. 키·URL·본문은 보관하지 않는다.

class ExclusiveServer(ThreadingHTTPServer):
 allow_reuse_address=False
 def server_bind(self):
  if hasattr(socket,'SO_EXCLUSIVEADDRUSE'):
   self.socket.setsockopt(socket.SOL_SOCKET,socket.SO_EXCLUSIVEADDRUSE,1)
  super().server_bind()

@st.cache_resource(show_spinner=False)
def server():
 token=secrets.token_urlsafe(24)
 class Handler(BaseHTTPRequestHandler):
  def log_message(self,*args):pass
  def do_GET(self):
   parts=urlsplit(self.path).path.strip('/').split('/')
   if not parts or parts[0]!=token:self.send_error(404);return
   content=None;mime='application/octet-stream'
   try:
    if len(parts)==2 and parts[1]=='health':
     content=json.dumps(list(DIAGNOSTICS)).encode();mime='application/json'
    elif len(parts)>=3 and parts[1]=='static':
     path=(ROOT/'static'/('/'.join(parts[2:]))).resolve()
     if path.is_relative_to((ROOT/'static').resolve()) and path.is_file():
      content=path.read_bytes();mime={'.js':'application/javascript','.css':'text/css','.png':'image/png'}.get(path.suffix,mime)
    elif len(parts)==5 and parts[1]=='carto':
     z,x,y=map(int,parts[2:])
     if 0<=z<=19 and 0<=x<2**z and 0<=y<2**z:
      r=requests.get(f'https://basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png',timeout=(3,5))
      # CARTO가 HTTP200으로 반환하는 API KEY REQUIRED 이미지(2026-11-10 실측).
      rejected='69be4aecf9f814ba45d585801a5aa41e79b16fc88eafec5b1954a9f06a69e6be'
      if r.status_code==200 and hashlib.sha256(r.content).hexdigest()!=rejected and r.content.startswith(b'\x89PNG'):
       content=r.content;mime='image/png'
    elif len(parts)==6 and parts[1]=='tile':
     from map_background import valid_tile,_tile
     layer,z,x,y=parts[2],int(parts[3]),int(parts[4]),int(parts[5])
     if valid_tile([layer,z,x,y]):
      image=_tile(layer,z,x,y,(self.headers.get('Origin') if self.headers.get('Origin','').startswith(('http://','https://')) else (self.headers.get('Referer') if self.headers.get('Referer','').startswith(('http://','https://')) else 'http://'+self.headers.get('Host','127.0.0.1').split(':')[0]+':18768')),_key=config.get('VWORLD_API_KEY'))
      if image:content=base64.b64decode(image.split(',',1)[1]);mime='image/jpeg' if layer=='Satellite' else 'image/png'
     DIAGNOSTICS.append(dict(layer=layer,z=z,x=x,y=y,ok=content is not None,reason='' if content else ('요청 범위 오류' if not valid_tile([layer,z,x,y]) else '상위 타일 응답 실패')))
   except Exception:pass
   if content is None:self.send_error(404);return
   self.send_response(200);self.send_header('Content-Type',mime);self.send_header('Access-Control-Allow-Origin','*');self.send_header('Cache-Control','private, max-age=300');self.end_headers()
   try:self.wfile.write(content)
   except (BrokenPipeError,ConnectionResetError):pass
 try:port=int(config.get('MAP_TILE_PORT') or '18769')
 except ValueError:port=18769
 if not 0<=port<=65535:port=18769
 try:httpd=ExclusiveServer(('0.0.0.0',port),Handler)
 except OSError:httpd=ExclusiveServer(('0.0.0.0',0),Handler)
 threading.Thread(target=httpd.serve_forever,daemon=True,name='leaflet-assets').start()
 return dict(port=httpd.server_port,token=token)
