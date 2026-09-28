import hashlib,json,os,queue,threading,time,urllib.parse,urllib.request
from pathlib import Path
import tkinter as tk
from tkinter import filedialog,messagebox,ttk
from concurrent.futures import ThreadPoolExecutor,as_completed

APP_VERSION="5.0.0"
BASE_URL="https://pub-c5632053ba844beca4069371167a6fff.r2.dev"
MANIFEST_URL=BASE_URL+"/manifest.json"
STATE=".506th_updater_state.json"; LOG="506th-updater.log"; CHUNK=4*1024*1024

def sha256(p):
    h=hashlib.sha256()
    with p.open("rb") as f:
        for b in iter(lambda:f.read(CHUNK),b""): h.update(b)
    return h.hexdigest()

def human(n):
    n=float(n)
    for u in ("B","KB","MB","GB","TB"):
        if n<1024 or u=="TB": return f"{n:.1f} {u}"
        n/=1024

class App:
    def __init__(self,r):
        self.r=r; r.title(f"506th Arma 3 Mod Sync v{APP_VERSION}"); r.geometry("920x680")
        self.q=queue.Queue(); self.cancel=threading.Event(); self.plan=None
        self.path=tk.StringVar(value=self.default_path()); self.status=tk.StringVar(value="Choose a location, then Preview Changes.")
        self.summary=tk.StringVar(); self.transfer=tk.StringVar(); self.progress=tk.DoubleVar()
        self.total=0; self.done=0; self.started=0; self.lock=threading.Lock()
        self.ui(); r.after(100,self.events)

    def default_path(self):
        for p in (Path(r"C:\Program Files (x86)\Steam\steamapps\common\Arma 3"),Path(r"C:\Program Files\Steam\steamapps\common\Arma 3")):
            if p.exists(): return str(p)
        return str(Path.home()/"Desktop"/"Arma 3")

    def ui(self):
        ttk.Label(self.r,text="506th Arma 3 Mod Sync",font=("Segoe UI",18,"bold")).pack(pady=(14,2))
        ttk.Label(self.r,text=f"v{APP_VERSION} • Exact R2 Sync").pack(pady=(0,12))
        f=ttk.Frame(self.r); f.pack(fill="x",padx=14); ttk.Label(f,text="Install / Sync Location").pack(anchor="w")
        row=ttk.Frame(f); row.pack(fill="x",pady=(4,10)); ttk.Entry(row,textvariable=self.path).pack(side="left",fill="x",expand=True)
        ttk.Button(row,text="Browse…",command=self.browse).pack(side="left",padx=(8,0))
        b=ttk.Frame(self.r); b.pack(fill="x",padx=14,pady=(0,10))
        self.preview=ttk.Button(b,text="Preview Changes",command=self.preview_changes); self.preview.pack(side="left")
        self.apply=ttk.Button(b,text="Apply Sync",command=self.apply_sync,state="disabled"); self.apply.pack(side="left",padx=8)
        self.cancelbtn=ttk.Button(b,text="Cancel",command=self.cancel.set,state="disabled"); self.cancelbtn.pack(side="left")
        ttk.Label(self.r,textvariable=self.status,font=("Segoe UI",10,"bold")).pack(anchor="w",padx=14)
        ttk.Label(self.r,textvariable=self.summary).pack(anchor="w",padx=14,pady=(2,8))
        lf=ttk.LabelFrame(self.r,text="Planned Changes"); lf.pack(fill="both",expand=True,padx=14,pady=(0,10))
        self.tree=ttk.Treeview(lf,columns=("a","p","s"),show="headings")
        for c,t,w in (("a","Action",110),("p","Path",630),("s","Size",120)): self.tree.heading(c,text=t); self.tree.column(c,width=w)
        sb=ttk.Scrollbar(lf,orient="vertical",command=self.tree.yview); self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left",fill="both",expand=True); sb.pack(side="right",fill="y")
        pf=ttk.LabelFrame(self.r,text="Transfer"); pf.pack(fill="x",padx=14,pady=(0,10))
        ttk.Progressbar(pf,variable=self.progress,maximum=100).pack(fill="x",padx=10,pady=(10,6))
        ttk.Label(pf,textvariable=self.transfer).pack(anchor="w",padx=10,pady=(0,8))
        ttk.Label(self.r,text="Extra files are removed only inside top-level paths managed by the R2 manifest, after preview and confirmation.").pack(anchor="w",padx=14)

    def browse(self):
        p=filedialog.askdirectory()
        if p: self.path.set(p); self.plan=None; self.apply.config(state="disabled")

    def safe(self,root,rel):
        root=root.resolve(); target=(root/Path(rel.replace("/",os.sep))).resolve()
        if os.path.commonpath([str(root),str(target)])!=str(root): raise ValueError(f"Unsafe path: {rel}")
        return target

    def manifest(self):
        req=urllib.request.Request(MANIFEST_URL,headers={"User-Agent":f"506th-Mod-Sync/{APP_VERSION}"})
        with urllib.request.urlopen(req,timeout=30) as x: m=json.loads(x.read().decode())
        if not isinstance(m.get("files"),list): raise ValueError("Invalid R2 manifest.")
        return m

    def state(self,root):
        try: return json.loads((root/STATE).read_text()) if (root/STATE).exists() else {"files":{}}
        except: return {"files":{}}

    def save_state(self,root,s):
        t=root/(STATE+".tmp"); t.write_text(json.dumps(s,indent=2)); os.replace(t,root/STATE)

    def current(self,p,i,s):
        if not p.is_file() or p.stat().st_size!=int(i["size"]): return False
        st=p.stat(); c=s["files"].get(i["path"])
        if c and c.get("mtime_ns")==st.st_mtime_ns and c.get("sha256","").lower()==i["sha256"].lower(): return True
        if sha256(p).lower()!=i["sha256"].lower(): return False
        s["files"][i["path"]]={"mtime_ns":st.st_mtime_ns,"sha256":i["sha256"]}; return True

    def make_plan(self,root):
        m=self.manifest(); s=self.state(root); wanted={}; roots=set(); downloads=[]
        for i in m["files"]:
            rp=Path(i["path"].replace("/",os.sep)); wanted[rp.as_posix().lower()]=i
            if rp.parts: roots.add(rp.parts[0])
        for i in m["files"]:
            if not self.current(self.safe(root,i["path"]),i,s): downloads.append(i)
        deletes=[]
        for top in roots:
            base=root/top
            if not base.exists(): continue
            seq=[base] if base.is_file() else base.rglob("*")
            for p in seq:
                if p.is_file() and p.name not in (STATE,LOG) and not p.name.endswith(".506thdownload"):
                    rel=p.relative_to(root).as_posix()
                    if rel.lower() not in wanted: deletes.append(rel)
        self.save_state(root,s)
        return {"root":root,"manifest":m,"downloads":downloads,"deletes":sorted(deletes),"roots":sorted(roots)}

    def preview_changes(self):
        root=Path(self.path.get()).expanduser()
        if not root.exists():
            if not messagebox.askyesno("Create directory?",f"Create {root}?"): return
            root.mkdir(parents=True)
        self.preview.config(state="disabled"); self.cancelbtn.config(state="normal"); self.tree.delete(*self.tree.get_children()); self.status.set("Checking files…")
        def w():
            try:self.q.put(("plan",self.make_plan(root)))
            except Exception as e:self.q.put(("err",str(e)))
        threading.Thread(target=w,daemon=True).start()

    def apply_sync(self):
        p=self.plan
        if not p:return
        if not messagebox.askyesno("Confirm Exact Sync",f"Download/replace: {len(p['downloads'])}\nDelete: {len(p['deletes'])}\n\nProceed?"):return
        self.cancel.clear(); self.preview.config(state="disabled"); self.apply.config(state="disabled"); self.cancelbtn.config(state="normal")
        threading.Thread(target=self.sync,daemon=True).start()

    def download(self,i,root):
        rel=i["path"]; out=self.safe(root,rel); out.parent.mkdir(parents=True,exist_ok=True); tmp=Path(str(out)+".506thdownload")
        expected=int(i["size"]); resume=tmp.stat().st_size if tmp.exists() else 0
        if resume>expected: tmp.unlink(); resume=0
        url=BASE_URL+"/"+urllib.parse.quote(rel,safe="/@()+,;=-_.!~*'[]"); headers={"User-Agent":f"506th-Mod-Sync/{APP_VERSION}"}; mode="wb"
        if resume: headers["Range"]=f"bytes={resume}-"; mode="ab"
        resp=urllib.request.urlopen(urllib.request.Request(url,headers=headers),timeout=120)
        if resume and getattr(resp,"status",None)!=206: resp.close(); tmp.unlink(missing_ok=True); resp=urllib.request.urlopen(url,timeout=120); mode="wb"
        with resp,tmp.open(mode) as f:
            while True:
                if self.cancel.is_set(): raise InterruptedError
                b=resp.read(CHUNK)
                if not b:break
                f.write(b)
                with self.lock:self.done+=len(b); elapsed=max(time.time()-self.started,.01); speed=self.done/elapsed; eta=max(self.total-self.done,0)/speed if speed else 0
                self.q.put(("prog",self.done,self.total,speed,eta))
        if tmp.stat().st_size!=expected or sha256(tmp).lower()!=i["sha256"].lower(): raise IOError(f"Verification failed: {rel}")
        os.replace(tmp,out); return rel,out.stat().st_mtime_ns

    def sync(self):
        p=self.plan; root=p["root"]; s=self.state(root); self.total=sum(int(i["size"]) for i in p["downloads"]); self.done=0; self.started=time.time()
        try:
            with ThreadPoolExecutor(max_workers=4) as pool:
                fs={pool.submit(self.download,i,root):i for i in p["downloads"]}
                for f in as_completed(fs):
                    rel,mt=f.result(); i=fs[f]; s["files"][rel]={"mtime_ns":mt,"sha256":i["sha256"]}
            for rel in p["deletes"]:
                if self.cancel.is_set(): raise InterruptedError
                q=self.safe(root,rel)
                if q.is_file(): q.unlink()
            keep={i["path"] for i in p["manifest"]["files"]}; s["files"]={k:v for k,v in s["files"].items() if k in keep}; self.save_state(root,s)
            self.q.put(("done",len(p["downloads"]),len(p["deletes"])))
        except InterruptedError:self.q.put(("cancel",))
        except Exception as e:self.q.put(("err",str(e)))

    def events(self):
        try:
            while True:
                e=self.q.get_nowait()
                if e[0]=="plan":
                    self.plan=e[1]
                    for i in self.plan["downloads"]:self.tree.insert("","end",values=("DOWNLOAD",i["path"],human(i["size"])))
                    for p in self.plan["deletes"]:self.tree.insert("","end",values=("DELETE",p,""))
                    size=sum(int(i["size"]) for i in self.plan["downloads"]); self.summary.set(f"{len(self.plan['downloads'])} download/replace • {len(self.plan['deletes'])} delete • {human(size)}")
                    self.status.set("Preview complete."); self.preview.config(state="normal"); self.apply.config(state="normal"); self.cancelbtn.config(state="disabled")
                elif e[0]=="prog":
                    _,d,t,s,eta=e; self.progress.set(d/t*100 if t else 100); self.transfer.set(f"{human(d)} / {human(t)} • {human(s)}/s • ETA {int(eta//60)}m")
                elif e[0]=="done":
                    self.status.set("Exact sync complete."); self.progress.set(100); self.preview.config(state="normal"); self.cancelbtn.config(state="disabled"); messagebox.showinfo("Complete",f"Downloaded/replaced: {e[1]}\nDeleted: {e[2]}")
                elif e[0]=="cancel":
                    self.status.set("Cancelled."); self.preview.config(state="normal"); self.cancelbtn.config(state="disabled")
                elif e[0]=="err":
                    self.status.set("Failed."); self.preview.config(state="normal"); self.cancelbtn.config(state="disabled"); messagebox.showerror("506th Mod Sync",e[1])
        except queue.Empty:pass
        self.r.after(100,self.events)

if __name__=="__main__":
    r=tk.Tk(); App(r); r.mainloop()
