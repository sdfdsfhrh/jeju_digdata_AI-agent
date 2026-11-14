"""지도 전용 벡터 아이콘. 판정색은 호출자가 전달한다."""
from urllib.parse import quote

def svg_icon(body,width=40,height=48,anchor_y=None):
    svg=f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">{body}</svg>'
    return dict(url='data:image/svg+xml;charset=utf-8,'+quote(svg),width=width,height=height,anchorX=width/2,anchorY=anchor_y if anchor_y is not None else height,mask=False)

def pin(color,number):
    rgb=','.join(map(str,color[:3]))
    return svg_icon(f'<path d="M20 46C17 39 3 29 3 19a17 17 0 0 1 34 0c0 10-14 20-17 27Z" fill="rgb({rgb})" stroke="white" stroke-width="2.5"/><text x="20" y="25" text-anchor="middle" font-family="Arial,sans-serif" font-size="17" font-weight="700" fill="white">{int(number)}</text>')

def facility(label):
    body={'입구':'<path d="M12 8h12v16H12M5 16h13m-4-4 4 4-4 4"/>',
          '주차':'<path d="M13 24V8h6a5 5 0 0 1 0 10h-6"/>',
          '화장실':'<circle cx="11" cy="9" r="2"/><path d="M11 13v8m-3 5 3-5 3 5M7 16h8M21 13v8m-3 5 3-5 3 5M18 16h6"/><circle cx="21" cy="9" r="2"/>'}[label]
    return svg_icon('<rect x="1" y="1" width="30" height="30" rx="8" fill="#2367b0" stroke="white" stroke-width="2"/><g fill="none" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'+body+'</g>',32,32,16)
