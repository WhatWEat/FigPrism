import {create} from 'zustand';
type State={loginOpen:boolean;ingestOpen:boolean;selectedId:string|null;toast:string;density:number;openLogin:()=>void;openIngest:()=>void;select:(id:string|null)=>void;notify:(text:string)=>void;setDensity:(n:number)=>void};
let toastTimer:ReturnType<typeof setTimeout>;
export const useUI=create<State>(set=>({loginOpen:false,ingestOpen:false,selectedId:null,toast:'',density:4,openLogin:()=>set({loginOpen:true}),openIngest:()=>set({ingestOpen:true}),select:id=>set({selectedId:id}),notify:toast=>{clearTimeout(toastTimer);set({toast});toastTimer=setTimeout(()=>set({toast:''}),3300);},setDensity:density=>set({density})}));
