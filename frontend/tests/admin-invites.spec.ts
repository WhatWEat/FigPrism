import {test,expect} from '@playwright/test';

test('admin chooses invite capacity and sees refreshed usage after successful registrations',async({page})=>{
 await page.route('**/api/auth/me',r=>r.fulfill({json:{user:{id:1,username:'Admin',role:'admin'}}}));
 await page.route('**/api/admin/users',r=>r.fulfill({json:{users:[],summary:{users:0,active_users:0,boards:0,items:0,figures:0}}}));
 let invitation:any=null;
 await page.route('**/api/admin/invites',r=>{
  if(r.request().method()==='POST'){
   expect(r.request().postDataJSON()).toEqual({max_uses:3});
   invitation={code:'test',url:'https://example.test/?invite=test',max_uses:3,used_count:0,remaining_uses:3,status:'active',expires_at:'2026-12-01 12:00:00'};
   return r.fulfill({json:invitation});
  }
  return r.fulfill({json:{items:invitation?[invitation]:[]}});
 });
 await page.goto('/admin/users');
 const input=page.getByLabel('可使用次数');
 await expect(input).toHaveValue('1');
 await input.fill('0');await expect(page.getByRole('button',{name:'生成邀请链接'})).toBeDisabled();
 await input.fill('1.5');await expect(page.getByRole('region',{name:'邀请链接管理'}).getByRole('alert')).toContainText('整数');
 await input.fill('3');await page.getByRole('button',{name:'生成邀请链接'}).click();
 await expect(page.locator('.invite-entry')).toContainText('已用 0 / 3 次 · 剩余 3 次');
 invitation={...invitation,used_count:2,remaining_uses:1};
 await expect(page.locator('.invite-entry')).toContainText('已用 2 / 3 次 · 剩余 1 次',{timeout:10000});
 invitation={...invitation,used_count:3,remaining_uses:0,status:'exhausted'};
 await page.reload();await expect(page.locator('.invite-entry')).toContainText('已用完');
 await expect(page.locator('.invite-entry')).toContainText('剩余 0 次');
 await page.setViewportSize({width:390,height:844});
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
 await page.screenshot({path:'../data/qa/invite-018-mobile.png'});
});
