"""선택한 키만 .env에 안전하게 저장. 입력·기존 키 값은 출력하지 않는다."""
import argparse
import getpass
import re
import warnings
from pathlib import Path

KEYS=['LLM_API_KEY','KMA_SERVICE_KEY','KTO_SERVICE_KEY','VWORLD_API_KEY']

def main():
    parser=argparse.ArgumentParser(description='API 키 설정(키 값은 명령행 인수로 받지 않습니다)')
    parser.add_argument('--key',choices=KEYS,default='VWORLD_API_KEY')
    args=parser.parse_args()
    with warnings.catch_warnings():
        warnings.simplefilter('error', getpass.GetPassWarning)
        try:
            value = getpass.getpass(args.key+' (빈 입력: 기존 값 유지): ').strip()
        except (getpass.GetPassWarning, EOFError):
            raise SystemExit('숨김 입력을 지원하는 터미널에서 실행하세요.') from None
    if not value:
        print('변경하지 않았습니다.');return
    if any(c in value for c in '\r\n'):
        raise SystemExit('줄바꿈이 있는 값은 저장할 수 없습니다.')
    path=Path(__file__).resolve().parent/'.env'
    text=path.read_text(encoding='utf-8-sig') if path.exists() else ''
    pattern=re.compile(r'^'+re.escape(args.key)+r'=.*$',re.M)
    line=args.key+'='+value
    text=pattern.sub(lambda _:line,text) if pattern.search(text) else text.rstrip()+'\n'+line+'\n'
    path.write_text(text,encoding='utf8')
    print(args.key+' 저장 완료. 앱을 재시작하세요. 키 값은 표시하지 않습니다.')

if __name__=='__main__':main()
