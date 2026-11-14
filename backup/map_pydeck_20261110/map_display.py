"""Agent 공통 구간 분류 결과를 실제 지도에 표시."""
import math
import pydeck as pdk
import map_icons
from agent.course_profile import GREEN,ORANGE,RED,BLUE,NOTE,text,valid,positive,proof
from agent import course_profile
GREEN=[8,80,65,255]
ORANGE=[216,90,48,255]
RED=[173,48,57,255]

def fit(points):
    if not points:return pdk.ViewState(latitude=33.38,longitude=126.55,zoom=8.6)
    xs=[float(p['lon']) for p in points];ys=[float(p['lat']) for p in points]
    # Web Mercator의 경계 폭·높이 모두 고려. 좁은 폰의 약280px 지도 폭에도 전 코스가 들어가도록 여백을 둔다.
    merc=lambda y:math.log(math.tan(math.pi/4+math.radians(max(-85,min(85,y)))/2))
    lo,hi=min(ys),max(ys);mid=(merc(lo)+merc(hi))/2
    lat=math.degrees(2*math.atan(math.exp(mid))-math.pi/2)
    dx=max((max(xs)-min(xs))/360,1e-7);dy=max((merc(hi)-merc(lo))/(2*math.pi),1e-7)
    zoom=min(math.log2(210/(512*dx)),math.log2(300/(512*dy)))-0.8
    return pdk.ViewState(latitude=lat,longitude=(min(xs)+max(xs))/2,zoom=max(1,min(17,zoom)),pitch=0,bearing=0)


def prepare(result):
    model=course_profile.prepare(result)
    # 화면 팔레트만 변환한다. level/판정/구간 수는 공통 함수 결과 유지.
    palette={tuple(course_profile.GREEN):GREEN,tuple(course_profile.ORANGE):ORANGE,tuple(course_profile.RED):RED}
    for group in ('segments','warnings'):
        for row in model[group]:
            if 'color' in row:row['color']=palette.get(tuple(row['color']),row['color'])
    model['view']=fit(model['bounds'])
    return model


def callouts(model):
    """주의 번호만 화면상 이동. 시설 좌표/경로/색은 원문 그대로."""
    scale=512*2**model['view'].zoom
    def project(lon,lat):return (float(lon)+180)/360*scale,(1-math.asinh(math.tan(math.radians(float(lat))))/math.pi)/2*scale
    def unproject(x,y):return [x/scale*360-180,math.degrees(math.atan(math.sinh(math.pi*(1-2*y/scale))))]
    center=project(model['view'].longitude,model['view'].latitude)
    occupied=([project(model['entrance']['lon'],model['entrance']['lat'])] if model['entrance'] else [])+[project(f['lon'],f['lat']) for f in model['facilities']]
    leaders=[]
    for w in model['warnings']:
        x,y=project(w['lon'],w['lat']);best=(x,y)
        candidates=[(0,0)]+[(dx,dy) for radius in (30,46,64,82) for dx,dy in ((-radius,0),(radius,0),(0,-radius),(0,radius),(-radius,-radius),(radius,-radius),(-radius,radius),(radius,radius))]
        for dx,dy in candidates:
            a,b=x+dx,y+dy
            if abs(a-center[0])>100 or abs(b-center[1])>145:continue
            if all(math.hypot(a-c,b-d)>=29 for c,d in occupied):best=(a,b);break
        occupied.append(best);w['display_position']=unproject(*best)
        if best!=(x,y):leaders.append(dict(path=[[w['lon'],w['lat']],w['display_position']]))
    for item in model['facilities']:item['label_offset']=[0,20]
    if model['entrance']:model['entrance']['label_offset']=[0,23]
    return leaders


def deck(model):
    layers=[]
    leaders=callouts(model)
    if model['segments']:
        layers.append(pdk.Layer('PathLayer',model['segments'],id='course-border',get_path='path',get_color=[255,255,255,240],get_width=11,width_units="'pixels'",width_min_pixels=10,cap_rounded=True,joint_rounded=True,pickable=False))
        layers.append(pdk.Layer('PathLayer',model['segments'],id='course-colors',get_path='path',get_color='color',get_width=7,width_units="'pixels'",width_min_pixels=6,cap_rounded=True,joint_rounded=True,pickable=True))
    if leaders:
        layers.append(pdk.Layer('PathLayer',leaders,get_path='path',get_color=[110,115,125,210],get_width=1,width_units="'pixels'",width_min_pixels=1,pickable=False))
    if model['warnings']:
        layers.extend([pdk.Layer('ScatterplotLayer',model['warnings'],get_position='display_position',get_fill_color='color',get_radius=14,radius_units="'pixels'",radius_min_pixels=13,radius_max_pixels=15,stroked=True,get_line_color=[255,255,255],line_width_min_pixels=2,pickable=True),
                       pdk.Layer('TextLayer',data=model['warnings'],character_set="'auto'",get_position='display_position',get_text='label',get_size=15,get_color=[255,255,255],get_text_anchor="'middle'",get_alignment_baseline="'center'",font_weight=700,pickable=True)])
    entry=model['entrance']
    facilities=[]
    for f in model['facilities']:
        near=entry and math.hypot((float(f['lon'])-float(entry['lon']))*92500,(float(f['lat'])-float(entry['lat']))*111000)<2
        facilities.append(dict(f,icon=map_icons.facility(f['label']),icon_offset=[26,0] if near else [0,0],label_offset=[28,-20] if near else f['label_offset']))
    if facilities:
        layers.append(pdk.Layer('IconLayer',facilities,id='facility-icons',get_position='[lon, lat]',get_icon='icon',get_size=25,get_pixel_offset='icon_offset',pickable=True))
        layers.append(pdk.Layer('TextLayer',data=facilities,id='facility-labels',character_set="'auto'",get_position='[lon, lat]',get_text='label',get_size=15,get_color=[30,55,80],background=True,get_background_color=[255,255,255,235],get_pixel_offset='label_offset',pickable=True))
    if model['entrance']:
        entries=[dict(model['entrance'])]
        layers.extend([pdk.Layer('ScatterplotLayer',entries,id='entrance-circle',get_position='[lon, lat]',get_fill_color=BLUE,get_radius=9,radius_units="'pixels'",radius_min_pixels=9,stroked=True,get_line_color=[255,255,255],line_width_min_pixels=2,pickable=True),
                       pdk.Layer('TextLayer',data=entries,id='entrance-label',character_set="'auto'",get_position='[lon, lat]',get_text='label',get_color=[20,80,190],get_size=17,get_pixel_offset='label_offset',background=True,get_background_color=[255,255,255,240],pickable=True)])
    return pdk.Deck(layers=layers,initial_view_state=model['view'],map_provider='carto',map_style='light',tooltip={'text':'{info}'})
