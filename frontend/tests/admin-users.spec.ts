import {test,expect} from '@playwright/test';
const alice={id:1,username:'Alice',role:'admin',is_active:1,created_at:'2026-11-01 12:00:00',last_viewed_at:null,board_count:2,item_count:25,figure_count:24,paper_count:8};
const bob={...alice,id:2,username:'Bob',role:'user',board_count:0,item_count:0,figure_count:0,paper_count:0};
const image='data:image/svg+xml,%3Csvg xmlns="http://www.w3.org/2000/svg" width="200" height="100"%3E%3C/svg%3E';

test('separate users page shows counts, board filters, pagination, empty details and invitations',async({page})=>{
 await page.route('**/api/auth/me',r=>r.fulfill({json:{user:alice}}));
 await page.route('**/api/admin/users',r=>r.fulfill({json:{users:[alice,bob],summary:{users:2,active_users:2,boards:2,items:25,figures:24}}}));
 await page.route('**/api/admin/users/*',async r=>{
  const url=new URL(r.request().url());const who=url.pathname.endsWith('/1')?alice:bob;
  const offset=Number(url.searchParams.get('offset'));const board=url.searchParams.get('collection_id');
  if(who.id===2)await new Promise(resolve=>setTimeout(resolve,350));
  const total=who.id===2?0:board?1:25;
  await r.fulfill({json:{user:who,boards:who.id===1?[{id:'a',name:'方法灵感',count:24},{id:'b',name:'实验配色',count:1}]:[],total,next_offset:offset+24<total?offset+24:null,items:Array.from({length:Math.min(24,total-offset)},(_,i)=>({id:`f${i}`,item_id:`i${offset+i}`,title:`收藏论文 ${offset+i+1}`,fig_label:'Fig. 1',caption:'Caption',thumb_url:image,hd_url:image,collection_name:board==='b'?'实验配色':'方法灵感',saved_at:'2026-11-02 12:00:00'}))}});
 });
 let invitation:any=null;
 await page.route('**/api/admin/invites',r=>{if(r.request().method()==='POST'){invitation={code:'qa',url:'https://example.test/?invite=qa',max_uses:1,used_count:0,remaining_uses:1,status:'active',expires_at:'2026-12-01 12:00:00'};return r.fulfill({json:invitation});}return r.fulfill({json:{items:invitation?[invitation]:[]}});});
 await page.goto('/admin/users');
 await expect(page.getByRole('heading',{name:'用户管理.'})).toBeVisible();
 await expect(page.getByLabel('用户总体统计')).toContainText('25');
 await page.getByRole('button',{name:'查看 Alice 的详情'}).click();
 const dialog=page.getByRole('dialog');
 await expect(dialog.locator('.admin-favorites article')).toHaveCount(24);
 await dialog.getByRole('button',{name:'下一页'}).click();
 await expect(dialog).toContainText('收藏论文 25');
 await dialog.getByLabel('筛选用户看板').selectOption('b');
 await expect(dialog.locator('.admin-favorites article')).toHaveCount(1);
 await expect(dialog.locator('.admin-favorites')).toContainText('实验配色');
 await page.setViewportSize({width:390,height:844});
 expect(await dialog.evaluate(el=>el.scrollWidth<=el.clientWidth)).toBeTruthy();
 await page.screenshot({path:'../data/qa/admin-017-user-mobile.png'});
 await dialog.getByRole('button',{name:'关闭',exact:true}).click();
 await page.getByRole('button',{name:'查看 Bob 的详情'}).click();
 await expect(dialog).not.toContainText('Alice');
 await expect(dialog.getByRole('heading',{name:'还没有收藏'})).toBeVisible();
 await dialog.getByRole('button',{name:'关闭',exact:true}).click();
 await page.getByRole('button',{name:'生成邀请链接'}).click();
 await expect(page.getByLabel('邀请链接',{exact:true})).toHaveValue('https://example.test/?invite=qa');
});

test('ordinary members cannot open user management or load its data',async({page})=>{
 let requests=0;
 await page.route('**/api/auth/me',r=>r.fulfill({json:{user:bob}}));
 await page.route('**/api/admin/users**',r=>{requests++;return r.fulfill({json:{}});});
 await page.goto('/admin/users');
 await expect(page.getByRole('heading',{name:'需要管理员权限'})).toBeVisible();
 expect(requests).toBe(0);
});

test('control room displays cache hit rate and resource snapshot with explicit scan states',async({page})=>{
 await page.route('**/api/auth/me',r=>r.fulfill({json:{user:alice}}));
 await page.route('**/api/admin/overview',r=>r.fulfill({json:{users:[],domains:[],repairs:[],review_count:0,vision_driver:'test',vision_model:'test'}}));
 await page.route('**/api/admin/pipeline',r=>r.fulfill({json:{stages:{}}}));
 let scan={status:'ready',completed_at:'2026-11-16 12:00:00',started_at:'2026-11-16 11:59:00',error:'',directories:12,files:123};
 await page.route('**/api/admin/storage/insights',r=>r.fulfill({json:{cache:{hits:80,misses:15,coalesced:5,requests:100,hit_rate:.8,started_at:'2026-11-16 00:00:00'},scan,resources:{total_bytes:12e9,remote_bytes:11e9,local_bytes:1.5e9,local_only_bytes:1e9,total_files:140,remote_files:123}}}));
 await page.route('**/api/admin/storage/scan',r=>{scan={...scan,status:'running'};return r.fulfill({json:{started:true}});});
 await page.goto('/admin');
 const panel=page.getByRole('region',{name:'缓存命中与资源统计'});
 await expect(panel).toContainText('80.0%');await expect(panel).toContainText('12 GB');await expect(panel).toContainText('11 GB');
 await expect(page.getByRole('heading',{name:'账号与邀请'})).toHaveCount(0);
 await page.getByRole('button',{name:'刷新 WebDAV 盘点'}).click();
 await expect(panel).toContainText('正在盘点 WebDAV');
 await expect(page.getByRole('button',{name:'刷新 WebDAV 盘点'})).toBeDisabled();
 scan={...scan,status:'error',error:'WebDAV 盘点失败'};
 await expect(panel.getByRole('alert')).toContainText('上次成功盘点',{timeout:10000});
 await expect(panel).toContainText('12 GB');
 await page.setViewportSize({width:390,height:844});
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
 await page.screenshot({path:'../data/qa/admin-017-resource-mobile.png'});
});
