import {test,expect} from '@playwright/test';

test('admins create counted manual codes and delete either kind without stale entries',async({page})=>{
 await page.route('**/api/auth/me',r=>r.fulfill({json:{user:{id:1,username:'Admin',role:'admin'}}}));
 await page.route('**/api/admin/users',r=>r.fulfill({json:{users:[],summary:{users:0,active_users:0,boards:0,items:0,figures:0}}}));
 let items:any[]=[];
 await page.route('**/api/admin/invites',r=>{
  if(r.request().method()==='POST'){
   const body=r.request().postDataJSON();const code=body.kind==='code'?'ABCD2345EFGH6789':'a-case-sensitive-link';
   const item={...body,code,url:`https://example.test/?invite=${code}`,used_count:0,remaining_uses:body.max_uses,status:'active',expires_at:'2026-12-01 12:00:00'};items.unshift(item);return r.fulfill({json:item});
  }
  return r.fulfill({json:{items}});
 });
 await page.route('**/api/admin/invites/*',r=>{expect(r.request().method()).toBe('DELETE');items=items.filter(i=>!r.request().url().endsWith(i.code));return r.fulfill({json:{ok:true}});});
 await page.goto('/admin/users');
 await page.getByLabel('邀请类型').selectOption('code');await page.getByLabel('可使用次数').fill('5');await page.getByRole('button',{name:'生成邀请码'}).click();
 await expect(page.getByLabel('邀请码',{exact:true})).toHaveValue('ABCD-2345-EFGH-6789');
 await expect(page.locator('.invite-entry')).toContainText('已用 0 / 5 次');
 await page.getByRole('button',{name:'删除邀请码',exact:true}).click();await page.getByRole('button',{name:'取消',exact:true}).click();await expect(page.locator('.invite-entry')).toHaveCount(1);
 await page.getByRole('button',{name:'删除邀请码',exact:true}).click();await page.getByRole('button',{name:'确认删除',exact:true}).click();await expect(page.locator('.invite-entry')).toHaveCount(0);
 await page.getByLabel('邀请类型').selectOption('link');await page.getByRole('button',{name:'生成邀请链接'}).click();await page.getByRole('button',{name:'删除邀请链接',exact:true}).click();await page.getByRole('button',{name:'确认删除',exact:true}).click();await expect(page.locator('.invite-entry')).toHaveCount(0);
 await page.reload();await expect(page.getByText('暂无邀请链接。')).toBeVisible();
});

test('login and manual registration require tokens, reset after failure, and use separate actions',async({page})=>{
 await page.route('**/api/auth/challenge-config',r=>r.fulfill({json:{enabled:true,site_key:'test-public-key'}}));
 await page.route('https://challenges.cloudflare.com/turnstile/v0/api.js*',r=>r.fulfill({contentType:'application/javascript',body:`window.turnstile={render:(el,options)=>{window.qaChallenge=options;el.textContent='QA human verification';return 'widget';},remove:()=>{}};`}));
 await page.route('**/api/auth/login',r=>{expect(r.request().postDataJSON().turnstile_token).toBe('login-token');return r.fulfill({status:401,json:{detail:'用户名或密码错误'}});});
 let registration:any;
 await page.route('**/api/auth/register',r=>{registration=r.request().postDataJSON();return r.fulfill({json:{user:{id:99,username:'qa-user',role:'user'}}});});
 await page.goto('/');await page.getByRole('button',{name:'登录',exact:false}).first().click();
 const dialog=page.getByRole('dialog');
 await expect(dialog.getByText('QA human verification')).toBeVisible();
 await dialog.getByLabel('用户名',{exact:true}).fill('qa-user');await dialog.getByLabel('密码',{exact:true}).fill('long-enough-password');
 await expect(dialog.getByRole('button',{name:'登录',exact:true})).toBeDisabled();
 await page.evaluate(()=>{const q=(window as any).qaChallenge;if(q.action!=='login')throw Error('Wrong action');q.callback('login-token');});
 await dialog.getByRole('button',{name:'登录',exact:true}).click();await expect(dialog).toContainText('用户名或密码错误');
 await expect(dialog.getByRole('button',{name:'登录',exact:true})).toBeDisabled();
 await dialog.getByRole('button',{name:'邀请码注册',exact:true}).click();await dialog.getByLabel('邀请码',{exact:true}).fill('ABCD-2345-EFGH-6789');
 await expect(dialog.getByRole('button',{name:'创建账号',exact:true})).toBeDisabled();
 await page.evaluate(()=>{const q=(window as any).qaChallenge;if(q.action!=='register')throw Error('Wrong action');q.callback('register-token');q['expired-callback']();});
 await expect(dialog.getByRole('button',{name:'创建账号',exact:true})).toBeDisabled();
 await page.evaluate(()=>(window as any).qaChallenge.callback('register-token'));
 await dialog.getByRole('button',{name:'创建账号',exact:true}).click();await expect(dialog).toHaveCount(0);
 expect(registration.invite_code).toBe('ABCD-2345-EFGH-6789');expect(registration.turnstile_token).toBe('register-token');
});

test('invitation links prefill registration while existing users can switch to login',async({page})=>{
 await page.route('**/api/auth/challenge-config',r=>r.fulfill({json:{enabled:false,site_key:null}}));
 await page.goto('/?invite=CaseSensitiveLink');const dialog=page.getByRole('dialog');
 await expect(dialog.getByLabel('邀请码',{exact:true})).toHaveValue('CaseSensitiveLink');
 await expect(dialog.getByRole('button',{name:'创建账号',exact:true})).toBeVisible();
 await dialog.getByRole('button',{name:'已有账号'}).click();await expect(dialog.getByLabel('邀请码',{exact:true})).toHaveCount(0);
 await expect(dialog.getByRole('button',{name:'登录',exact:true})).toBeVisible();
});
