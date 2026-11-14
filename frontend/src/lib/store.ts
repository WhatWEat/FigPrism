import { create } from "zustand";
type SelectionContext = {
  focus?: string | null;
  note?: string;
  boardId?: string;
};
type State = {
  loginOpen: boolean;
  ingestOpen: boolean;
  selectedId: string | null;
  selectedContext: SelectionContext | null;
  toast: string;
  density: number;
  openLogin: () => void;
  openIngest: () => void;
  select: (id: string | null, context?: SelectionContext) => void;
  notify: (text: string) => void;
  setDensity: (n: number) => void;
};
let toastTimer: ReturnType<typeof setTimeout>;
export const useUI = create<State>((set) => ({
  loginOpen: false,
  ingestOpen: false,
  selectedId: null,
  selectedContext: null,
  toast: "",
  density: 4,
  openLogin: () => set({ loginOpen: true }),
  openIngest: () => set({ ingestOpen: true }),
  select: (id, context) =>
    set({ selectedId: id, selectedContext: context || null }),
  notify: (toast) => {
    clearTimeout(toastTimer);
    set({ toast });
    toastTimer = setTimeout(() => set({ toast: "" }), 3300);
  },
  setDensity: (density) => set({ density }),
}));
