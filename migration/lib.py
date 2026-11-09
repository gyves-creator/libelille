import re, os, glob, html
SRC='/home/claude/lib_src/LIB'
def decode_name(b):
    # zip used CP850; some duplicates have UTF-8 lead byte replaced by '+'
    if re.search(rb'\+[\x80-\xbf]', b):
        try: return re.sub(rb'\+([\x80-\xbf])', lambda m: b'\xc3'+m.group(1), b).decode('utf-8'), True
        except UnicodeDecodeError: pass
    try: return b.decode('utf-8'), False
    except UnicodeDecodeError: return b.decode('cp850'), False
def lire(p):
    b=open(p,'rb').read()
    try: return b.decode('utf-8')
    except UnicodeDecodeError: return b.decode('cp1252',errors='replace')
def titre(t, fallback):
    m=re.findall(r'(?is)<h1[^>]*>(.*?)</h1>',t) or re.findall(r'(?is)<title>(.*?)</title>',t)
    s=html.unescape(re.sub(r'<[^>]+>|\s+',' ',m[0])).strip() if m else fallback
    return re.sub(r'\s*[-–|]\s*libelille(\.fr)?\s*$','',s,flags=re.I).strip()
def texte(t):
    t=re.sub(r'(?is)<(script|style|head)\b.*?</\1>|<ul class="navbar">.*?</ul>|<\?php.*?\?>',' ',t)
    return html.unescape(re.sub(r'\s+',' ',re.sub(r'<[^>]+>',' ',t))).strip()
def pages_php():
    out=[]
    for b in sorted(os.listdir(SRC.encode())):
        if b.endswith(b'.php'):
            n,_=decode_name(b); out.append((n, os.path.join(SRC.encode(),b)))
    return out
