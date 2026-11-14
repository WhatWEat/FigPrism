export async function api<T>(url:string,init:RequestInit={}):Promise<T>{
 const response=await fetch('/api'+url,{credentials:'same-origin',...init,headers:{...(init.body instanceof FormData?{}:{'Content-Type':'application/json'}),...init.headers}});
 if(!response.ok){const body=await response.json().catch(()=>({detail:'请求失败，请稍后重试'}));throw new Error(typeof body.detail==='string'?body.detail:'提交内容不符合要求，请检查后重试');}
 return response.json();
}
export const post=<T>(url:string,data:unknown={})=>api<T>(url,{method:'POST',body:JSON.stringify(data)});
export const put=<T>(url:string,data:unknown)=>api<T>(url,{method:'PUT',body:JSON.stringify(data)});
export function rgb(hex:string){return [1,3,5].map(n=>parseInt(hex.slice(n,n+2),16));}
export function paletteCode(colors:string[],format:string){
 if(format==='RGB')return colors.map(c=>`rgb(${rgb(c).join(', ')})`).join('\n');
 if(format==='Matplotlib')return `colors = [${colors.map(c=>`"${c}"`).join(', ')}]\nplt.rcParams["axes.prop_cycle"] = plt.cycler(color=colors)`;
 if(format==='LaTeX')return colors.map((c,i)=>`\\definecolor{figColor${i+1}}{HTML}{${c.slice(1)}}`).join('\n');
 if(format==='CSS')return ':root {\n'+colors.map((c,i)=>`  --fig-color-${i+1}: ${c};`).join('\n')+'\n}';
 return colors.join('\n');
}
