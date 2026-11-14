'use client';
import * as Dialog from '@radix-ui/react-dialog';
import {X,Loader2,Triangle,ArrowUpRight} from 'lucide-react';
import {useQuery} from '@tanstack/react-query';
import {api,post} from '@/lib/api';
import {User,Figure} from '@/lib/types';
import {useUI} from '@/lib/store';
export function useUser(){return useQuery({queryKey:['me'],queryFn:()=>api<{user:User|null}>('/auth/me'),staleTime:60_000});}
export function Modal({open,onOpenChange,title,description,children,className=''}:{open:boolean;onOpenChange:(open:boolean)=>void;title:string;description?:string;children:React.ReactNode;className?:string}){return <Dialog.Root open={open} onOpenChange={onOpenChange}><Dialog.Portal><Dialog.Overlay className="modal-overlay"/><Dialog.Content className={`modal ${className}`} aria-describedby={description?'modal-description':undefined}><div className="modal-heading"><div><Dialog.Title>{title}</Dialog.Title>{description&&<Dialog.Description id="modal-description">{description}</Dialog.Description>}</div><Dialog.Close className="icon-button" aria-label="关闭"><X size={19}/></Dialog.Close></div>{children}</Dialog.Content></Dialog.Portal></Dialog.Root>}
export function Spinner(){return <Loader2 className="spin" size={18}/>}
export function Logo(){return <span className="logo"><span className="logo-mark"><Triangle size={23} strokeWidth={1.6}/><i/></span>FigPrism<span className="logo-dot">.</span></span>}
export function Empty({title,description,action}:{title:string;description:string;action?:React.ReactNode}){return <div className="empty"><div className="empty-symbol"><Triangle size={33} strokeWidth={1}/></div><h3>{title}</h3><p>{description}</p>{action}</div>}
export function ErrorMessage({error,retry}:{error:Error|null;retry?:()=>void}){if(!error)return null;return <div className="error-box" role="alert">{error.message}{retry&&<button onClick={retry}>重新加载</button>}</div>}
export function PaperLink({figure:f}:{figure:Figure}){return <a className="icon-button" href={`/api/papers/${f.paper_id}/pdf#page=${f.page_number}`} target="_blank" rel="noreferrer" title={`查看论文第 ${f.page_number} 页`} aria-label="打开论文原文"><ArrowUpRight size={17}/></a>}
export async function copyColor(hex:string,fid:string,user:User|null,format='HEX'){
 try{await navigator.clipboard.writeText(hex);useUI.getState().notify(`已复制 ${hex}`);if(user)await post('/me/palette-history',{figure_id:fid,hex_code:hex,copied_format:format});}catch{useUI.getState().notify('复制失败，请手动选择色值复制');}
}
export function Swatches({figure:f,small=false}:{figure:Figure;small?:boolean}){const user=useUser().data?.user||null;return <div className={`swatches ${small?'small':''}`}>{f.palette.colors.slice(0,5).map(c=><button key={c.hex} style={{background:c.hex}} title={`复制 ${c.hex}`} aria-label={`复制色值 ${c.hex}`} onClick={e=>{e.stopPropagation();void copyColor(c.hex,f.id,user);}}/>)}</div>}
