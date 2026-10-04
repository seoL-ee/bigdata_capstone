import json,csv,re,glob,collections,math
L={3:'T',4:'T',5:'H T X',6:'T',8:'F',9:'F H',11:'T V',12:'T',13:'T',18:'F',20:'F',24:'H T',25:'T',29:'T',30:'T F H A',31:'T V H',33:'F',34:'H T',37:'D S',40:'T',42:'T',44:'T',46:'F',47:'T',49:'T',50:'T H',55:'T',56:'T V H',59:'V',61:'T',63:'A',70:'T',71:'T',72:'A',74:'H',79:'T H',80:'F',86:'H',88:'F',89:'T',90:'T',91:'F',93:'T',94:'X',95:'H',100:'H',101:'T H',102:'T',107:'F A',109:'F',111:'X',115:'F',116:'T V H A',118:'T H',123:'T',125:'F A',126:'T V',128:'T H',129:'T',130:'T',131:'T H',135:'V',137:'X',142:'T',143:'T',145:'F',147:'T V',149:'X',151:'T F',152:'T',153:'T H',156:'F',157:'T',158:'T',159:'T',160:'F',161:'T',164:'F',168:'T F',169:'T',170:'F T H',171:'X',175:'F',176:'V',177:'T',178:'T',185:'A',186:'V',187:'T',194:'T',198:'F',199:'A',200:'F',203:'T',204:'T H',205:'F',208:'T H',210:'A',211:'T',214:'H',215:'T H',217:'T',218:'F T',219:'V',221:'H',223:'T H',225:'T',226:'T H',227:'X',228:'V',229:'T',230:'T',231:'T',233:'F',238:'T',242:'T',243:'H T P',244:'F H',245:'T',246:'T',248:'T F A',249:'F A',251:'A',252:'T',253:'T',256:'A',258:'T F',259:'T',261:'H T',262:'T H',265:'T H F',267:'H T',272:'F A',273:'X',274:'T',280:'T F',285:'T H',286:'V H',290:'T',292:'T',294:'T F',296:'F H',297:'T H F',298:'X',299:'T',300:'F'}
AMB={116:'"친화적이나 돌변" 해석 애매',219:'"몸놀림 빠름"을 활동성으로 봄',228:'짖음방지기 착용은 짖음 암시, 라벨 안 함',251:'"앙칼진 면"을 공격성으로 봄',300:'"낯선 환경에 적응 중"을 겁/경계로 봄',170:'조건부(만지면 순해짐)',30:'공격성은 "없음"(부정 서술)'}
NAME={'T':'일반 기질(온순·얌전 등)','H':'사람 친화/반응','F':'겁·경계·예민','A':'공격성·입질','V':'활동성','D':'다른 개 적합성','C':'고양이 적합성','K':'아이 적합성','P':'배변훈련','S':'혼자 있는 시간/분리불안','X':'특수 돌봄 필요(행동 아님)'}
BEH='THFAVDCKPS'
import random,sys
DATA=sys.argv[1] if len(sys.argv)>1 else 'pawinhand-crawler/data/three_months'
_all=[]
for f in sorted(glob.glob(DATA+'/*.json')): _all+=json.load(open(f,encoding='utf-8'))
_all.sort(key=lambda r:r['notice_id'])
random.seed(20261005)
s=random.sample(_all,300)
rows=[]
for i,r in enumerate(s,1):
    codes=L.get(i,'').split()
    beh=[c for c in codes if c in BEH]
    row={'sample_no':i,'notice_id':r['notice_id'],'species':r['species'],'shelter_name':r['shelter_name'],'status_raw':r['status_raw'],'special_mark':r['special_mark'].strip(),'behavior_mention':'Y' if beh else 'N'}
    for c in BEH+'X': row[NAME[c]]=1 if c in codes else 0
    row['llm_note']=AMB.get(i,'')
    row['human_check']='';row['human_comment']=''
    rows.append(row)
with open('special_mark_sample300_labeled.csv','w',encoding='utf-8-sig',newline='') as f:
    w=csv.DictWriter(f,fieldnames=list(rows[0].keys()));w.writeheader();w.writerows(rows)
n=len(rows)
def ci(k,n):
    p=k/n;z=1.96;d=1+z*z/n;c=(p+z*z/(2*n))/d;h=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/d
    return f"{100*p:.1f}% ({100*(c-h):.1f}~{100*(c+h):.1f})"
k=sum(r['behavior_mention']=='Y' for r in rows)
print('behavior any',k,ci(k,n))
for c in BEH+'X':
    kk=sum(r[NAME[c]] for r in rows);print(NAME[c],kk,ci(kk,n))
only_T=sum(1 for i in range(1,n+1) if set(c for c in L.get(i,'').split() if c in BEH)=={'T'})
print('T only',only_T)
beyond=sum(1 for i in range(1,n+1) if set(L.get(i,'').split())&set('DCKPS'))
print('household/living feats',beyond)
for sp in ['개','고양이','기타']:
    m=[r for r in rows if r['species']==sp];kk=sum(r['behavior_mention']=='Y' for r in m);print(sp,len(m),kk,ci(kk,len(m)))
sh=collections.Counter(r['shelter_name'] for r in rows);shy=collections.Counter(r['shelter_name'] for r in rows if r['behavior_mention']=='Y')
print('shelters in sample',len(sh),'with behavior',len(shy),'top5 share of Y',sum(v for _,v in shy.most_common(5))/k, shy.most_common(5))
# keyword screen on full data, validated against the 300
pat=re.compile(r'온순|순함|순하|순한|순둥|순종|얌전|조용|착함|착하|착해|사람.{0,4}(따|좋아|친화)|손.{0,2}(탐|타)|애교|친화|겁|경계|소심|낯가림|낮가림|예민|무서워|공격|사나|사납|입질|앙칼|활발|활동|대견성|분리불안|배변')
recs=_all
tp=sum(1 for r in rows if r['behavior_mention']=='Y' and pat.search(r['special_mark']))
fp=sum(1 for r in rows if r['behavior_mention']=='N' and pat.search(r['special_mark']))
fn=sum(1 for r in rows if r['behavior_mention']=='Y' and not pat.search(r['special_mark']))
print('kw vs label tp fp fn',tp,fp,fn,[r['special_mark'] for r in rows if (r['behavior_mention']=='Y')!=bool(pat.search(r['special_mark']))])
hit=[r for r in recs if pat.search(r['special_mark'] or '')]
print('full kw hit',len(hit),len(hit)/len(recs))
for sp in ['개','고양이','기타']:
    a=[r for r in recs if r['species']==sp];print(sp,len(a),sum(1 for r in a if pat.search(r['special_mark'] or ''))/len(a))
allsh=collections.Counter(r['shelter_name'] for r in recs);hs=collections.Counter(r['shelter_name'] for r in hit)
print('shelters',len(allsh),'with hit',len(hs),'top10 share',sum(v for _,v in hs.most_common(10))/len(hit),'top10 share of all records',sum(v for _,v in allsh.most_common(10))/len(recs))
for st in collections.Counter(r['status_raw'] for r in recs):
    a=[r for r in recs if r['status_raw']==st];print(st,len(a),round(sum(1 for r in a if pat.search(r['special_mark'] or ''))/len(a),3))
for name,p in [('dog','대견성|다른 ?(개|강아지)|합사'),('cat','고양이와|대묘'),('kids','아이들?과|어린이|아동'),('house','배변'),('alone','분리불안|혼자'),('walk','산책')]:
    print(name,sum(1 for r in recs if re.search(p,r['special_mark'] or '')))
